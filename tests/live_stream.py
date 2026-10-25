"""Measure real token delivery through the public HTTPS endpoint."""
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
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
with httpx.Client(base_url=args.url, timeout=240) as client:
    response = client.post("/api/login", json={
        "username": os.environ["DASHBOARD_USERNAME"],
        "password": os.environ["DASHBOARD_PASSWORD"],
        "challenge_id":os.getenv("ALTER_CAPTCHA_ID",""),"captcha":os.getenv("ALTER_CAPTCHA_ANSWER","")})
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    response = client.post("/api/sessions", json={"title": "스트리밍 검증"})
    response.raise_for_status()
    identifier = response.json()["id"]
    started = time.monotonic()
    updates = []
    result = None
    with client.stream("POST", f"/api/sessions/{identifier}/messages/stream",
                       json={"message": "너는 어떤 일을 도와줄 수 있어? 한국어로 세 문장으로 소개해줘."}) as stream:
        stream.raise_for_status()
        assert stream.headers["content-type"].startswith("text/event-stream")
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            assert event["type"] != "error", event
            if event["type"] == "delta":
                updates.append({"seconds": round(time.monotonic()-started, 2),
                                "characters": len(event["text"])})
            if event["type"] == "result":
                result = event["result"]
                completed = round(time.monotonic()-started, 2)
    assert len(updates) >= 2, updates
    assert result and result["mode"] == "local_llm"
    assert updates[0]["seconds"] < completed
    messages = client.get(f"/api/sessions/{identifier}").json()
    assert len(messages) == 2
    client.post("/api/logout", json={}).raise_for_status()
print(json.dumps({"delta_events": len(updates), "first_delta_seconds": updates[0]["seconds"],
                  "completed_seconds": completed, "persisted_messages": len(messages),
                  "mode": result["mode"]}, indent=2))
