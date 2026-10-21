import json
import os
from pathlib import Path
import shutil
import subprocess
from fastapi import HTTPException
from . import db, config


def devices():
    result = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,FSTYPE,MOUNTPOINTS,UUID,TRAN,MODEL,SERIAL"],
        capture_output=True, text=True, check=True, timeout=10)
    found = []
    def visit(items, parent=None):
        for item in items:
            transport = item.get("tran") or (parent or {}).get("tran")
            model = item.get("model") or (parent or {}).get("model")
            serial = item.get("serial") or (parent or {}).get("serial")
            external = transport == "usb" or item["name"].startswith("nvme")
            if external and item.get("fstype") and item.get("uuid"):
                mounts = [m for m in item.get("mountpoints", []) if m and m != "[SWAP]"]
                mount = mounts[0] if mounts else None
                try:
                    usage = shutil.disk_usage(mount) if mount else None
                except OSError:
                    usage = None
                found.append({**item, "mount": mount, "model": model, "serial": serial, "transport": transport or "pcie",
                              "free": usage.free if usage else None})
            visit(item.get("children", []), {**item, "tran": transport, "model": model, "serial": serial})
    visit(json.loads(result.stdout)["blockdevices"])
    return found


def device_for_uuid(identifier, listing=None):
    matches = [d for d in (devices() if listing is None else listing) if d["uuid"] == identifier]
    if len(matches) > 1:
        raise HTTPException(409, "동일한 파일시스템 UUID의 장치가 여러 개입니다. 복제 드라이브를 분리하세요.")
    return matches[0] if matches else None


def excluded(path):
    return any(part.casefold() in config.EXCLUDED_DIRECTORY_NAMES for part in Path(path).parts)


def check_path(path):
    if excluded(path):
        raise HTTPException(403, "접근 제외 경로입니다.")


def external_path(path):
    check_path(path)
    p = Path(path).resolve(strict=True)
    check_path(p)
    listing = devices()
    for device in listing:
        if device["mount"] and p.is_relative_to(Path(device["mount"]).resolve()):
            device_for_uuid(device["uuid"], listing)
            if any(part.startswith(".") for part in p.relative_to(device["mount"]).parts):
                raise HTTPException(403, "숨김 폴더는 등록할 수 없습니다.")
            return p, device
    raise HTTPException(403, "연결된 외장 드라이브 내부 폴더를 선택하세요.")


def add_root(path):
    p, device = external_path(path)
    if not p.is_dir():
        raise HTTPException(400, "폴더를 선택하세요.")
    relative = str(p.relative_to(Path(device["mount"]).resolve()))
    with db.connect() as conn:
        conn.execute("""INSERT INTO roots(path,uuid,mount,label,relative_path) VALUES(?,?,?,?,?)
                     ON CONFLICT(uuid,relative_path) DO UPDATE SET path=excluded.path,mount=excluded.mount""",
                     (str(p), device["uuid"], device["mount"], p.name, relative))
    return db.rows("SELECT * FROM roots WHERE uuid=? AND relative_path=?",
                   (device["uuid"], relative))[0]


def root_path(root):
    check_path(root["path"])
    device = device_for_uuid(root["uuid"])
    if device and device["mount"]:
        relative = Path(root.get("relative_path") or Path(root["path"]).relative_to(root["mount"]))
        try:
            p = (Path(device["mount"]) / relative).resolve(strict=True)
        except OSError:
            raise HTTPException(409, "등록된 폴더가 현재 드라이브에 없습니다.")
        if p.is_relative_to(Path(device["mount"]).resolve()) and p.is_dir():
            if root["mount"] != device["mount"] or not root.get("relative_path"):
                with db.connect() as conn:
                    conn.execute("UPDATE roots SET path=?,mount=?,relative_path=? WHERE id=?",
                                 (str(p),device["mount"],str(relative),root["id"]))
            return p
    raise HTTPException(409, "외장 드라이브 또는 폴더가 연결되지 않았습니다.")


def safe_file(file_id):
    records = db.rows("SELECT * FROM files WHERE id=?", (file_id,))
    if not records:
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    record = records[0]
    roots = db.rows("SELECT * FROM roots WHERE id=?", (record["root"],))
    if not roots:
        raise HTTPException(403, "등록이 해제된 폴더입니다.")
    base = root_path(roots[0])
    candidate = base / record["path"].split("\n", 1)[1]
    check_path(candidate)
    p = candidate.resolve(strict=True)
    check_path(p)
    if not p.is_relative_to(base) or not p.is_file():
        raise HTTPException(403, "허용 폴더 밖의 파일입니다.")
    return p, record


def folders(path):
    p, device = external_path(path)
    return {"path": str(p), "mount": device["mount"],
            "children": sorted([str(x) for x in p.iterdir() if not excluded(x) and x.is_dir() and not x.is_symlink()
                                and not x.name.startswith(".")])[:500]}


def smb(action, path, name, readonly=True):
    if action not in {"set", "remove"}:
        raise HTTPException(400, "지원하지 않는 공유 작업입니다.")
    p, device = external_path(path) if action == "set" else (None, None)
    payload = json.dumps({"action": action, "path": str(p) if p else "", "name": name, "readonly": readonly})
    result = subprocess.run(["sudo", "-n", "/usr/local/sbin/alter-smb"], input=payload,
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise HTTPException(400, result.stderr[-500:] or "SMB 설정에 실패했습니다.")
    saved = json.loads(db.state("shares", "{}"))
    if action == "set":
        saved[name] = {"uuid":device["uuid"], "relative":str(p.relative_to(device["mount"])),
                       "readonly":readonly,"path":str(p),"name":name}
    else:
        saved.pop(name,None)
    db.set_state("shares",json.dumps(saved))
    return {"message": result.stdout.strip()}


def restore_shares():
    saved = json.loads(db.state("shares", "{}"))
    for share in saved.values():
        device = device_for_uuid(share["uuid"])
        if device and device["mount"]:
            path = str(Path(device["mount"])/share["relative"])
            if path != share["path"]:
                smb("set", path, share["name"], share["readonly"])
