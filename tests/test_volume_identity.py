import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = sandbox.name + "/state"
os.environ.setdefault("DASHBOARD_USERNAME", "test")
os.environ.setdefault("DASHBOARD_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "a" * 48)
from fastapi import HTTPException
from hw_agent import db, storage


class VolumeIdentity(unittest.TestCase):
    def setUp(self):
        db.init()
        with db.connect() as connection:
            connection.execute("DELETE FROM roots")
            connection.execute("DELETE FROM files")
        self.folder = Path(tempfile.mkdtemp(dir=sandbox.name))
        self.first = self.folder / "old-mount"
        self.second = self.folder / "new-mount"
        (self.first / "docs").mkdir(parents=True)
        self.second.mkdir()
        self.device = {"uuid": "volume-a", "mount": str(self.first)}

    def test_mount_change_preserves_root_and_file_ids(self):
        with patch.object(storage, "devices", return_value=[self.device]):
            root = storage.add_root(self.first / "docs")
            (self.first / "docs/note.txt").write_text("test")
            with db.connect() as connection:
                connection.execute("INSERT INTO files(id,root,path,name) VALUES(?,?,?,?)",
                                   (77, root["id"], f"{root['id']}\nnote.txt", "note.txt"))
            (self.first / "docs").rename(self.second / "docs")
            self.device["mount"] = str(self.second)
            again = storage.add_root(self.second / "docs")
            self.assertEqual(root["id"], again["id"])
            self.assertEqual(len(db.rows("SELECT * FROM roots")), 1)
            path, record = storage.safe_file(77)
            self.assertEqual(path, self.second / "docs/note.txt")
            self.assertEqual(record["id"], 77)

    def test_same_mount_different_volume_is_new_identity(self):
        with patch.object(storage, "devices", return_value=[self.device]):
            first = storage.add_root(self.first / "docs")
            self.device["uuid"] = "volume-b"
            second = storage.add_root(self.first / "docs")
            self.assertNotEqual(first["id"], second["id"])
            with self.assertRaises(HTTPException):
                storage.root_path(first)

    def test_duplicate_uuid_refuses_ambiguous_volume(self):
        clone = {**self.device, "mount": str(self.second)}
        with patch.object(storage, "devices", return_value=[self.device, clone]):
            with self.assertRaises(HTTPException) as error:
                storage.add_root(self.first / "docs")
            self.assertEqual(error.exception.status_code, 409)

    def test_legacy_schema_keeps_root_id(self):
        with db.connect() as connection:
            connection.execute("DROP TABLE roots")
            connection.execute("""CREATE TABLE roots(
                id INTEGER PRIMARY KEY,path TEXT UNIQUE,uuid TEXT,mount TEXT,label TEXT)""")
            connection.execute("INSERT INTO roots VALUES(?,?,?,?,?)",
                               (90, str(self.first / "docs"), "volume-a", str(self.first), "docs"))
        db.init()
        root = db.rows("SELECT * FROM roots")[0]
        self.assertEqual((root["id"], root["relative_path"]), (90, "docs"))


if __name__ == "__main__":
    unittest.main()
