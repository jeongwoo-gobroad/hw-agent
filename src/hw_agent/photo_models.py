"""CPU-only, local CLIP topics and YuNet/SFace face features."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from .config import BASE

TOPICS = {
    "people": ("사람", "a photograph of people, a person", "an empty room or an empty landscape"),
    "animals": ("동물", "a photograph of an animal, pet, dog, cat or bird", "a photograph of furniture and household objects"),
    "buildings": ("건물", "a photograph of buildings, houses or architecture", "a close up photograph of a small object"),
    "documents": ("서류", "a photograph of a printed document, receipt or paper with text", "a photograph of a landscape or a human face"),
    "cards": ("카드", "a close up photograph of a flat rectangular credit card, ID card or business card", "a photograph of a landscape or a human face"),
    "food": ("음식", "a photograph of food or a meal", "a photograph of furniture or a building"),
    "nature": ("자연", "a photograph of a natural landscape, trees, mountain or ocean", "an indoor scene"),
}


class PhotoModels:
    def __init__(self):
        import cv2
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.cv = cv2
        cv2.setNumThreads(1)
        root = BASE / "models" / "photos"
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        text = ort.InferenceSession(str(root / "clip-text.onnx"), options, providers=["CPUExecutionProvider"])
        tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        tokenizer.enable_padding(length=77, pad_id=49407, pad_token="<|endoftext|>")
        tokenizer.enable_truncation(max_length=77)
        encoded = tokenizer.encode_batch([p for row in TOPICS.values() for p in row[1:]])
        inputs = {"input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
                  "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64)}
        outputs = text.run(None, {i.name: inputs[i.name] for i in text.get_inputs()})
        names = [o.name for o in text.get_outputs()]
        self.text = outputs[names.index("text_embeds")]
        self.text /= np.linalg.norm(self.text, axis=1, keepdims=True)
        del text
        self.vision = ort.InferenceSession(str(root / "clip-vision.onnx"), options, providers=["CPUExecutionProvider"])
        self.detector = cv2.FaceDetectorYN.create(str(root / "yunet.onnx"), "", (640, 640), .85, .3, 100)
        self.recognizer = cv2.FaceRecognizerSF.create(str(root / "sface.onnx"), "")

    def analyze(self, image):
        image = image.convert("RGB")
        resized = ImageOps.fit(image, (224, 224), method=Image.Resampling.BICUBIC)
        pixels = np.asarray(resized, dtype=np.float32) / 255
        pixels = (pixels - np.array([.48145466, .4578275, .40821073], np.float32)) / np.array([.26862954, .26130258, .27577711], np.float32)
        outputs = self.vision.run(None, {"pixel_values": pixels.transpose(2, 0, 1)[None]})
        feature = outputs[[o.name for o in self.vision.get_outputs()].index("image_embeds")][0]
        feature /= np.linalg.norm(feature)
        similarity = self.text @ feature
        scores = {}
        # 각 주제를 따로 비교하므로 한 사진에 여러 주제를 붙일 수 있다.
        for i, key in enumerate(TOPICS):
            positive, negative = similarity[i*2:i*2+2]
            scores[key] = round(float(1 / (1 + np.exp(-30 * (positive-negative)))), 4)
        small = image.copy()
        small.thumbnail((960, 960))
        bgr = self.cv.cvtColor(np.asarray(small), self.cv.COLOR_RGB2BGR)
        self.detector.setInputSize(small.size)
        detected = self.detector.detect(bgr)[1]
        faces = []
        for face in ([] if detected is None else detected):
            if min(face[2:4]) < 24:
                continue
            aligned = self.recognizer.alignCrop(bgr, face)
            embedding = self.recognizer.feature(aligned).flatten()
            embedding /= np.linalg.norm(embedding)
            x, y, w, h = face[:4]
            box = [float(x/small.width), float(y/small.height), float(w/small.width), float(h/small.height)]
            faces.append((embedding, box))
        if faces:
            scores["people"] = max(.99, scores["people"])
        return scores, faces
