import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import json
from PIL import Image

sandbox=tempfile.TemporaryDirectory()
os.environ['DATA_DIR']=sandbox.name+'/data'
os.environ.setdefault('DASHBOARD_USERNAME','test')
os.environ.setdefault('DASHBOARD_PASSWORD','test')
os.environ.setdefault('SESSION_SECRET','x'*48)
os.environ['EXCLUDED_DIRECTORY_NAMES']='externalNodes'
from fastapi import HTTPException
from hw_agent import db,storage,preview,file_browser,photos,photo_search
from hw_agent.camera import Camera


class Features(unittest.TestCase):
    def setUp(self):
        db.init();photos.init()
        self.folder=Path(tempfile.mkdtemp(dir=sandbox.name))
        self.device={'uuid':'test','mount':str(self.folder)}
        self.mock=patch.object(storage,'devices',return_value=[self.device]);self.mock.start()
        self.root=storage.add_root(self.folder)

    def tearDown(self):self.mock.stop()

    def test_tree_uses_index_roots_only(self):
        (self.folder/'child').mkdir();(self.folder/'note.txt').write_text('text')
        rows=file_browser.entries(self.root['id'])['items']
        self.assertEqual([i['name'] for i in rows],['child','note.txt'])
        self.assertEqual(file_browser.entries(self.root['id'],folders_only=True)['total'],1)
        with self.assertRaises(HTTPException):file_browser.entries(999999)

    def test_protected_path_rejected_before_resolution(self):
        with patch.object(Path,'resolve',side_effect=AssertionError('must not resolve')):
            with self.assertRaises(HTTPException):file_browser.resolve(self.root['id'],'externalNodes/secret.txt')
        (self.folder/'externalNodes').mkdir()
        self.assertEqual(file_browser.entries(self.root['id'])['total'],0)
        with self.assertRaises(HTTPException):file_browser.resolve(self.root['id'],'../escape')

    def test_symlink_and_unregistered_path(self):
        (self.folder/'link').symlink_to('/tmp')
        self.assertEqual(file_browser.entries(self.root['id'])['total'],0)
        with self.assertRaises(HTTPException):file_browser.resolve(self.root['id'],'link')

    def test_code_is_plain_text_and_pdf_is_inline(self):
        code=self.folder/'sample.html';code.write_text('<script>alert(1)</script>')
        output,mime=preview.preview(code,{})
        self.assertTrue(mime.startswith('text/plain'))
        self.assertIn('<script>',output.read_text())
        pdf=self.folder/'sample.pdf';Image.new('RGB',(30,30)).save(pdf)
        result=file_browser.media(self.root['id'],'sample.pdf')
        self.assertEqual(result.media_type,'application/pdf')

    def test_camera_clockwise_and_mirror(self):
        camera=Camera();image=Image.new('RGB',(3,2));image.putpixel((0,0),(255,0,0))
        for rotation,position,dimensions in [(0,(0,0),(3,2)),(90,(1,0),(2,3)),(180,(2,1),(3,2)),(270,(0,2),(2,3))]:
            camera.set_orientation(rotation)
            transformed=camera.orient(image)
            self.assertEqual(transformed.size,dimensions);self.assertEqual(transformed.getpixel(position),(255,0,0))
        camera.set_orientation(0,True,True)
        self.assertEqual(camera.orient(image).getpixel((2,1)),(255,0,0))

    def test_camera_persistence_validation_recording(self):
        camera=Camera();camera.set_orientation(90,True)
        restored=Camera();restored.restore_orientation();self.assertEqual(camera.orientation,restored.orientation)
        with self.assertRaises(HTTPException):camera.set_orientation(45)
        with self.assertRaises(HTTPException):camera.set_orientation(True)
        camera.recording=True
        with self.assertRaises(HTTPException):camera.set_orientation(0)
        self.assertEqual(camera.orientation['rotation'],90)

    def test_chat_named_person_and_unknown_name(self):
        with db.connect() as c:
            c.execute('DELETE FROM photo_faces');c.execute('DELETE FROM photo_people');c.execute('DELETE FROM photos')
            person=c.execute("INSERT INTO photo_people(name) VALUES('테스트인물')").lastrowid
            photo=c.execute("INSERT INTO photos(name,labels,scores,captured) VALUES('fixture','[\"buildings\"]','{}',100)").lastrowid
            c.execute("INSERT INTO photo_faces(photo,person,box) VALUES(?,?,'[]')",(photo,person))
        self.assertEqual(photo_search.search('테스트인물이 나온 사진을 찾아줘',{})['photo_total'],1)
        self.assertEqual(photo_search.search('미등록인물이 나온 사진을 찾아줘',{})['photo_total'],0)
        self.assertEqual(photo_search.search('건물이 나온 사진을 찾아줘',{})['photo_total'],1)


if __name__=='__main__':unittest.main()
