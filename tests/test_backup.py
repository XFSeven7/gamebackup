import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup import add_folder, backup_once, dir_nbytes, format_bytes, remove_item, restore, save_now
from config import load
from store import graph


class BackupTest(unittest.TestCase):
    def test_two_folders_independent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            a = Path(d) / "gameA"
            b = Path(d) / "gameB"
            a.mkdir()
            b.mkdir()
            (a / "s.sav").write_bytes(b"A")
            (b / "s.sav").write_bytes(b"B")
            ia = add_folder(root, a, "阿尔")
            ib = add_folder(root, b, "贝塔")
            cfg = load(root)
            self.assertEqual(len(cfg.items), 2)
            self.assertEqual((a / "s.sav").read_bytes(), b"A")
            self.assertEqual((b / "s.sav").read_bytes(), b"B")
            self.assertNotEqual(ia.id, ib.id)

    def test_no_change_skips_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            live = Path(d) / "save"
            live.mkdir()
            (live / "s.sav").write_bytes(b"same")
            item = add_folder(root, live, "测试")
            r = backup_once(root, item)
            self.assertTrue(r["skipped"])
            self.assertEqual(r["reason"], "unchanged")

    def test_save_now_makes_visible_commit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            live = Path(d) / "save"
            live.mkdir()
            (live / "s.sav").write_bytes(b"v1")
            item = add_folder(root, live, "测试")
            skip = save_now(root, item)
            self.assertTrue(skip["skipped"])
            time.sleep(0.05)
            (live / "s.sav").write_bytes(b"v2")
            r = save_now(root, item)
            self.assertFalse(r["skipped"])
            repo = root / "repos" / item.id
            g = graph(repo, hide_auto=True, current_line=item.current_line)
            msgs = [n["message"] for n in g["nodes"]]
            self.assertTrue(any(m.startswith("手动保存") for m in msgs))
            self.assertFalse(any(n["id"] == g["current_id"] and n["auto"] for n in g["nodes"]))

    def test_fork_restore_keeps_current_on_new_line(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            live = Path(d) / "save"
            live.mkdir()
            (live / "s.sav").write_bytes(b"old")
            item = add_folder(root, live, "测试")
            repo = root / "repos" / item.id
            g1 = graph(repo, hide_auto=False, current_line="main")
            old_id = g1["current_id"]
            time.sleep(0.05)
            (live / "s.sav").write_bytes(b"new")
            from backup import backup_once
            backup_once(root, item)
            restore(root, item, old_id, fork=True)
            self.assertEqual((live / "s.sav").read_bytes(), b"old")
            from config import find_item as _find
            item = _find(load(root), item.id) or item
            g = graph(repo, hide_auto=False, current_line=item.current_line)
            self.assertEqual(g["current_id"], old_id)
            names = [ln["name"] for ln in g["lines"]]
            self.assertTrue(any(n.startswith("换档前-") for n in names))
            # 换档前那条进度应仍能看到 new
            from store import checkout_line
            pre = next(n for n in names if n.startswith("换档前-"))
            checkout_line(repo, pre)
            self.assertEqual((repo / "s.sav").read_bytes(), b"new")

    def test_remove_item_drops_backup_keeps_game_saves(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "data"
            a = Path(d) / "gameA"
            b = Path(d) / "gameB"
            a.mkdir()
            b.mkdir()
            (a / "s.sav").write_bytes(b"A")
            (b / "s.sav").write_bytes(b"B")
            ia = add_folder(root, a, "阿尔")
            ib = add_folder(root, b, "贝塔")
            repo_a = root / "repos" / ia.id
            repo_b = root / "repos" / ib.id
            self.assertTrue(repo_a.is_dir())
            remove_item(root, ia.id)
            cfg = load(root)
            self.assertEqual([it.id for it in cfg.items], [ib.id])
            self.assertFalse(repo_a.exists())
            self.assertTrue(repo_b.is_dir())
            self.assertEqual((a / "s.sav").read_bytes(), b"A")
            self.assertEqual((b / "s.sav").read_bytes(), b"B")
            self.assertTrue(a.is_dir())


class SizeTextTest(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(2048), "2.0 KB")
        self.assertEqual(format_bytes(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(format_bytes(2 * 1024 * 1024 * 1024), "2.0 GB")

    def test_dir_nbytes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.bin").write_bytes(b"x" * 100)
            (p / "sub").mkdir()
            (p / "sub" / "b.bin").write_bytes(b"y" * 50)
            self.assertEqual(dir_nbytes(p), 150)
            self.assertEqual(dir_nbytes(p / "missing"), 0)


if __name__ == "__main__":
    unittest.main()
