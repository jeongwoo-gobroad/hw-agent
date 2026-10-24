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
from tqdm import tqdm
from . import db, photos, storage
from .photo_models import PhotoModels

IMAGES = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tif', '.tiff', '.bmp'}
VIDEOS = {'.mov', '.mp4', '.m4v', '.mkv', '.avi'}
stopping = False


def progress(**values):
    previous = json.loads(db.state('photo_progress', '{}'))
    previous.update(values, updated=time.time())
    db.set_state('photo_progress', json.dumps(previous))
    db.set_state('photo_heartbeat', str(time.time()))


def paused():
    return stopping or db.state('photo_paused', '0') == '1'


def metadata(path):
    result = subprocess.run(['exiftool', '-j', '-DateTimeOriginal', '-OffsetTimeOriginal', '-CreateDate',
                             '-ContentIdentifier', '-MediaGroupUUID', '-Duration', '-n', str(path)],
                            capture_output=True, timeout=25, check=True)
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


def discover(root):
    base = photos.root_path(root)
    generation = uuid.uuid4().hex
    pairs = []
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
        if paused(): return False
        # 검사보다 먼저 제외하여 보호 폴더의 stat/resolve도 하지 않는다.
        dirs[:] = [d for d in dirs if not storage.excluded(Path(directory)/d)
                   and not d.startswith('.') and not (Path(directory)/d).is_symlink()]
        for name in files:
            if paused(): return False
            path = Path(directory)/name
            if storage.excluded(path) or name.startswith('.') or path.suffix.lower() not in IMAGES | VIDEOS:
                continue
            if path.is_symlink(): continue
            relative = str(path.relative_to(base))
            stat = path.stat()
            prior = db.rows('SELECT * FROM photos WHERE root=? AND relative=?', (root['id'], relative))
            unchanged = prior and prior[0]['modified'] == stat.st_mtime and prior[0]['size'] == stat.st_size
            kind = 'photo' if path.suffix.lower() in IMAGES else 'video'
            if unchanged:
                captured, source = prior[0]['captured'], prior[0]['date_source']
                content, duration = prior[0]['content_id'], prior[0]['duration']
            else:
                try:
                    captured, source, content, duration = metadata(path)
                except (subprocess.SubprocessError, ValueError, KeyError, OSError):
                    captured, source, content, duration = stat.st_mtime, '수정일 대체 (촬영 정보 읽기 실패)', None, 0
            with db.connect() as conn:
                if not conn.execute('SELECT 1 FROM photo_roots WHERE id=?', (root['id'],)).fetchone():
                    return False
                conn.execute('''INSERT INTO photos(id,root,relative,album,name,kind,modified,size,captured,date_source,seen,content_id,duration)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(root,relative) DO UPDATE SET
                  modified=excluded.modified,size=excluded.size,captured=excluded.captured,date_source=excluded.date_source,
                  seen=excluded.seen,content_id=excluded.content_id,duration=excluded.duration,scores=CASE WHEN photos.modified!=excluded.modified OR photos.size!=excluded.size THEN '{}' ELSE photos.scores END''',
                  (secrets.randbits(52), root['id'], relative, str(Path(relative).parent), name, kind, stat.st_mtime, stat.st_size, captured, source, generation, content, duration))
            pairs.append((relative, kind, content, duration, captured))
            progress(stage='discovering', discovered=len(pairs))
    # 읽기를 끝낸 폴더에서만 사라진 파일의 색인을 정리한다.
    with db.connect() as conn:
        stale = [r[0] for r in conn.execute('SELECT id FROM photos WHERE root=? AND seen!=?', (root['id'], generation))]
        stale_faces = [r[0] for r in conn.execute('SELECT id FROM photo_faces WHERE photo IN (SELECT id FROM photos WHERE root=? AND seen!=?)', (root['id'], generation))]
        conn.execute('DELETE FROM photo_faces WHERE photo IN (SELECT id FROM photos WHERE root=? AND seen!=?)', (root['id'], generation))
        conn.execute('DELETE FROM photos WHERE root=? AND seen!=?', (root['id'], generation))
        by_content, by_stem = {}, {}
        for relative, kind, content, duration, captured in pairs:
            if kind == 'video':
                if content: by_content.setdefault(content, []).append(relative)
                by_stem.setdefault(str(Path(relative).with_suffix('')), []).append((relative, captured))
        for relative, kind, content, duration, captured in pairs:
            if kind != 'photo': continue
            candidates = [(r, 'content_identifier') for r in by_content.get(content, [])]
            if not candidates:
                candidates = [(r, 'filename_candidate') for r,t in by_stem.get(str(Path(relative).with_suffix('')), [])
                              if abs(t-captured) <= 5]
            if len(candidates) == 1:
                conn.execute("UPDATE photos SET scores=CASE WHEN live_relative IS NOT ? THEN '{}' ELSE scores END WHERE root=? AND relative=?",
                             (candidates[0][0], root['id'], relative))
                conn.execute("UPDATE photos SET kind='live',live_relative=?,pair_source=? WHERE root=? AND relative=?",
                             (*candidates[0], root['id'], relative))
            else:
                conn.execute("UPDATE photos SET scores=CASE WHEN live_relative IS NOT NULL THEN '{}' ELSE scores END WHERE root=? AND relative=?", (root['id'], relative))
                conn.execute("UPDATE photos SET kind='photo',live_relative=NULL,pair_source=NULL WHERE root=? AND relative=?", (root['id'], relative))
        conn.execute("""UPDATE photos SET scores='{}' WHERE root=? AND live_relative IN
          (SELECT relative FROM photos WHERE root=? AND scores='{}')""", (root['id'],root['id']))
        conn.execute('DELETE FROM photo_people WHERE id NOT IN (SELECT person FROM photo_faces)')
    for identifier in stale:
        (photos.CACHE / f'{identifier}.jpg').unlink(missing_ok=True)
    for identifier in stale_faces:
        (photos.CACHE / f'{identifier}.face.jpg').unlink(missing_ok=True)
    return True


