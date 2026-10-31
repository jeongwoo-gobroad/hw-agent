"""Read aggregate NTFS maintenance progress without opening source files."""
import argparse
import json
from pathlib import Path
import sqlite3
import time


def read_state(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def inventory_totals(database):
    groups = {
        kind: {"total": 0, "done": 0, "pending": 0, "error": 0,
               "logical_bytes": 0, "done_bytes": 0, "pending_bytes": 0,
               "error_bytes": 0, "next_pending_bytes": 0}
        for kind in ("stream", "directory")
    }
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("""
            SELECT kind,status,count(*),coalesce(sum(size),0),coalesce(min(size),0)
            FROM entries WHERE format>0 GROUP BY kind,status
        """)
        for kind, status, count, size, smallest in rows:
            if kind not in groups:
                continue
            group = groups[kind]
            group["total"] += count
            group["logical_bytes"] += size
            if status in ("done", "pending", "error"):
                group[status] += count
            if status == "done":
                group["done_bytes"] += size
            elif status == "pending":
                group["pending_bytes"] += size
                group["next_pending_bytes"] = smallest
            elif status == "error":
                group["error_bytes"] += size
    finally:
        connection.close()
    return groups


def snapshot(state_directory):
    now = time.time()
    worker = read_state(state_directory / "real-worker" / "progress.json")
    windows = read_state(state_directory / "real-maintenance-result.json")
    supervisor = read_state(state_directory / "maintenance-supervisor.json")
    restored = read_state(state_directory / "restoration-result.json")
    # 화면에는 집계와 상태만 전달하고 개별 경로나 오류 원문은 내보내지 않는다.
    result = {
        "sampled_at": now,
        "recorded_at": worker.get("updated_at"),
        "recorded_done_bytes": worker.get("processed_logical_bytes"),
        "operation_id": ":".join(str(supervisor.get(key, "")) for key in (
            "pid", "restarted_at", "resume_count", "access_retry_count", "progress_lock_resume_count"
        )),
        "worker_phase": worker.get("phase", "unknown"),
        "windows_phase": windows.get("phase", "unknown"),
        "supervisor_phase": supervisor.get("phase", "unknown"),
        "worker_exit": windows.get("worker_exit"),
        "safe_to_restore": windows.get("safe_to_restore", False),
        "restored": restored.get("ok", False),
        "inventory_errors": worker.get("issues", 0),
        "free_bytes_at_last_record": worker.get("free_bytes"),
        "record_age_seconds": max(0, now - worker["updated_at"]) if worker.get("updated_at") else None,
        "supervisor_age_seconds": max(0, now - supervisor["checked_at"]) if supervisor.get("checked_at") else None,
    }
    try:
        result["inventory"] = inventory_totals(state_directory / "real-worker" / "inventory.sqlite3")
    except (OSError, sqlite3.Error):
        result["inventory"] = None
        result["inventory_error"] = "unavailable"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.state_directory), ensure_ascii=True))
