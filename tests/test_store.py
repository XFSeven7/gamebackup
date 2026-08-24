import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from store import (
    add_tag,
    commit_auto,
    commit_manual,
    create_line,
    graph,
    init_repo,
    put_note,
)


class StoreTest(unittest.TestCase):
    def test_auto_commit_and_lines(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            init_repo(repo)
            (repo / "save.dat").write_bytes(b"v1")
            cid1 = commit_auto(repo)
            (repo / "save.dat").write_bytes(b"v2")
            cid2 = commit_manual(repo, "打Boss前")
            create_line(repo, cid1, "练习")
            add_tag(repo, cid2, "重要")
            put_note(repo, cid2, "别删")
            g = graph(repo, hide_auto=False, current_line="main")
            ids = {n["id"] for n in g["nodes"]}
            self.assertIn(cid1, ids)
            self.assertIn(cid2, ids)
            names = {ln["name"] for ln in g["lines"]}
            self.assertIn("main", names)
            self.assertIn("练习", names)
            n2 = next(n for n in g["nodes"] if n["id"] == cid2)
            self.assertFalse(n2["auto"])
            self.assertIn("重要", n2["tags"])
            self.assertEqual(n2["note"], "别删")
            n1 = next(n for n in g["nodes"] if n["id"] == cid1)
            self.assertTrue(n1["auto"])
            hidden = graph(repo, hide_auto=True, current_line="main")
            hidden_ids = {n["id"] for n in hidden["nodes"]}
            self.assertIn(cid1, hidden_ids)  # 练习线的 tip
            self.assertIn(cid2, hidden_ids)


if __name__ == "__main__":
    unittest.main()
