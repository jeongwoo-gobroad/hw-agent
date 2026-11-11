"""Failed file work survives scan generations without invalidating successful results."""
import json
import re
import time
from . import db, inventory

ACCEPTED = {'ok', 'partial', 'unsupported', 'size_limit', 'expanded_size_limit'}


def fingerprint(stat):
    return json.dumps(inventory.fingerprint(stat), sort_keys=True) if stat is not None else ''


def get(root, relative):
    rows = db.rows('SELECT * FROM file_retries WHERE root=? AND relative=?', (root, relative))
    return rows[0] if rows else None


def delay(attempts):
    return min(86400, 300 * 2 ** min(9, max(0, attempts - 1)))


def error_code(code):
    return code if re.fullmatch(r'[A-Za-z0-9_]{1,80}', str(code)) else 'ExtractionError'


def defer(c, root, relative, code, stat, current, entry):
    previous = c.execute('SELECT * FROM file_retries WHERE root=? AND relative=?', (root, relative)).fetchone()
    stamp = fingerprint(stat)
    attempts = previous['attempts'] + 1 if previous and previous['fingerprint'] == stamp else 1
    code = error_code(code)
    c.execute('''INSERT INTO file_retries(root,relative,attempts,retry_after,error,fingerprint)
      VALUES(?,?,?,?,?,?) ON CONFLICT(root,relative) DO UPDATE SET attempts=excluded.attempts,
      retry_after=excluded.retry_after,error=excluded.error,fingerprint=excluded.fingerprint''',
      (root, relative, attempts, time.time() + delay(attempts), code, stamp))
    acknowledge_wait(c, root, relative, current, entry)


def acknowledge_wait(c, root, relative, current, entry):
    if current and entry and not entry.get('done', 0):
        inventory.acknowledge(c, current, entry, error=True)
        c.execute('UPDATE file_retries SET counted_generation=? WHERE root=? AND relative=?',
                  (current['generation'], root, relative))


def recovered(c, root, relative, current, entry, reused):
    previous = c.execute('SELECT counted_generation FROM file_retries WHERE root=? AND relative=?', (root, relative)).fetchone()
    if current and previous and previous[0] == current['generation'] and entry and entry.get('done', 0):
        c.execute('''UPDATE scan_jobs SET errors=max(0,errors-1),reused=reused+?,changed=changed+?
          WHERE kind='files' AND root=? AND generation=?''',
          (int(reused), int(not reused), root, current['generation']))
    c.execute('DELETE FROM file_retries WHERE root=? AND relative=?', (root, relative))


def summary():
    row = db.rows('''SELECT count(*) n,min(retry_after) next_at,
      COALESCE(sum(retry_after<=?),0) due FROM file_retries WHERE root IN (SELECT id FROM roots)''', (time.time(),))[0]
    return {'retry_pending':row['n'], 'retry_due':row['due'], 'retry_next_at':row['next_at']}
