import hashlib
from pathlib import Path
import subprocess
import threading
import time
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from fastapi import HTTPException
from .config import DATA

register_heif_opener()
CACHE = DATA / "previews"
CACHE.mkdir(exist_ok=True)
lock = threading.Lock()


def clean_cache():
    files = sorted(CACHE.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for p in files:
        total += p.stat().st_size
        if total > 1024**3 or p.stat().st_mtime < time.time() - 3 * 86400:
            p.unlink(missing_ok=True)


def preview(path, record):
    key = hashlib.sha256(f"{path}:{path.stat().st_mtime_ns}:{path.stat().st_size}".encode()).hexdigest()
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".bmp", ".tif", ".tiff"}:
        target = CACHE / (key + ".jpg")
        with lock:
            if not target.exists():
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source)
                    image.thumbnail((1600, 1200))
                    image.convert("RGB").save(target, quality=85)
                clean_cache()
        return target, "image/jpeg"
    if suffix in {".mov", ".mp4", ".mkv", ".avi", ".m4v"}:
        target = CACHE / (key + ".mp4")
        if path.stat().st_size > 2 * 1024**3:
            raise HTTPException(413, "2GiB 초과 영상은 다운로드로 확인하세요.")
        with lock:
            if not target.exists():
                temp = CACHE / (key + ".part.mp4")
                try:
                    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(path),
                                    "-t", "600", "-vf", "scale=960:-2", "-c:v", "libx264", "-preset", "ultrafast",
                                    "-crf", "28", "-c:a", "aac", "-movflags", "+faststart", str(temp)],
                                   timeout=180, check=True, capture_output=True)
                    temp.replace(target)
                except subprocess.SubprocessError:
                    temp.unlink(missing_ok=True)
                    raise HTTPException(422, "영상 변환 실패 또는 시간 초과")
                clean_cache()
        return target, "video/mp4"
    # 문서는 추출 텍스트만 표시해 활성 콘텐츠를 실행하지 않는다.
    target = CACHE / (key + ".txt")
    target.write_text(record["text"] or f"텍스트 미리보기 없음 ({record['extraction']})", encoding="utf-8")
    return target, "text/plain; charset=utf-8"
