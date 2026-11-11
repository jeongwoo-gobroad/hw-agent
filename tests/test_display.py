import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("brightness", Path(__file__).parents[1] / "scripts/display_brightness.py")
brightness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brightness)


class DisplayTests(unittest.TestCase):
    def test_wait_handles_late_compositor_without_changing_brightness(self):
        with patch.dict(brightness.os.environ, {'WAYLAND_DISPLAY':'wayland-test','XDG_RUNTIME_DIR':'/tmp/runtime'}), \
             patch.object(brightness.socket, 'socket') as factory, \
             patch.object(brightness.time, 'sleep') as sleep, \
             patch.object(brightness, 'change', side_effect=AssertionError('no display input')):
            connection = factory.return_value.__enter__.return_value
            connection.connect.side_effect = [FileNotFoundError(), None]
            brightness.wait_for_display()
            self.assertEqual(connection.connect.call_count, 2)
            connection.connect.assert_called_with('/tmp/runtime/wayland-test')
            sleep.assert_called_once_with(1)

    def test_unavailable_compositor_has_bounded_wait(self):
        with patch.object(brightness.socket, 'socket') as factory, \
             patch.object(brightness.time, 'monotonic', side_effect=[0, 90]), \
             patch.object(brightness.time, 'sleep') as sleep:
            factory.return_value.__enter__.return_value.connect.side_effect = ConnectionRefusedError()
            with self.assertRaisesRegex(RuntimeError, 'startup deadline'): brightness.wait_for_display()
            sleep.assert_not_called()

    def test_repeated_dim_keeps_original_brightness(self):
        with tempfile.TemporaryDirectory() as directory:
            panel = Path(directory) / "panel"
            panel.mkdir()
            (panel / "brightness").write_text("15")
            (panel / "max_brightness").write_text("31")
            state = Path(directory) / "state.json"
            with patch.object(brightness, "PANEL", panel), patch.object(brightness, "STATE", state):
                brightness.change("dim")
                brightness.change("dim")
                self.assertEqual((panel / "brightness").read_text(), "1")
                self.assertEqual(json.loads(state.read_text())["previous"], 15)
                brightness.change("restore")
                self.assertEqual((panel / "brightness").read_text(), "15")
                brightness.change("restore")
                self.assertEqual((panel / "brightness").read_text(), "15")


if __name__ == "__main__":
    unittest.main()
