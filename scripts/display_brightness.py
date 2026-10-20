"""Dim the DSI backlight without switching the display off."""
import fcntl
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/display-brightness.json"
PANEL = Path("/sys/class/backlight/panel_backlight@1")


def change(action):
    STATE.parent.mkdir(exist_ok=True)
    with (STATE.parent / "display-brightness.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        maximum = int((PANEL / "max_brightness").read_text())
        current = int((PANEL / "brightness").read_text())
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        if action == "dim":
            if not state.get("dimmed"):
                state["previous"] = current
            target = 1
            state["dimmed"] = True
        elif action == "restore":
            if not state.get("dimmed"):
                return
            target = max(1, min(maximum, int(state.get("previous", maximum // 2))))
            state["dimmed"] = False
        else:
            raise ValueError("Expected dim or restore")
        (PANEL / "brightness").write_text(str(target))
        state.update(brightness=target, changed_at=time.time(), action=action)
        temporary = STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(STATE)


if __name__ == "__main__":
    change(sys.argv[1])
