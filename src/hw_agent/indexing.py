import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from fastapi import HTTPException
from . import db, storage
from .progress import count_files, Estimate

scan_lock = threading.Lock()
status = {"running": False, "files": 0, "error": None}
stop_event = threading.Event()
EXTRACTOR_VERSION = "2026-10-20.2"


def tokens(text):
    # 한국어 조사 차이를 완화하도록 단어와 2글자 조각을 함께 넣는다.
    words = re.findall(r"[^\W_]+", text.lower(), re.UNICODE)
    pieces = list(words)
    for word in words:
        if re.search("[가-힣]", word):
            pieces.extend(word[i:i+2] for i in range(len(word)-1))
    return " ".join(pieces)


def scan():
    if not scan_lock.acquire(blocking=False):
        return
    status.update(running=True, files=0, error=None, stage="counting", total=0, eta_seconds=None, total_known=False)
    try:
        previous = float(db.state("generation_at", "0"))
        rebuild = time.time() - previous >= 3 * 86400 or db.state("extractor_version") != EXTRACTOR_VERSION
        generation = uuid.uuid4().hex
        complete = True
        roots = db.rows("SELECT * FROM roots")
        for root in roots:
            try:
                offset = status['total']
                count = count_files(storage.root_path(root), stop_event.is_set,
                                    on_count=lambda n: status.update(total=offset+n))
                status['total'] = offset+count
            except InterruptedError:
                return
            except (OSError, HTTPException) as exc:
                status['error'] = str(getattr(exc, 'detail', type(exc).__name__))
                complete = False
        status.update(total_known=True, stage='indexing')
        estimate = Estimate()
        for root in roots:
            try:
                base = storage.root_path(root)
            except HTTPException as error:
                if error.status_code not in {403, 409}:
                    raise
                status["error"] = error.detail
                complete = False
                continue
            with db.connect() as conn:
                conn.execute("DELETE FROM staging WHERE root=?", (root["id"],))
            for directory, dirs, names in os.walk(base, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".") and not storage.excluded(Path(directory)/d) and not (Path(directory)/d).is_symlink()]
                if not db.rows("SELECT id FROM roots WHERE id=?", (root["id"],)):
                    break
                for name in names:
                    if stop_event.is_set():
                        return
                    p = Path(directory) / name
                    if storage.excluded(p) or p.is_symlink() or name.startswith("."):
                        continue
                    st = p.stat()
                    key = f"{root['id']}\n{p.relative_to(base)}"
                    prior_rows = db.rows("SELECT * FROM files WHERE path=?", (key,))
                    prior = prior_rows[0] if prior_rows else None
                    if prior and not rebuild and prior["modified"] == st.st_mtime and prior["size"] == st.st_size:
                        text, extraction = prior["text"], prior["extraction"]
                    else:
                        try:
                            completed = subprocess.run([sys.executable, "-m", "hw_agent.extract", str(p)],
                                                       capture_output=True, text=True, timeout=12, check=True)
                            result = json.loads(completed.stdout)
                            text, extraction = result["text"], result["status"]
                        except (subprocess.SubprocessError, ValueError):
                            text, extraction = "", "timeout_or_error"
                    record = (root["id"], key, name, p.suffix.lower(), mimetypes.guess_type(name)[0] or "application/octet-stream",
                              st.st_size, st.st_mtime, getattr(st, "st_birthtime", None), text, extraction, generation)
                    with db.connect() as conn:
                        conn.execute("BEGIN IMMEDIATE")
                        if not conn.execute("SELECT id FROM roots WHERE id=?", (root["id"],)).fetchone():
                            break
                        conn.execute("INSERT INTO staging VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                     (*record, tokens(name), tokens(key), tokens(text)))
                    status["files"] += 1
                    status['total'] = max(status['total'], status['files'])
                    status.update(stage='indexing', eta_seconds=estimate.advance(status['total']-status['files']))
            if not db.rows("SELECT id FROM roots WHERE id=?", (root["id"],)):
                continue
            status.update(stage='finalizing', eta_seconds=None)
            # 드라이브가 사라지면 기존 색인을 지우지 않는다.
            storage.root_path(root)
            with db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute("SELECT id FROM roots WHERE id=?", (root["id"],)).fetchone():
                    continue
                conn.execute("""INSERT INTO files(root,path,name,ext,mime,size,modified,created,text,extraction,seen)
                      SELECT root,path,name,ext,mime,size,modified,created,text,extraction,seen FROM staging WHERE root=?
                      ON CONFLICT(path) DO UPDATE SET
                      name=excluded.name,ext=excluded.ext,mime=excluded.mime,size=excluded.size,
                      modified=excluded.modified,created=excluded.created,text=excluded.text,
                      extraction=excluded.extraction,seen=excluded.seen""", (root["id"],))
                conn.execute("DELETE FROM search WHERE rowid IN (SELECT id FROM files WHERE root=?)", (root["id"],))
                conn.execute("DELETE FROM files WHERE root=? AND seen<>?", (root["id"], generation))
                conn.execute("""INSERT INTO search(rowid,name,path,body)
                  SELECT files.id,staging.name_tokens,staging.path_tokens,staging.body_tokens
                  FROM staging JOIN files ON files.path=staging.path WHERE staging.root=?""", (root["id"],))
                conn.execute("DELETE FROM staging WHERE root=?", (root["id"],))
        if rebuild and complete:
            db.set_state("generation_at", str(time.time()))
            db.set_state("extractor_version", EXTRACTOR_VERSION)
        db.set_state("last_scan", str(time.time()))
        storage.restore_shares()
    except Exception as exc:
        status["error"] = str(getattr(exc, "detail", type(exc).__name__))
    finally:
        status['stage'] = 'stopped' if stop_event.is_set() else 'error' if status['error'] else 'complete'
        status['eta_seconds'] = 0 if status['stage']=='complete' else None
        status["running"] = False
        scan_lock.release()


def worker():
    while not stop_event.is_set():
        scan()
        stop_event.wait(60)


def search(query="", ext="", root=0, after=None, before=None, date_field="modified", offset=0, rerank=False):
    clauses, args = [], []
    join, order = "", "files.modified DESC"
    if query.strip():
        terms = list(dict.fromkeys(tokens(query).split()))[:30]
        if terms:
            join = "JOIN search ON search.rowid=files.id"
            clauses.append("search MATCH ?")
            args.append(" OR ".join('"' + t.replace('"', '""') + '"' for t in terms))
            order = "bm25(search,5.0,1.5,1.0)"
    if ext:
        clauses.append("ext=?")
        args.append("." + ext.lower().lstrip("."))
    if root:
        clauses.append("root=?")
        args.append(root)
    field = "created" if date_field == "created" else "modified"
    for value, operator in ((after, ">="), (before, "<=")):
        if value is not None:
            clauses.append(f"{field}{operator}?")
            args.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    result = db.rows(f"""SELECT files.*, substr(files.text,1,400) AS snippet FROM files {join}{where}
                        ORDER BY {order} LIMIT ? OFFSET ?""", (*args, 100 if rerank else 40, max(0, offset)))
    if rerank and query and result:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vectors = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=20000).fit_transform(
            [query] + [r["name"] + " " + r["text"][:10000] for r in result])
        scores = cosine_similarity(vectors[0], vectors[1:]).ravel()
        result = [result[i] for i in scores.argsort()[::-1]][:40]
    for r in result:
        r.pop("text", None)
        r["path"] = r["path"].split("\n", 1)[-1]
    return result
