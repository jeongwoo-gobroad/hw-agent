"""Bounded, local speech transcription; audio is deleted after each request."""
import base64
import binascii
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import wave
import array
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
BINARY = Path(os.getenv("WHISPER_BINARY", str(ROOT / "tools/whisper.cpp/build/bin/whisper-cli")))
MODEL = Path(os.getenv("WHISPER_MODEL", str(ROOT / "models/ggml-tiny.bin")))
_lock = threading.Lock()

def status():
    return {"ready": BINARY.is_file() and MODEL.is_file(), "engine": "whisper.cpp", "model": MODEL.name,
            "language": "ko", "max_seconds": 15, "local": True}

def transcribe(encoded):
    if not status()["ready"]:
        raise HTTPException(503, "음성 모델을 준비하고 있습니다.")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "올바른 오디오가 아닙니다.")
    if not audio or len(audio) > 1500000:
        raise HTTPException(413, "음성은 15초 이내로 녹음하세요.")
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "다른 음성을 처리 중입니다. 잠시 후 다시 시도하세요.")
    try:
        with tempfile.TemporaryDirectory(prefix="alter-voice-") as folder:
            source, wav = Path(folder)/"input", Path(folder)/"audio.wav"
            source.write_bytes(audio)
            converted = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                "-i", str(source), "-t", "15", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                capture_output=True, timeout=20)
            if converted.returncode:
                raise HTTPException(400, "오디오를 읽을 수 없습니다.")
            with wave.open(str(wav)) as stream:
                samples = array.array("h", stream.readframes(stream.getnframes()))
            if not samples or (sum(x*x for x in samples)/len(samples))**0.5 < 100:
                return {"text": "", "language": "ko", "silent": True}
            result = subprocess.run([str(BINARY), "-m", str(MODEL), "-f", str(wav), "-l", "ko", "-t", "2",
                "-nt", "-otxt", "-of", str(Path(folder)/"result")], capture_output=True, timeout=90)
            output = Path(folder)/"result.txt"
            if result.returncode or not output.exists():
                raise HTTPException(503, "음성을 인식하지 못했습니다. 다시 말씀해 주세요.")
            return {"text": output.read_text().strip()[:1200], "language": "ko", "silent": False}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "음성 처리 시간이 초과되었습니다.")
    finally:
        _lock.release()
