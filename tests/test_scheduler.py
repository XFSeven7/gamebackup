import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup import add_folder
from scheduler import Scheduler


class SchedulerTest(unittest.TestCase):
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
