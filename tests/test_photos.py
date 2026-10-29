import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = sandbox.name+'/state'
os.environ.setdefault('DASHBOARD_USERNAME', 'test')
os.environ.setdefault('DASHBOARD_PASSWORD', 'test')
os.environ.setdefault('SESSION_SECRET', 'x'*48)
os.environ['EXCLUDED_DIRECTORY_NAMES'] = 'excluded_fixture'
from fastapi import HTTPException
from PIL import Image
from hw_agent import db, photos, storage
from hw_agent.photo_worker import discover
from hw_agent.photo_worker import process
import numpy as np


class PhotoTests(unittest.TestCase):
    def setUp(self):
        db.init(); photos.init()
        with db.connect() as c:
            for table in ['photo_faces','photo_people','photos','photo_roots','roots']:
                c.execute('DELETE FROM '+table)
        db.set_state('photo_paused','0'); db.set_state('shares','{}')
        self.base = Path(tempfile.mkdtemp(dir=sandbox.name))
        self.folder = self.base/'album'; self.folder.mkdir()
        self.device = {'uuid':'photo-test', 'mount':str(self.base)}
        self.mock = patch.object(storage,'devices',return_value=[self.device]);self.mock.start()
        photos.add_root(photos.Folder(path=str(self.folder)))
        self.root = db.rows('SELECT * FROM photo_roots')[0]

    def tearDown(self): self.mock.stop()

    def insert(self, name='test.jpg', captured=100, labels='["people","cards"]'):
        Image.new('RGB',(20,20)).save(self.folder/name)
        with db.connect() as c:
            return c.execute("INSERT INTO photos(root,relative,album,name,kind,captured,labels) VALUES(?,?,'A',?,'photo',?,?)",
                             (self.root['id'],name,name,captured,labels)).lastrowid

    def test_independent_registration_and_offline_removal(self):
        self.assertEqual(db.rows('SELECT * FROM roots'),[])
        self.assertEqual(db.state('shares'),'{}')
        i=self.insert()
        with patch.object(storage,'devices',return_value=[]):
            photos.remove_root(self.root['id'])
        self.assertEqual(db.rows('SELECT * FROM photos'),[])
        self.assertTrue((self.folder/'test.jpg').exists())

    def test_uuid_remount_keeps_identity(self):
        i=self.insert();new=self.base/'renamed';self.folder.rename(new)
        # The mount changes, while the registered relative folder is stable.
        moved=self.base/'newmount';moved.mkdir();new.rename(moved/'album')
        self.device['mount']=str(moved)
        self.assertEqual(photos.safe_media(i)[0],moved/'album/test.jpg')

    def test_date_include_exclude_inclusive(self):
        self.insert('a.jpg',100);self.insert('b.jpg',200);self.insert('c.jpg',300)
        self.assertEqual(photos.items(after=100,before=200)['total'],2)
        self.assertEqual(photos.items(after=100,before=200,exclude=True)['total'],1)
        with self.assertRaises(HTTPException): photos.items(after=300,before=100)

    def test_multilabel_override(self):
        i=self.insert();self.assertEqual(photos.items(topic='cards')['total'],1)
        photos.labels(i,photos.Labels(labels=['documents']))
        self.assertEqual(photos.items(topic='cards')['total'],0)
        self.assertEqual(photos.items(topic='documents')['total'],1)
        photos.labels(i,photos.Labels(labels=None))
        self.assertEqual(photos.items(topic='cards')['total'],1)

    def test_traversal_denied(self):
        i=self.insert()
        with db.connect() as c:c.execute("UPDATE photos SET relative='../escape.jpg' WHERE id=?",(i,))
        Image.new('RGB',(20,20)).save(self.base/'escape.jpg')
        with self.assertRaises(HTTPException): photos.safe_media(i)

    def test_exclusion_before_walk(self):
        protected=self.folder/'excluded_fixture';protected.mkdir()
        Image.new('RGB',(20,20)).save(protected/'never.jpg')
        original=os.scandir
        def guarded(path):
            self.assertNotIn('excluded_fixture',str(path));return original(path)
        with patch('os.scandir',side_effect=guarded):discover(self.root)
        self.assertEqual(db.rows('SELECT * FROM photos'),[])

    def test_live_pair_and_incremental_scan(self):
        Image.new('RGB',(20,20)).save(self.folder/'live.jpg')
        (self.folder/'live.mov').write_bytes(b'fixture')
        with patch('hw_agent.photo_worker.metadata',return_value=(100,'EXIF','pair-id',2)):
            discover(self.root);discover(self.root)
        result=photos.items()
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['kind'],'live')
        self.assertEqual(result['items'][0]['pair_source'],'content_identifier')

    def test_face_rename_and_split(self):
        i=self.insert()
        with db.connect() as c:
            person=c.execute("INSERT INTO photo_people(name) VALUES('')").lastrowid
            face=c.execute("INSERT INTO photo_faces(photo,person,box) VALUES(?,?,'[]')",(i,person)).lastrowid
        photos.rename_person(person,photos.PersonName(name='Test person'))
        self.assertEqual(photos.people()[0]['name'],'Test person')
        self.assertEqual(photos.items(person=person)['total'],1)
        photos.move_face(face,photos.FacePerson(person=0))
        self.assertEqual(photos.items(person=person)['total'],0)

    def test_mp4_codec_fallback(self):
        for codec in ['libx264','mpeg4']:
            path=self.folder/(codec+'.mp4')
            subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','color=size=64x64:rate=5',
                            '-t','0.4','-c:v',codec,'-threads','1',str(path)],capture_output=True,check=True)
            with patch.object(photos,'safe_media',return_value=(path,{})):
                response=photos.media(1)
            self.assertEqual(Path(response.path)==path,codec=='libx264')
            self.assertTrue(Path(response.path).exists())

    def test_face_thumbnail_and_removal(self):
        identifier=self.insert()
        class Model:
            def analyze(self,image):
                embedding=np.zeros(128,dtype=np.float32);embedding[0]=1
                return {'people':.99},[(embedding,[0,0,1,1],image.copy())]
        process(db.rows('SELECT * FROM photos WHERE id=?',(identifier,))[0],Model())
        face=db.rows('SELECT id FROM photo_faces WHERE photo=?',(identifier,))[0]['id']
        response=photos.face_thumbnail(face)
        path=Path(response.path)
        self.assertTrue(path.exists())
        photos.remove_root(self.root['id'])
        self.assertFalse(path.exists())
        with self.assertRaises(HTTPException):photos.face_thumbnail(face)


if __name__=='__main__': unittest.main()
