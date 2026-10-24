"""Read-only explorer restricted to independently registered indexing roots."""
import os
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from . import db, storage, preview

router = APIRouter(prefix='/api/library')


def resolve(root, relative=''):
    path = PurePosixPath(relative)
    storage.check_path(relative)
    if path.is_absolute() or '..' in path.parts or any(p.startswith('.') for p in path.parts):
        raise HTTPException(403, '등록 폴더 안의 일반 경로만 열 수 있습니다.')
    records = db.rows('SELECT * FROM roots WHERE id=?', (root,))
    if not records: raise HTTPException(404, '등록된 색인 폴더가 아닙니다.')
    base = storage.root_path(records[0])
    target = base
    for part in path.parts:
        target = target / part
        storage.check_path(target)
        if target.is_symlink(): raise HTTPException(403, '심볼릭 링크는 탐색하지 않습니다.')
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError:
        raise HTTPException(404, '파일 또는 폴더가 이동되었거나 삭제됐습니다.')
    except PermissionError:
        raise HTTPException(403, '이 파일 또는 폴더를 읽을 권한이 없습니다.')
    storage.check_path(resolved)
    if not resolved.is_relative_to(base): raise HTTPException(403, '등록 폴더 밖입니다.')
    return resolved


@router.get('/entries')
def entries(root: int, path: str = '', offset: int = 0, folders_only: bool = False):
    if offset < 0: raise HTTPException(400, '잘못된 페이지입니다.')
    target = resolve(root, path)
    if not target.is_dir(): raise HTTPException(400, '폴더를 선택하세요.')
    result = []
    with os.scandir(target) as listing:
        for entry in listing:
            if storage.excluded(entry.name) or entry.name.startswith('.') or entry.is_symlink(): continue
            is_dir = entry.is_dir(follow_symlinks=False)
            if folders_only and not is_dir: continue
            if not is_dir and not entry.is_file(follow_symlinks=False): continue
            stat = entry.stat(follow_symlinks=False)
            result.append({'name':entry.name,'path':str(PurePosixPath(path)/entry.name),'directory':is_dir,
                           'size':None if is_dir else stat.st_size,'modified':stat.st_mtime,
                           'ext':Path(entry.name).suffix.lower()})
    result.sort(key=lambda i:(not i['directory'],i['name'].casefold()))
    return {'items':result[offset:offset+200], 'total':len(result),'root':root,'path':path,'offset':offset}


@router.get('/preview')
def media(root: int, path: str, download: bool = False):
    source = resolve(root, path)
    if not source.is_file(): raise HTTPException(400, '파일을 선택하세요.')
    if download: return FileResponse(source, filename=source.name, media_type='application/octet-stream')
    target, mime = preview.preview(source, {'text':'','extraction':'미리보기를 지원하지 않는 형식입니다.'})
    return FileResponse(target, media_type=mime)
