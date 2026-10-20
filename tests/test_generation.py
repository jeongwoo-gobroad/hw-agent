import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
os.environ["DATA_DIR"] = tempfile.mkdtemp() + "/state"
os.environ.setdefault("DASHBOARD_USERNAME", "test")
os.environ.setdefault("DASHBOARD_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "x" * 48)
from fastapi import HTTPException
from hw_agent import generation


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for token in ('{"intent":"chat","answer":"안', '녕', '하세요', '","query":""}'):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": token}}]})
        yield "data: [DONE]"


class GenerationTests(unittest.TestCase):
    def test_incomplete_string_and_unicode_escape(self):
        self.assertEqual(generation.partial_string('{"answer":"안녕', "answer"), "안녕")
        self.assertEqual(generation.partial_string(r'{"answer":"hi\n\uac', "answer"), "hi\n")
        self.assertEqual(generation.partial_string(r'{"answer":"hi\n\uac00"}', "answer"), "hi\n가")
        self.assertEqual(generation.partial_string(r'{"answer":"say \"yes\""}', "answer"), 'say "yes"')

    def test_deltas_precede_validated_result(self):
        events = []
        with patch.object(generation.httpx, "stream", return_value=Response()):
            result = generation.stream_completion({}, events.append, threading.Event())
        self.assertEqual([e["text"] for e in events], ["안", "안녕", "안녕하세요"])
        self.assertEqual(json.loads(result)["answer"], "안녕하세요")
        self.assertTrue(all("intent" not in event["text"] for event in events))

    def test_cancellation_stops_generation(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch.object(generation.httpx, "stream", return_value=Response()):
            with self.assertRaises(HTTPException) as error:
                generation.stream_completion({}, lambda event: None, cancelled)
        self.assertEqual(error.exception.status_code, 499)


if __name__ == "__main__":
    unittest.main()
