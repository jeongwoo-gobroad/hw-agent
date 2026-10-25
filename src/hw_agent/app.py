from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
import uuid
import queue
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from . import auth, chat, config, db, flows, indexing, preview, smartthings, storage, oauth
from .camera import camera
from .motion import motion
from . import oauth_gateway, voice
from . import photos, resources
from . import file_browser, inventory, login_security


@asynccontextmanager
async def lifespan(app):
    db.init()
    photos.init()
    login_security.init()
    camera.restore_orientation()
    oauth.initialize()
    indexing.stop_event.clear()
    worker = threading.Thread(target=indexing.worker, daemon=True)
    worker.start()
    threading.Thread(target=oauth.refresh_worker,args=(indexing.stop_event,),daemon=True).start()
    saved_motion = json.loads(db.state("motion_config", "{}"))
    if not saved_motion.get("enabled"):
        motion.configure(False, saved_motion.get("mappings", {}), saved_motion.get("rules", {}))
    if saved_motion.get("enabled"):
        try:
            camera.start()
            motion.configure(True, saved_motion.get("mappings", {}), saved_motion.get("rules", {}))
        except Exception as exc:
            motion.error = str(getattr(exc, "detail", type(exc).__name__))
    yield
    indexing.stop_event.set()
    # 종료 시 저장된 상시 감지 설정은 유지한다.
    camera.stop(persist=False)
    motion.close()


app = FastAPI(title="Alter", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(photos.router)
app.include_router(file_browser.router)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=__import__("os").getenv(
    "ALLOWED_HOSTS", "127.0.0.1,localhost,192.168.0.44,geb-v1,geb-v1.local").split(","))
WEB = Path(__file__).parent / "web"
app.add_api_route("/oauth/start", oauth_gateway.start, methods=["GET"])
app.add_api_route("/oauth/callback", oauth_gateway.callback, methods=["GET"])


