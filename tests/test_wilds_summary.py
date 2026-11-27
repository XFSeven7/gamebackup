import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bundled_support.wilds import _catalog_row, _changes, _slot
from bundled_support.wilds.save import murmur3, read_save
from bundled_support.wilds.steam_stats import achievement_rows


class WildsSummaryTests(unittest.TestCase):
    def test_new_hunter_and_monster_deltas(self):
        def fields(kills, captures):
            return {
                "Active": 1, "HunterId": "hunter-a", "PlayTime": 1500,
                "_BasicData": {"CharName": "Seven", "OtomoName": "Ka"},
                "_EnemyReport": {"_Boss": [
                    {"FixedId": -2003468672, "SlayingNum": kills, "CaptureNum": captures},
                ]},
                "_HunterProfile": {"_Medal": {"_Value": [0, 0, 0, 0]}},
                "_Item": {"_PouchItem": [{"ItemIdFixed": 2, "Num": 5}]},
            }

        before = _slot(0, fields(0, 0))
        after = _slot(0, fields(1, 2))
        self.assertEqual(before["play_time"], "0:25:00")
        self.assertEqual(before["facts"]["游戏内勋章"], 0)
        self.assertEqual(before["items"], [{"name": "回复药", "quantity": 5}])
        self.assertFalse(before["boss_progress"][0]["unlocked"])
        self.assertIn("讨伐 1", after["boss_progress"][0]["detail"])
        self.assertIn("捕获 2", after["boss_progress"][0]["detail"])
        self.assertEqual([row["label"] for row in _changes(after, before)][-2:], ["讨伐 · 白炽龙", "捕获 · 白炽龙"])
        catalog = _catalog_row(after["boss_progress"][0])
        self.assertEqual(catalog["display_name"], "白炽龙")
        self.assertIn("讨伐 1 · 捕获 2", catalog["name"])

    def test_steam_unknown_is_distinct_from_explicit_zero(self):
        schema = {"1": {"bits": {"0": {"name": "TEST", "display": {"name": {"schinese": "测试"}}}}}}
        self.assertIsNone(achievement_rows(schema, {"crc": 0})[0]["unlocked"])
        self.assertEqual(achievement_rows(schema, {"1": {"data": 0}})[0]["value"], 0)
        self.assertTrue(achievement_rows(schema, {"1": {"data": 1}})[0]["unlocked"])

    def test_corrupt_file_is_rejected(self):
        self.assertEqual(murmur3(b"PlayTime"), 0x984F9A59)
        with self.assertRaises(ValueError):
            read_save(b"DSSS\x02\0\0\0\x18\0\0\0" + bytes(64), ())
