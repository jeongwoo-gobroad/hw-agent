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
