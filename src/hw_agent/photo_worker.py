"""Bounded, resumable media processing in its own systemd cgroup."""
from datetime import datetime
import io
import json
import os
from pathlib import Path
import signal
import secrets
import subprocess
import time
import uuid
import numpy as np
from PIL import Image, ImageOps
from fastapi import HTTPException
from tqdm import tqdm
from . import db, photos, storage
from . import photo_runtime, inventory
from .progress import Estimate
from .photo_models import PhotoModels, MODEL_VERSION

IMAGES = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tif', '.tiff', '.bmp'}
VIDEOS = {'.mov', '.mp4', '.m4v', '.mkv', '.avi'}
stopping = False


def progress(**values):
    photo_runtime.write(**values)
    photo_runtime.heartbeat()


def paused():
    return stopping or db.state('photo_paused', '0') == '1'


META_ARGS = ['exiftool', '-j', '-DateTimeOriginal', '-OffsetTimeOriginal', '-CreateDate',
             '-ContentIdentifier', '-MediaGroupUUID', '-Duration', '-n']
_metadata_cache = {}


def metadata(path):
    data = _metadata_cache.get(str(path))
    if data is None:
        result = subprocess.run([*META_ARGS, str(path)], capture_output=True, timeout=25, check=True)
        data = json.loads(result.stdout)[0]
    raw = data.get('DateTimeOriginal') or data.get('CreateDate')
    captured, source = path.stat().st_mtime, '수정일 대체'
    if raw:
        try:
            parsed = datetime.strptime(raw[:19], '%Y:%m:%d %H:%M:%S')
            zone = data.get('OffsetTimeOriginal') or raw[19:]
            if zone:
                parsed = datetime.fromisoformat(parsed.isoformat()+zone.replace('Z', '+00:00'))
            captured, source = parsed.timestamp(), 'EXIF/QuickTime' + (' (시간대 없음: Pi 현지 시간)' if not zone else '')
        except (ValueError, TypeError):
            pass
    return captured, source, data.get('ContentIdentifier') or data.get('MediaGroupUUID'), float(data.get('Duration') or 0)


