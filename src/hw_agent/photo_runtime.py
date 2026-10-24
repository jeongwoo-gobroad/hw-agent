"""Atomic progress files stay responsive during the file search DB's FTS refresh."""
import json
import os
import time
from .config import DATA


def read():
    try: return json.loads((DATA/'photo-progress.json').read_text())
    except (FileNotFoundError, ValueError): return {}


def write(**values):
    current = read()
    current.update(values, updated=time.time())
    temporary = DATA/f'photo-progress-{os.getpid()}.tmp'
    temporary.write_text(json.dumps(current))
    temporary.replace(DATA/'photo-progress.json')


def heartbeat():
    (DATA/'photo-heartbeat').touch()


def online():
    try: return time.time()-(DATA/'photo-heartbeat').stat().st_mtime<180
    except OSError: return False
