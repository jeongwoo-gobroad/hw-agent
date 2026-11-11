"""Video sampling tolerates an empty tail without hiding a wholly unreadable clip."""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = sandbox.name + '/state'
os.environ['DASHBOARD_USERNAME'] = 'test'
os.environ['DASHBOARD_PASSWORD'] = 'test-password'
os.environ['SESSION_SECRET'] = 'a' * 48
from PIL import Image
from hw_agent import db, photos, photo_worker as worker


class MediaDecodingTests(unittest.TestCase):
    def setUp(self):
        db.init(); photos.init()
        worker.stopping = False
        db.set_state('photo_paused', '0')
        buffer = io.BytesIO()
        Image.new('RGB', (16, 16), 'red').save(buffer, 'JPEG')
        self.jpeg = buffer.getvalue()

    def run_frames(self, metadata, outputs):
        calls = []
        def run(args, **_):
            if args[0] == 'ffprobe':
                return SimpleNamespace(stdout=json.dumps(metadata).encode())
            calls.append(args)
            result = next(outputs)
            if isinstance(result, Exception): raise result
            return SimpleNamespace(stdout=result)
        with patch.object(worker.subprocess, 'run', side_effect=run):
            frames = list(worker.frames(Path('synthetic.mp4'), True))
        return frames, calls

    def test_empty_tail_and_failed_seek_keep_valid_frame(self):
        frames, _ = self.run_frames({'format':{'duration':'2'}},
            iter([self.jpeg, b'', subprocess.CalledProcessError(1, 'ffmpeg')]))
        self.assertEqual(len(frames), 1)

    def test_stream_duration_precedes_longer_audio_and_fallback_uses_start(self):
        frames, calls = self.run_frames({'streams':[{'duration':'2'}], 'format':{'duration':'20'}},
                                       iter([b'', b'', b'', self.jpeg]))
        self.assertEqual([float(c[c.index('-ss')+1]) for c in calls], [.2, 1, 1.8, 0])
        self.assertEqual(len(frames), 1)

    def test_missing_or_nonfinite_duration_samples_start(self):
        for duration in (None, 'N/A', 'nan', 'inf', '-1'):
            with self.subTest(duration=duration):
                frames, calls = self.run_frames({'format':{'duration':duration}}, iter([self.jpeg]))
                self.assertEqual(len(frames), 1)
                self.assertEqual(calls[0][calls[0].index('-ss')+1], '0')

    def test_no_valid_frame_is_failure(self):
        with self.assertRaises(worker.VideoDecodeError):
            self.run_frames({'format':{'duration':'2'}}, iter([b'bad jpeg', b'', b'', b'']))

    def test_pause_is_not_swallowed(self):
        with patch.object(worker, 'paused', return_value=True):
            with self.assertRaises(InterruptedError):
                self.run_frames({}, iter([self.jpeg]))

    def test_real_short_clip_and_live_pair_finish(self):
        with tempfile.TemporaryDirectory(dir=sandbox.name) as directory:
            clip = Path(directory) / 'short.mp4'
            still = Path(directory) / 'still.jpg'
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                            'color=c=blue:s=64x64:r=1', '-frames:v', '2', '-c:v', 'libx264',
                            '-threads', '1', str(clip)], capture_output=True, check=True)
            Image.new('RGB', (16,16), 'red').save(still)
            self.assertGreaterEqual(len(list(worker.frames(clip, True))), 1)
            with db.connect() as c:
                identifier = c.execute("INSERT INTO photos(root,relative,album,name,kind,live_relative,attempts,error,retry_after) VALUES(1,'still.jpg','','still.jpg','live','short.mp4',8,'old error',123)").lastrowid
            item = db.rows('SELECT * FROM photos WHERE id=?', (identifier,))[0]
            class Model:
                def analyze(self, image): return {'buildings':.8}, []
            with patch.object(photos, 'safe_media', side_effect=lambda _, live=False:(clip if live else still, {})):
                worker.process(item, Model())
            result = db.rows('SELECT error,attempts,retry_after,analysis_version FROM photos WHERE id=?', (identifier,))[0]
            self.assertEqual(result, {'error':None,'attempts':0,'retry_after':0.0,'analysis_version':worker.MODEL_VERSION})
            self.assertTrue((photos.CACHE / f'{identifier}.jpg').is_file())

    def test_retry_backoff_is_bounded(self):
        self.assertEqual([worker.retry_delay(i) for i in (None, 0, 1, 2, 3, 9, 10, 254)],
                         [300, 300, 300, 600, 1200, 76800, 86400, 86400])

    def test_large_still_is_oriented_after_reduction_and_closed_before_yield(self):
        with tempfile.TemporaryDirectory(dir=sandbox.name) as directory:
            path = Path(directory) / 'rotated.jpg'
            with Image.new('RGB', (4000, 2000), 'red') as image:
                exif = image.getexif(); exif[274] = 6
                image.save(path, exif=exif)
            source = Image.open(path)
            with patch.object(worker.Image, 'open', return_value=source):
                sequence = worker.frames(path)
                frame = next(sequence)
                self.assertEqual(frame.size, (960, 1920))
                self.assertIsNone(source.fp)
                with self.assertRaises(ValueError): source.getpixel((0, 0))
                sequence.close()


if __name__ == '__main__': unittest.main()
