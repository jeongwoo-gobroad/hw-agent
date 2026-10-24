import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hw_agent.progress import count_files, Estimate


class ProgressTests(unittest.TestCase):
    def test_count_filters_before_entering_and_skips_links(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            (base/'allowed').mkdir()
            (base/'allowed'/'one.jpg').touch()
            (base/'two.txt').touch()
            (base/'.hidden.jpg').touch()
            (base/'excluded-fixture').mkdir()
            (base/'excluded-fixture'/'secret.jpg').touch()
            (base/'link').symlink_to(base/'allowed')
            with patch('hw_agent.progress.storage.excluded', side_effect=lambda p: str(p)=='excluded-fixture'):
                self.assertEqual(count_files(base, lambda:False),2)
                self.assertEqual(count_files(base, lambda:False,{'.jpg'}),1)
            with self.assertRaises(InterruptedError):count_files(base,lambda:True)

    def test_eta_uses_current_work_not_existing_items(self):
        with patch('hw_agent.progress.time.monotonic',side_effect=[100,101,102,106,108]):
            estimate=Estimate()
            self.assertIsNone(estimate.advance(9))
            self.assertIsNone(estimate.advance(8))
            self.assertEqual(estimate.advance(7),14)
            self.assertEqual(estimate.advance(0),0)
