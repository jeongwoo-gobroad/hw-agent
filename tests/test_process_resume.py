"""Abrupt process exit after a committed item must not repeat completed work."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ProcessResumeTests(unittest.TestCase):
    def check_restart(self,kind):
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'DATA_DIR':folder+'/db','FIXTURE_BASE':folder+'/media','FIXTURE_KIND':kind}
            setup=r'''
import os
from pathlib import Path
from unittest.mock import patch
from hw_agent import db,storage,indexing,inventory,photos,photo_worker
from PIL import Image
db.init();photos.init();inventory.init()
base=Path(os.environ['FIXTURE_BASE']);base.mkdir(exist_ok=True)
storage.devices=lambda:[{'uuid':'process-fixture','mount':str(base)}]
kind=os.environ['FIXTURE_KIND'];first=os.environ['FIRST']=='1'
if first:
    if kind=='files':
        for name in ('a.txt','b.txt'):(base/name).write_text(name)
        storage.add_root(base)
    else:
        for name in ('a.jpg','b.jpg'):Image.new('RGB',(32,32),'red').save(base/name)
        photos.add_root(photos.Folder(path=str(base)))
if kind=='files':
    if first:
        original=inventory.acknowledge
        def kill(c,*args,**kwargs):
            original(c,*args,**kwargs);c.commit();os._exit(73)
        inventory.acknowledge=kill
    else:
        prior=db.rows('SELECT path FROM files')[0]['path'].split('\n',1)[-1]
        original=indexing.extract_content
        def checked(path):
            assert path.name!=prior,'committed extraction repeated'
            return original(path)
        indexing.extract_content=checked
    indexing.scan()
    assert len(db.rows('SELECT id FROM files'))==2
    assert inventory.job('files',1)['done']==2
else:
    photo_worker.metadata=lambda path:(100,'fixture',None,0)
    photo_worker.PhotoModels=lambda:None
    completed={r['id'] for r in db.rows("SELECT id FROM photos WHERE scores!='{}'")}
    def process(item,model):
        assert item['id'] not in completed,'committed classification repeated'
        with db.connect() as c:c.execute('UPDATE photos SET scores=?,analysis_version=? WHERE id=?',('{"people":0.9}',photo_worker.MODEL_VERSION,item['id']))
        if first:os._exit(73)
    photo_worker.process=process
    photo_worker.run_scan()
    assert len(db.rows("SELECT id FROM photos WHERE scores!='{}'"))==2
    assert not photo_worker.pending_photos()
'''
            first=subprocess.run([sys.executable,'-c',setup],env={**env,'FIRST':'1'},capture_output=True,text=True,timeout=60)
            self.assertEqual(first.returncode,73,first.stderr)
            second=subprocess.run([sys.executable,'-c',setup],env={**env,'FIRST':'0'},capture_output=True,text=True,timeout=60)
            self.assertEqual(second.returncode,0,second.stderr)

    def test_file_process_restart(self):self.check_restart('files')
    def test_photo_process_restart(self):self.check_restart('photos')


if __name__=='__main__':unittest.main()
