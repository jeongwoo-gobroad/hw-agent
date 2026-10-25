import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from hw_agent import db,storage,indexing,inventory,photos,photo_worker
from PIL import Image


class ResumeTests(unittest.TestCase):
    def setUp(self):
        db.init();photos.init();inventory.init()
        with db.connect() as c:
            for table in ['scan_jobs','scan_dirs','scan_entries','files','staging','search','roots','photos','photo_roots','photo_faces','photo_people','state']:
                c.execute('DELETE FROM '+table)
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.patch=patch.object(storage,'devices',return_value=[{'uuid':'resume-test','mount':str(self.base)}]);self.patch.start()
        self.root=storage.add_root(self.base)
        indexing.stop_event.clear();photo_worker.stopping=False

    def tearDown(self):
        self.patch.stop();self.tmp.cleanup();indexing.stop_event.clear()

    def test_hash_unchanged_metadata_and_same_content(self):
        file=self.base/'a.txt';file.write_text('first')
        indexing.scan()
        with patch.object(inventory,'digest',side_effect=AssertionError('no hash needed')),patch.object(indexing,'tokens',side_effect=AssertionError('no FTS rewrite')):
            indexing.scan()
        os.utime(file,(123456,123456))
        with patch.object(indexing,'extract_content',side_effect=AssertionError('same content')):
            indexing.scan()
        file.write_text('other');os.utime(file,(123456,123456))
        indexing.scan()
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'],'other')
        self.assertEqual(indexing.status['changed'],1)

    def test_resume_committed_file_skips_extraction(self):
        for name in ('a.txt','b.txt'):(self.base/name).write_text(name)
        original=inventory.acknowledge
        def interrupt(c,current,entry,**kw):
            original(c,current,entry,**kw);c.commit();indexing.stop_event.set()
        with patch.object(inventory,'acknowledge',side_effect=interrupt):indexing.scan()
        completed=db.rows('SELECT path FROM files')[0]['path'].split('\n',1)[1]
        self.assertEqual(inventory.job('files',self.root['id'])['done'],1)
        indexing.stop_event.clear()
        original_extract=indexing.extract_content
        def checked(path):
            self.assertNotEqual(path.name,completed);return original_extract(path)
        with patch.object(indexing,'extract_content',side_effect=checked):indexing.scan()
        self.assertEqual(len(db.rows('SELECT id FROM files')),2)
        self.assertTrue(indexing.status['resumed'])

    def test_discovery_resumes_after_completed_directory(self):
        (self.base/'sub').mkdir();(self.base/'sub'/'a.txt').write_text('a')
        current=inventory.begin('files',self.root,'test')
        def cancelled():
            return bool(db.rows("SELECT 1 FROM scan_dirs WHERE relative='' AND done=1"))
        with self.assertRaises(InterruptedError):inventory.discover(current,self.base,cancelled)
        real=os.scandir
        def guarded(path):
            self.assertNotEqual(Path(path),self.base);return real(path)
        with patch('os.scandir',side_effect=guarded):current=inventory.discover(current,self.base,lambda:False)
        self.assertEqual(current['total'],1)

    def test_legacy_staging_preserves_extraction(self):
        file=self.base/'a.txt';file.write_text('legacy');stat=file.stat();key=str(self.root['id'])+'\na.txt'
        with db.connect() as c:
            c.execute('INSERT INTO staging VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (self.root['id'],key,'a.txt','.txt','text/plain',stat.st_size,stat.st_mtime,None,'legacy','ok','old','a','a','legacy'))
        with patch.object(indexing,'extract_content',side_effect=AssertionError('use staged result')):indexing.scan()
        self.assertEqual(db.rows('SELECT text FROM files')[0]['text'],'legacy')
        self.assertEqual(db.rows('SELECT * FROM staging'),[])

    def test_photo_hash_preserves_faces_and_labels_on_touch(self):
        photos.add_root(photos.Folder(path=str(self.base)))
        root=db.rows('SELECT * FROM photo_roots')[0]
        file=self.base/'a.jpg';Image.new('RGB',(32,32),'red').save(file)
        with patch.object(photo_worker,'metadata',return_value=(100,'test',None,0)):photo_worker.discover(root)
        item=db.rows('SELECT * FROM photos')[0]
        with db.connect() as c:
            c.execute('UPDATE photos SET scores=?,analysis_version=? WHERE id=?',('{"people":0.99}',photo_worker.MODEL_VERSION,item['id']))
            person=c.execute("INSERT INTO photo_people(name) VALUES('Named')").lastrowid
            c.execute("INSERT INTO photo_faces(photo,person,box) VALUES(?,?,'[]')",(item['id'],person))
        os.utime(file,(123456,123456))
        with patch.object(photo_worker,'metadata',side_effect=AssertionError('hash unchanged')):photo_worker.discover(root)
        self.assertEqual(photo_worker.pending_photos(),[])
        self.assertEqual(len(db.rows('SELECT * FROM photo_faces')),1)
        Image.new('RGB',(32,32),'blue').save(file)
        with patch.object(photo_worker,'metadata',return_value=(100,'test',None,0)):photo_worker.discover(root)
        self.assertEqual(len(photo_worker.pending_photos()),1)
        self.assertEqual(db.rows('SELECT * FROM photo_faces'),[])

    def test_unreadable_file_keeps_old_index_and_does_not_block_next(self):
        first=self.base/'a.txt';first.write_text('keep')
        indexing.scan()
        (self.base/'b.txt').write_text('next')
        with db.connect() as c:c.execute('UPDATE files SET hash_checked=0')
        real=inventory.digest
        def read(path,cancelled):
            if path==first:raise PermissionError('fixture')
            return real(path,cancelled)
        with patch.object(inventory,'digest',side_effect=read):indexing.scan()
        self.assertEqual({r['name']:r['text'] for r in db.rows('SELECT name,text FROM files')},{'a.txt':'keep','b.txt':'next'})
        self.assertEqual(inventory.job('files',self.root['id'])['errors'],1)
        self.assertEqual(indexing.status['errors'],1)

    def test_analysis_version_and_progress_are_durable(self):
        from hw_agent import photo_runtime
        photos.add_root(photos.Folder(path=str(self.base)))
        root=db.rows('SELECT * FROM photo_roots')[0]
        Image.new('RGB',(32,32),'red').save(self.base/'a.jpg')
        with patch.object(photo_worker,'metadata',return_value=(100,'test',None,0)):photo_worker.discover(root)
        with db.connect() as c:c.execute("UPDATE photos SET scores=?,analysis_version=?",('{"people":0.9}','previous-model'))
        self.assertEqual(len(photo_worker.pending_photos()),1)
        photos.init()
        self.assertEqual(db.rows('SELECT analysis_version FROM photos')[0]['analysis_version'],'previous-model')
        photo_runtime.write(stage='classifying',done=12,total=20)
        self.assertIn('12',db.state('photo_progress'))
        self.assertEqual(photo_runtime.read()['done'],12)


if __name__=='__main__':unittest.main()
