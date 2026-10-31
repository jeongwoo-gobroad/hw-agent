from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ntfs_reader.catalog import Catalog, Gate
from ntfs_reader.server import ReaderServer, byte_range
from ntfs_reader.windows import NativeReader

TOKEN = 'synthetic-test-key-' * 3


def fixture(base, root='\\\\?\\Volume{synthetic}\\'):
    worker = base / 'real-worker'
    worker.mkdir()
    database = worker / 'inventory.sqlite3'
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript('CREATE TABLE meta(key TEXT,value TEXT); CREATE TABLE entries(identity TEXT,path TEXT,kind TEXT,size INTEGER,status TEXT);')
        connection.execute('INSERT INTO meta VALUES(?,?)', ('root', root))
        connection.executemany('INSERT INTO entries VALUES(?,?,?,?,?)', [
            ('10', root + 'Album\\ready.txt', 'stream', 8, 'done'),
            ('11', root + 'Album\\plain.txt', 'stream', 8, 'uncompressed'),
            ('12', root + 'Album\\pending.txt', 'stream', 8, 'pending'),
            ('13', root + 'Album\\error.txt', 'stream', 8, 'error'),
            ('14', root + 'Confidential\\hidden.txt', 'stream', 8, 'done'),
            ('15', root + 'secret.7z', 'stream', 8, 'done'),
            ('16:alt:$DATA', root + 'Album\\ready.txt:alt:$DATA', 'stream', 8, 'done'),
            ('17', root + '..\\outside.txt', 'stream', 8, 'done'),
        ])
        connection.commit()
    (base / 'real-maintenance-result.json').write_text(json.dumps({'phase':'inventory_and_decompression', 'safe_to_restore':False}))
    (base / 'maintenance-supervisor.json').write_text(json.dumps({'phase':'waiting_resumed_operation','checked_at':time.time()}))
    return {'root':root, 'state_directory':str(base), 'volume_serial':'0', 'token':TOKEN, 'port':0,
            'excluded_names':['Confidential','secret.7z']}


class FakeReader:
    def __init__(self):
        self.reads = 0

    def chunk(self, entry, offset, count):
        self.reads += bool(count)
        return b'abcdefgh'[offset:offset+count]


