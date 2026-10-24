"""Run 2048 generated tokens alongside both live camera detectors; save metrics only."""
import json
import subprocess
import time
from pathlib import Path
import httpx
from hw_agent import auth, config, db


def metrics():
    result = {}
    for unit in ("alter", "alter-llm"):
        values = subprocess.check_output(["systemctl", "show", unit, "-p", "MainPID", "-p", "NRestarts"], text=True)
        result[unit] = dict(line.split("=", 1) for line in values.strip().splitlines())
        folder = Path("/sys/fs/cgroup/system.slice") / (unit + ".service")
        for field in ("memory.current", "memory.peak", "memory.events", "memory.swap.current"):
            result[unit][field] = (folder / field).read_text().strip()
    result["available_kib"] = int(next(line for line in Path("/proc/meminfo").read_text().splitlines()
                                       if line.startswith("MemAvailable:")).split()[1])
    return result


def main():
    token, csrf = auth.login(config.USERNAME, config.PASSWORD, "motion-verification")
    headers = {"Cookie": "alter_session=" + token, "X-CSRF-Token": csrf, "Origin": "http://127.0.0.1:8080"}
    report = {"started_at": time.time(), "before": metrics(), "status": "running"}
    output = config.DATA / "motion-load-report.json"
    with httpx.Client(base_url="http://127.0.0.1:8080", headers=headers, timeout=60) as client:
        prior = client.get("/api/motion").json()
        camera_before = client.get("/api/camera").json()
        try:
            response = client.post("/api/motion", json={"enabled": True, "mappings": {}})
            response.raise_for_status()
            report["motion_before"] = response.json()
            output.write_text(json.dumps(report))
            start = time.monotonic()
            final = None
            chunks = 0
            min_available = report["before"]["available_kib"]
            peak = {"alter": 0, "alter-llm": 0}
            # EOS 무시로 생성량을 고정하고 본문은 저장하지 않는다.
            with httpx.stream("POST", config.LLM_URL + "/completion", headers=config.LLM_HEADERS,
                              json={"prompt": "Write a long numbered list of practical household organization ideas.\n1.",
                                    "n_predict": 2048, "ignore_eos": True, "stream": True, "seed": 42},
                              timeout=httpx.Timeout(1800, connect=10)) as response:
                response.raise_for_status()
                last_sample = 0
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    value = line[6:]
                    if value == "[DONE]":
                        continue
                    event = json.loads(value)
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))
                    chunks += 1
                    if event.get("stop"):
                        final = event
                    if time.monotonic() - last_sample >= 5:
                        sample = metrics()
                        min_available = min(min_available, sample["available_kib"])
                        for unit in peak:
                            peak[unit] = max(peak[unit], int(sample[unit]["memory.current"]))
                        last_sample = time.monotonic()
            report.update(elapsed_seconds=round(time.monotonic() - start, 2), chunks=chunks,
                          generated_tokens=final.get("tokens_predicted") if final else None,
                          timings=final.get("timings") if final else None,
                          minimum_available_kib=min_available, sampled_peak_bytes=peak,
                          after=metrics(), motion_after=client.get("/api/motion").json())
            assert report["generated_tokens"] == 2048, "Expected exactly 2048 generated tokens"
            for unit in peak:
                assert report["before"][unit]["MainPID"] == report["after"][unit]["MainPID"], "Service restarted"
                assert report["before"][unit]["memory.events"] == report["after"][unit]["memory.events"], "Memory pressure event"
            assert report["motion_after"]["frames"] > report["motion_before"]["frames"] + 10
            assert not report["motion_after"]["error"]
            report["status"] = "passed"
        except Exception as exc:
            report.update(status="failed", error=str(exc), after=metrics())
            raise
        finally:
            client.post("/api/motion", json={"enabled": prior["enabled"], "mappings": prior["mappings"], "rules": prior.get("rules", {})})
            if not camera_before["running"] and not prior["enabled"]:
                client.post("/api/camera/stop", json={})
            client.post("/api/logout", json={})
            report["finished_at"] = time.time()
            output.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
