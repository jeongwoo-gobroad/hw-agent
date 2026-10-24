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
from .motion import motion
from PIL import Image


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
        self.orientation_lock = threading.RLock()
        self.orientation = {"rotation": 0, "mirror_horizontal": False, "mirror_vertical": False}
        self.frame_size = None

    def restore_orientation(self):
        saved = json.loads(db.state("camera_orientation", "{}"))
        self.set_orientation(**{**self.orientation, **saved})

    def set_orientation(self, rotation=0, mirror_horizontal=False, mirror_vertical=False):
        if type(rotation) is not int or rotation not in {0, 90, 180, 270} or any(
                type(v) is not bool for v in (mirror_horizontal, mirror_vertical)):
            raise HTTPException(400, "회전은 0/90/180/270도, 반전은 켜기/끄기로 지정하세요.")
        with self.lock, self.orientation_lock:
            if self.recording:
                raise HTTPException(409, "녹화를 중지한 뒤 카메라 방향을 변경하세요.")
            settings = dict(rotation=rotation, mirror_horizontal=mirror_horizontal, mirror_vertical=mirror_vertical)
            db.set_state("camera_orientation", json.dumps(settings))
            self.orientation = settings
            self.frame = None
            # 방향을 바꾸기 전 프레임의 유지 시간은 새 방향에 이어 붙이지 않는다.
            with motion.lock:
                for gate in motion.gates.values():
                    gate.since = gate.absent_since = None
                    # 이미 실행한 상태와 쿨다운은 유지하여 회전만으로 재실행되지 않게 한다.
                motion.observed = {}
            self.candidate, self.held_since = None, 0
        return self.orientation.copy()

    def orient(self, image):
        rotation = self.orientation["rotation"]
        operations = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}
        if rotation:
            image = image.transpose(operations[rotation])
        if self.orientation["mirror_horizontal"]:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if self.orientation["mirror_vertical"]:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        return image

    def state(self):
        return {"running": self.running, "recording": self.recording,
                "gestures": self.gestures, "error": self.error,
                "last_gesture": self.last_gesture, "record_dir": self.record_dir,
                "orientation": self.orientation.copy(), "frame_size": self.frame_size,
                "mappings": json.loads(db.state("gesture_mappings", "{}"))}

    def start(self):
        with self.lock:
            if self.running:
                return
            if hasattr(self, "capture_thread") and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=5)
                if self.capture_thread.is_alive():
                    raise HTTPException(409, "카메라 종료 중입니다. 잠시 후 다시 켜세요.")
            try:
                from picamera2 import Picamera2
                self.device = Picamera2()
                self.device.configure(self.device.create_video_configuration(
                    main={"size": (640, 480), "format": "RGB888"}, controls={"FrameRate": 10}))
                self.device.start()
                self.running = True
                self.error = None
                self.capture_thread = threading.Thread(target=self.capture, daemon=True)
                self.capture_thread.start()
            except Exception as exc:
                self.error = type(exc).__name__ + ": " + str(exc)
                raise HTTPException(503, self.error)

    def stop(self, persist=True):
        self.stop_recording()
        self.gestures = False
        self.running = False
        if motion.enabled and persist:
            motion.configure(False, motion.mappings)
        if hasattr(self, "capture_thread") and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5)

    def capture(self):
        last_detect = 0
        try:
            while self.running:
                image = self.device.capture_image("main")
                with self.orientation_lock:
                    image = self.orient(image)
                    self.frame_size = image.size
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
                    if (motion.enabled or self.gestures) and time.monotonic() - last_detect > .3:
                        last_detect = time.monotonic()
                        if motion.enabled:
                            motion.detect(image)
                        else:
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
                self.recognizer = motion.load_gesture()
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
