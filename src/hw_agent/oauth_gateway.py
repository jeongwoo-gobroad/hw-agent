"""Public callback surface. This app exposes no dashboard or device API."""
from contextlib import asynccontextmanager
import html
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from . import db, oauth


@asynccontextmanager
async def lifespan(app):
    # Do not call db.init here: it would mark live Flow runs interrupted.
    oauth.initialize()
    yield


app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)


@app.middleware("http")
async def headers(request, call_next):
    allowed = {"127.0.0.1","localhost",urlparse(oauth.REDIRECT_URI).hostname}
    if request.url.hostname not in allowed:
        return HTMLResponse("Unknown callback host",status_code=400)
    response = await call_next(request)
    response.headers["Cache-Control"]="no-store"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Content-Security-Policy"]="default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get("/health")
def health():
    return {"status":"ok"}


@app.get("/oauth/start")
def start(ticket: str):
    url,binding=oauth.start(ticket)
    response=RedirectResponse(url,303)
    response.set_cookie("alter_oauth_binding",binding,max_age=600,httponly=True,secure=True,
                        samesite="lax",path="/oauth")
    return response


@app.get("/oauth/callback")
def callback(request: Request, state: str="", code: str|None=None, error: str|None=None):
    connected=oauth.finish(state,request.cookies.get("alter_oauth_binding",""),code,error)
    title="SmartThings 연결 완료" if connected else "SmartThings 연결이 취소되었습니다"
    message="대시보드에서 기기 목록을 불러올 수 있습니다." if connected else "대시보드에서 다시 연결할 수 있습니다."
    response=HTMLResponse(f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{title}</title>'
                          f'<h1>{title}</h1><p>{message}</p><a href="{html.escape(oauth.RETURN_URL,quote=True)}">Alter 대시보드로 돌아가기</a></html>')
    response.delete_cookie("alter_oauth_binding",path="/oauth",secure=True,httponly=True,samesite="lax")
    return response
