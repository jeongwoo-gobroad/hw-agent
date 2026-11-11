"""Storage arriving after boot must resume work without losing queue entries."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = sandbox.name + '/state'
os.environ['DASHBOARD_USERNAME'] = 'test'
os.environ['DASHBOARD_PASSWORD'] = 'test-password'
os.environ['SESSION_SECRET'] = 'a' * 48
from fastapi import HTTPException
from PIL import Image
from hw_agent import config, db, inventory, indexing, storage, photos, photo_worker


class StorageResumeTests(unittest.TestCase):
    def setUp(self):
        db.init(); photos.init(); inventory.init()
        with db.connect() as c:
            for table in ('file_retries','roots','files','staging','search','photo_roots','photos','photo_faces',
                          'photo_people','scan_jobs','scan_dirs','scan_entries','state'):
                c.execute('DELETE FROM ' + table)
        self.directory = tempfile.TemporaryDirectory(dir=sandbox.name)
        self.base = Path(self.directory.name)
        self.device = {'uuid':'fixture-volume','mount':str(self.base)}
        self.probe = patch.object(storage, 'devices', return_value=[self.device])
        self.probe.start()
        self.root = storage.add_root(self.base)
        indexing.stop_event.clear()
        photo_worker.stopping = False

    def tearDown(self):
        self.probe.stop(); self.directory.cleanup(); indexing.stop_event.clear()

    def test_boot_without_mount_keeps_queue_then_resumes_same_generation(self):
        (self.base / 'example.txt').write_text('fixture')
        current = inventory.begin('files', self.root, indexing.EXTRACTOR_VERSION)
        with patch.object(storage, 'devices', return_value=[]): indexing.scan(force=False)
        self.assertEqual(indexing.status['stage'], 'waiting_for_storage')
        self.assertIsNone(indexing.status['error'])
        self.assertEqual(indexing.status['waiting_roots'], [self.root['id']])
        indexing.scan(force=False)
        self.assertEqual(indexing.status['stage'], 'complete')
        self.assertEqual(inventory.job('files', self.root['id'])['generation'], current['generation'])
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'], 'fixture')

    def test_worker_retries_waiting_storage_without_ten_minute_delay(self):
        waits = []
        def scan(**_): indexing.status['waiting_roots'] = [self.root['id']]
        def wait(seconds): waits.append(seconds); indexing.stop_event.set()
        with patch.object(indexing, 'scan', side_effect=scan), patch.object(indexing.stop_event, 'wait', side_effect=wait):
            indexing.worker()
        self.assertEqual(waits, [10])

    def test_disconnection_during_read_leaves_item_pending(self):
        (self.base / 'example.txt').write_text('fixture')
        def disconnected(*_):
            self.device['mount'] = None
            raise OSError('fixture disconnect')
        with patch.object(inventory, 'digest', side_effect=disconnected): indexing.scan()
        current = inventory.job('files', self.root['id'])
        self.assertEqual((current['done'], current['errors']), (0, 0))
        self.assertEqual(indexing.status['stage'], 'waiting_for_storage')
        self.device['mount'] = str(self.base)
        indexing.scan(force=False)
        self.assertEqual(inventory.job('files', self.root['id'])['generation'], current['generation'])
        self.assertEqual(len(db.rows('SELECT id FROM files')), 1)

    def test_lost_directory_during_discovery_is_not_acknowledged_as_deleted(self):
        current = inventory.begin('files', self.root, 'fixture')
        with patch.object(inventory.os, 'scandir', side_effect=FileNotFoundError), \
             patch.object(storage, 'root_path', side_effect=storage.StorageUnavailable()):
            with self.assertRaises(storage.StorageUnavailable):
                inventory.discover(current, self.base, lambda:False, validate=lambda:storage.root_path(self.root))
        self.assertEqual(db.rows('SELECT done FROM scan_dirs')[0]['done'], 0)
        self.assertEqual(inventory.job('files', self.root['id'])['stage'], 'discovering')

    def test_missing_photo_folder_is_offline_even_if_volume_is_mounted(self):
        folder = self.base / 'album'; folder.mkdir()
        photos.add_root(photos.Folder(path=str(folder)))
        folder.rmdir()
        self.assertFalse(photos.roots()[0]['online'])
        with self.assertRaises(storage.StorageUnavailable): photos.root_path(photos.roots()[0])

    def test_remount_uses_uuid_and_preserves_root_identity(self):
        replacement = self.base / 'new-mount'; replacement.mkdir()
        self.device['mount'] = str(replacement)
        self.assertEqual(storage.root_path(self.root), replacement)
        saved = db.rows('SELECT * FROM roots')[0]
        self.assertEqual((saved['id'], saved['uuid']), (self.root['id'], self.root['uuid']))

    def test_exclusion_is_checked_before_any_filesystem_lookup(self):
        root = {**self.root, 'relative_path':'private-fixture'}
        with patch.object(config, 'EXCLUDED_DIRECTORY_NAMES', {'private-fixture'}), \
             patch.object(Path, 'resolve', side_effect=AssertionError('must not access')), \
             patch.object(storage, 'devices', side_effect=AssertionError('must not probe')):
            with self.assertRaises(HTTPException) as caught: storage.registered_path(root)
        self.assertEqual(caught.exception.status_code, 403)

    def test_symlink_root_is_rejected_before_following_target(self):
        target = self.base / 'target'; target.mkdir()
        (self.base / 'alias').symlink_to(target)
        with self.assertRaises(HTTPException) as caught:
            storage.registered_path({**self.root, 'relative_path':'alias'})
        self.assertEqual(caught.exception.status_code, 403)

    def test_offline_photos_do_not_consume_classification_attempts(self):
        Image.new('RGB', (16,16), 'red').save(self.base / 'sample.jpg')
        photos.add_root(photos.Folder(path=str(self.base)))
        root = db.rows('SELECT * FROM photo_roots')[0]
        with patch.object(photo_worker, 'metadata', return_value=(100,'fixture',None,0)):
            photo_worker.discover(root)
        before = db.rows('SELECT id,attempts,retry_after,error FROM photos')
        with patch.object(storage, 'devices', return_value=[]), \
             patch.object(photo_worker, 'PhotoModels', side_effect=AssertionError('must not load')):
            photo_worker.run_scan()
        self.assertEqual(before, db.rows('SELECT id,attempts,retry_after,error FROM photos'))
        self.assertEqual(db.state('photo_waiting_storage'), '1')
        self.assertEqual(photos.status()['stage'], 'waiting_for_storage')
        self.assertIsNone(photos.status()['eta_seconds'])
        def process(item, _):
            with db.connect() as c:
                c.execute('UPDATE photos SET scores=?,analysis_version=? WHERE id=?',
                          ('{"people":0.9}',photo_worker.MODEL_VERSION,item['id']))
        with patch.object(photo_worker, 'PhotoModels', return_value=None), \
             patch.object(photo_worker, 'process', side_effect=process): photo_worker.run_scan()
        self.assertEqual(db.state('photo_waiting_storage'), '0')
        self.assertFalse(photo_worker.pending_photos())

    def test_failed_photos_back_off_and_log_codes_without_paths(self):
        Image.new('RGB', (16,16), 'red').save(self.base / 'sample.jpg')
        photos.add_root(photos.Folder(path=str(self.base)))
        root = db.rows('SELECT * FROM photo_roots')[0]
        with patch.object(photo_worker, 'metadata', return_value=(100,'fixture',None,0)):
            photo_worker.discover(root)
        for attempt in (1, 2):
            with db.connect() as c: c.execute('UPDATE photos SET retry_after=0')
            with patch.object(photos, 'safe_media', side_effect=PermissionError('private-path-do-not-log')), \
                 self.assertLogs(photo_worker.logger, level='WARNING') as log:
                before = photo_worker.time.time()
                photo_worker.run_scan()
            item = db.rows('SELECT attempts,retry_after,error FROM photos')[0]
            self.assertEqual(item['attempts'], attempt)
            self.assertGreaterEqual(item['retry_after'], before + photo_worker.retry_delay(attempt))
            self.assertFalse(photo_worker.pending_photos())
            self.assertIn('PermissionError', ' '.join(log.output))
            self.assertNotIn('private-path-do-not-log', ' '.join(log.output))

    def test_memory_recycle_commits_item_and_keeps_remaining_queue(self):
        for name in ('a.jpg', 'b.jpg'):
            Image.new('RGB', (16,16), 'red').save(self.base / name)
        photos.add_root(photos.Folder(path=str(self.base)))
        root = db.rows('SELECT * FROM photo_roots')[0]
        with patch.object(photo_worker, 'metadata', return_value=(100,'fixture',None,0)):
            photo_worker.discover(root)
        generation = inventory.job('photos', root['id'])['generation']
        class Model:
            def analyze(self, image): return {'people':.9}, []
        with patch.object(photo_worker, 'PhotoModels', return_value=Model()), \
             patch.object(photo_worker, 'resident_bytes', return_value=photo_worker.CLASSIFICATION_RSS_LIMIT):
            photo_worker.run_scan()
            self.assertEqual(len(photo_worker.pending_photos()), 1)
            self.assertEqual(db.state('photo_classify_pending'), '1')
            self.assertEqual(db.state('photo_active_item'), '')
            photo_worker.run_scan()
            self.assertFalse(photo_worker.pending_photos())
            self.assertEqual(db.state('photo_classify_pending'), '0')
        self.assertEqual(inventory.job('photos', root['id'])['generation'], generation)
        self.assertEqual(db.rows('SELECT count(*) n FROM photos WHERE error IS NOT NULL')[0]['n'], 0)

    def test_photo_disconnect_after_availability_check_restores_attempt_count(self):
        Image.new('RGB', (16,16), 'red').save(self.base / 'sample.jpg')
        photos.add_root(photos.Folder(path=str(self.base)))
        root = db.rows('SELECT * FROM photo_roots')[0]
        with patch.object(photo_worker, 'metadata', return_value=(100,'fixture',None,0)):
            photo_worker.discover(root)
        with patch.object(photo_worker, 'PhotoModels', return_value=None), \
             patch.object(photo_worker, 'process', side_effect=storage.StorageUnavailable()):
            photo_worker.run_scan()
        item = db.rows('SELECT attempts,retry_after,error FROM photos')[0]
        self.assertEqual(item, {'attempts':0, 'retry_after':0.0, 'error':None})
        self.assertEqual(db.state('photo_active_item'), '')
        self.assertEqual(photos.status()['stage'], 'waiting_for_storage')


if __name__ == '__main__': unittest.main()
