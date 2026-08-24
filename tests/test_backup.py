import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from backup import add_folder, restore
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
            g = graph(repo, hide_auto=False, current_line=item.current_line)
            names = [ln["name"] for ln in g["lines"]]
            self.assertTrue(any(n.startswith("恢复前-") for n in names))
            # 恢复前线应仍能看到 new
            from store import checkout_line
            pre = next(n for n in names if n.startswith("恢复前-"))
            checkout_line(repo, pre)
            self.assertEqual((repo / "s.sav").read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
