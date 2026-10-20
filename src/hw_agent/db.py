from contextlib import contextmanager
import sqlite3
from pathlib import PurePosixPath
from .config import DATA


@contextmanager
def connect():
    db = sqlite3.connect(DATA / "agent.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def init():
    with connect() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS roots(
          id INTEGER PRIMARY KEY, path TEXT UNIQUE, uuid TEXT, mount TEXT, label TEXT);
        CREATE TABLE IF NOT EXISTS files(
          id INTEGER PRIMARY KEY, root INTEGER, path TEXT UNIQUE, name TEXT,
          ext TEXT, mime TEXT, size INTEGER, modified REAL, created REAL,
          text TEXT, extraction TEXT, seen TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
          name, path, body, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS staging(
          root INTEGER, path TEXT, name TEXT, ext TEXT, mime TEXT, size INTEGER,
          modified REAL, created REAL, text TEXT, extraction TEXT, seen TEXT,
          name_tokens TEXT, path_tokens TEXT, body_tokens TEXT);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS sessions(
          id TEXT PRIMARY KEY, title TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS flows(
          id TEXT PRIMARY KEY, name TEXT, steps TEXT);
        CREATE TABLE IF NOT EXISTS runs(
          id TEXT PRIMARY KEY, flow TEXT, status TEXT, log TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS auth(
          token TEXT PRIMARY KEY, csrf TEXT, expires REAL, fingerprint TEXT);
        """)
        if "relative_path" not in {row[1] for row in db.execute("PRAGMA table_info(roots)")}:
            migrated = []
            identities = set()
            for row in db.execute("SELECT * FROM roots"):
                relative = str(PurePosixPath(row["path"]).relative_to(row["mount"]))
                identity = (row["uuid"], relative)
                if identity in identities:
                    raise RuntimeError("Duplicate volume/folder registrations require reconciliation before migration")
                identities.add(identity)
                migrated.append((*tuple(row), relative))
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE roots_v2(
                id INTEGER PRIMARY KEY, path TEXT, uuid TEXT, mount TEXT, label TEXT,
                relative_path TEXT, UNIQUE(uuid,relative_path))""")
            db.executemany("INSERT INTO roots_v2 VALUES(?,?,?,?,?,?)", migrated)
            db.execute("DROP TABLE roots")
            db.execute("ALTER TABLE roots_v2 RENAME TO roots")
        db.execute("PRAGMA user_version=2")
        db.execute("UPDATE runs SET status='interrupted' WHERE status='running'")


def rows(query, args=()):
    with connect() as db:
        return [dict(row) for row in db.execute(query, args)]


def state(key, default=None):
    result = rows("SELECT value FROM state WHERE key=?", (key,))
    return result[0]["value"] if result else default


def set_state(key, value):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, value))