def frames(path, video=False):
    if not video:
        with Image.open(path) as image:
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
        conn.execute('UPDATE photos SET scores=?,labels=?,error=NULL WHERE id=?',
                     (json.dumps(scores), json.dumps([k for k,v in scores.items() if v >= (.82 if k == 'cards' else .7)]), item['id']))
        if item['live_relative']:
            conn.execute("UPDATE photos SET scores=? WHERE root=? AND relative=?",
                         (json.dumps({'paired': True}), item['root'], item['live_relative']))
    for identifier in old_faces:
        (photos.CACHE / f'{identifier}.face.jpg').unlink(missing_ok=True)


def run_scan():
    progress(stage='discovering', running=True, discovered=0, done=0, total=0, errors=0, error=None)
    errors = 0
    for root in db.rows('SELECT * FROM photo_roots'):
        try: discover(root)
        except Exception as exc:
            errors += 1
            progress(error=f"{root['label']}: {getattr(exc, 'detail', type(exc).__name__)}")
    pending = db.rows("""SELECT * FROM photos p WHERE scores='{}' AND NOT EXISTS
      (SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative)""")
    progress(stage='classifying', total=len(pending), errors=errors)
    models = None
    try:
        for i, item in enumerate(tqdm(pending, desc='Photo library', unit='media')):
            if paused(): break
            try:
                # 오프라인 원본을 확인한 뒤에만 모델을 메모리에 올린다.
                photos.safe_media(item['id'])
                if models is None: models = PhotoModels()
                process(item, models)
            except InterruptedError: break
            except Exception as exc:
                errors += 1
                with db.connect() as conn:
                    conn.execute('UPDATE photos SET error=? WHERE id=?', (str(getattr(exc, 'detail', type(exc).__name__))[:200], item['id']))
            progress(done=i+1, errors=errors)
    finally:
        progress(stage='paused' if paused() else 'complete', running=False, errors=errors)


def main():
    global stopping
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__('stopping', True))
    photos.init()
    last = 0
    progress(stage='idle', running=False)
    while not stopping:
        db.set_state('photo_heartbeat', str(time.time()))
        requested = float(db.state('photo_scan_requested', '0'))
        if not paused() and (requested > last or time.time()-last > 600):
            started = time.time()
            # 각 작업은 별도 자식으로 실행해 완료 후 모델 메모리를 돌려준다.
            child = subprocess.Popen([os.sys.executable, '-m', 'hw_agent.photo_worker', '--scan'])
            while child.poll() is None and not stopping:
                db.set_state('photo_heartbeat', str(time.time()))
                time.sleep(2)
            if stopping:
                child.terminate()
                try: child.wait(timeout=10)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
            if child.returncode:
                progress(stage='error', running=False, error='사진 작업이 중단됐습니다. 다시 색인하면 이어서 처리합니다.')
            last = started
        time.sleep(2)


if __name__ == '__main__':
    if '--scan' in os.sys.argv: run_scan()
    else: main()
