import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ntfs_progress_eta import estimate


def sample(at, done, *, now=None, operation='one'):
    return {
        'operation_id': operation, 'sampled_at': at if now is None else now,
        'recorded_at': at, 'recorded_done_bytes': done,
        'windows_phase': 'inventory_and_decompression', 'worker_phase': 'decompressing',
        'supervisor_age_seconds': 1,
        'inventory': {'stream': {'done_bytes': done, 'pending': 2,
            'pending_bytes': 10000, 'error_bytes': 900000, 'next_pending_bytes': 1000}},
    }


class EtaTests(unittest.TestCase):
    def history(self):
        _, history = estimate(sample(100, 1000), {})
        return history

    def test_confirmed_rate_and_bounded_in_file_estimate_exclude_errors(self):
        result, history = estimate(sample(200, 3000, now=230), self.history(), io_active=True)
        self.assertEqual(result['bytes_per_second'], 20)
        self.assertEqual(result['seconds_high'], 500)
        self.assertEqual(result['seconds_low'], 470)
        later, _ = estimate(sample(200, 3000, now=400), history, io_active=True)
        self.assertEqual(later['seconds_low'], 450)  # 다음 파일의 용량까지 미리 차감하지 않는다.
        stopped, _ = estimate(sample(200, 3000, now=400), history)
        self.assertEqual(stopped['seconds_low'], 500)

    def test_restart_counter_rollback_and_short_interval_collect_again(self):
        for current in (sample(200, 3000, operation='two'), sample(200, 999), sample(101, 3000)):
            result, _ = estimate(current, self.history())
            self.assertEqual(result['status'], 'collecting')

    def test_detach_stale_and_inconsistent_state_never_predict_completion(self):
        for field, value, status in [('windows_phase', 'detaching', 'inactive'),
                                     ('supervisor_age_seconds', 100, 'stale'),
                                     ('recorded_done_bytes', 6000, 'inconsistent')]:
            current = sample(200, 3000)
            current[field] = value
            result, _ = estimate(current, self.history())
            self.assertEqual(result['status'], status)
            self.assertIsNone(result['seconds_low'])

    def test_history_uses_recent_window_and_finishes_only_current_pass(self):
        history = self.history()
        for at in range(200, 11001, 100):
            result, history = estimate(sample(at, at * 20), history)
        self.assertLessEqual(result['window_seconds'], 7300)
        current = sample(11100, 222000)
        current['inventory']['stream'].update(pending=0, pending_bytes=0)
        result, _ = estimate(current, history)
        self.assertEqual(result['status'], 'pass_finished')
        self.assertIsNone(result['seconds_low'])

    def test_cli_persists_only_aggregate_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'history.json'
            current = sample(100, 1000)
            current['private_path'] = 'private-do-not-copy'
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts' / 'ntfs_progress_eta.py'), '--history', str(path)]
            result = subprocess.run(command, input=json.dumps(current), text=True, capture_output=True, check=True)
            saved = path.read_text(encoding='utf-8')
            self.assertNotIn('private-', saved + result.stdout)
            self.assertEqual(set(json.loads(saved)), {'version', 'operation_id', 'samples'})
            self.assertEqual(json.loads(result.stdout)['status'], 'collecting')


if __name__ == '__main__':
    unittest.main()