def discover(root, on_batch=None, discovered_offset=0, force=True, interval=600):
    base=photos.root_path(root)
    current=inventory.begin('photos',root,'photo-metadata-v2',force,interval)
    generation=current['generation']
    if current['stage']=='complete': return True
    current=inventory.discover(current,base,paused,IMAGES|VIDEOS,
        lambda j:progress(stage='counting',inventory_total=discovered_offset+j['total'],
                          discovered=discovered_offset+j['done'],resumed=j['done']>0))
    progress(stage='discovering',discovery_complete=False,inventory_total=discovered_offset+current['total'],
             discovered=discovered_offset+current['done'],discovery_started=time.time(),resumed=current['done']>0)
    estimate=Estimate()
    while entries:=inventory.pending(current,64):
        base=photos.root_path(root)
        for entry in entries:
            if paused(): return False
            try:
                path=inventory.safe_path(base,entry['relative'])
                try: stat=path.stat()
                except FileNotFoundError:
                    with db.connect() as c: inventory.acknowledge(c,current,entry,error=True)
                    continue
                previous=db.rows('SELECT * FROM photos WHERE root=? AND relative=?',(root['id'],entry['relative']))
                prior=previous[0] if previous else None
                same_metadata=inventory.unchanged(prior,stat)
                old_hash=prior.get('content_hash') if prior else None
                digest,checked=old_hash,prior.get('hash_checked') if prior else None
                if not old_hash or not same_metadata or time.time()-(checked or 0)>=3*86400:
                    digest,stat=inventory.digest(path,paused);checked=time.time()
                reuse=bool(prior and ((old_hash and old_hash==digest) or (not old_hash and same_metadata)))
                if reuse: captured,source,content,duration=prior['captured'],prior['date_source'],prior['content_id'],prior['duration']
                else:
                    try: captured,source,content,duration=metadata(path)
                    except (subprocess.SubprocessError,ValueError,KeyError,OSError):
                        captured,source,content,duration=stat.st_mtime,'수정일 대체 (촬영 정보 읽기 실패)',None,0
                if inventory.fingerprint(path.stat())!=inventory.fingerprint(stat):
                    raise OSError('Photo changed during metadata read; retry pending item')
                with db.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    if not c.execute('SELECT id FROM photo_roots WHERE id=?',(root['id'],)).fetchone():
                        inventory.drop(c,'photos',root['id']);return False
                    if reuse:
                        c.execute('UPDATE photos SET modified=?,modified_ns=?,ctime_ns=?,content_hash=?,hash_checked=?,seen=? WHERE id=?',
                                  (stat.st_mtime,stat.st_mtime_ns,stat.st_ctime_ns,digest,checked,generation,prior['id']))
                    else:
                        if prior:
                            for face in c.execute('SELECT id FROM photo_faces WHERE photo=?',(prior['id'],)):
                                (photos.CACHE/f"{face[0]}.face.jpg").unlink(missing_ok=True)
                            c.execute('DELETE FROM photo_faces WHERE photo=?',(prior['id'],))
                            (photos.CACHE/f"{prior['id']}.jpg").unlink(missing_ok=True)
                        c.execute("""INSERT INTO photos(id,root,relative,album,name,kind,modified,size,captured,date_source,seen,
                          content_id,duration,modified_ns,ctime_ns,content_hash,hash_checked) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(root,relative) DO UPDATE SET modified=excluded.modified,size=excluded.size,captured=excluded.captured,
                          date_source=excluded.date_source,seen=excluded.seen,content_id=excluded.content_id,duration=excluded.duration,
                          modified_ns=excluded.modified_ns,ctime_ns=excluded.ctime_ns,content_hash=excluded.content_hash,
                          hash_checked=excluded.hash_checked,scores='{}',error=NULL,retry_after=0,attempts=0,analysis_version=NULL""",
                          (secrets.randbits(52),root['id'],entry['relative'],str(Path(entry['relative']).parent),path.name,
                           'photo' if path.suffix.lower() in IMAGES else 'video',stat.st_mtime,stat.st_size,captured,source,generation,
                           content,duration,stat.st_mtime_ns,stat.st_ctime_ns,digest,checked))
                    inventory.acknowledge(c,current,entry,reused=reuse)
            except InterruptedError: raise
            except (OSError,HTTPException):
                with db.connect() as c:
                    c.execute('UPDATE photos SET seen=? WHERE root=? AND relative=?',(generation,root['id'],entry['relative']))
                    inventory.acknowledge(c,current,entry,error=True)
            current=inventory.job('photos',root['id'])
            progress(stage='discovering',discovered=discovered_offset+current['done'],
                     eta_seconds=estimate.advance(current['total']-current['done']),reused=current['reused'],errors=current['errors'])
        if on_batch: on_batch(root)
    photos.root_path(root)
    while True:
        stale=db.rows('SELECT id FROM photos WHERE root=? AND (seen IS NULL OR seen!=?) LIMIT 128',(root['id'],generation))
        if not stale: break
        with db.connect() as c:
            for item in stale:
                for face in c.execute('SELECT id FROM photo_faces WHERE photo=?',(item['id'],)):
                    (photos.CACHE/f"{face[0]}.face.jpg").unlink(missing_ok=True)
                c.execute('DELETE FROM photo_faces WHERE photo=?',(item['id'],))
                c.execute('DELETE FROM photos WHERE id=?',(item['id'],))
                (photos.CACHE/f"{item['id']}.jpg").unlink(missing_ok=True)
    # Live Photo 연결은 작은 트랜잭션으로 갱신해 파일 색인과 DB 잠금을 오래 경쟁하지 않는다.
    by_content,by_stem={},{}
    for row in db.rows("SELECT relative,content_id,captured FROM photos WHERE root=? AND kind='video'",(root['id'],)):
        if row['content_id']: by_content.setdefault(row['content_id'],[]).append(row['relative'])
        by_stem.setdefault(str(Path(row['relative']).with_suffix('')),[]).append((row['relative'],row['captured']))
    last=0
    while rows:=db.rows("SELECT id,relative,content_id,captured,live_relative FROM photos WHERE root=? AND kind!='video' AND id>? ORDER BY id LIMIT 128",(root['id'],last)):
        if paused(): return False
        with db.connect() as c:
            for row in rows:
                candidates=[(r,'content_identifier') for r in by_content.get(row['content_id'],[])]
                if not candidates: candidates=[(r,'filename_candidate') for r,t in by_stem.get(str(Path(row['relative']).with_suffix('')),[]) if abs(t-row['captured'])<=5]
                live,source=candidates[0] if len(candidates)==1 else (None,None)
                if live!=row['live_relative']:
                    c.execute("UPDATE photos SET scores='{}',analysis_version=NULL,retry_after=0 WHERE id=?",(row['id'],))
                c.execute('UPDATE photos SET kind=?,live_relative=?,pair_source=? WHERE id=?',('live' if live else 'photo',live,source,row['id']))
        last=rows[-1]['id']
    with db.connect() as c:
        c.execute("""UPDATE photos SET scores='{}',analysis_version=NULL WHERE root=? AND live_relative IN
          (SELECT relative FROM photos WHERE root=? AND scores='{}')""",(root['id'],root['id']))
        inventory.finish(c,current)
    return True


