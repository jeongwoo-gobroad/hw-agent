"""SmartThings authorization code flow and encrypted, rotating token storage."""
from contextlib import contextmanager
import base64
import fcntl
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse
from authlib.integrations.httpx_client import OAuth2Client
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from . import auth, config, db

SCOPES = "r:locations:* r:devices:* x:devices:*"
OAUTH_BASE = os.getenv("SMARTTHINGS_OAUTH_BASE", "https://api.smartthings.com/oauth").rstrip("/")
CLIENT_ID = os.getenv("SMARTTHINGS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SMARTTHINGS_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("SMARTTHINGS_REDIRECT_URI", "")
RETURN_URL = os.getenv("DASHBOARD_URL", "http://192.168.0.44:8080")
CIPHER = Fernet(base64.urlsafe_b64encode(hashlib.sha256(
    b"alter-smartthings-token-v1\0" + config.SECRET.encode()).digest()))


def initialize():
    with db.connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS oauth_states(
            ticket TEXT PRIMARY KEY,state TEXT UNIQUE,binding TEXT,auth_token TEXT,
            expires REAL,phase TEXT)""")


@contextmanager
def token_lock():
    # 웹 서버와 콜백 서버가 같은 갱신 토큰을 동시에 쓰지 않도록 잠근다.
    with (config.DATA / "smartthings-token.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def load_tokens():
    value = db.state("st_tokens")
    if not value:
        return None
    try:
        return json.loads(CIPHER.decrypt(value.encode()))
    except (InvalidToken, ValueError):
        raise HTTPException(409, "저장된 SmartThings 인증을 읽을 수 없습니다. 다시 연결하세요.")


def save_tokens(value):
    if not value.get("access_token") or not value.get("refresh_token"):
        raise ValueError("Incomplete token response")
    if not value.get("expires_at"):
        value["expires_at"] = time.time() + int(value.get("expires_in", 86400))
    encrypted = CIPHER.encrypt(json.dumps(value).encode()).decode()
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO state VALUES('st_tokens',?)", (encrypted,))
        conn.execute("INSERT OR REPLACE INTO state VALUES('st_oauth_error','')")


def client():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(409, "SmartThings OAuth 앱 등록이 필요합니다.")
    return OAuth2Client(CLIENT_ID, CLIENT_SECRET, scope=SCOPES,
                        redirect_uri=REDIRECT_URI, token_endpoint_auth_method="client_secret_basic", timeout=20)


def validate_config():
    parsed = urlparse(REDIRECT_URI)
    if not CLIENT_ID or not CLIENT_SECRET or parsed.scheme != "https" or parsed.path != "/oauth/callback":
        raise HTTPException(409, "OAuth 클라이언트와 HTTPS 콜백 주소를 먼저 등록하세요.")
    return parsed


def connection_status():
    try:
        tokens = load_tokens()
        error = db.state("st_oauth_error", "")
    except HTTPException:
        tokens, error = None, "reauthorization_required"
    return {"configured":bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI),
            "connected":bool(tokens), "expires_at":tokens.get("expires_at") if tokens else None,
            "callback":REDIRECT_URI or None, "scopes":SCOPES, "error":error,
            "pat_configured":bool(os.getenv("SMARTTHINGS_PAT"))}


def begin(session):
    parsed = validate_config()
    ticket = secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("DELETE FROM oauth_states WHERE expires<?", (time.time(),))
        conn.execute("INSERT INTO oauth_states VALUES(?,?,?,?,?,?)",
                     (digest(ticket),None,None,session["token"],time.time()+600,"created"))
    return f"{parsed.scheme}://{parsed.netloc}/oauth/start?{urlencode({'ticket':ticket})}"


def valid_session(row):
    sessions = db.rows("SELECT * FROM auth WHERE token=?", (row["auth_token"],))
    return bool(sessions and sessions[0]["expires"] > time.time()
                and secrets.compare_digest(sessions[0]["fingerprint"], auth.fingerprint()))


def start(ticket):
    rows = db.rows("SELECT * FROM oauth_states WHERE ticket=?", (digest(ticket),))
    if not rows or rows[0]["phase"]!="created" or rows[0]["expires"]<time.time() or not valid_session(rows[0]):
        raise HTTPException(400, "로그인 연결이 만료되었습니다. 대시보드에서 다시 시작하세요.")
    state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connect() as conn:
        updated = conn.execute("UPDATE oauth_states SET state=?,binding=?,phase='started' WHERE ticket=? AND phase='created'",
                               (digest(state),digest(binding),digest(ticket)))
        if updated.rowcount != 1:
            raise HTTPException(400, "이미 사용한 로그인 연결입니다.")
    with client() as oauth_client:
        url, _ = oauth_client.create_authorization_url(OAUTH_BASE+"/authorize",state=state)
    return url, binding


def finish(state, binding, code=None, error=None):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM oauth_states WHERE state=?", (digest(state),)).fetchone()
        if (not row or row["phase"]!="started" or row["expires"]<time.time()
                or not secrets.compare_digest(row["binding"],digest(binding)) or not valid_session(row)):
            raise HTTPException(400, "OAuth 상태 검증 실패. 대시보드에서 다시 연결하세요.")
        updated=conn.execute("UPDATE oauth_states SET phase='consumed' WHERE ticket=? AND phase='started'", (row["ticket"],))
        if updated.rowcount != 1:
            raise HTTPException(400,"이미 사용한 OAuth 상태입니다.")
    if error:
        db.set_state("st_oauth_error", "authorization_denied")
        return False
    if not code:
        raise HTTPException(400, "인가 코드가 없습니다.")
    try:
        with token_lock(), client() as oauth_client:
            tokens = oauth_client.fetch_token(OAUTH_BASE+"/token",code=code,
                                              grant_type="authorization_code",client_id=CLIENT_ID)
            save_tokens(dict(tokens))
    except HTTPException:
        raise
    except Exception:
        db.set_state("st_oauth_error","token_exchange_failed")
        raise HTTPException(502,"SmartThings 토큰 교환에 실패했습니다. 다시 연결하세요.")
    return True


def access_token():
    with token_lock():
        tokens = load_tokens()
        if not tokens:
            raise HTTPException(409,"SmartThings 연결이 필요합니다.")
        if float(tokens.get("expires_at",0)) > time.time()+300:
            return tokens["access_token"]
        try:
            with client() as oauth_client:
                refreshed = dict(oauth_client.refresh_token(OAUTH_BASE+"/token",
                                  refresh_token=tokens["refresh_token"],client_id=CLIENT_ID))
                for key in ("installed_app_id","location_id"):
                    if key not in refreshed and key in tokens:
                        refreshed[key]=tokens[key]
                save_tokens(refreshed)
                return refreshed["access_token"]
        except Exception:
            db.set_state("st_oauth_error","refresh_failed")
            raise HTTPException(409,"SmartThings 인증 갱신에 실패했습니다. 다시 연결하세요.")


def invalidate_access():
    with token_lock():
        tokens=load_tokens()
        if tokens:
            tokens["expires_at"]=1
            save_tokens(tokens)


def disconnect():
    with token_lock(), db.connect() as conn:
        conn.execute("DELETE FROM state WHERE key IN ('st_tokens','st_access','st_refresh','st_expires','st_oauth_error')")
        conn.execute("DELETE FROM oauth_states")


def refresh_worker(stop):
    while not stop.wait(60):
        try:
            if load_tokens():
                access_token()
        except HTTPException:
            pass
