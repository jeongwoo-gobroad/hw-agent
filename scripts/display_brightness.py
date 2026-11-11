"""Dim the DSI backlight without switching the display off."""
import fcntl
import json
import os
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/display-brightness.json"
PANEL = Path("/sys/class/backlight/panel_backlight@1")


def wait_for_display(seconds=90):
    display = Path(os.getenv('WAYLAND_DISPLAY', 'wayland-0'))
    if not display.is_absolute():
        display = Path(os.getenv('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / display
    deadline = time.monotonic() + seconds
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(1)
                connection.connect(str(display))
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Wayland compositor was not ready within the startup deadline') from None
            time.sleep(1)


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
    if sys.argv[1] == 'wait': wait_for_display()
    else: change(sys.argv[1])
