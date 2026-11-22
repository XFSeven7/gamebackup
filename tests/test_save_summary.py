import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from save_summary import (
    load_onimusha_boss_index, onimusha_boss_nodes, save_onimusha_boss_index,
    scan_onimusha_boss_index, summarize_onimusha,
)
from store import commit_manual, graph, init_repo


class SaveSummaryTest(unittest.TestCase):
    def test_reads_selected_commit_and_its_parent_instead_of_working_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            tools = root / "tools"
            tools.mkdir()
            (tools / "UniversalSaveEditor.exe").touch()
            (tools / "onimusha_items.tsv").write_text("15508\tWhetstone\n2\tUnknown tool\n", encoding="utf-8")
            init_repo(repo)
            save = repo / "data001Slot.bin"
            save.write_bytes(b"previous")
            previous = commit_manual(repo, "previous")
            save.write_bytes(b"selected")
            selected = commit_manual(repo, "selected")
            save.write_bytes(b"newer")
            commit_manual(repo, "newer")
            save.write_bytes(b"live edits")

            slot = "/Root/Slots/20"

            def parse_copy(args, **kwargs):
                snapshot = Path(args[2]).read_bytes()
                self.assertNotEqual(Path(args[2]), save)
                self.assertIn(snapshot, {b"previous", b"selected"})
                earlier = snapshot == b"previous"
                values = {
                    f"{slot}/_Data/_ResourceData/PlayTime": 1,
                    f"{slot}/_Data/_ResourceData/SoulAmount": 100 if earlier else 115,
                    f"{slot}/Detail": f"11/21/2026 22:00:{'00' if earlier else '25'}\t009:35:23\t剑戟\t{'击败怒伐天' if earlier else '寻找父亲'}",
                    f"{slot}/Subtitle": "101\t清水寺",
                    f"{slot}/_Data/_Items/0/ItemID": 15508,
                    f"{slot}/_Data/_Items/0/EquipNum": 2 if earlier else 5,
                    f"{slot}/_Data/_Items/1/ItemID": 2,
                    f"{slot}/_Data/_Items/1/EquipNum": 1 if earlier else 0,
                    f"{slot}/_Data/_BossRematch/#d54d09c5/_MaxElement": 3,
                    f"{slot}/_Data/_BossRematch/#d54d09c5/_Value/0": 1 if earlier else 7,
                    f"{slot}/_Data/_BossRematch/BossID/0": 354,
                    f"{slot}/_Data/_BossRematch/BossID/1": 26515,
                    f"{slot}/_Data/_BossRematch/BossID/2": 28128,
                }
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(values))

            with patch("save_summary.subprocess.run", side_effect=parse_copy):
                result = summarize_onimusha(repo, selected, tools)["slots"][0]
                baseline = summarize_onimusha(repo, previous, tools)["slots"][0]
                nodes = [node for node in graph(repo, False, "main")["nodes"] if node["id"] in {previous, selected}]
                missing = onimusha_boss_nodes(repo, nodes, {})
                self.assertEqual(len(missing), 2)
                index = scan_onimusha_boss_index(repo, tools, missing, lambda: False)
                save_onimusha_boss_index(repo, index)
                self.assertEqual(onimusha_boss_nodes(repo, nodes, load_onimusha_boss_index(repo)), set())
                indexed = {node["id"]: node.get("boss_milestone") for node in nodes}
                self.assertEqual(indexed, {
                    selected: {"names": ["怒伐天", "怒伐天（强化）"], "defeated": ["怒伐天"]},
                    previous: None,
                })
            self.assertEqual(result["goal"], "寻找父亲")
            self.assertEqual(result["location"], "清水寺")
            self.assertEqual(result["play_time"], "009:35:23")
            self.assertEqual(result["previous_goal"], "击败怒伐天")
            self.assertEqual(result["souls_delta"], 15)
            self.assertEqual(result["boss_progress"], [
                {"name": "佐佐木巌流", "unlocked": True},
                {"name": "怒伐天", "unlocked": True},
                {"name": "怒伐天（强化）", "unlocked": True},
            ])
            self.assertEqual(result["boss_unlocked"], ["怒伐天", "怒伐天（强化）"])
            self.assertEqual(baseline["boss_progress"], [
                {"name": "佐佐木巌流", "unlocked": True},
                {"name": "怒伐天", "unlocked": False},
                {"name": "怒伐天（强化）", "unlocked": False},
            ])
            self.assertTrue(result["has_previous"])
            self.assertCountEqual(result["items"], [
                {"id": 15508, "name": "砥石", "quantity": 5, "delta": 3},
                {"id": 2, "name": "Unknown tool", "quantity": 0, "delta": -1},
            ])
            self.assertFalse(baseline["has_previous"])
            self.assertIsNone(baseline["items"][0]["delta"])
            self.assertEqual(save.read_bytes(), b"live edits")

    def test_unavailable_parser_reports_setup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            with self.assertRaisesRegex(ValueError, "install-summary-tools"):
                summarize_onimusha(path, "a" * 40, path)
