import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup import add_folder, repo_dir
from app import Api
from config import load
from scheduler import Scheduler
from storage import backup_root, lock_backup_instance, migrate_backup
from store import add_tag, graph


class BackupLocationTest(unittest.TestCase):
    def test_moves_history_and_tools_and_preserves_live_saves(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "old"
            target = base / "new"
            target.mkdir()
            live = base / "live"
            live.mkdir()
            save_file = live / "game.sav"
            save_file.write_bytes(b"progress")
            item = add_folder(source, live, "Game")
            repo = repo_dir(source, item.id)
            history = graph(repo, hide_auto=False, current_line="main")
            add_tag(repo, history["current_id"], "checkpoint")
            history = graph(repo, hide_auto=False, current_line="main")
            (source / "tools").mkdir()
            (source / "tools" / "catalog.tsv").write_bytes(b"catalog")

            self.assertIsNone(migrate_backup(source, target, default_root=source))

            self.assertEqual(backup_root(source), target)
            self.assertFalse(source.exists())
            self.assertEqual(save_file.read_bytes(), b"progress")
            self.assertEqual(load(target).items, [item])
            self.assertEqual((target / "tools" / "catalog.tsv").read_bytes(), b"catalog")
            self.assertEqual(graph(repo_dir(target, item.id), False, "main"), history)

            self.assertIsNone(migrate_backup(target, source, default_root=source))
            self.assertEqual(backup_root(source), source)
            self.assertFalse(target.exists())
            self.assertEqual(load(source).items, [item])

    def test_migration_rejects_nonempty_destination_and_live_save(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "old"
            target = base / "new"
            target.mkdir()
            extra = target / "keep.txt"
            extra.write_text("keep", encoding="utf-8")
            live = base / "live"
            live.mkdir()
            add_folder(source, live, "Game")
            nested = live / "new"
            nested.mkdir()

            for destination in (target, nested, source / "new"):
                with self.assertRaises(ValueError):
                    migrate_backup(source, destination, default_root=source)
            self.assertEqual(extra.read_text(encoding="utf-8"), "keep")
            self.assertEqual(backup_root(source), source)
            self.assertTrue(source.is_dir())

    def test_location_write_failure_keeps_source_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "old"
            target = base / "new"
            source.mkdir()
            target.mkdir()
            (source / "backup.bin").write_bytes(b"old")

            with patch("storage._write_location", side_effect=OSError("write failed")):
                with self.assertRaises(OSError):
                    migrate_backup(source, target, default_root=source)

            self.assertEqual(backup_root(source), source)
            self.assertEqual((source / "backup.bin").read_bytes(), b"old")
            self.assertEqual(list(target.iterdir()), [])
            self.assertIsNone(migrate_backup(source, target, default_root=source))
            self.assertEqual((target / "backup.bin").read_bytes(), b"old")

    def test_corrupt_copy_leaves_the_original_backup_active(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "old"
            target = Path(d) / "new"
            source.mkdir()
            target.mkdir()
            (source / "backup.bin").write_bytes(b"original")
            copytree = shutil.copytree

            def corrupt_copy(src, dst, **kwargs):
                copytree(src, dst, **kwargs)
                (dst / "backup.bin").write_bytes(b"modified")

            with patch("storage.shutil.copytree", side_effect=corrupt_copy):
                with self.assertRaisesRegex(ValueError, "校验失败"):
                    migrate_backup(source, target, default_root=source)

            self.assertEqual(backup_root(source), source)
            self.assertEqual((source / "backup.bin").read_bytes(), b"original")
            self.assertEqual(list(target.iterdir()), [])

    def test_scheduler_continues_backing_up_to_moved_location(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "old"
            target = base / "new"
            live = base / "live"
            live.mkdir()
            save_file = live / "game.sav"
            save_file.write_bytes(b"first")
            item = add_folder(source, live, "Game")
            scheduler = Scheduler(source)
            try:
                with patch("app.ROOT", source), patch("app.DEFAULT_ROOT", source):
                    self.assertTrue(Api(scheduler).move_backup_location(str(target))["ok"])
                    save_file.write_bytes(b"second")
                    scheduler._run()
                self.assertEqual((repo_dir(target, item.id) / save_file.name).read_bytes(), b"second")
                self.assertEqual(len(graph(repo_dir(target, item.id), False, "main")["nodes"]), 2)
                self.assertFalse(source.exists())
            finally:
                scheduler.stop()

    def test_two_instances_cannot_share_location_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "gamebackup"
            with lock_backup_instance(root), self.assertRaises(ValueError):
                with lock_backup_instance(root):
                    self.fail("second instance acquired the lock")
            with lock_backup_instance(root):
                pass
