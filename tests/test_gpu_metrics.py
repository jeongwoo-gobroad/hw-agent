"""V3D counter semantics: overlap, reset and unavailability must stay distinct."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hw_agent.gpu_metrics import V3dMetrics


class GpuMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.stats = root / "card1/device/gpu_stats"
        self.stats.parent.mkdir(parents=True)
        self.sampler = V3dMetrics(root)

    def write(self, stamp, render, compute, cpu=0):
        self.stats.write_text(f"queue timestamp jobs runtime\nrender {stamp} 1 {render}\ncsd {stamp} 1 {compute}\ncpu {stamp} 1 {cpu}\n")
        self.sampler.sampled_at = -10

    def test_overlapping_engines_are_not_added_and_cpu_queue_is_excluded(self):
        self.write(100, 10, 10)
        self.assertIsNone(self.sampler.snapshot()["gpu_percent"])
        self.write(200, 70, 90, 1000)
        result = self.sampler.snapshot()
        self.assertEqual(result["gpu_engines"], {"render": 60., "csd": 80.})
        self.assertEqual(result["gpu_percent"], 80.)

    def test_counter_reset_and_unavailable_are_not_zero(self):
        self.write(100, 50, 50)
        self.sampler.snapshot()
        self.write(10, 0, 0)
        self.assertIsNone(self.sampler.snapshot()["gpu_percent"])
        self.stats.unlink()
        self.sampler.sampled_at = -10
        result = self.sampler.snapshot()
        self.assertIsNone(result["gpu_percent"])
        self.assertIsNone(result["gpu_source"])

    def test_idle_is_zero_only_after_two_valid_samples(self):
        self.write(100, 10, 10)
        self.sampler.snapshot()
        self.write(200, 10, 10)
        self.assertEqual(self.sampler.snapshot()["gpu_percent"], 0.)

    def test_frequent_clients_reuse_the_same_sample(self):
        self.write(100, 10, 10)
        with patch("hw_agent.gpu_metrics.time.monotonic", return_value=100):
            first = self.sampler.snapshot()
            self.stats.unlink()
            self.assertEqual(self.sampler.snapshot(), first)


if __name__ == "__main__":
    unittest.main()
