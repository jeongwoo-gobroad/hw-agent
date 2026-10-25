"""Disposable media only; never enumerates existing drive content."""
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import httpx
from PIL import Image, ImageDraw
from hw_agent import auth, config, db, storage


def main():
    token, csrf = auth.login(config.USERNAME, config.PASSWORD, 'photo-verification')
    client = httpx.Client(base_url='http://127.0.0.1:11977', headers={'Cookie':'alter_session='+token,
                            'X-CSRF-Token':csrf}, timeout=240)
    assert httpx.get('http://127.0.0.1:11977/api/photos/items').status_code == 401
    assert client.post('/api/photos/scan',headers={'X-CSRF-Token':''}).status_code == 403
    listing = storage.devices()
    device = next(d for d in listing if d['mount'])
    folder = Path(device['mount'])/('Alter-Photo-Verification-'+uuid.uuid4().hex[:8])
    folder.mkdir()
    album=folder/'Demo album';album.mkdir()
    portrait=config.DATA/'vision-fixtures/portrait.jpg'
    shutil.copy2(portrait,album/'Portrait.jpg')
    shutil.copy2(portrait,album/'Portrait again.jpg')
    shutil.copy2(portrait,album/'Live.jpg')
    canvas=Image.new('RGB',(800,600),'ivory');draw=ImageDraw.Draw(canvas)
    draw.rectangle((120,100,680,500),fill='white',outline='black',width=3)
    draw.text((180,160),'ALTER DEMO DOCUMENT',fill='black')
    for y in range(210,460,30):draw.line((180,y,610,y),fill='gray',width=2)
    canvas.save(album/'Document.jpg')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-loop','1','-i',str(album/'Live.jpg'),'-t','2',
                    '-vf','scale=480:-2','-c:v','libx264','-pix_fmt','yuv420p',str(album/'Live.mov')],check=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i','testsrc=size=480x320:rate=10',
                    '-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(album/'Video.mp4')],check=True)
    for path in album.iterdir():
        subprocess.run(['exiftool','-overwrite_original','-DateTimeOriginal=2026:10:01 12:00:00',
                        '-CreateDate=2026:10:01 12:00:00',str(path)],capture_output=True,check=True)
    before=(db.rows('SELECT * FROM roots'),db.state('shares'))
    client.post('/api/photos/roots',json={'path':str(folder)}).raise_for_status()
    root=next(r for r in client.get('/api/photos/roots').json() if r['path']==str(folder))
    (config.DATA/'photo-verification.json').write_text(json.dumps({'folder':str(folder),'root':root['id']}))
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        response=client.get('/api/photos/items',params={'root':root['id']}).json()
        if response['total']==5 and all(i['scores'] for i in response['items']):break
        time.sleep(2)
    assert response['total']==5, response
    assert all(i['scores'] and not i['error'] for i in response['items']),response
    live=next(i for i in response['items'] if i['kind']=='live')
    assert client.get(f"/api/photos/items/{live['id']}/thumbnail").headers['content-type']=='image/jpeg'
    assert client.get(f"/api/photos/items/{live['id']}/media?live=true").headers['content-type']=='video/mp4'
    video=next(i for i in response['items'] if i['kind']=='video')
    assert client.get(f"/api/photos/items/{video['id']}/media",headers={'Range':'bytes=0-99'}).status_code==206
    people=client.get('/api/photos/people').json()
    assert any(p['count']>=3 for p in people), people
    person=next(p for p in people if p['count']>=3)
    client.patch('/api/photos/people/'+str(person['id']),json={'name':'검증용 인물'}).raise_for_status()
    assert client.get('/api/photos/items',params={'person':person['id']}).json()['total']>=3
    assert before==(db.rows('SELECT * FROM roots'),db.state('shares'))
    print(json.dumps({'passed':True,'media':5,'face_group_media':person['count'],'root':root['id'],
                      'model_scores':[(i['name'],i['scores']) for i in response['items']]},ensure_ascii=False))


if __name__=='__main__':main()
