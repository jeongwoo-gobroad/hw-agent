"""Verify the public HTTPS boundary from a machine outside the Pi."""
import argparse
import json
import os
from pathlib import Path
import time
import httpx
from dotenv import load_dotenv

parser = argparse.ArgumentParser()
parser.add_argument("url")
args = parser.parse_args()
assert args.url.startswith("https://")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
results = []


def check(name, condition):
    assert condition, name
    results.append(name)


with httpx.Client(base_url=args.url, timeout=30) as client:
    check("HTTPS health", client.get("/health").status_code == 200)
    check("anonymous dashboard redirects", client.get("/").status_code == 303)
    for path in ("/api/search", "/api/camera/stream", "/api/files/1/download"):
        check("anonymous denied " + path, client.get(path).status_code == 401)
    check("invalid OAuth state rejected",
          client.get("/oauth/callback?state=invalid&code=invalid").status_code == 400)
    response = client.post("/api/login", headers={"Origin": args.url}, json={
        "username": os.environ["DASHBOARD_USERNAME"],
        "password": os.environ["DASHBOARD_PASSWORD"],
        "challenge_id":os.getenv("ALTER_CAPTCHA_ID",""),"captcha":os.getenv("ALTER_CAPTCHA_ANSWER","")})
    check("same-origin HTTPS login", response.status_code == 200)
    cookie = response.headers["set-cookie"].lower()
    check("secure HttpOnly strict cookie",
          all(value in cookie for value in ("secure", "httponly", "samesite=strict")))
    check("CSRF required", client.post("/api/index", json={}).status_code == 403)
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    client.headers["Origin"] = args.url
    check("foreign origin rejected", client.post("/api/index", json={},
          headers={"Origin": "https://untrusted.example"}).status_code == 403)
    response = client.get("/api/search", params={"q": "회의", "ext": "txt"})
    check("Korean file search", response.status_code == 200 and bool(response.json()))
    file_id = response.json()[0]["id"]
    response = client.get(f"/api/files/{file_id}/preview")
    check("text preview", response.status_code == 200 and "회의" in response.text)
    before = client.get("/api/camera").json()
    try:
        response = client.post("/api/camera/start", json={})
        check("authenticated camera start", response.status_code == 200)
        with client.stream("GET", "/api/camera/stream") as stream:
            check("MJPEG response", stream.status_code == 200 and
                  "multipart/x-mixed-replace" in stream.headers["content-type"])
            frame = b""
            started = time.monotonic()
            for part in stream.iter_bytes():
                frame += part
                if b"\xff\xd9" in frame or time.monotonic() - started > 15:
                    break
            check("complete JPEG received", b"\xff\xd8" in frame and b"\xff\xd9" in frame)
    finally:
        if not before["running"]:
            client.post("/api/camera/stop", json={}).raise_for_status()
    client.post("/api/logout", json={}).raise_for_status()
    check("logout blocks camera", client.get("/api/camera/stream").status_code == 401)
print(json.dumps({"passed": len(results), "checks": results}, ensure_ascii=False, indent=2))
