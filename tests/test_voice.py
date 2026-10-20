import base64
import io
import unittest
import wave
from unittest.mock import patch
from fastapi import HTTPException
from hw_agent import voice

class VoiceTests(unittest.TestCase):
    def test_missing_engine(self):
        with patch.object(voice, "status", return_value={"ready":False}):
            with self.assertRaises(HTTPException) as error: voice.transcribe("YQ==")
            self.assertEqual(error.exception.status_code,503)
    def test_invalid_and_oversized(self):
        with patch.object(voice,"status",return_value={"ready":True}):
            for data,code in [("!!!",400),(base64.b64encode(b"a"*1500001).decode(),413)]:
                with self.assertRaises(HTTPException) as error: voice.transcribe(data)
                self.assertEqual(error.exception.status_code,code)
    def test_silence_without_inference(self):
        data=io.BytesIO()
        with wave.open(data,"wb") as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000);stream.writeframes(bytes(32000))
        with patch.object(voice,"status",return_value={"ready":True}):
            self.assertTrue(voice.transcribe(base64.b64encode(data.getvalue()).decode())["silent"])
    def test_single_request(self):
        with patch.object(voice,"status",return_value={"ready":True}):
            voice._lock.acquire()
            try:
                with self.assertRaises(HTTPException) as error: voice.transcribe("YQ==")
                self.assertEqual(error.exception.status_code,409)
            finally: voice._lock.release()

if __name__ == "__main__": unittest.main()
