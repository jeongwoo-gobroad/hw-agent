"""Publish maintenance snapshots despite short Windows reader locks."""
import json
import os
from pathlib import Path
import tempfile
import time


def write_json_atomic(path, value, *, timeout=10.0, interval=0.05):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent,
            prefix=path.name + '.', suffix='.tmp', delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream)
        deadline = time.monotonic() + timeout
        while True:
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                # Windows 독자가 잠깐 잡은 파일은 닫힐 때까지 기다린다.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(interval, remaining))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
