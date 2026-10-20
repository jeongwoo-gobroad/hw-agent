import json
import threading
import time
import uuid
from fastapi import HTTPException
from . import db, smartthings

lock = threading.Lock()
active = set()
last_run = {}


def validate(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise HTTPException(400, "Flow에는 1~20단계가 필요합니다.")
    for step in steps:
        if step.get("type") == "delay":
            if not isinstance(step.get("seconds"), (float, int)) or not 0 <= step["seconds"] <= 60:
                raise HTTPException(400, "지연은 0~60초입니다.")
        elif step.get("type") == "device":
            if not all(isinstance(step.get(k), str) and step[k] for k in ("device_id", "capability", "command")):
                raise HTTPException(400, "기기 단계 필드가 부족합니다.")
        else:
            raise HTTPException(400, "지원하지 않는 Flow 단계입니다.")
    return steps


def execute(flow_id, request_id=None):
    request_id = request_id or uuid.uuid4().hex
    with lock:
        prior = db.rows("SELECT * FROM runs WHERE id=?", (request_id,))
        if prior:
            return prior[0]
        if flow_id in active or time.monotonic() - last_run.get(flow_id, 0) < 3:
            raise HTTPException(409, "Flow가 실행 중이거나 쿨다운 중입니다.")
        flow = db.rows("SELECT * FROM flows WHERE id=?", (flow_id,))
        if not flow:
            raise HTTPException(404, "Flow를 찾을 수 없습니다.")
        steps = validate(json.loads(flow[0]["steps"]))
        active.add(flow_id)
        with db.connect() as conn:
            conn.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (request_id, flow_id, "running", "[]", time.time()))
    log, status = [], "completed"
    try:
        for index, step in enumerate(steps):
            if step["type"] == "delay":
                time.sleep(step["seconds"])
            else:
                smartthings.command(step["device_id"], step["capability"], step["command"],
                                    step.get("component", "main"), step.get("arguments", []))
            log.append({"step": index + 1, "status": "completed"})
            with db.connect() as conn:
                conn.execute("UPDATE runs SET log=? WHERE id=?", (json.dumps(log), request_id))
    except Exception as exc:
        status = "failed"
        log.append({"step": len(log) + 1, "status": "failed", "error": str(getattr(exc, "detail", type(exc).__name__))})
    finally:
        with db.connect() as conn:
            conn.execute("UPDATE runs SET status=?,log=? WHERE id=?", (status, json.dumps(log), request_id))
        with lock:
            active.discard(flow_id)
            last_run[flow_id] = time.monotonic()
    return db.rows("SELECT * FROM runs WHERE id=?", (request_id,))[0]
