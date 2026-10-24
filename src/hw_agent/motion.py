"""Shared MediaPipe models and debounced, bounded Flow dispatch."""
import json
import threading
import time
from fastapi import HTTPException
from . import db, flows
from .config import BASE

LABELS = {"Face": "얼굴 감지", "Open_Palm": "손바닥", "Closed_Fist": "주먹",
          "Victory": "브이", "Thumb_Up": "엄지척", "Thumb_Down": "엄지다운"}


class PresenceGate:
    def __init__(self, hold=1.0, release=1.5, cooldown=5.0, repeat=False):
        self.hold, self.release, self.cooldown = hold, release, cooldown
        self.repeat = repeat
        self.since = None
        self.last_seen = None
        self.absent_since = None
        self.fired = False
        self.last_fire = float("-inf")

    def update(self, present, now):
        # 잠깐 놓친 프레임은 무시하되, 지속 감지가 끊기면 유지 시간은 다시 센다.
        if not present:
            self.since = None
            if self.absent_since is None:
                self.absent_since = now
            if now - self.absent_since >= self.release:
                self.fired = False
            return False
        if self.absent_since is not None:
            if now - self.absent_since >= self.release:
                self.fired = False
            self.absent_since = None
        self.last_seen = now
        if self.since is None:
            self.since = now
        if (not self.fired or self.repeat) and now - self.since >= self.hold and now - self.last_fire >= self.cooldown:
            self.fired, self.last_fire = True, now
            return True
        return False


class Motion:
    def __init__(self):
        self.lock = threading.RLock()
        self.dispatch_lock = threading.Lock()
        self.gesture = None
        self.face = None
        self.enabled = False
        self.mappings = {}
        self.rules = {}
        self.gates = {key: PresenceGate() for key in LABELS}
        self.error = None
        self.last_event = None
        self.observed = {}
        self.frames = 0
        self.last_frame_at = None
        self.inference_ms = 0

    def load_gesture(self):
        with self.lock:
            if self.gesture is None:
                import mediapipe as mp
                self.gesture = mp.tasks.vision.GestureRecognizer.create_from_options(
                    mp.tasks.vision.GestureRecognizerOptions(
                        base_options=mp.tasks.BaseOptions(model_asset_path=str(BASE / "models/gesture_recognizer.task")),
                        running_mode=mp.tasks.vision.RunningMode.IMAGE))
            return self.gesture

    def load(self):
        with self.lock:
            self.load_gesture()
            if self.face is None:
                import mediapipe as mp
                self.face = mp.tasks.vision.FaceDetector.create_from_options(
                    mp.tasks.vision.FaceDetectorOptions(
                        base_options=mp.tasks.BaseOptions(model_asset_path=str(BASE / "models/blaze_face_short_range.tflite")),
                        min_detection_confidence=.7))

    def close(self):
        with self.lock:
            for name in ("face", "gesture"):
                model = getattr(self, name)
                if model is not None:
                    model.close()
                    setattr(self, name, None)

    def configure(self, enabled, mappings, rules=None):
        rules = self.rules if rules is None else rules
        normalized = {}
        for key in LABELS:
            rule = rules.get(key, {})
            hold, release, interval = rule.get("hold_seconds", 1.0), rule.get("release_seconds", 1.5), rule.get("repeat_seconds", 5.0)
            repeat = rule.get("repeat", False)
            if not isinstance(repeat, bool) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (hold, release, interval)):
                raise HTTPException(400, "감지 시간과 반복 설정을 확인하세요.")
            if not (.3 <= hold <= 60 and .3 <= release <= 60 and 3 <= interval <= 3600):
                raise HTTPException(400, "유지·재감지 시간은 0.3~60초, 실행 간격은 3~3600초입니다.")
            normalized[key] = {"hold_seconds": hold, "release_seconds": release, "repeat_seconds": interval, "repeat": repeat}
        if set(rules) - set(LABELS):
            raise HTTPException(400, "잘못된 감지 항목입니다.")
        for key, value in mappings.items():
            if key not in LABELS or not isinstance(value, str):
                raise HTTPException(400, "잘못된 감지 항목입니다.")
            if enabled and value and not db.rows("SELECT id FROM flows WHERE id=?", (value,)):
                raise HTTPException(400, "존재하는 Flow를 선택하세요.")
        if enabled:
            try:
                self.load()
            except Exception as exc:
                raise HTTPException(503, "감지 모델 준비 실패: " + str(exc))
        with self.lock:
            self.enabled = enabled
            self.mappings = dict(mappings)
            self.rules = normalized
            self.gates = {key: PresenceGate(rule["hold_seconds"], rule["release_seconds"], rule["repeat_seconds"], rule["repeat"])
                          for key, rule in normalized.items()}
            self.error = None
            db.set_state("motion_config", json.dumps({"enabled": enabled, "mappings": mappings, "rules": normalized}))

    def state(self):
        with self.lock:
            return {"enabled": self.enabled, "mappings": dict(self.mappings), "error": self.error,
                    "rules": self.rules,
                    "observed": dict(self.observed), "frames": self.frames, "last_frame_at": self.last_frame_at,
                    "inference_ms": round(self.inference_ms, 1), "last_event": self.last_event,
                    "models_loaded": {"face": self.face is not None, "gesture": self.gesture is not None}}

    def detect(self, image):
        with self.lock:
            if not self.enabled:
                return
            try:
                import mediapipe as mp
                import numpy as np
                start = time.monotonic()
                frame = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(image.convert("RGB")))
                faces = self.face.detect(frame)
                hands = self.gesture.recognize(frame)
                observed = {"Face": max((d.categories[0].score for d in faces.detections), default=0)}
                for categories in hands.gestures:
                    if categories and categories[0].category_name in LABELS:
                        top = categories[0]
                        observed[top.category_name] = max(observed.get(top.category_name, 0), float(top.score))
                self.observed = {k: float(v) for k, v in observed.items() if v >= .7}
                self.frames += 1
                self.last_frame_at = time.time()
                self.inference_ms = (time.monotonic() - start) * 1000
                self.consume(self.observed, time.monotonic())
            except Exception as exc:
                self.error = "감지 오류: " + type(exc).__name__ + ": " + str(exc)
                self.enabled = False

    def consume(self, observed, now):
        for key, gate in self.gates.items():
            if gate.update(observed.get(key, 0) >= .7, now):
                flow_id = self.mappings.get(key)
                if flow_id:
                    event = {"kind": key, "flow": flow_id, "time": time.time(), "status": "running"}
                    if not self.dispatch_lock.acquire(blocking=False):
                        event["status"] = "skipped_busy"
                        self.last_event = event
                        continue
                    self.last_event = event
                    threading.Thread(target=self.run, args=(flow_id, event, gate), daemon=True).start()

    def run(self, flow_id, event, gate):
        try:
            result = flows.execute(flow_id)
            event["status"] = result["status"]
        except Exception as exc:
            event["status"] = "failed"
            event["error"] = str(getattr(exc, "detail", type(exc).__name__))
        finally:
            with self.lock:
                gate.last_fire = time.monotonic()
            self.dispatch_lock.release()


motion = Motion()
