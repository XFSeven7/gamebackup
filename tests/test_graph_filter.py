import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from store import filter_auto_nodes


def _node(i, parents=None, auto=False, note="", tags=None):
    return {
        "id": i,
        "parents": parents or [],
        "time": 0,
        "message": "[auto] x" if auto else "manual",
        "auto": auto,
        "note": note,
        "tags": tags or [],
    }


def _graph(nodes, tip="c3"):
    return {
        "nodes": nodes,
        "lines": [{"name": "main", "tip": tip, "display": "主线"}],
        "current_line": "main",
        "current_id": tip,
    }


class GraphFilterTest(unittest.TestCase):
    def test_hides_plain_auto_keeps_start_and_tip(self):
        # c3(tip, auto) <- c2(auto) <- c1(manual) <- c0(auto 起始)
        nodes = [
            _node("c0", auto=True),
            _node("c1", ["c0"], auto=False),
            _node("c2", ["c1"], auto=True),
            _node("c3", ["c2"], auto=True, tags=["Boss前"]),
        ]
        out = filter_auto_nodes(_graph(nodes), hide_auto=True)
        ids = {n["id"] for n in out["nodes"]}
        self.assertIn("c0", ids)
        self.assertIn("c1", ids)
        self.assertIn("c3", ids)
        self.assertNotIn("c2", ids)
        c3 = next(n for n in out["nodes"] if n["id"] == "c3")
        self.assertEqual(c3["parents"], ["c1"])

    def test_show_noted_auto_keeps_notes_hides_plain(self):
        nodes = [
            _node("c0", auto=True),
            _node("c1", ["c0"], auto=True),
            _node("c2", ["c1"], auto=True, note="Boss"),
            _node("c3", ["c2"], auto=False),
        ]
        shown = filter_auto_nodes(_graph(nodes), hide_auto=False)
        ids = {n["id"] for n in shown["nodes"]}
        self.assertIn("c0", ids)
        self.assertIn("c2", ids)
        self.assertIn("c3", ids)
        self.assertNotIn("c1", ids)
        c2 = next(n for n in shown["nodes"] if n["id"] == "c2")
        self.assertEqual(c2["parents"], ["c0"])

        hidden = filter_auto_nodes(_graph(nodes), hide_auto=True)
        hid = {n["id"] for n in hidden["nodes"]}
        self.assertNotIn("c1", hid)
        self.assertNotIn("c2", hid)
        c3 = next(n for n in hidden["nodes"] if n["id"] == "c3")
        self.assertEqual(c3["parents"], ["c0"])


if __name__ == "__main__":
    unittest.main()
