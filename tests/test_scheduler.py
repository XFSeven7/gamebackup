import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup import add_folder
from scheduler import Scheduler


class SchedulerTest(unittest.TestCase):
    def test_schedules_next_scan_using_new_and_migrated_defaults(self):
        for old_interval, expected in ((None, 120), (15, 120), (60, 120), (300, 300)):
            with self.subTest(old_interval=old_interval), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "config.json"
                if old_interval is not None:
                    config.write_text(json.dumps({"interval_sec": old_interval}), encoding="utf-8")
                scheduler = Scheduler(root)
                with patch.object(scheduler, "_arm") as arm:
                    scheduler._run()
                arm.assert_called_once_with(expected)
                if config.exists():
                    self.assertEqual(json.loads(config.read_text(encoding="utf-8"))["interval_sec"], expected)

    def test_generation_stays_when_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            live = Path(d) / "save"
            live.mkdir()
            (live / "s.sav").write_bytes(b"v1")
            add_folder(root, live, "测试")
            sch = Scheduler(root)
            sch._run()
            sch.stop()
            self.assertEqual(sch.generation, 0)

    def test_generation_bumps_when_files_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            live = Path(d) / "save"
            live.mkdir()
            (live / "s.sav").write_bytes(b"v1")
            add_folder(root, live, "测试")
            sch = Scheduler(root)
            time.sleep(0.05)
            (live / "s.sav").write_bytes(b"v2")
            sch._run()
            sch.stop()
            self.assertGreater(sch.generation, 0)


if __name__ == "__main__":
    unittest.main()
