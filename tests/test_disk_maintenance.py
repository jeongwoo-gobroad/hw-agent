import io
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


class MaintenanceGuard(unittest.TestCase):
    def test_mount_is_rejected_before_device_access(self):
        helper = Path(__file__).resolve().parents[1] / 'deploy' / 'alter-disk'
        request = io.StringIO('{"action":"mount","device":"/dev/sda1"}')
        errors = io.StringIO()
        with patch('sys.stdin', request), patch('sys.stderr', errors), \
                patch('pathlib.Path.exists', return_value=True), \
                patch('subprocess.check_output') as discovery, \
                patch('subprocess.run') as mutation:
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(helper), run_name='__main__')
        self.assertEqual(result.exception.code, 1)
        self.assertIn('maintenance is active', errors.getvalue())
        discovery.assert_not_called()
        mutation.assert_not_called()


if __name__ == '__main__':
    unittest.main()
