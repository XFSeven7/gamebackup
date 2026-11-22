import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dulwich.repo import Repo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup import add_folder, repo_dir
from scheduler import Scheduler
from store import graph


class SchedulerTest(unittest.TestCase):
    def test_event_backup_keeps_only_the_last_sample_before_and_the_first_after(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            live = Path(d) / "MortalShell2" / "Saved" / "SaveGames"
            live.mkdir(parents=True)
            save = live / "WorldState_0.sav"
            save.write_text("0:start")
            item = add_folder(root, live, "Mortal Shell 2")
            repo = repo_dir(root, item.id)

            def read_state(_kind, directory, _tools):
                return {"stage": (directory / save.name).read_text().split(":")[0]}

            with (
                patch("event_backup.read_event_state", side_effect=read_state),
                patch("event_backup.major_events", side_effect=lambda _kind, old, new: ["Boss"] if old != new else []),
            ):
                for content in ("0:first", "0:middle", "0:before"):
                    save.write_text(content)
                    scheduler = Scheduler(root)
                    with patch.object(scheduler, "_arm"):
                        scheduler._run()
                    self.assertEqual(len(graph(repo, False, "main")["nodes"]), 1)
                    self.assertEqual(scheduler.generation, 0)
                save.write_text("1:after")
                scheduler = Scheduler(root)
                with patch("event_backup._event_commit", side_effect=[b"unused-parent", OSError("disk busy")]):
                    with patch.object(scheduler, "_arm"):
                        scheduler._run()
                    self.assertEqual(len(graph(repo, False, "main")["nodes"]), 1)
                    self.assertEqual(scheduler.generation, 0)
                with patch.object(scheduler, "_arm"):
                    scheduler._run()

            with Repo(str(repo)) as history:
                after = history[history.head()]
                before = history[after.parents[0]]
                self.assertEqual(history[history[after.tree][save.name.encode()][1]].data, b"1:after")
                self.assertEqual(history[history[before.tree][save.name.encode()][1]].data, b"0:before")
            self.assertEqual(len(graph(repo, True, "main")["nodes"]), 3)
            self.assertEqual(scheduler.generation, 1)

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
