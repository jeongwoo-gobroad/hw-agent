import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = sandbox.name
os.environ.setdefault("DASHBOARD_USERNAME", "test")
os.environ.setdefault("DASHBOARD_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "a" * 48)
from fastapi import HTTPException
from hw_agent import db, photos

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).parents[1] / "scripts/recover.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        db.init()
        photos.init()
        with db.connect() as connection:
            connection.execute("DELETE FROM roots")
            connection.execute("DELETE FROM photo_roots")
        db.set_state("shares", "{}")

    def test_mounts_share_only_volume_without_index_root(self):
        db.set_state("shares", '{"files":{"uuid":"share-only"}}')
        devices = [{"uuid": "share-only", "mount": None, "path": "/dev/sdc1"}]
        with patch.object(recovery.storage, "devices", return_value=devices), \
             patch.object(recovery.storage, "restore_shares"), \
             patch.object(recovery.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(recovery.restore_storage(), {"registered": 1, "missing": 0})
            self.assertIn("/dev/sdc1", run.call_args.kwargs["input"])
        self.assertEqual(db.rows("SELECT * FROM roots"), [])

    def test_mounts_only_registered_uuid(self):
        db.init()
        with db.connect() as connection:
            connection.execute("INSERT INTO roots(path,uuid,mount,label) VALUES(?,?,?,?)",
                               ("/mnt/test/folder", "known", "/mnt/test", "test"))
        devices = [{"uuid": "known", "mount": None, "path": "/dev/sda1"},
                   {"uuid": "unregistered", "mount": None, "path": "/dev/sdb1"}]
        with patch.object(recovery.storage, "devices", return_value=devices), \
             patch.object(recovery.storage, "restore_shares"), \
             patch.object(recovery.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(recovery.restore_storage(), {"registered": 1, "missing": 0})
            self.assertEqual(run.call_count, 1)
            self.assertIn("/dev/sda1", run.call_args.kwargs["input"])

    def test_refreshes_once_after_expired_access(self):
        with patch.object(recovery.smartthings, "devices",
                          side_effect=[HTTPException(401, "expired"), [{}, {}]]) as devices:
            self.assertEqual(recovery.check_smartthings(), 2)
            self.assertEqual(devices.call_count, 2)

    def test_does_not_loop_revoked_refresh(self):
        with patch.object(recovery.smartthings, "devices",
                          side_effect=HTTPException(409, "reconnect")) as devices:
            with self.assertRaises(HTTPException):
                recovery.check_smartthings()
            self.assertEqual(devices.call_count, 1)


if __name__ == "__main__":
    unittest.main()
