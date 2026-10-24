"""Independent media library, volume identities and authenticated API."""
import json
from pathlib import Path
import time
import secrets
import subprocess
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import db, storage, config, preview
from .photo_models import TOPICS
from . import photo_runtime

router = APIRouter(prefix="/api/photos")
CACHE = config.DATA / "photos"
CACHE.mkdir(exist_ok=True)


def init():
    with db.connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS photo_roots(id INTEGER PRIMARY KEY, uuid TEXT, relative_path TEXT,
          path TEXT, mount TEXT, label TEXT, UNIQUE(uuid,relative_path));
        CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY, root INTEGER, relative TEXT,
          album TEXT, name TEXT, kind TEXT, modified REAL, size INTEGER, captured REAL,
          date_source TEXT, content_id TEXT, duration REAL, live_relative TEXT, pair_source TEXT, scores TEXT DEFAULT '{}',
          labels TEXT DEFAULT '[]', manual_labels TEXT, error TEXT, seen TEXT,
          UNIQUE(root,relative));
        CREATE INDEX IF NOT EXISTS photos_date ON photos(captured);
        CREATE INDEX IF NOT EXISTS photos_live_pair ON photos(root,live_relative);
        CREATE TABLE IF NOT EXISTS photo_people(id INTEGER PRIMARY KEY, name TEXT DEFAULT '', embedding BLOB);
        CREATE TABLE IF NOT EXISTS photo_faces(id INTEGER PRIMARY KEY, photo INTEGER, person INTEGER, box TEXT);
        CREATE INDEX IF NOT EXISTS photo_face_person ON photo_faces(person,photo);
        ''')


def root_path(root):
    storage.check_path(root['path'])
    storage.check_path(root['relative_path'])
    device = storage.device_for_uuid(root['uuid'])
    if not device or not device['mount']:
        raise HTTPException(409, '사진 드라이브가 연결되지 않았습니다.')
    base = Path(device['mount']).resolve(strict=True)
    candidate = base / root['relative_path']
    storage.check_path(candidate)
    path = candidate.resolve(strict=True)
    storage.check_path(path)
    if not path.is_relative_to(base) or not path.is_dir():
        raise HTTPException(403, '사진 폴더 경계를 벗어났습니다.')
    return path


def safe_media(identifier, live=False):
    found = db.rows('SELECT * FROM photos WHERE id=?', (identifier,))
    if not found:
        raise HTTPException(404, '사진을 찾을 수 없습니다.')
    item = found[0]
    roots = db.rows('SELECT * FROM photo_roots WHERE id=?', (item['root'],))
    if not roots:
        raise HTTPException(404, '등록이 해제된 사진 폴더입니다.')
    base = root_path(roots[0])
    relative = item['live_relative'] if live else item['relative']
    if not relative:
        raise HTTPException(404, '연결된 Live Photo 영상이 없습니다.')
    candidate = base / relative
    storage.check_path(candidate)
    current = base
    for part in Path(relative).parts:
        if part == '..' or Path(relative).is_absolute():
            raise HTTPException(403, '사진 폴더 밖의 파일입니다.')
        current = current / part
        if current.is_symlink():
            raise HTTPException(403, '심볼릭 링크는 열지 않습니다.')
    path = candidate.resolve(strict=True)
    storage.check_path(path)
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(403, '사진 폴더 밖의 파일입니다.')
    return path, item


@router.get('/roots')
def roots():
    result = db.rows('SELECT * FROM photo_roots ORDER BY id')
    listing = storage.devices()
    for root in result:
        device = storage.device_for_uuid(root['uuid'], listing)
        root['online'] = bool(device and device['mount'])
        if root['online']:
            root['path'] = str(Path(device['mount']) / root['relative_path'])
    return result


class Folder(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


@router.post('/roots')
def add_root(body: Folder):
    path, device = storage.external_path(body.path)
    if not path.is_dir():
        raise HTTPException(400, '사진 폴더를 선택하세요.')
    relative = str(path.relative_to(Path(device['mount']).resolve()))
    with db.connect() as conn:
        conn.execute('''INSERT INTO photo_roots(id,uuid,relative_path,path,mount,label) VALUES(?,?,?,?,?,?)
          ON CONFLICT(uuid,relative_path) DO UPDATE SET path=excluded.path,mount=excluded.mount''',
          (secrets.randbits(52), device['uuid'], relative, str(path), device['mount'], path.name))
    scan()
    return {'ok': True}


@router.delete('/roots/{identifier}')
def remove_root(identifier: int):
    # 오프라인 드라이브도 등록 정보만으로 해제한다. 원본에는 손대지 않는다.
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute('SELECT id FROM photos WHERE root=?', (identifier,))]
        faces = [r[0] for r in conn.execute('SELECT id FROM photo_faces WHERE photo IN (SELECT id FROM photos WHERE root=?)', (identifier,))]
        conn.execute('DELETE FROM photo_faces WHERE photo IN (SELECT id FROM photos WHERE root=?)', (identifier,))
        conn.execute('DELETE FROM photos WHERE root=?', (identifier,))
        conn.execute('DELETE FROM photo_roots WHERE id=?', (identifier,))
        conn.execute('DELETE FROM photo_people WHERE id NOT IN (SELECT person FROM photo_faces)')
    for i in ids:
        (CACHE / f'{i}.jpg').unlink(missing_ok=True)
    for i in faces:
        (CACHE / f'{i}.face.jpg').unlink(missing_ok=True)
    return {'ok': True}


@router.post('/scan')
def scan():
    db.set_state('photo_scan_requested', str(time.time()))
    db.set_state('photo_paused', '0')
    return {'ok': True}


@router.post('/pause')
def pause():
    db.set_state('photo_paused', '1')
    return {'ok': True}


@router.get('/status')
def status():
    result = photo_runtime.read() or json.loads(db.state('photo_progress', '{}'))
    result['paused'] = db.state('photo_paused', '0') == '1'
    result['total_media'] = db.rows('SELECT count(*) n FROM photos p WHERE NOT EXISTS(SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative)')[0]['n']
    result['classified_media'] = db.rows("SELECT count(*) n FROM photos p WHERE scores!='{}' AND NOT EXISTS(SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative)")[0]['n']
    result['topics'] = {key: value[0] for key, value in TOPICS.items()}
    result['worker_online'] = photo_runtime.online()
    return result


@router.get('/albums')
def albums():
    return db.rows('SELECT root,album,count(*) count FROM photos p WHERE NOT EXISTS(SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative) GROUP BY root,album ORDER BY album')


@router.get('/items')
def items(root: int = 0, album: str | None = None, topic: str = '', person: int = 0,
          after: float | None = None, before: float | None = None, exclude: bool = False,
          kind: str = '', q: str = '', offset: int = 0):
    if offset < 0 or (after is not None and before is not None and after > before):
        raise HTTPException(400, '날짜 범위 또는 페이지 값이 올바르지 않습니다.')
    where, args = ['NOT EXISTS(SELECT 1 FROM photos l WHERE l.root=p.root AND l.live_relative=p.relative)'], []
    for key, value in [('root', root), ('album', album), ('kind', kind)]:
        if value is not None and (value or key == 'album'):
            where.append(f'p.{key}=?'); args.append(value)
    if q:
        where.append('p.name LIKE ?'); args.append('%'+q+'%')
    if topic:
        if topic not in TOPICS:
            raise HTTPException(400, '알 수 없는 주제입니다.')
        where.append('EXISTS(SELECT 1 FROM json_each(COALESCE(p.manual_labels,p.labels)) WHERE value=?)'); args.append(topic)
    if person:
        where.append('EXISTS(SELECT 1 FROM photo_faces f WHERE f.photo=p.id AND f.person=?)'); args.append(person)
    dates, bounds = [], []
    if after is not None: dates.append('p.captured>=?'); bounds.append(after)
    if before is not None: dates.append('p.captured<=?'); bounds.append(before)
    if dates:
        where.append(('NOT ' if exclude else '') + '('+' AND '.join(dates)+')'); args.extend(bounds)
    clause = ' AND '.join(where)
    count = db.rows('SELECT count(*) n FROM photos p WHERE '+clause, args)[0]['n']
    result = db.rows('SELECT p.* FROM photos p WHERE '+clause+' ORDER BY captured DESC,id DESC LIMIT 120 OFFSET ?', (*args, offset))
    for item in result:
        item['labels'] = json.loads(item['manual_labels'] or item['labels'])
        item['scores'] = json.loads(item['scores'])
        item['faces'] = db.rows('SELECT f.id,f.person,p.name,f.box FROM photo_faces f JOIN photo_people p ON p.id=f.person WHERE f.photo=?', (item['id'],))
    return {'items': result, 'total': count}


@router.get('/people')
def people():
    return db.rows('''SELECT p.id,p.name,count(DISTINCT f.photo) count,min(f.photo) cover,min(f.id) cover_face
      FROM photo_people p JOIN photo_faces f ON f.person=p.id GROUP BY p.id ORDER BY count DESC''')


class PersonName(BaseModel):
    name: str = Field(max_length=100)


@router.patch('/people/{identifier}')
def rename_person(identifier: int, body: PersonName):
    with db.connect() as conn:
        conn.execute('UPDATE photo_people SET name=? WHERE id=?', (body.name.strip(), identifier))
    return {'ok': True}


@router.get('/faces/{identifier}/thumbnail')
def face_thumbnail(identifier: int):
    face = db.rows('SELECT photo FROM photo_faces WHERE id=?', (identifier,))
    if not face: raise HTTPException(404, '얼굴을 찾을 수 없습니다.')
    safe_media(face[0]['photo'])
    target = CACHE / f'{identifier}.face.jpg'
    if not target.exists(): raise HTTPException(404, '얼굴 미리보기 준비 중입니다.')
    return FileResponse(target, media_type='image/jpeg')


class FacePerson(BaseModel):
    person: int = Field(ge=0)


@router.patch('/faces/{identifier}')
def move_face(identifier: int, body: FacePerson):
    with db.connect() as conn:
        face = conn.execute('SELECT * FROM photo_faces WHERE id=?', (identifier,)).fetchone()
        if not face: raise HTTPException(404, '얼굴을 찾을 수 없습니다.')
        if body.person:
            if not conn.execute('SELECT 1 FROM photo_people WHERE id=?', (body.person,)).fetchone():
                raise HTTPException(404, '사람을 찾을 수 없습니다.')
            target = body.person
        else:
            target = conn.execute("INSERT INTO photo_people(name) VALUES('')").lastrowid
        conn.execute('UPDATE photo_faces SET person=? WHERE id=?', (target, identifier))
    return {'ok': True}


class Labels(BaseModel):
    labels: list[str] | None = None


@router.patch('/items/{identifier}')
def labels(identifier: int, body: Labels):
    if body.labels is not None and any(x not in TOPICS for x in body.labels):
        raise HTTPException(400, '알 수 없는 주제입니다.')
    with db.connect() as conn:
        conn.execute('UPDATE photos SET manual_labels=? WHERE id=?',
                     (json.dumps(sorted(set(body.labels))) if body.labels is not None else None, identifier))
    return {'ok': True}


@router.get('/items/{identifier}/thumbnail')
def thumbnail(identifier: int):
    safe_media(identifier)
    path = CACHE / f'{identifier}.jpg'
    if not path.exists(): raise HTTPException(404, '미리보기 준비 중입니다.')
    return FileResponse(path, media_type='image/jpeg')


@router.get('/items/{identifier}/media')
def media(identifier: int, live: bool = False, original: bool = False):
    path, item = safe_media(identifier, live)
    if original:
        return FileResponse(path, filename=path.name)
    if path.suffix.lower() == '.mp4':
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name',
                                '-of', 'json', str(path)], capture_output=True, timeout=20)
        try:
            streams = json.loads(probe.stdout).get('streams', [])
            compatible = any(s.get('codec_type') == 'video' for s in streams) and all(
                s.get('codec_name') in {'h264', 'aac', 'mp3'} for s in streams if s.get('codec_type') in {'video','audio'})
        except ValueError:
            compatible = False
        if compatible:
            return FileResponse(path, media_type='video/mp4')
    target, mime = preview.preview(path, {'text': '', 'extraction': ''})
    return FileResponse(target, media_type=mime)
