"""Authenticated API, persistence, real camera and mapping checks without device commands."""
import json
import time
import httpx
from hw_agent import auth, config
from hw_agent.motion import LABELS


def main():
    base = "http://127.0.0.1:8080"
    results = []
    def check(name, condition):
        assert condition, name
        results.append(name)

    check("anonymous read denied", httpx.get(base + "/api/motion").status_code == 401)
    token, csrf = auth.login(config.USERNAME, config.PASSWORD, "motion-api-test")
    with httpx.Client(base_url=base, headers={"Cookie": "alter_session=" + token}, timeout=60) as client:
        check("CSRF enforced", client.post("/api/motion", json={"enabled": False}).status_code == 403)
        client.headers.update({"X-CSRF-Token": csrf, "Origin": base})
        prior = client.get("/api/motion").json()
        camera_prior = client.get("/api/camera").json()
        response = client.post("/api/flows", json={"name": "Motion verification (no device command)",
                                                  "steps": [{"type": "delay", "seconds": 0}]})
        response.raise_for_status()
        flow = response.json()["id"]
        try:
            mappings = {key: flow for key in LABELS}
            rules = {key: {"hold_seconds": 2, "release_seconds": 2, "repeat_seconds": 10, "repeat": False} for key in LABELS}
            # 설정 저장/읽기를 먼저 확인하고 라이브 카메라 시험에서는 모든 실행 매핑을 비운다.
            response = client.post("/api/motion", json={"enabled": False, "mappings": mappings, "rules": rules})
            check("save six mappings", response.status_code == 200)
            saved = client.get("/api/motion").json()
            check("six mappings retained", saved["mappings"] == mappings)
            check("timing rules retained", saved["rules"] == rules)
            bad = client.post("/api/motion", json={"enabled": True, "mappings": {"Face": "missing"}})
            check("unknown Flow denied", bad.status_code == 400)
            bad = client.post("/api/motion", json={"enabled": False, "rules": {"Face": {"repeat_seconds": 0}}})
            check("unsafe interval denied", bad.status_code == 400)
            response = client.post("/api/motion", json={"enabled": True, "mappings": {}, "rules": rules})
            response.raise_for_status()
            start = response.json()["frames"]
            time.sleep(3)
            state = client.get("/api/motion").json()
            check("both models loaded", all(state["models_loaded"].values()))
            check("live inference advances", state["frames"] > start and not state["error"])
            with client.stream("GET", "/api/camera/stream") as stream:
                for chunk in stream.iter_bytes():
                    if b"\xff\xd8" in chunk:
                        check("shared camera JPEG stream", True)
                        break
            client.post("/api/motion", json={"enabled": False, "mappings": {}, "rules": rules}).raise_for_status()
            check("explicit stop", not client.get("/api/motion").json()["enabled"])
        finally:
            client.post("/api/motion", json={"enabled": prior["enabled"], "mappings": prior["mappings"], "rules": prior.get("rules", {})}).raise_for_status()
            if not camera_prior["running"] and not prior["enabled"]:
                client.post("/api/camera/stop", json={}).raise_for_status()
            client.delete("/api/flows/" + flow).raise_for_status()
            client.post("/api/logout", json={})
    (config.DATA / "motion-api-report.json").write_text(json.dumps(results, indent=2))
    print(str(len(results)) + " motion API checks passed")


if __name__ == "__main__":
    main()
