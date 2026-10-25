import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException
from . import config, db, login_security

def fingerprint():
    return hmac.new(config.SECRET.encode(), (config.USERNAME + "\0" + config.PASSWORD).encode(), hashlib.sha256).hexdigest()


def login(username, password, ip, exposure='internal', challenge_id='', answer=''):
    login_security.init()
    login_security.verify(username,password,ip,exposure,challenge_id,answer)
    now=time.time()
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("DELETE FROM auth WHERE expires < ?", (now,))
        conn.execute("INSERT INTO auth(token,csrf,expires,fingerprint,scope) VALUES(?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), csrf, now + 43200, fingerprint(),exposure))
    return token, csrf


def session(request):
    token = request.cookies.get(login_security.cookie_name(request), "")
    result = db.rows("SELECT * FROM auth WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))
    if not result or result[0]["scope"]!=login_security.scope(request) or result[0]["expires"] < time.time() or result[0]["fingerprint"] != fingerprint():
        return None
    return result[0]
