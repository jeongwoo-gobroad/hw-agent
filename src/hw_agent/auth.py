import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from fastapi import HTTPException
from . import config, db

attempts = defaultdict(deque)
lock = threading.Lock()


def fingerprint():
    return hmac.new(config.SECRET.encode(), (config.USERNAME + "\0" + config.PASSWORD).encode(), hashlib.sha256).hexdigest()


def login(username, password, ip):
    now = time.time()
    with lock:
        recent = attempts[ip]
        while recent and recent[0] < now - 300:
            recent.popleft()
        if len(recent) >= 8:
            raise HTTPException(429, "5분 후 다시 시도하세요.")
        recent.append(now)
    if not (hmac.compare_digest(username.encode(), config.USERNAME.encode()) &
            hmac.compare_digest(password.encode(), config.PASSWORD.encode())):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다.")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("DELETE FROM auth WHERE expires < ?", (now,))
        conn.execute("INSERT INTO auth VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), csrf, now + 43200, fingerprint()))
    return token, csrf


def session(request):
    token = request.cookies.get("alter_session", "")
    result = db.rows("SELECT * FROM auth WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))
    if not result or result[0]["expires"] < time.time() or result[0]["fingerprint"] != fingerprint():
        return None
    return result[0]
