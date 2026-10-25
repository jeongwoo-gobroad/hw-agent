"""Persistent login policy and single-use, client-bound image challenges."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from fastapi import HTTPException
from . import config,db

DEFAULT={'max_failures':5,'block_minutes':10,'window_minutes':10}


def init():
    with db.connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS login_failures(client TEXT PRIMARY KEY,count INTEGER,started REAL,blocked_until REAL);
        CREATE TABLE IF NOT EXISTS login_challenges(id TEXT PRIMARY KEY,client TEXT,answer TEXT,expires REAL,created REAL);
        CREATE INDEX IF NOT EXISTS login_challenge_client ON login_challenges(client,created);
        """)
        if 'scope' not in {r[1] for r in c.execute('PRAGMA table_info(auth)')}:
            c.execute("ALTER TABLE auth ADD COLUMN scope TEXT DEFAULT 'internal'")


def policy():
    return {**DEFAULT,**json.loads(db.state('login_policy','{}'))}


def scope(request):
    return 'internal' if request.headers.get('x-alter-exposure')=='internal' else 'public'


def cookie_name(request):
    return 'alter_session' if scope(request)=='internal' else 'alter_public_session'


def client_key(ip,exposure):
    return hmac.new(config.SECRET.encode(),(exposure+':'+ip).encode(),hashlib.sha256).hexdigest()


def answer_hash(identifier,answer):
    return hmac.new(config.SECRET.encode(),(identifier+':'+answer.upper().strip()).encode(),hashlib.sha256).hexdigest()


def check_block(c,key,now):
    row=c.execute('SELECT * FROM login_failures WHERE client=?',(key,)).fetchone()
    if row and row['blocked_until']>now:
        seconds=max(1,int(row['blocked_until']-now)+1)
        raise HTTPException(429,f'로그인이 일시 차단됐습니다. 약 {(seconds+59)//60}분 후 다시 시도하세요.',headers={'Retry-After':str(seconds)})
    return row


def challenge(ip):
    from captcha.image import ImageCaptcha
    now=time.time();key=client_key(ip,'public')
    identifier=secrets.token_urlsafe(24)
    answer=''.join(secrets.choice('23456789ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(6))
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');check_block(c,key,now)
        c.execute('DELETE FROM login_failures WHERE started<? AND blocked_until<?',(now-86400,now))
        c.execute('DELETE FROM login_challenges WHERE expires<?',(now,))
        latest=c.execute('SELECT max(created) FROM login_challenges WHERE client=?',(key,)).fetchone()[0]
        if latest and now-latest<1: raise HTTPException(429,'잠시 후 새 보안 문자를 요청하세요.',headers={'Retry-After':'1'})
        c.execute('DELETE FROM login_challenges WHERE client=?',(key,))
        c.execute('INSERT INTO login_challenges VALUES(?,?,?,?,?)',(identifier,key,answer_hash(identifier,answer),now+180,now))
    data=ImageCaptcha(width=260,height=90).generate(answer).getvalue()
    return {'required':True,'id':identifier,'image':'data:image/png;base64,'+base64.b64encode(data).decode(),'expires_in':180}


def verify(username,password,ip,exposure,challenge_id='',answer=''):
    now=time.time();key=client_key(ip,exposure);settings=policy();failure=None
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');row=check_block(c,key,now)
        valid_captcha=exposure=='internal'
        if exposure=='public':
            item=c.execute('SELECT * FROM login_challenges WHERE id=?',(challenge_id,)).fetchone()
            c.execute('DELETE FROM login_challenges WHERE id=?',(challenge_id,))
            valid_captcha=bool(item and item['client']==key and item['expires']>=now and hmac.compare_digest(item['answer'],answer_hash(challenge_id,answer)))
        credentials=(hmac.compare_digest(username.encode(),config.USERNAME.encode()) & hmac.compare_digest(password.encode(),config.PASSWORD.encode()))
        if valid_captcha and credentials:
            c.execute('DELETE FROM login_failures WHERE client=?',(key,))
        else:
            started=row['started'] if row and now-row['started']<settings['window_minutes']*60 and not row['blocked_until'] else now
            count=(row['count'] if row and started==row['started'] else 0)+1
            blocked=now+settings['block_minutes']*60 if count>=settings['max_failures'] else 0
            c.execute('INSERT OR REPLACE INTO login_failures VALUES(?,?,?,?)',(key,count,started,blocked))
            failure=HTTPException(429,f"로그인 실패 {count}회로 {settings['block_minutes']}분 차단됐습니다.",headers={'Retry-After':str(settings['block_minutes']*60)}) if blocked else HTTPException(401,'아이디·비밀번호 또는 보안 문자를 확인하세요.')
    # 예외를 트랜잭션 밖에서 발생시켜 실패 횟수와 일회용 CAPTCHA 소비를 보존한다.
    if failure: raise failure
