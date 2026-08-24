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
    delete_node,
    fork_node,
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

    def test_fork_node_adds_new_commit(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            init_repo(repo)
            (repo / "save.dat").write_bytes(b"v1")
            cid1 = commit_auto(repo)
            new_id, branch = fork_node(repo, cid1, "支线")
            self.assertNotEqual(new_id, cid1)
            g = graph(repo, hide_auto=False, current_line=branch)
            ids = {n["id"] for n in g["nodes"]}
            self.assertIn(cid1, ids)
            self.assertIn(new_id, ids)
            n = next(x for x in g["nodes"] if x["id"] == new_id)
            self.assertEqual(n["parents"], [cid1])
            self.assertFalse(n["auto"])
            self.assertTrue(n["fork"])
            self.assertIn(branch, {ln["name"] for ln in g["lines"]})

    def test_delete_node_drops_self_and_descendants(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            init_repo(repo)
            (repo / "save.dat").write_bytes(b"v1")
            start = commit_auto(repo)
            (repo / "save.dat").write_bytes(b"v2")
            mid = commit_auto(repo)
            (repo / "save.dat").write_bytes(b"v3")
            tip = commit_auto(repo)
            with self.assertRaises(ValueError):
                delete_node(repo, start)
            delete_node(repo, mid)
            g = graph(repo, hide_auto=False, current_line="main")
            ids = {n["id"] for n in g["nodes"]}
            self.assertIn(start, ids)
            self.assertNotIn(mid, ids)
            self.assertNotIn(tip, ids)

    def test_remarks_can_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            init_repo(repo)
            (repo / "save.dat").write_bytes(b"v1")
            a = commit_manual(repo, "a")
            (repo / "save.dat").write_bytes(b"v2")
            b = commit_manual(repo, "b")
            put_note(repo, a, "same")
            put_note(repo, b, "same")
            id1, br1 = fork_node(repo, a, "新进度")
            id2, br2 = fork_node(repo, b, "新进度")
            self.assertNotEqual(br1, br2)
            g = graph(repo, hide_auto=False, current_line=br2)
            by_id = {n["id"]: n for n in g["nodes"]}
            self.assertEqual(by_id[a]["note"], "same")
            self.assertEqual(by_id[b]["note"], "same")
            self.assertEqual(by_id[id1]["message"], "[fork] 新进度")
            self.assertEqual(by_id[id2]["message"], "[fork] 新进度")

    def test_delete_fork_keeps_original(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            init_repo(repo)
            (repo / "save.dat").write_bytes(b"v1")
            a = commit_auto(repo)
            (repo / "save.dat").write_bytes(b"v2")
            b = commit_auto(repo)
            fork_id, _branch = fork_node(repo, a, "支线")
            delete_node(repo, fork_id)
            g = graph(repo, hide_auto=False, current_line="main")
            ids = {n["id"] for n in g["nodes"]}
            self.assertIn(a, ids)
            self.assertIn(b, ids)
            self.assertNotIn(fork_id, ids)


if __name__ == "__main__":
    unittest.main()
