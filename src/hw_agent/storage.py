import json
import os
from pathlib import Path
import shutil
import subprocess
from fastapi import HTTPException
from . import db


def devices():
    result = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,FSTYPE,MOUNTPOINTS,UUID,TRAN,MODEL"],
        capture_output=True, text=True, check=True, timeout=10)
    found = []
    def visit(items, parent=None):
        for item in items:
            transport = item.get("tran") or (parent or {}).get("tran")
            external = transport == "usb" or item["name"].startswith("nvme")
            if external and item.get("fstype") and item.get("uuid"):
                mounts = [m for m in item.get("mountpoints", []) if m and m != "[SWAP]"]
                mount = mounts[0] if mounts else None
                try:
                    usage = shutil.disk_usage(mount) if mount else None
                except OSError:
                    usage = None
                found.append({**item, "mount": mount, "transport": transport or "pcie",
                              "free": usage.free if usage else None})
            visit(item.get("children", []), {**item, "tran": transport})
    visit(json.loads(result.stdout)["blockdevices"])
    return found


def external_path(path):
    p = Path(path).resolve(strict=True)
    for device in devices():
        if device["mount"] and p.is_relative_to(Path(device["mount"]).resolve()):
            if any(part.startswith(".") for part in p.relative_to(device["mount"]).parts):
                raise HTTPException(403, "숨김 폴더는 등록할 수 없습니다.")
            return p, device
    raise HTTPException(403, "연결된 외장 드라이브 내부 폴더를 선택하세요.")


def add_root(path):
    p, device = external_path(path)
    if not p.is_dir():
        raise HTTPException(400, "폴더를 선택하세요.")
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO roots(path,uuid,mount,label) VALUES(?,?,?,?)",
                     (str(p), device["uuid"], device["mount"], p.name))
    return db.rows("SELECT * FROM roots WHERE path=?", (str(p),))[0]


def root_path(root):
    for device in devices():
        if device["uuid"] == root["uuid"] and device["mount"]:
            relative = Path(root["path"]).relative_to(root["mount"])
            p = (Path(device["mount"]) / relative).resolve(strict=True)
            if p.is_relative_to(Path(device["mount"]).resolve()) and p.is_dir():
                if root["mount"] != device["mount"]:
                    with db.connect() as conn:
                        conn.execute("UPDATE roots SET path=?,mount=? WHERE id=?", (str(p),device["mount"],root["id"]))
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
    p = (base / record["path"].split("\n", 1)[1]).resolve(strict=True)
    if not p.is_relative_to(base) or not p.is_file():
        raise HTTPException(403, "허용 폴더 밖의 파일입니다.")
    return p, record


def folders(path):
    p, device = external_path(path)
    return {"path": str(p), "mount": device["mount"],
            "children": sorted([str(x) for x in p.iterdir() if x.is_dir() and not x.is_symlink()
                                and not x.name.startswith(".")])[:500]}


def smb(action, path, name, readonly=True):
    p, device = external_path(path)
    payload = json.dumps({"action": action, "path": str(p), "name": name, "readonly": readonly})
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
        device = next((d for d in devices() if d["uuid"]==share["uuid"] and d["mount"]),None)
        if device:
            path = str(Path(device["mount"])/share["relative"])
            if path != share["path"]:
                smb("set", path, share["name"], share["readonly"])
