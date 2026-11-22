import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from store import commit_auto, filter_auto_nodes, graph, init_repo, put_note


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
    def test_keeps_boss_milestones_when_hiding_auto_nodes(self):
        nodes = [
            _node("c0", auto=True),
            _node("c1", ["c0"], auto=True),
            {**_node("c2", ["c1"], auto=True), "boss_milestone": {"names": ["弁庆"], "defeated": "弁庆"}},
            _node("c3", ["c2"], auto=True),
        ]
        hidden = filter_auto_nodes(_graph(nodes), hide_auto=True)
        self.assertEqual([(n["id"], n["parents"]) for n in hidden["nodes"]], [
            ("c0", []), ("c2", ["c0"]), ("c3", ["c2"]),
        ])

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

    def test_keeps_progress_milestones_when_hiding_auto_nodes(self):
        nodes = [_node("c0", auto=True)]
        for i, kind in enumerate(("exploration", "mystery", "achievement"), start=1):
            empty = f"empty-{i}"
            nodes.append({**_node(empty, [f"c{i - 1}"], auto=True), "progress_milestones": []})
            nodes.append({
                **_node(f"c{i}", [empty], auto=True),
                "progress_milestones": [{"kind": kind, "text": kind}],
            })
        nodes.append(_node("c4", ["c3"], auto=True))
        shown = filter_auto_nodes(_graph(nodes, tip="c4"), hide_auto=True)
        self.assertEqual([(node["id"], node["parents"]) for node in shown["nodes"]], [
            ("c0", []), ("c1", ["c0"]), ("c2", ["c1"]), ("c3", ["c2"]), ("c4", ["c3"]),
        ])

    def test_keeps_explicit_and_reused_event_pairs_when_hiding_auto_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            save = repo / "game.sav"

            def commit(message):
                save.write_text(message, encoding="utf-8")
                return commit_auto(repo, message)

            start = commit("start")
            ordinary = commit("ordinary")
            before = commit("[event-before]")
            after = commit("[event-after] 击败：弁庆")
            reused = commit("reused")
            second_after = commit("[event-after] 成就解锁：强行突破")
            third_after = commit("[event-after] 完成任务 1 项")
            tip = commit("tip")
            put_note(repo, before, "检查装备")

            raw = {node["id"]: node for node in graph(repo, False, "main")["nodes"]}
            self.assertNotIn("event_phase", raw[ordinary])
            self.assertEqual(raw[before]["event_phase"], "before")
            self.assertEqual(raw[before]["note"], "检查装备")
            self.assertEqual(raw[after]["event_phase"], "after")
            self.assertEqual(raw[after]["event_label"], "击败：弁庆")
            self.assertEqual(raw[reused]["event_phase"], "before")
            self.assertEqual(raw[second_after]["event_phase"], "after")
            self.assertEqual(raw[third_after]["event_label"], "完成任务 1 项")

            filtered = {node["id"]: node for node in graph(repo, True, "main")["nodes"]}
            self.assertEqual(set(filtered), {start, before, after, reused, second_after, third_after, tip})
            self.assertEqual(filtered[before]["parents"], [start])
            self.assertEqual(filtered[after]["parents"], [before])

    def test_show_auto_keeps_plain_autos(self):
        nodes = [
            _node("c0", auto=True),
            _node("c1", ["c0"], auto=True),
            _node("c2", ["c1"], auto=True, note="Boss"),
            _node("c3", ["c2"], auto=False),
        ]
        shown = filter_auto_nodes(_graph(nodes), hide_auto=False)
        ids = {n["id"] for n in shown["nodes"]}
        self.assertEqual(ids, {"c0", "c1", "c2", "c3"})

        hidden = filter_auto_nodes(_graph(nodes), hide_auto=True)
        hid = {n["id"] for n in hidden["nodes"]}
        self.assertNotIn("c1", hid)
        self.assertNotIn("c2", hid)
        c3 = next(n for n in hidden["nodes"] if n["id"] == "c3")
        self.assertEqual(c3["parents"], ["c0"])


if __name__ == "__main__":
    unittest.main()
