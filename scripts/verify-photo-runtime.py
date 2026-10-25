"""Exercise the installed models on synthetic images without opening user media."""
import json
import os
from pathlib import Path
import resource
import tempfile
import time
from PIL import Image,ImageDraw
from tqdm import tqdm

with tempfile.TemporaryDirectory(prefix='alter-photo-runtime-') as folder:
    os.environ['DATA_DIR']=folder
    from hw_agent import photo_models
    started=time.monotonic()
    model=photo_models.PhotoModels()
    image=Image.new('RGB',(1920,1440),'white')
    draw=ImageDraw.Draw(image)
    for row in range(20):draw.text((180,100+row*50),'SYNTHETIC DOCUMENT 12345 '*6,fill='black')
    for _ in tqdm(range(8),desc='사진 모델 검증',unit='장'):
        scores,faces=model.analyze(image)
        assert set(scores)==set(photo_models.TOPICS)
    del model
    model=photo_models.PhotoModels()
    assert len(list(Path(folder).glob('photo-text-*.npy')))==1
    scores,faces=model.analyze(image)
    print(json.dumps({'images':9,'prompt_cache_reused':True,'elapsed_seconds':round(time.monotonic()-started,1),
                      'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
                      'topics':len(scores),'faces_on_fixture':len(faces)}))