def frames(path, video=False):
    if not video:
        with Image.open(path) as image:
            image.draft("RGB", (1920, 1920))
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1920, 1920))
            yield image.convert('RGB')
        return
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)],
                           capture_output=True, timeout=20, check=True)
    duration = float(json.loads(probe.stdout).get('format', {}).get('duration', 0))
    for fraction in (.1, .5, .9):
        result = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '1', '-ss', str(duration*fraction),
                                 '-i', str(path), '-frames:v', '1', '-vf', 'scale=960:-2', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'],
                                capture_output=True, timeout=45, check=True)
        with Image.open(io.BytesIO(result.stdout)) as image:
            yield image.convert('RGB')


def process(item, models):
    path, _ = photos.safe_media(item['id'])
    all_frames = frames(path, item['kind'] == 'video')
    scores, faces, cover = {}, [], None
    def analyze(sequence):
        nonlocal cover
        for image in sequence:
            if paused(): raise InterruptedError()
            if cover is None: cover = image.copy()
            current, found = models.analyze(image)
            for key, value in current.items(): scores[key] = max(scores.get(key, 0), value)
            for embedding, box, crop in found:
                if not any(float(embedding @ e) >= .55 for e,b,c in faces):
                    faces.append((embedding, box, crop))
            progress(stage='classifying')
    analyze(all_frames)
    if item['live_relative']:
        video, _ = photos.safe_media(item['id'], True)
        analyze(frames(video, True))
    if cover is None: raise ValueError('No decodable image')
    cover.thumbnail((480, 480))
    temp = photos.CACHE / f"{item['id']}.part.jpg"
    cover.save(temp, quality=83)
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT 1 FROM photos WHERE id=?', (item['id'],)).fetchone():
            temp.unlink(missing_ok=True)
            return
        temp.replace(photos.CACHE / f"{item['id']}.jpg")
        old_faces = [r[0] for r in conn.execute('SELECT id FROM photo_faces WHERE photo=?', (item['id'],))]
        conn.execute('DELETE FROM photo_faces WHERE photo=?', (item['id'],))
        for embedding, box, crop in faces:
            candidates = [(float(embedding @ np.frombuffer(p['embedding'], np.float32)), p['id'])
                          for p in conn.execute('SELECT * FROM photo_people WHERE embedding IS NOT NULL')]
            score, person = max(candidates, default=(0, 0))
            # 보수적인 유사도 기준. 사용자는 잘못 묶인 얼굴을 분리/이동할 수 있다.
            if score < .55:
                person = conn.execute('INSERT INTO photo_people(embedding) VALUES(?)', (embedding.astype(np.float32).tobytes(),)).lastrowid
            face_id = secrets.randbits(52)
            conn.execute('INSERT INTO photo_faces(id,photo,person,box) VALUES(?,?,?,?)', (face_id, item['id'], person, json.dumps(box)))
            crop.save(photos.CACHE / f'{face_id}.face.jpg', quality=90)
        conn.execute('UPDATE photos SET scores=?,labels=?,error=NULL,analysis_version=?,retry_after=0,attempts=0 WHERE id=?',
                     (json.dumps(scores), json.dumps([k for k,v in scores.items() if v >= (.82 if k == 'cards' else .65 if k == 'buildings' else .7)]), MODEL_VERSION, item['id']))
        if item['live_relative']:
            conn.execute("UPDATE photos SET scores=? WHERE root=? AND relative=?",
                         (json.dumps({'paired': True}), item['root'], item['live_relative']))
    for identifier in old_faces:
        (photos.CACHE / f'{identifier}.face.jpg').unlink(missing_ok=True)


CLASSIFICATION_BATCH = 128


def pending_photos(limit=32):
    return db.rows("""SELECT p.* FROM photos p WHERE (scores='{}' OR COALESCE(analysis_version,'')!=?)
      AND COALESCE(retry_after,0)<=? AND NOT EXISTS
      (SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative) ORDER BY id LIMIT ?""",
      (MODEL_VERSION,time.time(),limit))


