import ctypes
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'ntfs_state', Path(__file__).parents[1] / 'scripts' / 'ntfs_state.py',
)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class StateTests(unittest.TestCase):
    def test_persistent_denial_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'progress.json'
            path.write_text('{"changed": 1}')
            with patch.object(state.os, 'replace', side_effect=PermissionError(13, 'test lock')):
                with self.assertRaises(PermissionError):
                    state.write_json_atomic(path, {'changed': 2}, timeout=0)
            self.assertEqual(json.loads(path.read_text()), {'changed': 1})
            self.assertEqual(list(Path(folder).iterdir()), [path])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows sharing semantics')
    def test_real_windows_reader_lock_releases_before_replace(self):
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.restype = W.HANDLE
        kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p,
                                      W.DWORD, W.DWORD, W.HANDLE]
        kernel.CloseHandle.argtypes = [W.HANDLE]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'progress.json'
            path.write_text('{"changed": 1}')
            handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            release = threading.Timer(0.2, lambda: kernel.CloseHandle(handle))
            release.start()
            try:
                with patch.object(state.os, 'replace', wraps=state.os.replace) as replace:
                    state.write_json_atomic(path, {'changed': 2}, timeout=3)
                    self.assertGreater(replace.call_count, 1)
                self.assertEqual(json.loads(path.read_text()), {'changed': 2})
                self.assertEqual(list(Path(folder).iterdir()), [path])
            finally:
                release.join()


if __name__ == '__main__':
    unittest.main()
