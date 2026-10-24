"""Download revision-pinned public photo models; never uploads library media."""
import hashlib
import json
from pathlib import Path
import urllib.request
from tqdm import tqdm

CLIP_REV = "d15189d7028b43f1d3e65039190477f6af591c2a"
ZOO_REV = "47534e27c9851bb1128ccc0102f1145e27f23f98"
FILES = {
    "clip-vision-fp32.onnx": f"https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/{CLIP_REV}/onnx/vision_model.onnx",
    "clip-text-fp32.onnx": f"https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/{CLIP_REV}/onnx/text_model.onnx",
    "tokenizer.json": f"https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/{CLIP_REV}/tokenizer.json",
    "yunet.onnx": f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{ZOO_REV}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "sface.onnx": f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{ZOO_REV}/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

HASHES = {
    'clip-vision-fp32.onnx': 'fd6e1402a588279d1723c7534d4bcba5bc0b14b47dfab0e46f8c47b8270d7d40',
    'clip-text-fp32.onnx': '3f6571f5bad13a97c469c1622e1cfc4d9aef78b79fdbfcff804ca357bfada8cc',
    'tokenizer.json': 'f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd',
    'yunet.onnx': '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',
    'sface.onnx': '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79',
}


def main():
    root = Path(__file__).resolve().parents[1] / "models" / "photos"
    root.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in FILES.items():
        target = root / name
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != HASHES[name]:
            partial = target.with_suffix(".partial")
            with urllib.request.urlopen(url, timeout=90) as source, partial.open("wb") as output:
                with tqdm(total=int(source.headers.get("Content-Length", 0)), unit="B", unit_scale=True, desc=name) as bar:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                        bar.update(len(chunk))
            if hashlib.sha256(partial.read_bytes()).hexdigest() != HASHES[name]:
                partial.unlink()
                raise RuntimeError('Photo model checksum mismatch: '+name)
            partial.replace(target)
        manifest[name] = {"url": url, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
