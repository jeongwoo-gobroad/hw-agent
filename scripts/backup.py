"""Create a consistent SQLite backup without exposing credentials."""
from datetime import datetime
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parents[1]
folder = root / "data" / "backups"
folder.mkdir(parents=True, exist_ok=True)
target = folder / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".sqlite3")
with sqlite3.connect(root / "data" / "agent.sqlite3") as source:
    with sqlite3.connect(target) as backup:
        source.backup(backup)
print(target)
