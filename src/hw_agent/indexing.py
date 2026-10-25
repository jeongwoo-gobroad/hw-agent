import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from fastapi import HTTPException
from . import db, storage, inventory
from .progress import Estimate

scan_lock = threading.Lock()
status = {"running": False, "files": 0, "error": None}
stop_event = threading.Event()
EXTRACTOR_VERSION = "2026-10-20.2"


def tokens(text):
    # 한국어 조사 차이를 완화하도록 단어와 2글자 조각을 함께 넣는다.
    words = re.findall(r"[^\W_]+", text.lower(), re.UNICODE)
    pieces = list(words)
    for word in words:
        if re.search("[가-힣]", word):
            pieces.extend(word[i:i+2] for i in range(len(word)-1))
    return " ".join(pieces)


HASH_INTERVAL = 3*86400
SCAN_INTERVAL = 600
TEXT_EXTENSIONS = {'.txt','.md','.csv','.json','.py','.log','.yaml','.yml','.xml','.docx','.hwpx','.pdf','.hwp'}


def extract_content(path):
    if path.suffix.lower() not in TEXT_EXTENSIONS: return '', 'unsupported'
    if path.stat().st_size>32*1024**2: return '', 'size_limit'
    try:
        result=subprocess.run([sys.executable,'-m','hw_agent.extract',str(path)],
                              capture_output=True,text=True,timeout=12,check=True)
        output=json.loads(result.stdout)
        return output['text'],output['status']
    except (subprocess.SubprocessError,ValueError):
        return '', 'timeout_or_error'


def scan(force=True):
    if not scan_lock.acquire(blocking=False): return
    status.update(running=True, files=0, total=0, error=None, eta_seconds=None,
                  total_known=False, stage='counting', reused=0, changed=0, resumed=False)
    inventory.init()
    try:
        roots=db.rows('SELECT * FROM roots')
        current_jobs=[]
        for root in roots:
            current=inventory.begin('files',root,EXTRACTOR_VERSION,force,SCAN_INTERVAL)
            status['resumed'] |= current['done']>0 and current['stage']!='complete'
            current_jobs.append((root,current))
        def refresh(stage=None,eta=None):
            jobs=[inventory.job('files',root['id']) for root,_ in current_jobs]
            jobs=[j for j in jobs if j]
            status.update(files=sum(j['done'] for j in jobs),total=sum(j['total'] for j in jobs),
                          reused=sum(j['reused'] for j in jobs),changed=sum(j['changed'] for j in jobs),
                          errors=sum(j['errors'] for j in jobs),
                          total_known=all(j['stage']!='discovering' for j in jobs),eta_seconds=eta)
            if stage: status['stage']=stage
        for root,current in current_jobs:
            try:
                if current['stage']=='complete': refresh();continue
                base=storage.root_path(root)
                current=inventory.discover(current,base,stop_event.is_set,notify=lambda _:refresh('counting'))
                refresh('indexing')
                estimate=Estimate()
                while entries:=inventory.pending(current,64):
                    base=storage.root_path(root)
                    for entry in entries:
                        if stop_event.is_set(): raise InterruptedError()
                        key=f"{root['id']}\n{entry['relative']}"
                        try:
                            path=inventory.safe_path(base,entry['relative'])
                            try: stat=path.stat()
                            except FileNotFoundError:
                                with db.connect() as c: inventory.acknowledge(c,current,entry,error=True)
                                continue
                            previous=db.rows('SELECT * FROM files WHERE path=?',(key,))
                            prior=previous[0] if previous else None
                            # 이전 staging에도 완료한 추출 결과가 있으므로 재사용한다.
                            if prior is None or not inventory.unchanged(prior,stat):
                                legacy=db.rows('SELECT * FROM staging WHERE path=? AND size=? AND modified=? ORDER BY rowid DESC LIMIT 1',
                                               (key,stat.st_size,stat.st_mtime))
                                if legacy: prior=legacy[0]
                            same_metadata=inventory.unchanged(prior,stat)
                            old_hash=prior.get('content_hash') if prior else None
                            hash_due=not old_hash or not same_metadata or time.time()-(prior.get('hash_checked') or 0)>=HASH_INTERVAL
                            digest,checked=old_hash,(prior.get('hash_checked') if prior else None)
                            if hash_due:
                                digest,stat=inventory.digest(path,stop_event.is_set);checked=time.time()
                            same_content=bool(prior and ((old_hash and digest==old_hash) or (not old_hash and same_metadata)))
                            version=(prior.get('extractor_version') or db.state('extractor_version',EXTRACTOR_VERSION)) if prior else None
                            reuse=same_content and version==EXTRACTOR_VERSION
                            if reuse: text,extraction=prior['text'],prior['extraction']
                            else: text,extraction=extract_content(path)
                            if inventory.fingerprint(path.stat())!=inventory.fingerprint(stat):
                                raise OSError('File changed during extraction; retry pending item')
                            with db.connect() as c:
                                c.execute('BEGIN IMMEDIATE')
                                if not c.execute('SELECT 1 FROM roots WHERE id=?',(root['id'],)).fetchone():
                                    inventory.drop(c,'files',root['id']);current=None;break
                                old=c.execute('SELECT id,content_hash,extractor_version FROM files WHERE path=?',(key,)).fetchone()
                                needs_fts=not old or not reuse or prior.get('id')!=old['id']
                                if old and not needs_fts:
                                    c.execute('UPDATE files SET seen=?,modified=?,modified_ns=?,ctime_ns=?,content_hash=?,hash_checked=?,extractor_version=? WHERE id=?',
                                              (current['generation'],stat.st_mtime,stat.st_mtime_ns,stat.st_ctime_ns,digest,checked,EXTRACTOR_VERSION,old['id']))
                                else:
                                    c.execute("""INSERT INTO files(root,path,name,ext,mime,size,modified,created,text,extraction,seen,
                                      modified_ns,ctime_ns,content_hash,hash_checked,extractor_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                      ON CONFLICT(path) DO UPDATE SET size=excluded.size,modified=excluded.modified,created=excluded.created,
                                      text=excluded.text,extraction=excluded.extraction,seen=excluded.seen,modified_ns=excluded.modified_ns,
                                      ctime_ns=excluded.ctime_ns,content_hash=excluded.content_hash,hash_checked=excluded.hash_checked,
                                      extractor_version=excluded.extractor_version""",
                                      (root['id'],key,path.name,path.suffix.lower(),mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                                       stat.st_size,stat.st_mtime,getattr(stat,'st_birthtime',None),text,extraction,current['generation'],
                                       stat.st_mtime_ns,stat.st_ctime_ns,digest,checked,EXTRACTOR_VERSION))
                                identifier=c.execute('SELECT id FROM files WHERE path=?',(key,)).fetchone()[0]
                                if needs_fts:
                                    c.execute('DELETE FROM search WHERE rowid=?',(identifier,))
                                    c.execute('INSERT INTO search(rowid,name,path,body) VALUES(?,?,?,?)',
                                              (identifier,tokens(path.name),tokens(key),tokens(text)))
                                c.execute('DELETE FROM staging WHERE path=?',(key,))
                                inventory.acknowledge(c,current,entry,reused=reuse)
                        except InterruptedError: raise
                        except (OSError,HTTPException):
                            with db.connect() as c:
                                c.execute('UPDATE files SET seen=? WHERE path=?',(current['generation'],key))
                                inventory.acknowledge(c,current,entry,error=True)
                        current=inventory.job('files',root['id'])
                        if current is None: break
                        refresh('indexing',estimate.advance(current['total']-current['done']))
                    if current is None: break
                if current is None: continue
                # 삭제 반영은 해당 루트를 끝까지 확인하고 드라이브가 연결된 경우에만 한다.
                storage.root_path(root)
                refresh('finalizing')
                while True:
                    stale=db.rows('SELECT id FROM files WHERE root=? AND (seen IS NULL OR seen!=?) LIMIT 256',
                                  (root['id'],current['generation']))
                    if not stale: break
                    with db.connect() as c:
                        c.executemany('DELETE FROM search WHERE rowid=?',[(r['id'],) for r in stale])
                        c.executemany('DELETE FROM files WHERE id=?',[(r['id'],) for r in stale])
                with db.connect() as c: inventory.finish(c,current)
                refresh()
            except InterruptedError: raise
            except Exception as exc:
                status['error']=str(getattr(exc,'detail',type(exc).__name__))
        db.set_state('last_scan',str(time.time()))
        db.set_state('extractor_version',EXTRACTOR_VERSION)
        storage.restore_shares()
    except InterruptedError:
        status['stage']='stopped'
    except Exception as exc:
        status['error']=str(getattr(exc,'detail',type(exc).__name__))
    finally:
        status['stage']='stopped' if stop_event.is_set() else 'error' if status['error'] else 'complete'
        status['eta_seconds']=0 if status['stage']=='complete' else None
        status['running']=False
        scan_lock.release()


