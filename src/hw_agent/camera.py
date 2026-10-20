import io
import json
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import uuid
from fastapi import HTTPException
from . import db, flows, storage
from .config import BASE


class Camera:
    def __init__(self):
        self.lock = threading.RLock()
        self.condition = threading.Condition()
        self.frame = None
        self.running = False
        self.recording = False
        self.gestures = False
        self.error = None
        self.last_gesture = None
        self.record_dir = None
        self.recognizer = None
        self.record_queue = queue.Queue(maxsize=20)

    def state(self):
        return {"running": self.running, "recording": self.recording,
                "gestures": self.gestures, "error": self.error,
                "last_gesture": self.last_gesture, "record_dir": self.record_dir,
                "mappings": json.loads(db.state("gesture_mappings", "{}"))}

    def start(self):
        with self.lock:
            if self.running:
                return
            try:
                from picamera2 import Picamera2
                self.device = Picamera2()
                self.device.configure(self.device.create_video_configuration(
                    main={"size": (640, 480), "format": "RGB888"}, controls={"FrameRate": 10}))
                self.device.start()
                self.running = True
                self.error = None
                threading.Thread(target=self.capture, daemon=True).start()
            except Exception as exc:
                self.error = type(exc).__name__ + ": " + str(exc)
                raise HTTPException(503, self.error)

    def stop(self):
        self.stop_recording()
        self.gestures = False
        self.running = False

    def capture(self):
        last_detect = 0
        try:
            while self.running:
                image = self.device.capture_image("main")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=75)
                frame = output.getvalue()
                with self.condition:
                    self.frame = frame
                    self.condition.notify_all()
                if self.recording:
                    try:
                        self.record_queue.put_nowait(frame)
                    except queue.Full:
                        self.error = "녹화 처리 속도 부족: 일부 프레임 생략"
                if self.gestures and time.monotonic() - last_detect > .3:
                    last_detect = time.monotonic()
                    self.detect(image)
                time.sleep(.03)
        except Exception as exc:
            self.error = type(exc).__name__ + ": " + str(exc)
        finally:
            self.running = False
            self.device.stop()
            self.device.close()

    def stream(self):
        while self.running:
            with self.condition:
                self.condition.wait(timeout=2)
                frame = self.frame
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    def start_recording(self, root_id):
        with self.lock:
            if self.recording:
                raise HTTPException(409, "이미 녹화 중입니다.")
            roots = db.rows("SELECT * FROM roots WHERE id=?", (root_id,))
            if not roots:
                raise HTTPException(400, "등록된 저장 폴더를 선택하세요.")
            base = storage.root_path(roots[0])
            if shutil.disk_usage(base).free < 512 * 1024**2:
                raise HTTPException(409, "녹화 시작에는 512MiB 이상 여유 공간이 필요합니다.")
            self.start()
            target = base / "Alter-recordings"
            target.mkdir(exist_ok=True)
            target = target.resolve()
            if not target.is_relative_to(base):
                raise HTTPException(403, "녹화 경로가 허용 폴더 밖에 있습니다.")
            name = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
            self.encoder = subprocess.Popen([
                "ffmpeg", "-v", "error", "-nostdin", "-f", "image2pipe", "-framerate", "10",
                "-vcodec", "mjpeg", "-i", "-", "-an", "-c:v", "libx264", "-threads", "2",
                "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-b:v", "1500k",
                "-g", "20", "-f", "segment", "-segment_time", "120", "-reset_timestamps", "1",
                str(target / (name + "-%03d.mp4"))],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.record_dir = str(target)
            self.recording = True
            self.writer = threading.Thread(target=self.write_recording, daemon=True)
            self.writer.start()

    def write_recording(self):
        try:
            while self.recording or not self.record_queue.empty():
                if not Path(self.record_dir).exists() or shutil.disk_usage(self.record_dir).free < 256 * 1024**2:
                    raise OSError("녹화 드라이브 분리 또는 여유 공간 부족")
                try:
                    frame = self.record_queue.get(timeout=.5)
                except queue.Empty:
                    continue
                self.encoder.stdin.write(frame)
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.recording = False
            try:
                self.encoder.stdin.close()
                self.encoder.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                self.encoder.kill()

    def stop_recording(self):
        self.recording = False
        if hasattr(self, "writer") and self.writer.is_alive():
            self.writer.join(timeout=20)

    def enable_gestures(self, enabled):
        if enabled and self.recognizer is None:
            try:
                import mediapipe as mp
                self.recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(
                    mp.tasks.vision.GestureRecognizerOptions(
                        base_options=mp.tasks.BaseOptions(model_asset_path=str(BASE / "models/gesture_recognizer.task")),
                        running_mode=mp.tasks.vision.RunningMode.IMAGE))
            except Exception as exc:
                raise HTTPException(503, "제스처 모델 준비 실패: " + str(exc))
        if enabled:
            self.start()
        self.gestures = enabled
        self.candidate, self.held_since, self.fired, self.fired_at = None, 0, False, 0

    def detect(self, image):
        try:
            import mediapipe as mp
            import numpy as np
            result = self.recognizer.recognize(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(image.convert("RGB"))))
            top = result.gestures[0][0] if result.gestures else None
            gesture = top.category_name if top and top.score >= .7 else None
            if gesture not in {"Open_Palm", "Closed_Fist", "Victory", "Thumb_Up", "Thumb_Down"}:
                gesture = None
            now = time.monotonic()
            self.last_gesture = {"name": gesture, "score": float(top.score) if top else 0}
            if gesture != self.candidate:
                self.candidate, self.held_since, self.fired = gesture, now, False
            if gesture and not self.fired and now - self.held_since >= 1 and now - self.fired_at >= 3:
                self.fired, self.fired_at = True, now
                mapping = json.loads(db.state("gesture_mappings", "{}")).get(gesture)
                if mapping and mapping.startswith("flow:"):
                    threading.Thread(target=self.run_mapped, args=(mapping[5:],), daemon=True).start()
                elif mapping == "chat":
                    db.set_state("gesture_event", json.dumps({"gesture": gesture, "time": time.time()}))
        except Exception as exc:
            self.error = "제스처 오류: " + type(exc).__name__
            self.gestures = False

    def run_mapped(self, flow_id):
        try:
            flows.execute(flow_id)
        except Exception as exc:
            self.error = str(getattr(exc, "detail", type(exc).__name__))


camera = Camera()
