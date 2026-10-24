"""Download official, checksum-pinned MediaPipe inference models."""
import hashlib
from pathlib import Path
import urllib.request
from tqdm import tqdm

MODELS = {
    "gesture_recognizer.task": (
        "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
        "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482"),
    "blaze_face_short_range.tflite": (
        "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
        "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f"),
}


def main():
    root = Path(__file__).resolve().parents[1] / "models"
    root.mkdir(exist_ok=True)
    for name, (url, digest) in MODELS.items():
        target = root / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        temporary = target.with_suffix(".partial")
        with urllib.request.urlopen(url, timeout=60) as source, temporary.open("wb") as output:
            with tqdm(total=int(source.headers.get("Content-Length", 0)), unit="B", unit_scale=True, desc=name) as progress:
                while chunk := source.read(65536):
                    output.write(chunk)
                    progress.update(len(chunk))
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            temporary.unlink()
            raise RuntimeError("Model checksum mismatch: " + name)
        temporary.replace(target)


if __name__ == "__main__":
    main()
