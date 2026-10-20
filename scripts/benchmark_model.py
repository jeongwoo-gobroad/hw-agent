"""Small reproducible Korean routing probe, not a general model ranking."""
import argparse
import json
from pathlib import Path
import subprocess
import threading
import time
import httpx
from tqdm import tqdm

parser = argparse.ArgumentParser()
parser.add_argument("label")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
headers = {"Authorization":"Bearer "+(root/"data/llm-api-key").read_text().strip()}
for attempt in range(120):
    try:
        if httpx.get("http://127.0.0.1:8081/health",headers=headers,timeout=2).is_success:
            break
    except httpx.HTTPError:
        pass
    time.sleep(2)
else:
    raise RuntimeError("Model did not become ready")
cases = [
    ("지난달 회의 PDF를 찾아줘", "search"),
    ("안녕, 너는 무슨 일을 도와줄 수 있어?", "chat"),
    ("취침 Flow 실행해줘", "flow"),
]
system = ('한국어 도우미 얼터다. 현재 날짜 2026-10-20. '
          'JSON만 출력: {"intent":"search 또는 chat 또는 flow","query":"","ext":"",'
          '"after":null,"before":null,"flow_id":null,"answer":""}. '
          '파일 찾기는 search, 일반 대화는 chat, 자동화 실행은 flow. '
          '날짜는 YYYY-MM-DD. 등록 Flow: [{"id":"sleep","name":"취침"}].')
results = []
for prompt, expected in tqdm(cases, desc=args.label):
    samples = []
    done = threading.Event()
    def monitor():
        while not done.is_set():
            p = Path("/sys/fs/cgroup/system.slice/alter-llm.service/memory.current")
            mem = int(p.read_text()) if p.exists() else None
            available = next(int(line.split()[1])*1024 for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
            samples.append((mem, available))
            done.wait(.25)
    thread = threading.Thread(target=monitor,daemon=True)
    thread.start()
    start = time.monotonic()
    try:
        r = httpx.post("http://127.0.0.1:8081/v1/chat/completions",headers=headers,json={
            "messages":[{"role":"system","content":system},{"role":"user","content":prompt}],
            "temperature":0.1,"max_tokens":180,"response_format":{"type":"json_object"},
            "chat_template_kwargs":{"enable_thinking":False}},timeout=300)
        r.raise_for_status()
        result=r.json()
        text=result["choices"][0]["message"]["content"]
        try:
            parsed=json.loads(text)
            passed=parsed.get("intent")==expected
        except ValueError:
            passed=False
        results.append({"prompt":prompt,"expected":expected,"passed":passed,"response":text,
                        "seconds":round(time.monotonic()-start,2),"usage":result.get("usage"),
                        "timings":result.get("timings")})
    except Exception as exc:
        results.append({"prompt":prompt,"passed":False,"error":str(exc)})
    finally:
        done.set();thread.join()
        results[-1]["peak_cgroup_bytes"]=max((s[0] or 0 for s in samples),default=0)
        results[-1]["minimum_available_bytes"]=min((s[1] for s in samples),default=0)
out=root/"data"/f"benchmark-{args.label}.json"
out.write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(out)
