"""Bounded scan counters and estimates from work completed in this run."""
import time
from pathlib import Path
from . import storage


def count_files(base, cancelled, extensions=None, on_count=None):
    total = 0
    def visit(directory):
        nonlocal total
        import os
        if cancelled(): raise InterruptedError()
        with os.scandir(directory) as entries:
            for position, entry in enumerate(entries):
                if position % 128 == 0 and cancelled(): raise InterruptedError()
                if entry.name.startswith('.') or storage.excluded(entry.name): continue
                if entry.is_symlink(): continue
                if entry.is_dir(follow_symlinks=False):
                    visit(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and (extensions is None or Path(entry.name).suffix.lower() in extensions):
                    total += 1
                    if on_count and total % 100 == 0: on_count(total)
    visit(base)
    return total


class Estimate:
    def __init__(self):
        self.started = time.monotonic()
        self.samples = 0

    def advance(self, remaining):
        self.samples += 1
        elapsed = time.monotonic() - self.started
        # 시작 직후 몇 개만으로 수 시간을 단정하지 않는다.
        if self.samples < 3 or elapsed < 2: return None
        return round(max(0, remaining) * elapsed / self.samples)
