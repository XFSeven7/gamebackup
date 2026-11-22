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
                    f"{slot}/_Data/_Items/2/ItemID": 22384,
                    f"{slot}/_Data/_Items/2/EquipNum": 1,
                    f"{slot}/_Data/_Items/3/ItemID": 22649,
                    f"{slot}/_Data/_Items/3/EquipNum": 0,
                    f"{slot}/_Data/_Items/3/BoxNum": 0 if earlier else 1,
                    f"{slot}/_Data/_Items/4/ItemID": 22384,
                    f"{slot}/_Data/_Items/4/EquipNum": 0,
                    f"{slot}/_Data/_Items/4/BoxNum": 1,
                    f"{slot}/_Data/_BossRematch/#d54d09c5/_MaxElement": 3,
                    f"{slot}/_Data/_BossRematch/#d54d09c5/_Value/0": 1 if earlier else 7,
                    f"{slot}/_Data/_BossRematch/BossID/0": 354,
                    f"{slot}/_Data/_BossRematch/BossID/1": 26515,
                    f"{slot}/_Data/_BossRematch/BossID/2": 28128,
                    f"{slot}/_Data/#7efc175b/_ReleasedIndex/_MaxElement": 32,
                    f"{slot}/_Data/#7efc175b/_ReleasedIndex/_Value/0": 1 if earlier else 5,
                    f"{slot}/_Data/#62b8a2f4/_VisitArea/_MaxElement": 32,
                    f"{slot}/_Data/#62b8a2f4/_VisitArea/_Value/0": 3 if earlier else 2,
                    f"{slot}/_Data/_MysteryParam/#6858d6b7": 3 if earlier else 7,
                    f"{slot}/_Data/_MysteryParam/#a9abfbb2": 1 if earlier else 3,
                    f"{slot}/_Data/_StoryParam/#71379cfa/_MaxElement": 128,
                    f"{slot}/_Data/_StoryParam/#71379cfa/_Value/0": 1 if earlier else (1 << 24) | 1,
                    f"{slot}/_Data/_StoryParam/#71379cfa/_Value/1": 1 << 12,
                    f"{slot}/_Data/_StoryParam/#71379cfa/_Value/2": 0 if earlier else 1 << 11,
                    f"{slot}/_Data/_StoryParam/#71379cfa/_Value/3": 0,
                    "/Root/_SystemSaveData/_Data/_Achievement/46/#78cfd7e7": 46,
                    "/Root/_SystemSaveData/_Data/_Achievement/24/#78cfd7e7": 24,
                    "/Root/_SystemSaveData/_Data/_Achievement/24/IsUnlocked": 0,
                    "/Root/_SystemSaveData/_Data/_Achievement/46/IsUnlocked": 0 if earlier else 1,
                    "/Root/_SystemSaveData/_Data/_Achievement/46/Count": 49 if earlier else 74,
                    "/Root/_SystemSaveData/_Data/_Achievement/44/#78cfd7e7": 44,
                    "/Root/_SystemSaveData/_Data/_Achievement/44/IsUnlocked": 0,
                    "/Root/_SystemSaveData/_Data/_Achievement/44/Count": 20 if earlier else 40,
                    "/Root/_SystemSaveData/_Data/_Achievement/50/#78cfd7e7": 50,
                    "/Root/_SystemSaveData/_Data/_Achievement/50/IsUnlocked": 1,
                }
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(values))

            with patch("save_summary.subprocess.run", side_effect=parse_copy):
                selected_summary = summarize_onimusha(repo, selected, tools)
                previous_summary = summarize_onimusha(repo, previous, tools)
                result = selected_summary["slots"][0]
                baseline = previous_summary["slots"][0]
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
                progress = {node["id"]: node.get("progress_milestones") for node in nodes}
                self.assertEqual(progress, {
                    selected: [
                        {"kind": "exploration", "text": "传送镜 +1（累计 2）"},
                        {"kind": "mystery", "text": "异闻解锁 +1（累计 3）"},
                        {"kind": "mystery", "text": "异闻已汇报 +1（累计 2）"},
                        {"kind": "achievement", "text": "战斗成就：能赢就行"},
                    ],
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
                {"id": 22384, "name": "幻魔杂记（一目笠）", "quantity": 1, "delta": 0},
            ])
            self.assertFalse(baseline["has_previous"])
            self.assertIsNone(baseline["items"][0]["delta"])
            achievements = {entry["id"]: entry for entry in selected_summary["achievements"]}
            self.assertEqual(len(achievements), 52)
            self.assertEqual((achievements[16]["value"], achievements[16]["target"]), (2, 8))
            self.assertEqual((achievements[18]["value"], achievements[18]["target"]), (1, 18))
            self.assertEqual((achievements[23]["value"], achievements[23]["target"]), (2, 36))
            self.assertEqual((achievements[24]["value"], achievements[24]["target"]), (2, 23))
            self.assertEqual((achievements[44]["value"], achievements[44]["target"]), (40, 50))
            self.assertEqual((achievements[46]["value"], achievements[46]["target"]), (50, 50))
            self.assertTrue(achievements[46]["unlocked"])
            self.assertEqual((achievements[50]["value"], achievements[50]["target"]), (1, 1))
            self.assertIsNone(achievements[51]["value"])
            previous_achievements = {entry["id"]: entry for entry in previous_summary["achievements"]}
            self.assertEqual(previous_achievements[16]["value"], 0)
            self.assertEqual(previous_achievements[23]["value"], 1)
            self.assertEqual(previous_achievements[24]["value"], 1)
            self.assertEqual(previous_achievements[44]["value"], 20)
            self.assertEqual(previous_achievements[46]["value"], 49)
            self.assertEqual(save.read_bytes(), b"live edits")

    def test_unavailable_parser_reports_setup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            with self.assertRaisesRegex(ValueError, "install-summary-tools"):
                summarize_onimusha(path, "a" * 40, path)