class ReaderTests(unittest.TestCase):
    def test_catalog_excludes_unfinished_private_ads_and_traversal_without_file_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config = fixture(base)
            catalog = Catalog(base/'real-worker/inventory.sqlite3', config['root'], config['excluded_names'], TOKEN)
            root = catalog.list()
            self.assertEqual([item['name'] for item in root['items']], ['Album'])
            entries = catalog.list(root['items'][0]['id'])['items']
            self.assertEqual([item['name'] for item in entries], ['plain.txt','ready.txt'])
            self.assertNotIn('Volume{', json.dumps(entries))
            ready = entries[1]['id']
            with closing(sqlite3.connect(base/'real-worker/inventory.sqlite3')) as writer:
                writer.execute("UPDATE entries SET status='pending' WHERE identity='10'")
                writer.commit()
            with self.assertRaises(KeyError):
                catalog.lookup(ready)

    def test_ranges(self):
        self.assertEqual(byte_range('bytes=2-4',8), (2,4,True))
        self.assertEqual(byte_range('bytes=-3',8), (5,7,True))
        self.assertEqual(byte_range(None,0), (0,-1,False))
        for header in ('bytes=8-', 'bytes=-0', 'bytes=2-1', 'bytes=0-1,3-4', 'bad'):
            with self.assertRaises(ValueError):
                byte_range(header,8)

    def test_gate_fails_closed_on_stale_state_detach_and_missing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            fixture(base)
            gate=Gate(base)
            self.assertTrue(gate.active())
            (base/'maintenance-supervisor.json').write_text(json.dumps({'phase':'waiting_resumed_operation','checked_at':time.time()-100}))
            self.assertFalse(gate.active())
            (base/'maintenance-supervisor.json').unlink()
            self.assertFalse(gate.active())

    def test_http_auth_origin_ranges_write_denial_and_detach(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            config=fixture(base)
            reader=FakeReader()
            server=ReaderServer(config, reader=reader)
            thread=threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(path, *, method='GET', headers=None, body=None, auth=True):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                all_headers={'Cookie':'alter_reader='+TOKEN} if auth else {}
                all_headers.update(headers or {})
                connection.request(method,path,body=body,headers=all_headers)
                response=connection.getresponse()
                result=response.status,dict(response.getheaders()),response.read()
                connection.close()
                return result
            try:
                self.assertEqual(request('/api/list',auth=False)[0],401)
                self.assertEqual(request('/',auth=False,headers={'Sec-Fetch-Site':'cross-site'})[0],200)
                self.assertEqual(request('/api/list',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
                self.assertEqual(request('/api/list',headers={'Host':'attacker.example'})[0],403)
                self.assertEqual(request('/api/list',headers={'Origin':'https://attacker.example'})[0],403)
                self.assertEqual(request('/api/list',method='POST',headers={'Origin':server.origin},body='{}')[0],405)
                self.assertEqual(request('/api/session',method='POST',auth=False,headers={'Origin':server.origin},body=json.dumps({'token':TOKEN}))[0],200)
                listing=json.loads(request('/api/list?q=ready')[2])
                self.assertEqual(reader.reads,0)
                key=listing['items'][0]['id']
                status,headers,data=request('/api/file/'+key,headers={'Range':'bytes=2-4'})
                self.assertEqual((status,data),(206,b'cde'))
                self.assertEqual(headers['Content-Range'],'bytes 2-4/8')
                self.assertEqual(request('/api/file/'+key,headers={'Range':'bytes=20-'})[0],416)
                self.assertEqual(request('/api/file/unknown')[0],404)
                (base/'real-maintenance-result.json').write_text(json.dumps({'phase':'detaching'}))
                before=reader.reads
                self.assertEqual(request('/api/file/'+key)[0],503)
                self.assertEqual(before,reader.reads)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    @unittest.skipUnless(os.name == 'nt','Windows native metadata and content checks')
    def test_native_reads_only_own_synthetic_file_and_rejects_identity_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            path=base/'fixture.txt'
            path.write_bytes(b'abcdefgh')
            state=path.stat()
            # 실제 합성 파일의 볼륨 일련번호를 메타데이터 핸들에서 얻는다.
            reader=NativeReader(str(base), '0', lambda path:path, lambda:True)
            handle=reader.open(str(path))
            try:
                reader.serial=reader.information(handle).volume
            finally:
                reader.close(handle)
            entry={'path':str(path),'identity':str(state.st_ino),'size':8}
            self.assertEqual(reader.chunk(entry,2,3),b'cde')
            import ctypes as C
            handle=reader.open(str(path))
            try:
                final=C.create_unicode_buffer(32768)
                self.assertGreater(reader.final(handle,final,len(final),1),0)
                guid_path=final.value
            finally:
                reader.close(handle)
            guid_root=guid_path[:guid_path.index('}')+2]
            guid_reader=NativeReader(guid_root,f'{reader.serial:08X}',lambda path:path,lambda:True)
            self.assertEqual(guid_reader.chunk(entry | {'path':guid_path},0,8),b'abcdefgh')
            with self.assertRaises(OSError):
                reader.chunk(entry | {'identity':'1'},0,1)
            os.link(path,base/'second-link.txt')
            with self.assertRaises(OSError):
                reader.chunk(entry,0,1)

            (base/'second-link.txt').unlink()
            reader.active=lambda:False
            with self.assertRaises(OSError):
                reader.chunk(entry,0,1)

    def test_active_transfer_stops_after_detach_starts(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            config=fixture(base)
            with closing(sqlite3.connect(base/'real-worker/inventory.sqlite3')) as writer:
                writer.execute("UPDATE entries SET size=600000 WHERE identity='10'")
                writer.commit()
            class ChangingReader:
                reads=0
                def chunk(self,entry,offset,count):
                    if count:
                        self.reads+=1
                        (base/'real-maintenance-result.json').write_text(json.dumps({'phase':'detaching'}))
                    return b'x'*count
            reader=ChangingReader()
            server=ReaderServer(config,reader=reader)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                key=server.catalog.list(query='ready')['items'][0]['id']
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                connection.request('GET','/api/file/'+key,headers={'Cookie':'alter_reader='+TOKEN})
                response=connection.getresponse()
                with self.assertRaises(http.client.IncompleteRead) as failure:
                    response.read()
                self.assertEqual(len(failure.exception.partial),256*1024)
                self.assertEqual(reader.reads,1)
                connection.close()
            finally:
                server.shutdown();server.server_close();thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
