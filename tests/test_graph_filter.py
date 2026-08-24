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


class GraphFilterTest(unittest.TestCase):
    def test_hides_auto_but_keeps_tips_tags_notes(self):
        # c3(tip, auto) <- c2(auto) <- c1(manual) <- c0(auto)
        nodes = [
            _node("c0", auto=True),
            _node("c1", ["c0"], auto=False),
            _node("c2", ["c1"], auto=True),
            _node("c3", ["c2"], auto=True, tags=["Boss前"]),
        ]
        lines = [{"name": "main", "tip": "c3", "display": "主线"}]
        out = filter_auto_nodes(
            {"nodes": nodes, "lines": lines, "current_line": "main", "current_id": "c3"},
            hide_auto=True,
        )
        ids = {n["id"] for n in out["nodes"]}
        self.assertIn("c1", ids)
        self.assertIn("c3", ids)
        self.assertNotIn("c2", ids)
        self.assertNotIn("c0", ids)
        c3 = next(n for n in out["nodes"] if n["id"] == "c3")
        self.assertEqual(c3["parents"], ["c1"])

    def test_show_auto_keeps_all(self):
        nodes = [_node("a", auto=True), _node("b", ["a"], auto=False)]
        g = {"nodes": nodes, "lines": [{"name": "main", "tip": "b", "display": "主线"}], "current_line": "main", "current_id": "b"}
        out = filter_auto_nodes(g, hide_auto=False)
        self.assertEqual(len(out["nodes"]), 2)


if __name__ == "__main__":
    unittest.main()
