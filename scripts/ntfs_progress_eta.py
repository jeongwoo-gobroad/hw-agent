"""Estimate the current conversion pass from committed byte-count samples."""
import argparse
import json
import math
from pathlib import Path
import sys

from ntfs_state import write_json_atomic

WINDOW_SECONDS = 2 * 3600


def estimate(snapshot, history, *, io_active=False):
    operation = snapshot.get("operation_id")
    empty = {"version": 1, "operation_id": operation, "samples": []}
    if not isinstance(history, dict) or history.get("version") != 1 or history.get("operation_id") != operation:
        history = empty
    samples = []
    for point in history.get("samples", []):
        if not isinstance(point, dict):
            continue
        at, done = point.get("at"), point.get("done_bytes")
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x >= 0 for x in (at, done)):
            continue
        if not samples or (at > samples[-1]["at"] and done > samples[-1]["done_bytes"]):
            samples.append({"at": at, "done_bytes": done})
    history = {**empty, "samples": samples}
    result = {"status": "collecting", "scope": "primary_pass", "seconds_low": None,
              "seconds_high": None, "bytes_per_second": None, "window_seconds": None}
    inventory = snapshot.get("inventory") or {}
    files = inventory.get("stream") or {}
    if (snapshot.get("windows_phase") != "inventory_and_decompression"
            or snapshot.get("worker_phase") != "decompressing"):
        result["status"] = "inactive"
        return result, history
    if snapshot.get("supervisor_age_seconds") is None or snapshot["supervisor_age_seconds"] > 90:
        result["status"] = "stale"
        return result, history
    now, at, done = (snapshot.get(key) for key in ("sampled_at", "recorded_at", "recorded_done_bytes"))
    if (not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (now, at, done))
            or at > now or done != files.get("done_bytes")):
        result["status"] = "inconsistent"
        return result, history
    if samples and (done < samples[-1]["done_bytes"] or at < samples[-1]["at"]):
        samples.clear()
    if not samples or (done > samples[-1]["done_bytes"] and at > samples[-1]["at"]):
        samples.append({"at": at, "done_bytes": done})
    cutoff = samples[-1]["at"] - WINDOW_SECONDS
    while len(samples) > 2 and samples[1]["at"] <= cutoff:
        samples.pop(0)
    samples[:] = samples[-512:]
    pending = files.get("pending_bytes", 0)
    if files.get("pending") == 0:
        result["status"] = "pass_finished"
        return result, history
    if now - at > 3 * WINDOW_SECONDS:
        result["status"] = "stale"
        return result, history
    if len(samples) < 2:
        return result, history
    duration = samples[-1]["at"] - samples[0]["at"]
    if duration < 60:
        return result, history
    rate = (samples[-1]["done_bytes"] - samples[0]["done_bytes"]) / duration
    if rate <= 0 or pending <= 0:
        return result, history
    # 파일 내부는 보이지 않는다. 추정 차감은 현재 순차 처리 항목 한 개까지만 허용한다.
    credit = min(files.get("next_pending_bytes", 0), max(0, now - at) * rate) if io_active else 0
    result.update(status="estimated", seconds_low=max(0, pending - credit) / rate,
                  seconds_high=pending / rate, bytes_per_second=rate,
                  window_seconds=duration, in_file_extrapolated=bool(credit))
    return result, history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--io-active", action="store_true")
    args = parser.parse_args()
    snapshot = json.load(sys.stdin)
    try:
        history = json.loads(args.history.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = {}
    result, updated = estimate(snapshot, history, io_active=args.io_active)
    if updated != history:
        try:
            write_json_atomic(args.history, updated, timeout=0.2)
        except OSError:
            result["history_saved"] = False
    print(json.dumps(result))


if __name__ == "__main__":
    main()
