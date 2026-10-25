"""SQLite-backed directory and file queues survive service and power restarts."""
import json
import hashlib
import os
from pathlib import Path
import time
import uuid
from fastapi import HTTPException
from . import db, storage

BATCH = 256


def init():
    with db.connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS scan_jobs(
          kind TEXT, root INTEGER, identity TEXT, generation TEXT, stage TEXT,
          version TEXT, started REAL, completed REAL, total INTEGER DEFAULT 0,
          done INTEGER DEFAULT 0, reused INTEGER DEFAULT 0, changed INTEGER DEFAULT 0,
          errors INTEGER DEFAULT 0, PRIMARY KEY(kind,root));
        CREATE TABLE IF NOT EXISTS scan_dirs(
          kind TEXT, root INTEGER, relative TEXT, done INTEGER DEFAULT 0,
          PRIMARY KEY(kind,root,relative));
        CREATE INDEX IF NOT EXISTS scan_dirs_pending ON scan_dirs(kind,root,done);
        CREATE TABLE IF NOT EXISTS scan_entries(
          id INTEGER PRIMARY KEY, kind TEXT, root INTEGER, relative TEXT,
          done INTEGER DEFAULT 0, UNIQUE(kind,root,relative));
        CREATE INDEX IF NOT EXISTS scan_entries_pending ON scan_entries(kind,root,done,id);
        """)


def drop(c, kind, root):
    for table in ('scan_entries','scan_dirs','scan_jobs'):
        c.execute(f'DELETE FROM {table} WHERE kind=? AND root=?',(kind,root))


def job(kind, root):
    rows=db.rows('SELECT * FROM scan_jobs WHERE kind=? AND root=?',(kind,root))
    return rows[0] if rows else None


def begin(kind, root, version, force=True, interval=600):
    init()
    identity=json.dumps([root.get('uuid'),root.get('relative_path',root['path'])])
    current=job(kind,root['id'])
    if current and current['identity']==identity and current['version']==version:
        if current['stage']!='complete': return current
        if not force and time.time()-(current['completed'] or 0)<interval: return current
    with db.connect() as c:
        drop(c,kind,root['id'])
        c.execute("""INSERT INTO scan_jobs(kind,root,identity,generation,stage,version,started)
          VALUES(?,?,?,?,'discovering',?,?)""",(kind,root['id'],identity,uuid.uuid4().hex,version,time.time()))
        c.execute("INSERT INTO scan_dirs(kind,root,relative) VALUES(?,?,'')",(kind,root['id']))
    return job(kind,root['id'])


def safe_path(base, relative):
    storage.check_path(relative)
    parts=Path(relative).parts
    if Path(relative).is_absolute() or '..' in parts or any(p.startswith('.') for p in parts):
        raise HTTPException(403,'등록 폴더 밖의 경로입니다.')
    target=base
    for part in parts:
        target=target/part
        if target.is_symlink(): raise HTTPException(403,'심볼릭 링크는 처리하지 않습니다.')
    return target


def discover(current, base, cancelled, extensions=None, notify=None):
    kind,root=current['kind'],current['root']
    if current['stage']!='discovering': return current
    while True:
        if cancelled(): raise InterruptedError()
        rows=db.rows('SELECT relative FROM scan_dirs WHERE kind=? AND root=? AND done=0 LIMIT 1',(kind,root))
        if not rows: break
        relative=rows[0]['relative']
        folder=safe_path(base,relative)
        files,dirs=[],[]
        def flush():
            with db.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                registered='roots' if kind=='files' else 'photo_roots'
                if not c.execute(f'SELECT 1 FROM {registered} WHERE id=?',(root,)).fetchone():
                    raise InterruptedError()
                c.executemany('INSERT OR IGNORE INTO scan_dirs(kind,root,relative) VALUES(?,?,?)',dirs)
                before=c.total_changes
                c.executemany('INSERT OR IGNORE INTO scan_entries(kind,root,relative) VALUES(?,?,?)',files)
                c.execute('UPDATE scan_jobs SET total=total+? WHERE kind=? AND root=?',(c.total_changes-before,kind,root))
            files.clear();dirs.clear()
            if notify: notify(job(kind,root))
        try:
            with os.scandir(folder) as listing:
                for i,entry in enumerate(listing):
                    if i%BATCH==0 and cancelled(): raise InterruptedError()
                    # 제외 이름은 stat, 링크 검사, 하위 폴더 진입보다 먼저 거른다.
                    if entry.name.startswith('.') or storage.excluded(entry.name): continue
                    if entry.is_symlink(): continue
                    child=str(Path(relative)/entry.name)
                    if entry.is_dir(follow_symlinks=False): dirs.append((kind,root,child))
                    elif entry.is_file(follow_symlinks=False) and (extensions is None or Path(entry.name).suffix.lower() in extensions):
                        files.append((kind,root,child))
                    if len(files)+len(dirs)>=BATCH: flush()
        except FileNotFoundError:
            if not base.is_dir(): raise
        flush()
        with db.connect() as c:
            c.execute('UPDATE scan_dirs SET done=1 WHERE kind=? AND root=? AND relative=?',(kind,root,relative))
    with db.connect() as c:
        c.execute("UPDATE scan_jobs SET stage='processing' WHERE kind=? AND root=?",(kind,root))
    return job(kind,root)


def pending(current, limit=BATCH):
    return db.rows('SELECT id,relative FROM scan_entries WHERE kind=? AND root=? AND done=0 ORDER BY id LIMIT ?',
                   (current['kind'],current['root'],limit))


def acknowledge(c, current, entry, reused=False, error=False):
    updated=c.execute('UPDATE scan_entries SET done=1 WHERE id=? AND done=0',(entry['id'],)).rowcount
    if updated:
        c.execute('UPDATE scan_jobs SET done=done+1,reused=reused+?,changed=changed+?,errors=errors+? WHERE kind=? AND root=?',
                  (int(reused),int(not reused and not error),int(error),current['kind'],current['root']))


def finish(c,current):
    c.execute("UPDATE scan_jobs SET stage='complete',completed=? WHERE kind=? AND root=?",
              (time.time(),current['kind'],current['root']))


def fingerprint(stat):
    return {'size':stat.st_size,'modified_ns':stat.st_mtime_ns,'ctime_ns':stat.st_ctime_ns}


def unchanged(record, stat):
    if record is None or record['size']!=stat.st_size: return False
    # 이전 DB는 초 단위 시간을 쓴다. 최초 비교 후 정밀 시간을 추가 저장한다.
    if record.get('modified_ns') is None: return record['modified']==stat.st_mtime
    return record['modified_ns']==stat.st_mtime_ns and record.get('ctime_ns')==stat.st_ctime_ns


def digest(path, cancelled):
    before=path.stat()
    result=hashlib.sha256()
    with path.open('rb') as source:
        while block:=source.read(1024*1024):
            if cancelled(): raise InterruptedError()
            result.update(block)
    after=path.stat()
    if fingerprint(before)!=fingerprint(after):
        raise OSError('File changed during hashing; retry pending item')
    return result.hexdigest(), after
