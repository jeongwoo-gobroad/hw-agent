"""Retry failed entries independently of successful hashes and whole-folder scans."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = sandbox.name + '/state'
os.environ['DASHBOARD_USERNAME'] = 'test'
os.environ['DASHBOARD_PASSWORD'] = 'test-password'
os.environ['SESSION_SECRET'] = 'r' * 48
from hw_agent import db, storage, indexing, inventory, file_retries, config


class FileRetryTests(unittest.TestCase):
    def setUp(self):
        db.init(); inventory.init()
        with db.connect() as c:
            for table in ('file_retries','scan_jobs','scan_dirs','scan_entries','files','search','staging','roots','state'):
                c.execute('DELETE FROM ' + table)
        self.tmp = tempfile.TemporaryDirectory(dir=sandbox.name)
        self.base = Path(self.tmp.name)
        self.devices = patch.object(storage, 'devices', return_value=[{'uuid':'retry-test','mount':str(self.base)}])
        self.devices.start()
        self.root = storage.add_root(self.base)
        indexing.stop_event.clear()

    def tearDown(self):
        self.devices.stop(); self.tmp.cleanup(); indexing.stop_event.clear()

    def fail(self, status='timeout_or_error'):
        with patch.object(indexing, 'extract_content', return_value=('', status)):
            indexing.scan()
        self.assertIsNone(indexing.status['error'])

    def due(self):
        with db.connect() as c: c.execute('UPDATE file_retries SET retry_after=0')

    def test_failed_extraction_retries_unchanged_hash_without_rediscovery(self):
        (self.base/'a.txt').write_text('recovered text')
        self.fail()
        self.assertEqual(len(indexing.search('a')), 1)
        generation = inventory.job('files', self.root['id'])['generation']
        self.due()
        with patch.object(inventory, 'discover', side_effect=AssertionError('completed scan must not restart')):
            indexing.scan(force=False)
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'recovered text')
        self.assertEqual(db.rows('SELECT * FROM file_retries'), [])
        current = inventory.job('files', self.root['id'])
        self.assertEqual((current['generation'],current['done'],current['errors']), (generation,1,0))

    def test_waiting_failures_keep_backoff_across_scan_generations(self):
        (self.base/'a.txt').write_text('fixture')
        self.fail()
        before = db.rows('SELECT attempts,retry_after FROM file_retries')[0]
        with patch.object(indexing, 'extract_content', side_effect=AssertionError('too soon')), \
             patch.object(inventory, 'digest', side_effect=AssertionError('must not reread')):
            indexing.scan()
        self.assertEqual(db.rows('SELECT attempts,retry_after FROM file_retries')[0], before)
        self.due(); self.fail()
        self.assertEqual(db.rows('SELECT attempts FROM file_retries')[0]['attempts'], 2)
        self.assertEqual(indexing.status['stage'], 'waiting_for_retry')

    def test_changed_file_bypasses_backoff_and_preserves_last_text_until_success(self):
        file = self.base/'a.txt'; file.write_text('last valid text'); indexing.scan()
        file.write_text('replacement text')
        self.fail('BadZipFile')
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'last valid text')
        self.assertEqual(len(indexing.search('last valid')), 1)
        file.write_text('newly corrected longer text')
        indexing.scan()
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'newly corrected longer text')
        self.assertEqual(db.rows('SELECT * FROM file_retries'), [])

    def test_legacy_cached_failure_is_never_reused(self):
        (self.base/'a.txt').write_text('correct content'); indexing.scan()
        with db.connect() as c: c.execute("UPDATE files SET text='',extraction='timeout_or_error'")
        indexing.scan()
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'correct content')

    def test_unsupported_and_size_limits_are_not_retried(self):
        (self.base/'a.txt').write_text('fixture')
        for outcome in ('unsupported','size_limit','expanded_size_limit','partial'):
            with self.subTest(outcome=outcome):
                with db.connect() as c: c.execute('DELETE FROM files'); c.execute('DELETE FROM search')
                with patch.object(indexing, 'extract_content', return_value=('',outcome)): indexing.scan()
                self.assertEqual(db.rows('SELECT * FROM file_retries'), [])

    def test_missing_file_is_retried_then_pruned_after_complete_discovery(self):
        file = self.base/'a.txt'; file.write_text('keep'); indexing.scan()
        current = inventory.job('files', self.root['id'])
        entry = db.rows('SELECT id,relative,done FROM scan_entries')[0]
        file.unlink()
        indexing.index_entry(self.root, current, entry, self.base)
        self.assertEqual(len(db.rows('SELECT id FROM files')), 1)
        self.assertEqual(file_retries.summary()['retry_pending'], 1)
        indexing.scan()
        self.assertEqual(db.rows('SELECT id FROM files'), [])
        self.assertEqual(db.rows('SELECT * FROM file_retries'), [])

    def test_offline_retry_preserves_attempts(self):
        (self.base/'a.txt').write_text('fixture'); self.fail(); self.due()
        before = db.rows('SELECT * FROM file_retries')
        with patch.object(storage, 'devices', return_value=[]), \
             patch.object(indexing, 'extract_content', side_effect=AssertionError('offline')):
            indexing.scan(force=False)
        self.assertEqual(db.rows('SELECT * FROM file_retries'), before)
        self.assertEqual(indexing.status['stage'], 'waiting_for_storage')

    def test_stat_failure_respects_existing_backoff(self):
        current = inventory.begin('files', self.root, indexing.EXTRACTOR_VERSION)
        entry = {'id':None, 'relative':'missing.txt', 'done':1}
        indexing.index_entry(self.root, current, entry, self.base)
        before = db.rows('SELECT * FROM file_retries')
        indexing.index_entry(self.root, current, entry, self.base)
        self.assertEqual(db.rows('SELECT * FROM file_retries'), before)

    def test_retry_commit_rolls_back_result_and_queue_together(self):
        (self.base/'a.txt').write_text('fixture')
        with patch.object(indexing, 'extract_content', return_value=('', 'timeout_or_error')), \
             patch.object(file_retries, 'defer', side_effect=RuntimeError('simulated failed commit')):
            indexing.scan()
        self.assertEqual(db.rows('SELECT * FROM files'), [])
        self.assertEqual(db.rows('SELECT * FROM file_retries'), [])
        self.assertEqual(inventory.job('files', self.root['id'])['done'], 0)
        indexing.scan(force=False)
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'fixture')

    def test_successful_retry_replay_does_not_double_count(self):
        (self.base/'a.txt').write_text('fixture'); self.fail(); self.due()
        indexing.retry_due([self.root])
        current = inventory.job('files', self.root['id'])
        entry = db.rows('SELECT id,relative,done FROM scan_entries')[0]
        indexing.index_entry(self.root, current, entry, self.base)
        after = inventory.job('files', self.root['id'])
        self.assertEqual((after['done'],after['errors'],after['changed']), (1,0,1))

    def test_excluded_retry_is_removed_before_filesystem_access(self):
        inventory.begin('files', self.root, indexing.EXTRACTOR_VERSION)
        with db.connect() as c:
            c.execute("INSERT INTO file_retries(root,relative,retry_after) VALUES(?,'private-fixture/item.txt',0)", (self.root['id'],))
        with patch.object(config, 'EXCLUDED_DIRECTORY_NAMES', {'private-fixture'}), \
             patch.object(storage, 'root_path', side_effect=AssertionError('must not touch volume')), \
             patch.object(Path, 'stat', side_effect=AssertionError('must not touch source')):
            indexing.retry_due([self.root])
        self.assertEqual(db.rows('SELECT * FROM file_retries'), [])

    def test_many_offline_retries_do_not_starve_online_root(self):
        online = self.base/'online'; online.mkdir(); (online/'a.txt').write_text('online')
        second = storage.add_root(online)
        for root in (self.root, second): inventory.begin('files', root, indexing.EXTRACTOR_VERSION)
        with db.connect() as c:
            c.executemany('INSERT INTO file_retries(root,relative,retry_after) VALUES(?,?,0)',
                          [(self.root['id'],f'{i}.txt') for i in range(70)]+[(second['id'],'a.txt')])
        real = storage.root_path
        def root_path(root):
            if root['id'] == self.root['id']: raise storage.StorageUnavailable()
            return real(root)
        with patch.object(storage, 'root_path', side_effect=root_path): indexing.retry_due([self.root,second])
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'online')
        self.assertEqual(len(db.rows('SELECT * FROM file_retries')), 70)

    def test_due_retry_does_not_wait_for_other_pending_entries(self):
        (self.base/'a.txt').write_text('fixture'); self.fail(); self.due()
        with db.connect() as c:
            c.execute("UPDATE scan_jobs SET stage='processing'")
        real = inventory.pending
        def pending(*args):
            self.assertEqual(db.rows('SELECT * FROM file_retries'), [])
            return real(*args)
        with patch.object(inventory, 'pending', side_effect=pending): indexing.scan(force=False)
        self.assertIsNone(indexing.status['error'])

    def test_retry_budget_and_worker_wakeup(self):
        self.assertEqual([file_retries.delay(i) for i in (1,2,9,10,1000)], [300,600,76800,86400,86400])
        waits=[]
        def scan(**_): indexing.status.update(waiting_roots=[], retry_next_at=indexing.time.time()+30)
        def wait(seconds): waits.append(seconds); indexing.stop_event.set()
        with patch.object(indexing, 'scan', side_effect=scan), patch.object(indexing.stop_event, 'wait', side_effect=wait): indexing.worker()
        self.assertTrue(10 <= waits[0] <= 30)

    def test_queue_survives_a_fresh_process(self):
        (self.base/'a.txt').write_text('persistent content'); self.fail()
        code = '''
import os
from hw_agent import db,indexing,storage
storage.devices=lambda:[{'uuid':'retry-test','mount':os.environ['TEST_MOUNT']}]
assert db.rows('SELECT attempts FROM file_retries')[0]['attempts']==1
with db.connect() as c:c.execute('UPDATE file_retries SET retry_after=0')
indexing.scan(force=False)
assert db.rows('SELECT * FROM file_retries')==[]
assert db.rows('SELECT text FROM files')[0]['text']=='persistent content'
'''
        result = subprocess.run([sys.executable,'-c',code], env={**os.environ,'TEST_MOUNT':str(self.base)},
                                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
