import hashlib
import hmac
import json
import ntpath
from pathlib import Path
import sqlite3
import threading
import time


class Unavailable(Exception):
    pass


class Gate:
    def __init__(self, state_directory):
        self.base = Path(state_directory)

    def active(self):
        try:
            windows = json.loads((self.base / 'real-maintenance-result.json').read_text(encoding='utf-8-sig'))
            supervisor = json.loads((self.base / 'maintenance-supervisor.json').read_text(encoding='utf-8-sig'))
            return (windows.get('phase') == 'inventory_and_decompression'
                    and not windows.get('safe_to_restore')
                    and supervisor.get('phase') in ('waiting_native_operation', 'waiting_resumed_operation')
                    and 0 <= time.time() - supervisor['checked_at'] < 90)
        except (OSError, ValueError, KeyError, TypeError):
            return False


class Catalog:
    def __init__(self, database, root, excluded_names, secret):
        self.database = Path(database)
        self.root = ntpath.normpath(root).rstrip('\\') + '\\'
        self.excluded = {name.casefold() for name in excluded_names}
        self.secret = secret.encode()
        self.lock = threading.Lock()
        self.loaded_at = 0
        self.entries = {}
        self.folders = {}

    def identifier(self, kind, value):
        return hmac.new(self.secret, (kind + ':' + value).encode(), hashlib.sha256).hexdigest()[:32]

    def relative(self, path):
        if not path.casefold().startswith(self.root.casefold()):
            return None
        relative = path[len(self.root):]
        parts = relative.split('\\')
        if any(not part or part in ('.', '..') or ':' in part or '/' in part
               or part.casefold() in self.excluded for part in parts):
            return None
        if ntpath.normpath(path).casefold() != path.casefold():
            return None
        return relative

    def refresh(self, force=False):
        with self.lock:
            if not force and time.monotonic() - self.loaded_at < 15:
                return
            connection = sqlite3.connect(self.database.resolve().as_uri() + '?mode=ro', uri=True, timeout=.5)
            try:
                connection.execute('PRAGMA query_only=ON')
                recorded = connection.execute("SELECT value FROM meta WHERE key='root'").fetchone()
                if not recorded or ntpath.normcase(ntpath.normpath(recorded[0])) != ntpath.normcase(ntpath.normpath(self.root)):
                    raise Unavailable()
                entries, folders = {}, {'': ''}
                for identity, path, size in connection.execute(
                    "SELECT identity,path,size FROM entries WHERE kind='stream' AND status IN ('done','uncompressed')"
                ):
                    relative = self.relative(path)
                    if relative is None or not identity.isdecimal():
                        continue
                    key = self.identifier('file', identity)
                    entries[key] = {'id': key, 'identity': identity, 'path': path, 'relative': relative,
                                    'name': ntpath.basename(relative), 'parent': ntpath.dirname(relative), 'size': size}
                    parent = ntpath.dirname(relative)
                    while parent:
                        folders[self.identifier('folder', parent)] = parent
                        parent = ntpath.dirname(parent)
            finally:
                connection.close()
            self.entries, self.folders = entries, folders
            self.loaded_at = time.monotonic()

    def list(self, folder='', query='', offset=0):
        self.refresh()
        with self.lock:
            if folder not in self.folders:
                raise KeyError()
            parent = self.folders[folder]
            items = []
            if not query:
                for key, relative in self.folders.items():
                    if key and ntpath.dirname(relative) == parent:
                        items.append({'id': key, 'name': ntpath.basename(relative), 'kind': 'folder'})
            for entry in self.entries.values():
                if (query and query.casefold() in entry['name'].casefold()) or (not query and entry['parent'] == parent):
                    items.append({key: entry[key] for key in ('id', 'name', 'size')} | {'kind': 'file', 'folder': entry['parent']})
            items.sort(key=lambda item: (item['kind'] != 'folder', item['name'].casefold()))
            breadcrumbs = [{'id': '', 'name': '전체 폴더'}]
            current = ''
            for part in parent.split('\\') if parent else []:
                current = ntpath.join(current, part)
                breadcrumbs.append({'id': self.identifier('folder', current), 'name': part})
            return {'items': items[offset:offset + 100], 'total': len(items), 'offset': offset,
                    'breadcrumbs': breadcrumbs, 'available_files': len(self.entries)}

    def lookup(self, key):
        self.refresh()
        with self.lock:
            entry = self.entries[key].copy()
        # 전송 직전에 DB 상태를 다시 확인한다. 목록 캐시만 믿고 파일을 열지 않는다.
        connection = sqlite3.connect(self.database.resolve().as_uri() + '?mode=ro', uri=True, timeout=.5)
        try:
            connection.execute('PRAGMA query_only=ON')
            row = connection.execute('SELECT path,status,size FROM entries WHERE identity=?', (entry['identity'],)).fetchone()
            if not row or row[0] != entry['path'] or row[1] not in ('done', 'uncompressed') or row[2] != entry['size']:
                raise KeyError()
        finally:
            connection.close()
        return entry
