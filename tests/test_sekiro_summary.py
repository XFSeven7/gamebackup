import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bundled_support.sekiro import read_save


def synthetic_save():
    data = bytearray(0x110000)
    data[:4] = b"BND4"
    struct.pack_into("<I", data, 12, 12)
    account = (0x01100001 << 32) | 12345
    for index, offset, name, size in ((0, 0x300, "USER_DATA000", 0x100010),
                                      (10, 0x100310, "USER_DATA010", 0x400)):
        name_at = 0x200 + (24 * (1 if index else 0))
        text = name.encode("utf-16-le")
        data[name_at:name_at + len(text)] = text
        struct.pack_into("<QIIIIII", data, 0x40 + index * 32, 0xFFFFFFFF00000050,
                         size, 0, offset, name_at, 0, 0)
    start = 0x310
    menu = 0x100320
    struct.pack_into("<Q", data, menu + 36, account)
    data[menu + 212] = 1
    struct.pack_into("<Q", data, start + 0x33E54, account)
    data[start + 0x33F34] = 2
    struct.pack_into("<I", data, start + 0x33F80, 3723)
    struct.pack_into("<II", data, start + 0x34498, 11, 21)
    data[start + 0x34562] = 10
    struct.pack_into("<II", data, start, 0xFFFFFFFF, 1000)
    struct.pack_into("<I", data, start + 0x30, 212480)
    data[start + 52 + 9 * 128 + (301 // 8 ^ 3)] = 4
    for offset, size in ((0x300, 0x100010), (0x100310, 0x400)):
        data[offset:offset + 16] = hashlib.md5(memoryview(data)[offset + 16:offset + size], usedforsecurity=False).digest()
    return data


class SekiroSummaryTest(unittest.TestCase):
    def test_reads_occupied_slot_and_boss_flag(self):
        slots, _ = read_save(synthetic_save())
        self.assertEqual(len(slots), 1)
        slot = slots[0]
        self.assertEqual(slot["play_time"], "1:02:03")
        self.assertEqual(slot["facts"]["当前周目"], "第 3 周目")
        self.assertEqual(slot["facts"]["攻击力"], 21)
        self.assertEqual(slot["facts"]["伤药葫芦上限"], 10)
        self.assertEqual([b["name"] for b in slot["boss_progress"] if b["unlocked"]], ["鬼形部"])

    def test_rejects_invalid_profile_checksum(self):
        data = synthetic_save()
        data[0x100310] ^= 1
        with self.assertRaises(ValueError):
            read_save(data)
