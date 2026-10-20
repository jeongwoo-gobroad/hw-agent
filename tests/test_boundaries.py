import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = sandbox.name + "/state"
os.environ.setdefault("DASHBOARD_USERNAME", "test")
os.environ.setdefault("DASHBOARD_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "a" * 48)
from fastapi import HTTPException
from hw_agent import auth, config, db, flows, indexing, storage, smartthings, chat


class Boundaries(unittest.TestCase):
    def setUp(self):
        db.init()
        with db.connect() as conn:
            for table in ("roots","files","search","staging","flows","runs","state"):
                conn.execute("DELETE FROM " + table)
        self.folder = Path(tempfile.mkdtemp(dir=sandbox.name))
        self.device = {"uuid":"test-drive","mount":str(self.folder)}
        self.patch = patch.object(storage, "devices", return_value=[self.device])
        self.patch.start()
        self.root = storage.add_root(str(self.folder))
        indexing.stop_event.clear()

    def tearDown(self):
        self.patch.stop()

    def test_explicit_search_filters_override_model_omission(self):
        from datetime import date
        class Clock(date):
            @classmethod
            def today(cls): return cls(2026,10,20)
        with patch.object(chat,"calendar_date",Clock):
            plan=chat.explicit_filters("지난달 회의 PDF를 찾아줘",{"after":"2025-09-01"})
        self.assertEqual(plan,{"after":"2026-09-01","before":"2026-09-30","ext":"pdf"})

    def test_symlink_cannot_escape(self):
        (self.folder/"safe.txt").write_text("inside")
        indexing.scan()
        file_id = db.rows("SELECT id FROM files WHERE name='safe.txt'")[0]["id"]
        (self.folder/"safe.txt").unlink()
        outside = Path(sandbox.name)/"secret.txt"
        outside.write_text("private")
        (self.folder/"safe.txt").symlink_to(outside)
        with self.assertRaises(HTTPException) as error:
            storage.safe_file(file_id)
        self.assertEqual(error.exception.status_code,403)

    def test_failed_generation_preserves_active_index(self):
        (self.folder/"before.txt").write_text("original")
        indexing.scan()
        before = db.rows("SELECT path,text FROM files")
        db.set_state("generation_at","0")
        with patch.object(storage,"root_path",side_effect=HTTPException(409,"offline")):
            indexing.scan()
        self.assertEqual(before,db.rows("SELECT path,text FROM files"))
        self.assertEqual(db.state("generation_at"),"0")

    def test_expired_generation_reextracts_unchanged_file(self):
        (self.folder/"test.txt").write_text("alpha")
        indexing.scan()
        with db.connect() as conn:
            conn.execute("UPDATE files SET text='corrupted'")
        db.set_state("generation_at","0")
        indexing.scan()
        self.assertEqual(db.rows("SELECT text FROM files")[0]["text"],"alpha")
        self.assertNotEqual(db.state("generation_at"),"0")

    def test_unknown_creation_time_is_not_ctime(self):
        (self.folder/"test.txt").write_text("alpha")
        indexing.scan()
        self.assertEqual(indexing.search(after=1,date_field="created"),[])
        self.assertTrue(indexing.search(after=1,date_field="modified"))

    def test_flow_failure_is_recorded_without_retry(self):
        steps=[{"type":"device","device_id":"x","capability":"switch","command":"on"},
               {"type":"device","device_id":"y","capability":"switch","command":"off"}]
        with db.connect() as conn:
            conn.execute("INSERT INTO flows VALUES('failure','failure',?)",(json.dumps(steps),))
        with patch.object(flows.smartthings,"command",side_effect=HTTPException(502,"offline")) as command:
            result=flows.execute("failure","request1")
            duplicate=flows.execute("failure","request1")
        self.assertEqual(command.call_count,1)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(duplicate["id"],result["id"])
        self.assertEqual(len(json.loads(result["log"])),1)

    def test_password_change_invalidates_session(self):
        token, csrf = auth.login(config.USERNAME,config.PASSWORD,"unit-test")
        request = SimpleNamespace(cookies={"alter_session":token})
        self.assertIsNotNone(auth.session(request))
        with patch.object(config,"PASSWORD","changed-password"):
            self.assertIsNone(auth.session(request))

    def test_smartthings_rate_limit_does_not_retry_command(self):
        response=SimpleNamespace(status_code=429,is_success=False)
        with patch.object(smartthings,"token",return_value="test-token"), \
             patch.object(smartthings.httpx,"request",return_value=response) as request:
            with self.assertRaises(HTTPException) as error:
                smartthings.request("POST","devices/test/commands",{})
        self.assertEqual(error.exception.status_code,429)
        self.assertEqual(request.call_count,1)

    def test_smartthings_expiry_is_visible(self):
        response=SimpleNamespace(status_code=401,is_success=False)
        with patch.object(smartthings,"token",return_value="test-token"), \
             patch.object(smartthings.httpx,"request",return_value=response):
            with self.assertRaises(HTTPException) as error:
                smartthings.request("GET","devices")
        self.assertEqual(error.exception.status_code,401)
        self.assertEqual(db.state("st_expires"),"0")


if __name__ == "__main__":
    unittest.main()
