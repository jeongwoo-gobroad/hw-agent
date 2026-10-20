"""Exercise the dedicated test USB's remount and share restoration."""
import json
import os
from pathlib import Path
import time
import httpx
from dotenv import load_dotenv

base = Path(__file__).resolve().parents[1]
load_dotenv(base/".env")
c = httpx.Client(base_url="http://127.0.0.1:8080",timeout=45)
for _ in range(30):
    try:
        if c.get("/health").is_success: break
    except httpx.HTTPError: pass
    time.sleep(1)
r = c.post("/api/login",json={"username":os.environ["DASHBOARD_USERNAME"],"password":os.environ["DASHBOARD_PASSWORD"]})
r.raise_for_status()
c.headers["X-CSRF-Token"]=r.json()["csrf"]
devices=c.get("/api/devices").json()
device=next(d for d in devices if d["uuid"]=="72FB-1A24")
root=next(r for r in c.get("/api/roots").json() if r["uuid"]==device["uuid"] and r["label"]=="Alter-test")
r=c.post("/api/shares",json={"path":root["path"],"name":"Test","readonly":True})
r.raise_for_status()
for attempt in range(60):
    if not c.get("/api/status").json()["index"]["running"]:
        break
    time.sleep(1)
before=c.get("/api/status").json()["indexed_files"]
r=c.post("/api/devices/action",json={"device":device["path"],"action":"unmount"})
r.raise_for_status()
r=c.get("/api/search",params={"root":root["id"]})
assert len(r.json())>0,"Offline metadata was removed"
file_id=r.json()[0]["id"]
assert c.get(f"/api/files/{file_id}/download").status_code in (404,409)
r=c.post("/api/devices/action",json={"device":device["path"],"action":"mount"})
r.raise_for_status()
roots=c.get("/api/roots").json()
new_root=next(r for r in roots if r["id"]==root["id"])
assert new_root["mount"].startswith("/mnt/alter/"),"Expected managed remount path"
assert c.get(f"/api/files/{file_id}/download").is_success
shares=c.get("/api/shares").json()
assert next(s for s in shares if s["name"]=="Test")["path"]==new_root["path"]
result={"unmount":True,"offline_index_preserved":True,"offline_download_blocked":True,
        "uuid_remount":True,"new_mount":new_root["mount"],"smb_path_restored":True,
        "indexed_before":before}
(base/"data/live-storage.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result))
