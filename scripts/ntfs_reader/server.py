import argparse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit

from ntfs_state import write_json_atomic
from .catalog import Catalog, Gate, Unavailable
from .windows import NativeReader

PREVIEW = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
           '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif',
           '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
           '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.txt': 'text/plain; charset=utf-8',
           '.py': 'text/plain; charset=utf-8', '.json': 'text/plain; charset=utf-8',
           '.md': 'text/plain; charset=utf-8', '.csv': 'text/plain; charset=utf-8'}


def byte_range(header, size):
    if not header:
        return 0, size - 1, False
    if size <= 0 or not header.startswith('bytes=') or ',' in header:
        raise ValueError()
    start, end = header[6:].split('-', 1)
    if not start:
        length = int(end)
        if length <= 0:
            raise ValueError()
        start, end = max(0, size - length), size - 1
    else:
        start, end = int(start), min(int(end), size - 1) if end else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError()
    return start, end, True


class ReaderServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, config, *, reader=None):
        self.config = config
        self.token = config['token']
        self.gate = Gate(config['state_directory'])
        self.catalog = Catalog(Path(config['state_directory']) / 'real-worker' / 'inventory.sqlite3',
                               config['root'], config['excluded_names'], self.token)
        self.reader = reader or NativeReader(config['root'], config['volume_serial'], self.catalog.relative, self.gate.active)
        self.transfer = threading.BoundedSemaphore(1)
        self.expiry = time.time() + 12 * 3600
        self.transferred = 0
        super().__init__(('127.0.0.1', config.get('port', 11979)), Handler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)
        self.host_header = '127.0.0.1:' + str(self.server_port)

    def handle_error(self, request, client_address):
        pass  # 요청 경로나 개인 파일명을 로그에 남기지 않는다.

    def monitor(self):
        while self.gate.active() and time.time() < self.expiry:
            time.sleep(.5)
        self.shutdown()


class Handler(BaseHTTPRequestHandler):
    server_version = 'AlterReader'

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, *_):
        pass

    def boundary(self, *, landing=False):
        origin = self.headers.get('Origin')
        return (self.client_address[0] == '127.0.0.1'
                and self.headers.get('Host') == self.server.host_header
                and (not origin or origin == self.server.origin)
                and (landing or self.headers.get('Sec-Fetch-Site') != 'cross-site'))

    def authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            value = cookie['alter_reader'].value
            return secrets.compare_digest(value, self.server.token) and time.time() < self.server.expiry
        except (KeyError, ValueError):
            return False

    def response_headers(self, code, length, content_type, *, extra=None, sandbox=False):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Content-Security-Policy', "sandbox; default-src 'none'" if sandbox else
                         "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def json(self, code, value, extra=None):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.response_headers(code, len(data), 'application/json; charset=utf-8', extra=extra)
        self.wfile.write(data)

    def do_POST(self):
        if not self.boundary() or self.headers.get('Origin') != self.server.origin:
            return self.json(403, {'error': '이 PC의 접근창에서만 사용할 수 있습니다.'})
        if self.path != '/api/session':
            return self.json(405, {'error': '읽기 전용입니다.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 512:
                raise ValueError()
            payload = json.loads(self.rfile.read(length))
            if not secrets.compare_digest(str(payload.get('token', '')), self.server.token):
                raise ValueError()
            return self.json(200, {'ok': True}, {'Set-Cookie': 'alter_reader=' + self.server.token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
        except (ValueError, TypeError):
            return self.json(403, {'error': '프로젝트의 임시 파일 창 실행파일로 열어 주세요.'})

    def do_GET(self):
        url = urlsplit(self.path)
        static = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
        if not self.boundary(landing=url.path in static):
            return self.json(403, {'error': '접근할 수 없습니다.'})
        if url.path in static:
            name = static[url.path]
            data = (Path(__file__).parent / 'static' / name).read_bytes()
            self.response_headers(200, len(data), {'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[Path(name).suffix])
            return self.wfile.write(data)
        if not self.authenticated():
            return self.json(401, {'error': '프로젝트의 임시 파일 창 실행파일로 열어 주세요.'})
        if not self.server.gate.active():
            return self.json(503, {'error': '변환 단계가 끝나 임시 접근을 종료합니다.'})
        try:
            query = parse_qs(url.query)
            if url.path == '/api/status':
                return self.json(200, {'active': True, 'rate_limit_mib': 8})
            if url.path == '/api/list':
                folder = query.get('folder', [''])[0]
                search = query.get('q', [''])[0][:200]
                offset = max(0, int(query.get('offset', ['0'])[0]))
                return self.json(200, self.server.catalog.list(folder, search, offset))
            if url.path.startswith('/api/file/'):
                return self.file(url.path[len('/api/file/'):], query.get('download', ['0'])[0] == '1')
            return self.json(404, {'error': '찾을 수 없습니다.'})
        except (KeyError, ValueError):
            return self.json(404, {'error': '접근 가능한 완료 파일이 아닙니다.'})
        except (OSError, Unavailable, sqlite3.Error):
            return self.json(503, {'error': '파일 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.'})

    def file(self, key, download):
        entry = self.server.catalog.lookup(key)
        try:
            start, end, partial = byte_range(self.headers.get('Range'), entry['size'])
        except ValueError:
            return self.json(416, {'error': '요청 범위가 잘못되었습니다.'}, {'Content-Range': 'bytes */' + str(entry['size'])})
        if not self.server.transfer.acquire(blocking=False):
            return self.json(429, {'error': '다른 파일 전송이 진행 중입니다. 끝난 뒤 다시 시도해 주세요.'})
        sent_headers = False
        try:
            self.server.reader.chunk(entry, 0, 0)
            content_type = PREVIEW.get(Path(entry['name']).suffix.lower())
            disposition = 'attachment' if download or not content_type else 'inline'
            extra = {'Accept-Ranges': 'bytes', 'Content-Disposition': disposition + "; filename*=UTF-8''" + quote(entry['name'], safe='')}
            if partial:
                extra['Content-Range'] = f'bytes {start}-{end}/{entry["size"]}'
            self.response_headers(206 if partial else 200, end - start + 1, content_type or 'application/octet-stream', extra=extra, sandbox=True)
            sent_headers = True
            offset = start
            while offset <= end:
                if not self.server.gate.active() or time.time() >= self.server.expiry:
                    break
                tick = time.monotonic()
                chunk = self.server.reader.chunk(entry, offset, min(256 * 1024, end - offset + 1))
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                offset += len(chunk)
                self.server.transferred += len(chunk)
                time.sleep(max(0, len(chunk) / (8 * 1024 * 1024) - (time.monotonic() - tick)))
        except (OSError, ValueError):
            if not sent_headers:
                self.json(409, {'error': '파일이 변경되었거나 아직 읽을 수 없습니다.'})
        finally:
            self.server.transfer.release()
            self.close_connection = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if len(config['token']) < 32:
        raise SystemExit('Invalid reader configuration')
    server = ReaderServer(config)
    if not server.gate.active():
        server.server_close()
        raise SystemExit('Maintenance conversion is not active')
    status = Path(config['state_directory']) / 'reader-status.json'
    write_json_atomic(status, {'pid': os.getpid(), 'port': server.server_port, 'active': True, 'started_at': time.time()})
    threading.Thread(target=server.monitor, daemon=True).start()
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        write_json_atomic(status, {'pid': os.getpid(), 'port': server.server_port, 'active': False,
                                   'stopped_at': time.time(), 'transferred_bytes': server.transferred})


if __name__ == '__main__':
    main()