def run_scan():
    progress(running=True,error=None,eta_seconds=None,discovery_complete=False)
    errors=0
    classification_pending=db.state('photo_classify_pending','0')=='1'
    try:
        offset=0
        for root in db.rows('SELECT * FROM photo_roots'):
            if paused(): raise InterruptedError()
            try:
                if not discover(root,discovered_offset=offset,force=False,interval=10**15 if classification_pending else 600):
                    raise InterruptedError()
                current=inventory.job('photos',root['id'])
                offset+=current['total']
                errors+=current['errors']
            except InterruptedError: raise
            except Exception as exc:
                errors+=1
                progress(error=str(getattr(exc,'detail',type(exc).__name__)))
        db.set_state('photo_classify_pending','1')
        state=photos.status()
        total=state['total_media']
        remaining=db.rows("""SELECT count(*) n FROM photos p WHERE (scores='{}' OR COALESCE(analysis_version,'')!=?) AND NOT EXISTS
          (SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative)""",(MODEL_VERSION,))[0]['n']
        progress(stage='classifying',discovery_complete=True,processed_base=total-remaining,
                 media_total=total,total=remaining,done=0,errors=errors)
        model=None
        estimate=Estimate()
        done=0
        while done<CLASSIFICATION_BATCH:
            pending=pending_photos(min(16,CLASSIFICATION_BATCH-done))
            if not pending: break
            for item in pending:
                if paused(): raise InterruptedError()
                db.set_state('photo_active_item',str(item['id']))
                with db.connect() as c:
                    c.execute('UPDATE photos SET attempts=COALESCE(attempts,0)+1 WHERE id=?',(item['id'],))
                try:
                    photos.safe_media(item['id'])
                    if model is None: model=PhotoModels()
                    process(item,model)
                except InterruptedError: raise
                except Exception as exc:
                    errors+=1
                    with db.connect() as c:
                        c.execute('UPDATE photos SET error=?,retry_after=? WHERE id=?',
                                  (str(getattr(exc,'detail',type(exc).__name__))[:200],time.time()+3600,item['id']))
                db.set_state('photo_active_item','')
                done+=1
                progress(done=done,errors=errors,eta_seconds=estimate.advance(remaining-done))
        more=bool(pending_photos(1))
        deferred=db.rows("""SELECT count(*) n FROM photos p WHERE (scores='{}' OR COALESCE(analysis_version,'')!=?)
          AND retry_after>? AND NOT EXISTS(SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative)""",
          (MODEL_VERSION,time.time()))[0]['n']
        db.set_state('photo_classify_pending','1' if more else '0')
        if not more: db.set_state('photo_last_complete',str(time.time()))
        progress(stage='classifying' if more else 'waiting' if deferred else 'complete',running=False,errors=max(errors,deferred),
                 deferred=deferred,eta_seconds=estimate.advance(max(0,remaining-done)) if more else None if deferred or errors else 0)
    except InterruptedError:
        progress(stage='paused',running=False,eta_seconds=None)
    finally:
        db.set_state('photo_model_version',MODEL_VERSION)


def interrupted_item():
    active=db.state('photo_active_item','')
    if active:
        with db.connect() as c:
            c.execute("UPDATE photos SET error='작업 중단: 자동 재시도 대기',retry_after=?+min(86400,300*pow(2,min(COALESCE(attempts,1)-1,8))) WHERE id=? AND (scores='{}' OR COALESCE(analysis_version,'')!=?)",
                      (time.time(),int(active),MODEL_VERSION))
        db.set_state('photo_active_item','')


def main():
    global stopping
    signal.signal(signal.SIGTERM,lambda *_:globals().__setitem__('stopping',True))
    photos.init()
    interrupted_item()
    last=float(db.state('photo_last_complete','0'))
    while not stopping:
        photo_runtime.heartbeat()
        requested=float(db.state('photo_scan_requested','0'))
        unfinished=db.rows("SELECT 1 FROM scan_jobs WHERE kind='photos' AND stage!='complete' LIMIT 1")
        if not paused() and (unfinished or db.state('photo_classify_pending','0')=='1' or requested>last or time.time()-last>600):
            child=subprocess.Popen([os.sys.executable,'-m','hw_agent.photo_worker','--scan'])
            while child.poll() is None and not stopping:
                photo_runtime.heartbeat();time.sleep(2)
            if stopping:
                child.terminate()
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired: child.kill();child.wait()
            if child.returncode:
                interrupted_item()
                progress(stage='error',running=False,error='작업 중단: 저장한 위치에서 재개합니다.',eta_seconds=None)
            last=float(db.state('photo_last_complete','0'))
        time.sleep(2 if db.state('photo_classify_pending','0')=='1' else 10)


if __name__=='__main__':
    if '--scan' in os.sys.argv: run_scan()
    else: main()
