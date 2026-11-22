import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from save_events import major_events


class SaveEventsTest(unittest.TestCase):
    def test_onimusha_tracks_matching_slots_and_known_achievement_unlocks(self):
        before = {
            "slots": {"20": {
                "goal": "击败弁庆", "mission_flags": 1,
                "boss_progress": [{"name": "弁庆", "unlocked": False}],
            }},
            "achievements": {"48": False},
        }
        after = {
            "slots": {"20": {
                "goal": "寻找父亲", "mission_flags": 7,
                "boss_progress": [{"name": "弁庆", "unlocked": True}],
            }},
            "achievements": {"48": True, "49": True},
        }
        before = json.loads(json.dumps(before))
        self.assertEqual(major_events("onimusha", before, after), [
            "击败：弁庆", "完成任务 1 项", "成就解锁：强行突破",
        ])
        after["slots"]["19"] = after["slots"].pop("20")
        self.assertEqual(major_events("onimusha", before, after), ["成就解锁：强行突破"])

    def test_mortal_shell_tracks_milestones_but_not_deaths_or_currency(self):
        before = {"0": {"击败 Boss": 1, "已解锁登陆点": 3, "死亡次数": 1, "幽质": 500}}
        after = {"0": {"击败 Boss": 1, "已解锁登陆点": 3, "死亡次数": 2, "幽质": 200}}
        self.assertEqual(major_events("mortal_shell", before, after), [])
        after["0"]["击败 Boss"] = 2
        after["0"]["已解锁登陆点"] = 5
        after["1"] = {"击败 Boss": 1}
        self.assertEqual(major_events("mortal_shell", before, after), [
            "击败 Boss 1 名", "解锁登陆点 2 个",
        ])