def worker():
    while not stop_event.is_set():
        scan(force=False)
        stop_event.wait(SCAN_INTERVAL)


def search(query="", ext="", root=0, after=None, before=None, date_field="modified", offset=0, rerank=False):
    clauses, args = [], []
    join, order = "", "files.modified DESC"
    if query.strip():
        terms = list(dict.fromkeys(tokens(query).split()))[:30]
        if terms:
            join = "JOIN search ON search.rowid=files.id"
            clauses.append("search MATCH ?")
            args.append(" OR ".join('"' + t.replace('"', '""') + '"' for t in terms))
            order = "bm25(search,5.0,1.5,1.0)"
    if ext:
        clauses.append("ext=?")
        args.append("." + ext.lower().lstrip("."))
    if root:
        clauses.append("root=?")
        args.append(root)
    field = "created" if date_field == "created" else "modified"
    for value, operator in ((after, ">="), (before, "<=")):
        if value is not None:
            clauses.append(f"{field}{operator}?")
            args.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    result = db.rows(f"""SELECT files.*, substr(files.text,1,400) AS snippet FROM files {join}{where}
                        ORDER BY {order} LIMIT ? OFFSET ?""", (*args, 100 if rerank else 40, max(0, offset)))
    if rerank and query and result:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vectors = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=20000).fit_transform(
            [query] + [r["name"] + " " + r["text"][:10000] for r in result])
        scores = cosine_similarity(vectors[0], vectors[1:]).ravel()
        result = [result[i] for i in scores.argsort()[::-1]][:40]
    for r in result:
        r.pop("text", None)
        r["path"] = r["path"].split("\n", 1)[-1]
    return result
