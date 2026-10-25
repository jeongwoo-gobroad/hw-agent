"""Run against the installed Pi service; writes only Alter-test on the USB."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import zipfile
import httpx
from dotenv import load_dotenv
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
BASE = os.getenv("ALTER_TEST_URL", "http://127.0.0.1:11977")
client = httpx.Client(base_url=BASE, timeout=240)
results = []


def check(name, condition):
    assert condition, name
    results.append({"test": name, "passed": True})


def post(path, body=None):
    r = client.post(path, json=body or {})
    assert r.is_success, (path, r.status_code, r.text[:300])
    return r.json()


def wait_scan():
    time.sleep(.3)
    for _ in range(90):
        status = client.get("/api/status").json()["index"]
        if not status["running"]:
            assert not status["error"], status
            return
        time.sleep(1)
    raise AssertionError("scan timeout")


def main():
    for _ in range(30):
        try:
            if client.get("/health").is_success: break
        except httpx.HTTPError: pass
        time.sleep(1)
    for path in ["/api/status", "/api/files/1/download", "/api/files/1/preview", "/api/camera/stream"]:
        check("unauthenticated " + path, client.get(path).status_code == 401)
    check("wrong password", client.post("/api/login", json={"username":"invalid","password":"invalid"}).status_code == 401)
    logged = post("/api/login", {"username":os.environ["DASHBOARD_USERNAME"], "password":os.environ["DASHBOARD_PASSWORD"]})
    check("csrf required", client.post("/api/index", json={}).status_code == 403)
    client.headers["X-CSRF-Token"] = logged["csrf"]
    check("cross origin rejected", client.post("/api/index", json={}, headers={"Origin":"http://untrusted.test"}).status_code == 403)
    check("system root denied", client.post("/api/roots", json={"path":"/etc"}).status_code == 403)
    disk = next(d for d in client.get("/api/devices").json() if d["mount"])
    fixture = Path(disk["mount"]) / "Alter-test"
    fixture.mkdir(exist_ok=True)
    (fixture / "회의-메모.txt").write_text("얼터 테스트 문서입니다. 프로젝트 회의 일정과 예산을 확인합니다.", encoding="utf-8")
    for ext, member in [("docx","word/document.xml"),("hwpx","Contents/section0.xml")]:
        with zipfile.ZipFile(fixture / ("프로젝트."+ext), "w") as z:
            z.writestr(member, '<root><t>프로젝트 회의 자료 한국어 키워드</t></root>')
    (fixture / "legacy.hwp").write_bytes(b"unsupported legacy sample")
    register_heif_opener()
    image = Image.new("RGB", (320, 240), (60, 120, 80))
    image.save(fixture / "미리보기.png")
    image.save(fixture / "미리보기.heic", format="HEIF")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
                    "-t", "2", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(fixture/"영상.mov")], check=True)
    root = post("/api/roots", {"path":str(fixture)})
    post("/api/index")
    wait_scan()
    files = client.get("/api/search", params={"q":"프로젝트"}).json()
    check("Korean BM25 text DOCX HWPX", len(files) >= 3)
    check("extension filter", len(client.get("/api/search",params={"q":"프로젝트","ext":"hwpx"}).json()) == 1)
    check("TF-IDF rerank", len(client.get("/api/search",params={"q":"회의","rerank":"true"}).json()) >= 3)
    check("date excludes future", client.get("/api/search",params={"after":time.time()+10000}).json() == [])
    all_files = client.get("/api/search",params={"root":root["id"]}).json()
    for file in tqdm(all_files, desc="Preview checks"):
        r = client.get(f"/api/files/{file['id']}/preview")
        check("preview "+file["ext"], r.status_code == 200 and len(r.content) > 0)
        r = client.get(f"/api/files/{file['id']}/download")
        check("download integrity "+file["ext"], hashlib.sha256(r.content).digest() == hashlib.sha256((fixture/file["path"]).read_bytes()).digest())
    modified = fixture / "tracking-test.txt"
    modified.write_text("신규파일 추적표본", encoding="utf-8")
    post("/api/index"); wait_scan()
    check("created file tracked", bool(client.get("/api/search",params={"q":"추적표본"}).json()))
    modified.rename(fixture/"renamed-test.txt")
    post("/api/index"); wait_scan()
    check("renamed file tracked", any(f["name"]=="renamed-test.txt" for f in client.get("/api/search",params={"q":"추적표본"}).json()))
    (fixture/"renamed-test.txt").unlink()
    post("/api/index"); wait_scan()
    check("deleted file removed", client.get("/api/search",params={"q":"추적표본"}).json() == [])
    flow = post("/api/flows", {"name":"검증 · 0초 대기", "steps":[{"type":"delay","seconds":0}]})
    request_id = str(uuid.uuid4())
    run = post(f"/api/flows/{flow['id']}/run", {"request_id":request_id})
    check("flow execution", run["status"]=="completed")
    duplicate = post(f"/api/flows/{flow['id']}/run", {"request_id":request_id})
    check("flow idempotency", duplicate["id"]==run["id"])
    check("invalid flow denied", client.post("/api/flows",json={"name":"invalid","steps":[{"type":"shell"}]}).status_code == 400)
    session = post("/api/sessions", {"title":"실기기 검증"})
    answer = post(f"/api/sessions/{session['id']}/messages", {"message":"프로젝트 회의 문서를 찾아줘"})
    check("chat persistence", len(client.get("/api/sessions/"+session["id"]).json())==2)
    check("chat returns search cards", isinstance(answer["files"],list))
    results.append({"test":"chat mode", "value":answer["mode"], "query":answer["query"]})
    post("/api/camera/start")
    with client.stream("GET", "/api/camera/stream") as stream:
        frame = next(stream.iter_bytes())
        check("live camera JPEG stream", stream.status_code==200 and b"image/jpeg" in frame[:200])
    post("/api/camera/record", {"root_id":root["id"]})
    time.sleep(6)
    post("/api/camera/record/stop")
    videos = sorted((fixture/"Alter-recordings").glob("*.mp4"))
    check("recording file exists", bool(videos))
    probe = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(videos[-1])], capture_output=True,text=True,check=True)
    check("recording playable duration", float(json.loads(probe.stdout)["format"]["duration"])>0)
    post("/api/gestures", {"enabled":True,"mappings":{}})
    time.sleep(3)
    state = client.get("/api/camera").json()
    check("gesture engine initialized", state["gestures"] and not state["error"])
    post("/api/gestures", {"enabled":False,"mappings":{}})
    post("/api/camera/stop")
    post("/api/logout")
    check("logout invalidates session", client.get("/api/status").status_code == 401)
    output = ROOT/"data"/"live-smoke.json"
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"passed":len(results),"results":str(output)},ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    finally:
        (ROOT/"data"/"live-smoke-progress.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
