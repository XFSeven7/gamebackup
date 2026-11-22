import hashlib
import struct
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import vdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bundled_support.elden_ring import annotate_nodes, load_index, read_save, save_index, scan_index, steam_achievements, summarize
from store import commit_manual, graph, init_repo


def example_save(level=42, seconds=3723, body=False, clear_count=0, boss=False):
    data = bytearray(0x19603B0)
    data[:4] = b"BND4"
    struct.pack_into("<I", data, 12, 12)
    data[0x1901D05] = 1
    profile = 0x1901D0E + 0x24C
    name = "褪色".encode("utf-16-le")
    data[profile:profile + len(name)] = name
    struct.pack_into("<II", data, profile + 34, level, seconds)
    data[0x19003A0:0x19003B0] = hashlib.md5(data[0x19003B0:], usedforsecurity=False).digest()
    if body:
        slot = 0x300 + 0x280010
        stats = slot + 0xA030
        struct.pack_into("<I", data, slot + 16, 252)
        struct.pack_into("<8I", data, stats + 0x34, 30, 10, 10, 12, 10, 10, 10, 10)
        struct.pack_into("<3I", data, stats + 0x60, level, 500, 4000)
        data[stats + 0x94:stats + 0x94 + len(name)] = name
        data[stats + 0xB7] = 9
        deaths = stats + 0x280 + 0x124 + 16 + 12 * (0xA80 + 0x180) + 116 + 140 + 24
        deaths += 4 + 156 + 12 + 303 + 16 + 12 * (0x780 + 0x80) + 256
        regions_end = deaths + 4
        struct.pack_into("<I", data, regions_end + 0x6D, clear_count)
        deaths = regions_end + 40 + 77 + 8 + 52 + 0x1B588 + 8 + 3
        struct.pack_into("<I", data, deaths, 7)
        if boss:
            data[deaths + 26 + 11067 * 125 + 800 // 8] = 0x80
        save_body = memoryview(data)[slot + 16:slot + 0x280010]
        data[slot:slot + 16] = hashlib.md5(save_body, usedforsecurity=False).digest()
    return data


class EldenRingSummaryTest(unittest.TestCase):
    def test_reads_active_character_profile_and_rejects_bad_checksum(self):
        data = example_save()
        slots = read_save(data)
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0]["index"], 1)
        self.assertEqual(slots[0]["label"], "槽 2 · 褪色")
        self.assertEqual(slots[0]["facts"], {"等级": 42})
        self.assertEqual(slots[0]["play_time"], "1:02:03")
        data[0x1901D0E + 0x24C] ^= 1
        with self.assertRaises(ValueError):
            read_save(data)

    def test_reads_world_flags_and_compares_the_selected_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            init_repo(repo)
            live = repo / "ER0000.sl2"
            live.write_bytes(example_save(body=True))
            commit_manual(repo, "before")
            live.write_bytes(example_save(43, 3783, body=True, clear_count=7, boss=True))
            selected = commit_manual(repo, "after")
            live.write_bytes(b"uncommitted")

            slot = summarize(repo, selected, repo / "tools")["slots"][0]
            self.assertEqual(slot["facts"]["死亡次数"], 7)
            self.assertEqual(slot["facts"]["当前周目"], "第 8 周目（NG+7）")
            self.assertEqual(slot["facts"]["生命力"], 30)
            self.assertEqual(slot["facts"]["持有卢恩"], 500)
            self.assertEqual(slot["facts"]["本体已击败"], "接肢葛瑞克")
            self.assertIn({"name": "接肢葛瑞克", "unlocked": True, "group": "本体"}, slot["boss_progress"])
            self.assertFalse(slot["boss_unlocked"])  # Different journeys are separate.
            self.assertIn({"label": "等级", "before": 42, "after": 43}, slot["changes"])
            self.assertIn({"label": "当前周目", "before": "第 1 周目", "after": "第 8 周目（NG+7）"}, slot["changes"])
            self.assertIn({"label": "游玩时长", "before": "1:02:03", "after": "1:03:03"}, slot["changes"])
            self.assertEqual(live.read_bytes(), b"uncommitted")

    def test_indexes_boss_defeat_between_commits_on_same_journey(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            init_repo(repo)
            live = repo / "ER0000.sl2"
            live.write_bytes(example_save(body=True))
            commit_manual(repo, "before")
            live.write_bytes(example_save(seconds=3783, body=True, boss=True))
            selected = commit_manual(repo, "after")
            nodes = graph(repo, False, "main")["nodes"]
            needed = annotate_nodes(repo, nodes, {})
            index = scan_index(repo, repo / "tools", needed, lambda: False)
            save_index(repo, index, cache_version="1.0.0")
            self.assertFalse(annotate_nodes(repo, nodes, load_index(repo, cache_version="1.0.0")))
            newest = next(node for node in nodes if node["id"] == selected)
            self.assertEqual(newest["boss_milestone"]["defeated"], ["接肢葛瑞克"])

    def test_steam_cache_matches_the_owning_account_and_preserves_unlock_time(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            trophy = {"name": "ACH00", "display": {"name": {"schinese": "艾尔登法环"}}}
            schema = {"1245620": {"stats": {"1": {"bits": {"0": trophy, "3": {"name": "ACH01"}}}}}}
            (folder / "UserGameStatsSchema_1245620.bin").write_bytes(vdf.binary_dumps(schema))
            cache = {"cache": {"1": {"data": 1, "AchievementTimes": {"0": 1700000000}}}}
            (folder / "UserGameStats_12345_1245620.bin").write_bytes(vdf.binary_dumps(cache))
            with patch("bundled_support.elden_ring.achievements._stats_dirs", return_value=[folder]):
                rows = steam_achievements((0x01100001 << 32) | 12345)
                self.assertFalse(steam_achievements((0x01100001 << 32) | 54321))
            self.assertEqual(rows[0]["name"], "艾尔登法环")
            self.assertTrue(rows[0]["unlocked"])
            self.assertEqual(rows[0]["unlocked_at"], datetime.fromtimestamp(1700000000).strftime("%Y-%m-%d %H:%M"))
            self.assertIn(rows[0]["unlocked_at"], rows[0]["description"])
            self.assertFalse(rows[1]["unlocked"])
            self.assertEqual(rows[1]["unlocked_at"], "")
