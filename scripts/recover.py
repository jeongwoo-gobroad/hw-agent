"""Recover saved resources and verify readiness without changing credentials."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
from fastapi import HTTPException
from tqdm import tqdm
from hw_agent import config, db, smartthings, storage


def wait_for(check, seconds=120):
    deadline = time.monotonic() + seconds
    while True:
        try:
            value = check()
            if value:
                return value
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("준비 시간 초과. 네트워크와 서비스 상태를 확인하세요.")
        time.sleep(3)


def healthy(url, headers=None):
    response = httpx.get(url, headers=headers, timeout=5)
    return response.status_code == 200


def tunnel():
    response = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=5)
    response.raise_for_status()
    expected = os.getenv("DASHBOARD_URL", "").rstrip("/")
    urls = [item["public_url"] for item in response.json()["tunnels"]
            if item["public_url"].startswith("https://")]
    if expected.startswith("https://") and expected not in urls:
        return None
    url = expected if expected in urls else next(iter(urls), None)
    return url if url and healthy(url + "/health") else None


def restore_storage():
    with db.connect() as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("데이터베이스 검사 실패. 자동 초기화하지 않습니다. 백업 복구가 필요합니다.")
        registered = {row[0] for row in connection.execute("SELECT uuid FROM roots")}
    registered.update(share["uuid"] for share in json.loads(db.state("shares", "{}")).values())
    present = set()
    listing = storage.devices()
    for identifier in registered:
        device = storage.device_for_uuid(identifier, listing)
        if not device:
            continue
        present.add(device["uuid"])
        if not device["mount"]:
            result = subprocess.run(
                ["sudo", "-n", "/usr/local/sbin/alter-disk"],
                input=json.dumps({"action": "mount", "device": device["path"]}),
                capture_output=True, text=True, timeout=40)
            if result.returncode:
                raise RuntimeError("등록 드라이브 마운트 실패. 디스크 상태를 확인하세요.")
    storage.restore_shares()
    return {"registered": len(registered), "missing": len(registered - present)}


def check_smartthings():
    try:
        devices = smartthings.devices()
    except HTTPException as error:
        if error.status_code != 401:
            raise
        # 만료된 액세스 토큰을 무효화한 뒤, 저장된 refresh token으로 한 번 갱신한다.
        devices = smartthings.devices()
    return len(devices)


def main():
    lock = (config.DATA / "startup.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("다른 시작/부팅 복구가 실행 중입니다. 잠시 후 다시 실행하세요.")
        return 1
    status = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}}
    code = 0
    steps = [
        ("웹 서버", lambda: wait_for(lambda: healthy("http://127.0.0.1:8080/health"))),
        ("언어 모델", lambda: wait_for(lambda: healthy(config.LLM_URL + "/health", config.LLM_HEADERS))),
        ("등록 드라이브·공유", restore_storage),
        ("ngrok HTTPS", lambda: wait_for(tunnel, 60)),
        ("SmartThings", check_smartthings),
    ]
    for name, check in tqdm(steps, desc="Alter 준비", unit="단계", disable=not sys.stderr.isatty()):
        try:
            result = check()
            status["checks"][name] = {"ok": True, "result": result}
            suffix = ""
            if name == "ngrok HTTPS":
                suffix = " · " + result
            elif name == "SmartThings":
                suffix = f" · 기기 {result}개 연결"
            elif name == "등록 드라이브·공유" and result["missing"]:
                suffix = f" · 연결되지 않은 드라이브 {result['missing']}개"
            print(name + ": 준비 완료" + suffix, flush=True)
        except HTTPException as error:
            needs_login = error.status_code in {401, 403, 409}
            message = ("삼성 계정 재연결이 필요합니다. 대시보드의 스마트홈에서 로그인하세요."
                       if needs_login else "SmartThings 네트워크/API 연결을 확인하세요.")
            status["checks"][name] = {"ok": False, "message": message}
            code = max(code, 2) if needs_login and code != 1 else 1
            print(name + ": " + message, flush=True)
        except Exception as error:
            message = str(error) if isinstance(error, RuntimeError) else "준비 실패. 서비스 상태를 확인하세요."
            status["checks"][name] = {"ok": False, "message": message}
            code = 1
            print(name + ": " + message, flush=True)
    status["exit_code"] = code
    temporary = config.DATA / "startup-status.json.tmp"
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2))
    temporary.replace(config.DATA / "startup-status.json")
    print("내부 대시보드: http://192.168.0.44:8080/", flush=True)
    print("준비 완료." if code == 0 else "일부 항목에 확인이 필요합니다.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
