"""Official sample images verify positive inference; this is not an accuracy benchmark."""
import json
import time
import uuid
import urllib.request
from PIL import Image
from hw_agent.config import DATA
from hw_agent.motion import Motion
from hw_agent import db


def main():
    folder = DATA / "vision-fixtures"
    folder.mkdir(exist_ok=True)
    cases = {"portrait.jpg": "Face", "thumb_up.jpg": "Thumb_Up", "victory.jpg": "Victory", "fist.jpg": "Closed_Fist"}
    report = {}
    model = Motion()
    test_flow = uuid.uuid4().hex
    try:
        model.load()
        model.enabled = True
        for name, expected in cases.items():
            target = folder / name
            if not target.exists():
                with urllib.request.urlopen("https://storage.googleapis.com/mediapipe-assets/" + name, timeout=30) as response:
                    target.write_bytes(response.read())
            with Image.open(target) as image:
                model.detect(image)
            assert not model.error and expected in model.observed, (name, model.observed, model.error)
            report[name] = model.observed
        model.detect(Image.new("RGB", (640, 480)))
        assert not model.observed and not model.error
        report["blank"] = {}
        with db.connect() as conn:
            conn.execute("INSERT INTO flows VALUES(?,?,?)", (test_flow, "Vision fixture test", '[{"type":"delay","seconds":0}]'))
        model.mappings = {"Face": test_flow}
        model.gates["Face"].hold = .3
        with Image.open(folder / "portrait.jpg") as image:
            model.detect(image)
            time.sleep(.4)
            model.detect(image)
        assert model.dispatch_lock.acquire(timeout=3)
        model.dispatch_lock.release()
        assert model.last_event and model.last_event["status"] == "completed"
        report["face_to_delay_flow"] = "completed"
    finally:
        model.close()
        with db.connect() as conn:
            conn.execute("DELETE FROM runs WHERE flow=?", (test_flow,))
            conn.execute("DELETE FROM flows WHERE id=?", (test_flow,))
    (DATA / "vision-fixture-report.json").write_text(json.dumps(report, indent=2))
    print("4 positive fixtures, blank negative and face-to-Flow passed")


if __name__ == "__main__":
    main()