@app.middleware("http")
async def security(request: Request, call_next):
    path = request.url.path
    public = (path in {"/login", "/api/login", "/api/login/challenge", "/health"} or path.startswith("/static/")
              or (path in {"/oauth/start", "/oauth/callback"} and request.method == "GET"))
    current = auth.session(request) if not public else None
    if not public and current is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
        return RedirectResponse("/login?next=/panel" if path == "/panel" else "/login", 303)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Origin mismatch"}, status_code=403)
        if path != "/api/login" and (current is None or not secrets.compare_digest(request.headers.get("x-csrf-token", ""), current["csrf"])):
            return JSONResponse({"detail": "CSRF token required"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        if length > (2000100 if path == "/api/voice/transcribe" else 65536):
            return JSONResponse({"detail": "요청이 너무 큽니다."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; media-src 'self' blob:; frame-src 'self'; connect-src 'self'; frame-ancestors 'self'"
    return response


@app.exception_handler(FileNotFoundError)
async def missing(request, exc):
    return JSONResponse({"detail": "파일 또는 드라이브가 없습니다."}, status_code=404)


@app.exception_handler(PermissionError)
async def permission_error(request, exc):
    return JSONResponse({"detail": "해당 파일 또는 폴더의 접근 권한이 없습니다."}, status_code=403)

class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)
    challenge_id: str = Field(default="",max_length=100)
    captcha: str = Field(default="",max_length=20)


@app.post("/api/login")
def login(body: Login, request: Request):
    token, csrf = auth.login(body.username, body.password, request.client.host, login_security.scope(request),body.challenge_id,body.captcha)
    response = JSONResponse({"csrf": csrf})
    response.set_cookie(login_security.cookie_name(request), token, httponly=True,
                        secure=config.SECURE_COOKIE or request.url.scheme == "https",
                        samesite="strict", max_age=43200)
    return response


@app.post("/api/logout")
def logout(request: Request):
    with db.connect() as conn:
        conn.execute("DELETE FROM auth WHERE token=?", (hashlib.sha256(request.cookies.get(login_security.cookie_name(request), "").encode()).hexdigest(),))
    response = JSONResponse({"ok": True})
    response.delete_cookie(login_security.cookie_name(request))
    return response


@app.get('/api/login/challenge')
def login_challenge(request: Request):
    if login_security.scope(request)=='internal': return {'required':False}
    return login_security.challenge(request.client.host)


class LoginPolicy(BaseModel):
    max_failures: int = Field(ge=1,le=20,strict=True)
    block_minutes: int = Field(ge=1,le=1440,strict=True)
    window_minutes: int = Field(ge=1,le=60,strict=True)


@app.get('/api/settings/security')
def security_settings():
    return login_security.policy()


@app.put('/api/settings/security')
def set_security_settings(body: LoginPolicy):
    db.set_state('login_policy',json.dumps(body.model_dump()))
    return login_security.policy()


@app.get("/api/me")
def me(request: Request):
    return {"username": config.USERNAME, "csrf": auth.session(request)["csrf"]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login")
def login_page():
    return FileResponse(WEB / "login.html", media_type="text/html")


@app.get("/")
@app.get("/panel")
def home():
    return FileResponse(WEB / "index.html", media_type="text/html")


@app.get("/api/status")
def status():
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapFree"}:
            memory[key] = int(value.split()[0]) * 1024
    return {"memory": memory, "index": indexing.status, "photos": photos.status(), "resources": resources.snapshot(),
            "indexed_files": db.rows("SELECT count(*) AS n FROM files")[0]["n"],
            "last_scan": db.state("last_scan"), "generation_at": db.state("generation_at"),
            "camera": camera.state(), "gesture_event": json.loads(db.state("gesture_event", "null")),
            "smartthings_configured": bool(oauth.connection_status()["connected"] or oauth.connection_status()["pat_configured"])}


@app.get("/api/devices")
def devices():
    return storage.devices()


class DiskAction(BaseModel):
    device: str = Field(max_length=100)
    action: str = Field(pattern="^(mount|unmount)$")


@app.post("/api/devices/action")
def disk_action(body: DiskAction):
    if camera.recording or indexing.status["running"]:
        raise HTTPException(409, "녹화 또는 색인 종료 후 시도하세요.")
    if not any(d["path"] == body.device for d in storage.devices()):
        raise HTTPException(403, "외장 드라이브만 관리할 수 있습니다.")
    result = subprocess.run(["sudo", "-n", "/usr/local/sbin/alter-disk"],
                            input=body.model_dump_json(), text=True, capture_output=True, timeout=35)
    if result.returncode:
        raise HTTPException(409, result.stderr[-500:])
    if body.action == "mount":
        storage.restore_shares()
        for root in db.rows("SELECT * FROM roots"):
            try:
                storage.root_path(root)
            except HTTPException:
                pass
    return {"message": result.stdout.strip()}


@app.get("/api/folders")
def folders(path: str):
    return storage.folders(path)


@app.get("/api/roots")
def roots():
    for root in db.rows("SELECT * FROM roots"):
        try:
            storage.root_path(root)
        except (HTTPException, FileNotFoundError):
            pass
    return db.rows("SELECT * FROM roots")


class Root(BaseModel):
    path: str = Field(max_length=4096)


@app.post("/api/roots")
def add_root(body: Root):
    return storage.add_root(body.path)


@app.delete("/api/roots/{identifier}")
def delete_root(identifier: int):
    roots = db.rows("SELECT * FROM roots WHERE id=?", (identifier,))
    if camera.recording and roots and camera.record_dir and Path(camera.record_dir).is_relative_to(roots[0]["path"]):
        raise HTTPException(409, "이 폴더에 녹화 중입니다. 녹화 종료 후 해제하세요.")
    with db.connect() as conn:
        conn.execute("DELETE FROM search WHERE rowid IN (SELECT id FROM files WHERE root=?)", (identifier,))
        conn.execute("DELETE FROM files WHERE root=?", (identifier,))
        conn.execute("DELETE FROM roots WHERE id=?", (identifier,))
        conn.execute("DELETE FROM staging WHERE root=?", (identifier,))
        inventory.drop(conn,'files',identifier)
    return {"ok": True}


@app.post("/api/index")
def start_index():
    threading.Thread(target=indexing.scan, daemon=True).start()
    return {"status": "queued"}


@app.get("/api/search")
def search(q: str = "", ext: str = "", root: int = 0, after: float | None = None,
           before: float | None = None, date_field: str = "modified", offset: int = 0, rerank: bool = False):
    return indexing.search(q[:500], ext[:20], root, after, before, date_field, offset, rerank)


@app.get("/api/files/{identifier}/download")
def download(identifier: int):
    path, record = storage.safe_file(identifier)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/files/{identifier}/preview")
def file_preview(identifier: int):
    path, record = storage.safe_file(identifier)
    target, media_type = preview.preview(path, record)
    return FileResponse(target, media_type=media_type)


class Share(BaseModel):
    path: str
    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    readonly: bool = True


@app.get("/api/shares")
def shares():
    return list(json.loads(db.state("shares", "{}")).values())


@app.post("/api/shares")
def share(body: Share):
    return storage.smb("set", body.path, body.name, body.readonly)


@app.delete("/api/shares/{name}")
def unshare(name: str, path: str = ""):
    return storage.smb("remove", path, name)


@app.get("/api/sessions")
def sessions():
    return db.rows("SELECT * FROM sessions ORDER BY created DESC")


class Title(BaseModel):
    title: str = Field(default="새 대화", min_length=1, max_length=120)


@app.post("/api/sessions")
def new_session(body: Title):
    return chat.create(body.title)


@app.patch("/api/sessions/{identifier}")
def rename_session(identifier: str, body: Title):
    with db.connect() as conn:
        conn.execute("UPDATE sessions SET title=? WHERE id=?", (body.title, identifier))
    return {"ok": True}


@app.get("/api/sessions/{identifier}")
def messages(identifier: str):
    return db.rows("SELECT * FROM messages WHERE session=? ORDER BY id", (identifier,))


@app.delete("/api/sessions/{identifier}")
def delete_session(identifier: str):
    with db.connect() as conn:
        conn.execute("DELETE FROM messages WHERE session=?", (identifier,))
        conn.execute("DELETE FROM sessions WHERE id=?", (identifier,))
    return {"ok": True}


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@app.post("/api/sessions/{identifier}/messages")
def message(identifier: str, body: Message):
    return chat.respond(identifier, body.message)


@app.post("/api/sessions/{identifier}/messages/stream")
def message_stream(identifier: str, body: Message, request: Request):
    if not db.rows("SELECT id FROM sessions WHERE id=?", (identifier,)):
        raise HTTPException(404, "대화를 찾을 수 없습니다.")
    events = queue.Queue()
    cancelled = threading.Event()

    def generate():
        try:
            result = chat.respond(identifier, body.message, events.put, cancelled)
            events.put({"type": "result", "result": result})
        except HTTPException as exc:
            events.put({"type": "error", "message": exc.detail})
        except Exception:
            events.put({"type": "error", "message": "응답을 생성하지 못했습니다. 다시 시도하세요."})
        finally:
            events.put(None)

    def stream():
        threading.Thread(target=generate, daemon=True).start()
        try:
            yield 'data: {"type":"status","text":"요청을 읽고 있습니다…"}\n\n'
            while True:
                if auth.session(request) is None:
                    break
                try:
                    event = events.get(timeout=2)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield "data: " + json.dumps(event, ensure_ascii=True) + "\n\n"
        finally:
            cancelled.set()
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})


@app.get("/api/smartthings/devices")
def st_devices():
    return smartthings.devices()


@app.get("/api/smartthings/connection")
def st_connection():
    return oauth.connection_status()


@app.post("/api/smartthings/oauth/start")
def oauth_start(request: Request):
    return {"url":oauth.begin(auth.session(request))}


@app.delete("/api/smartthings/oauth")
def oauth_disconnect():
    oauth.disconnect()
    return {"message":"이 장치의 OAuth 연결을 해제했습니다. 삼성 계정의 앱 권한은 SmartThings에서 별도로 철회할 수 있습니다."}


@app.get("/api/smartthings/devices/{identifier}/status")
def st_status(identifier: uuid.UUID):
    return smartthings.request("GET", f"devices/{identifier}/status")


class Command(BaseModel):
    device_id: uuid.UUID
    capability: str
    command: str
    component: str = "main"
    arguments: list = Field(default_factory=list, max_length=5)


@app.post("/api/smartthings/command")
def st_command(body: Command):
    return smartthings.command(str(body.device_id), body.capability, body.command, body.component, body.arguments)


@app.get("/api/flows")
def list_flows():
    return [{**r, "steps": json.loads(r["steps"])} for r in db.rows("SELECT * FROM flows")]


class Flow(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    steps: list[dict] = Field(max_length=20)


@app.post("/api/flows")
def save_flow(body: Flow):
    steps = flows.validate(body.steps)
    identifier = uuid.uuid4().hex
    with db.connect() as conn:
        conn.execute("INSERT INTO flows VALUES(?,?,?)", (identifier, body.name, json.dumps(steps)))
    return {"id": identifier}


@app.put("/api/flows/{identifier}")
def edit_flow(identifier: str, body: Flow):
    steps = flows.validate(body.steps)
    with db.connect() as conn:
        conn.execute("UPDATE flows SET name=?,steps=? WHERE id=?", (body.name, json.dumps(steps), identifier))
    return {"ok": True}


@app.delete("/api/flows/{identifier}")
def remove_flow(identifier: str):
    if identifier in flows.active:
        raise HTTPException(409, "실행 중인 Flow입니다.")
    with db.connect() as conn:
        conn.execute("DELETE FROM flows WHERE id=?", (identifier,))
    return {"ok": True}


class Run(BaseModel):
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)


@app.post("/api/flows/{identifier}/run")
def run_flow(identifier: str, body: Run):
    return flows.execute(identifier, str(body.request_id))


@app.get("/api/runs")
def runs():
    return db.rows("SELECT * FROM runs ORDER BY created DESC LIMIT 50")


class MotionSettings(BaseModel):
    enabled: bool
    mappings: dict[str, str] = Field(default_factory=dict)
    rules: dict[str, dict] = Field(default_factory=dict)


@app.get("/api/motion")
def motion_status():
    return {**motion.state(), "camera_running": camera.running}


@app.post("/api/motion")
def motion_settings(body: MotionSettings):
    motion.configure(body.enabled, body.mappings, body.rules)
    if body.enabled:
        try:
            camera.start()
            camera.gestures = False
        except Exception:
            motion.configure(False, body.mappings)
            raise
    return motion_status()


@app.get("/api/camera")
def camera_status():
    return camera.state()


class CameraOrientation(BaseModel):
    rotation: int = Field(strict=True)
    mirror_horizontal: bool = Field(default=False, strict=True)
    mirror_vertical: bool = Field(default=False, strict=True)


@app.post("/api/camera/orientation")
def camera_orientation(body: CameraOrientation):
    camera.set_orientation(**body.model_dump())
    return camera.state()


@app.post("/api/camera/start")
def camera_start():
    camera.start()
    return camera.state()


@app.post("/api/camera/stop")
def camera_stop():
    camera.stop()
    return camera.state()


@app.get("/api/camera/stream")
def camera_stream(request: Request):
    if not camera.running:
        raise HTTPException(409, "카메라를 먼저 켜세요.")
    def authenticated_stream():
        checked_at = 0
        for frame in camera.stream():
            if time.monotonic() - checked_at > 2:
                if auth.session(request) is None:
                    return
                checked_at = time.monotonic()
            yield frame
    return StreamingResponse(authenticated_stream(), media_type="multipart/x-mixed-replace; boundary=frame")


class Recording(BaseModel):
    root_id: int


@app.post("/api/camera/record")
def record_start(body: Recording):
    camera.start_recording(body.root_id)
    return camera.state()


@app.post("/api/camera/record/stop")
def record_stop():
    camera.stop_recording()
    return camera.state()


class Gestures(BaseModel):
    enabled: bool
    mappings: dict[str, str] = Field(default_factory=dict)


@app.post("/api/gestures")
def gestures(body: Gestures):
    allowed = {"Open_Palm", "Closed_Fist", "Victory", "Thumb_Up", "Thumb_Down"}
    for key, value in body.mappings.items():
        if key not in allowed or (value and value != "chat" and not value.startswith("flow:")):
            raise HTTPException(400, "잘못된 제스처 매핑")
    db.set_state("gesture_mappings", json.dumps(body.mappings))
    camera.enable_gestures(body.enabled)
    return camera.state()


app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


class VoiceAudio(BaseModel):
    audio: str = Field(min_length=1, max_length=2000000)


@app.get("/api/voice")
def voice_status():
    return voice.status()


@app.post("/api/voice/transcribe")
def voice_transcribe(body: VoiceAudio):
    return voice.transcribe(body.audio)
