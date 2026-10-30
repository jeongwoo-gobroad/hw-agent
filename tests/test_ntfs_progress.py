import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'ntfs_progress_snapshot', Path(__file__).resolve().parents[1] / 'scripts' / 'ntfs_progress_snapshot.py'
)
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


class ProgressSnapshotTests(unittest.TestCase):
    def test_counts_only_committed_compressed_streams_and_exposes_no_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            worker = base / 'real-worker'; worker.mkdir()
            database = worker / 'inventory.sqlite3'
            with closing(sqlite3.connect(database)) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('CREATE TABLE entries(kind TEXT,status TEXT,size INTEGER,format INTEGER,path TEXT)')
                writer.executemany('INSERT INTO entries VALUES(?,?,?,?,?)', [
                    ('stream','done',100,2,'private-file-name'),
                    ('stream','pending',900,2,'private-other-name'),
                    ('stream','uncompressed',500,0,'already-plain'),
                    ('directory','done',0,1,'private-folder-name'),
                ])
                writer.commit()
                writer.execute("UPDATE entries SET status='done' WHERE status='pending'")
                (base / 'real-maintenance-result.json').write_text(json.dumps({'phase':'detaching','error':'private-error-path'}))
                snapshot = progress.snapshot(base)
                self.assertEqual(snapshot['inventory']['stream'], {
                    'total':2,'done':1,'pending':1,'error':0,'logical_bytes':1000,'done_bytes':100,
                })
                self.assertEqual(snapshot['inventory']['directory']['done'],1)
                self.assertNotIn('private-',json.dumps(snapshot))
                self.assertEqual(snapshot['windows_phase'],'detaching')
                writer.rollback()

    def test_missing_state_never_creates_a_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            snapshot = progress.snapshot(base)
            self.assertIsNone(snapshot['inventory'])
            self.assertFalse((base / 'real-worker').exists())


if __name__ == '__main__':
    unittest.main()
