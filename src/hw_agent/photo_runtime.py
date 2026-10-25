"""Progress is persisted in SQLite; a lightweight heartbeat tracks process health."""
import json
import time
from .config import DATA
from . import db


def read():
    return json.loads(db.state('photo_progress', '{}'))


def write(**values):
    current = read()
    current.update(values, updated=time.time())
    db.set_state('photo_progress',json.dumps(current))


def heartbeat():
    (DATA/'photo-heartbeat').touch()


def online():
    try: return time.time()-(DATA/'photo-heartbeat').stat().st_mtime<180
    except OSError: return False
