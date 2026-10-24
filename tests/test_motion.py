import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = sandbox.name
os.environ.setdefault("DASHBOARD_USERNAME", "test")
os.environ.setdefault("DASHBOARD_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "x" * 48)
from fastapi import HTTPException
from hw_agent import db
from hw_agent.motion import Motion, PresenceGate, LABELS


class GateTests(unittest.TestCase):
    def test_hold_then_fire_once_for_continuous_presence(self):
        gate = PresenceGate(hold=2)
        self.assertFalse(gate.update(True, 0))
        self.assertFalse(gate.update(True, 1))
        self.assertFalse(gate.update(True, 1.9))
        self.assertTrue(gate.update(True, 2))
        for t in range(3, 21):
            self.assertFalse(gate.update(True, t))

    def test_short_flicker_does_not_rearm(self):
        gate = PresenceGate(hold=1)
        gate.update(True, 0)
        self.assertTrue(gate.update(True, 1))
        gate.update(False, 1.1)
        gate.update(True, 1.2)
        self.assertFalse(gate.update(True, 2.2))

    def test_absence_rearms_with_cooldown(self):
        gate = PresenceGate(hold=1, release=2, cooldown=5)
        gate.update(True, 0)
        self.assertTrue(gate.update(True, 1))
        gate.update(False, 2)
        gate.update(False, 4)
        self.assertFalse(gate.update(True, 5))
        self.assertTrue(gate.update(True, 6))

    def test_slow_positive_frames_do_not_count_as_absence(self):
        gate = PresenceGate(hold=2, release=.3)
        self.assertFalse(gate.update(True, 0))
        self.assertFalse(gate.update(True, 1))
        self.assertTrue(gate.update(True, 2))
        self.assertFalse(gate.update(True, 10))

    def test_repeat_respects_interval(self):
        gate = PresenceGate(hold=1, cooldown=5, repeat=True)
        gate.update(True, 0)
        self.assertTrue(gate.update(True, 1))
        for t in (2, 3, 4, 5):
            self.assertFalse(gate.update(True, t))
        self.assertTrue(gate.update(True, 6))

    def test_interrupted_hold_starts_again(self):
        gate = PresenceGate(hold=2)
        gate.update(True, 0)
        gate.update(False, 1)
        self.assertFalse(gate.update(True, 1.5))
        self.assertFalse(gate.update(True, 2.5))
        self.assertFalse(gate.update(True, 3))
        self.assertTrue(gate.update(True, 3.5))


class MotionTests(unittest.TestCase):
    def setUp(self):
        db.init()
        with db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO flows VALUES(?,?,?)", ("test-flow", "Test", '[{"type":"delay","seconds":0}]'))
        self.motion = Motion()

    def test_save_all_six_rules_and_reload(self):
        rules = {key: {"hold_seconds": 2, "repeat": True, "repeat_seconds": 10, "release_seconds": 3} for key in LABELS}
        with patch.object(self.motion, "load"):
            self.motion.configure(True, {key: "test-flow" for key in LABELS}, rules)
        saved = json.loads(db.state("motion_config"))
        self.assertEqual(saved["rules"], rules)
        restored = Motion()
        with patch.object(restored, "load"):
            restored.configure(**saved)
        self.assertTrue(restored.gates["Face"].repeat)
        self.assertEqual(restored.gates["Face"].hold, 2)

    def test_reject_invalid_rule_and_unknown_flow(self):
        for rules in ({"Face": {"hold_seconds": 0}}, {"Face": {"repeat_seconds": 1}}, {"Face": {"hold_seconds": float("nan")}}, {"invalid": {}}):
            with self.assertRaises(HTTPException):
                self.motion.configure(False, {}, rules)
        with self.assertRaises(HTTPException):
            self.motion.configure(True, {"Face": "missing"})

    def test_bounded_dispatch_skips_when_busy(self):
        self.motion.mappings = {"Face": "test-flow"}
        self.motion.dispatch_lock.acquire()
        self.motion.consume({"Face": .99}, 0)
        self.motion.consume({"Face": .99}, 1)
        self.assertEqual(self.motion.last_event["status"], "skipped_busy")
        self.motion.dispatch_lock.release()

    def test_event_runs_real_delay_flow(self):
        self.motion.mappings = {"Face": "test-flow"}
        self.motion.consume({"Face": .99}, 0)
        self.motion.consume({"Face": .99}, 1)
        self.assertTrue(self.motion.dispatch_lock.acquire(timeout=3))
        self.motion.dispatch_lock.release()
        self.assertEqual(self.motion.last_event["status"], "completed")


if __name__ == "__main__":
    unittest.main()
