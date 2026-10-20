import os
import threading
import time
import httpx
from fastapi import HTTPException
from . import db, oauth

lock = threading.Lock()


def token():
    if oauth.load_tokens():
        return oauth.access_token()
    pat = os.getenv("SMARTTHINGS_PAT", "")
    if pat:
        return pat
    raise HTTPException(409, "SmartThings에서 삼성 계정을 연결하세요.")


def request(method, path, data=None):
    try:
        response = httpx.request(method, "https://api.smartthings.com/v1/" + path,
                                 headers={"Authorization": "Bearer " + token()}, json=data, timeout=20)
    except httpx.HTTPError:
        raise HTTPException(502, "SmartThings 연결 실패")
    if response.status_code == 401:
        db.set_state("st_expires", "0")
        oauth.invalidate_access()
        raise HTTPException(401, "SmartThings 인증 만료: PAT 교체 또는 OAuth 재인증이 필요합니다.")
    if response.status_code == 429:
        raise HTTPException(429, "SmartThings 요청 제한: 잠시 후 다시 시도하세요.")
    if not response.is_success:
        raise HTTPException(502, f"SmartThings API 오류 ({response.status_code})")
    return response.json()


def devices():
    return request("GET", "devices").get("items", [])


def command(device_id, capability, command_name, component="main", arguments=None):
    # 위험한 기기 동작은 현재 허용 목록에 넣지 않는다.
    allowed = {"switch": {"on", "off"}, "switchLevel": {"setLevel"},
               "colorTemperature": {"setColorTemperature"},
               "audioVolume": {"setVolume", "mute", "unmute"}}
    if command_name not in allowed.get(capability, set()):
        raise HTTPException(403, "이 명령은 허용된 기기 제어 목록에 없습니다.")
    listing = devices()
    device = next((d for d in listing if d["deviceId"] == device_id), None)
    if not device:
        raise HTTPException(404, "기기를 찾을 수 없습니다.")
    supported = any(c["id"] == component and any(x["id"] == capability for x in c["capabilities"])
                    for c in device["components"])
    if not supported:
        raise HTTPException(400, "기기가 이 capability를 지원하지 않습니다.")
    args = arguments or []
    if command_name in {"setLevel", "setVolume"}:
        if len(args) != 1 or not isinstance(args[0], (int, float)) or not 0 <= args[0] <= 100:
            raise HTTPException(400, "값은 0~100이어야 합니다.")
    if command_name == "setColorTemperature":
        if len(args) != 1 or not isinstance(args[0], (int, float)) or not 2000 <= args[0] <= 6500:
            raise HTTPException(400, "색온도는 2000~6500K이어야 합니다.")
    return request("POST", f"devices/{device_id}/commands",
                   {"commands": [{"component": component, "capability": capability,
                                  "command": command_name, "arguments": args}]})
