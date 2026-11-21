import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from save_summary import summarize_mortal_shell
from store import commit_manual, init_repo


def string(value):
    data = value.encode() + b"\0"
    return struct.pack("<i", len(data)) + data


def tag(name, kind, data):
    return string(name) + string(kind) + struct.pack("<iiB", 0, len(data), 0) + data


def save_data(seconds, gold):
    inventory = struct.pack("<ii", 0, 1) + string("/Game/Sparta/ID_Gold.ID_Gold_C")
    inventory += struct.pack("<i", gold)
    fields = tag("TotalPlayTimeSeconds", "FloatProperty", struct.pack("<f", seconds))
    fields += string("DropItems") + string("MapProperty") + struct.pack("<i", 2)
    fields += string("ObjectProperty") + bytes(4) + string("IntProperty") + bytes(4)
    fields += struct.pack("<iB", len(inventory), 0) + inventory + string("None")
    header = b"GVAS" + struct.pack("<IIIHHHI", 3, 522, 1017, 5, 6, 1, 0)
    header += string("test") + struct.pack("<ii", 3, 0)
    header += string("/Script/Sparta.SpartaSaveGame") + b"\0" + string("None")
    return (
        header + struct.pack("<ii", 0, 1)
        + string("/Game/Test.BP_SpartaPlayerSaveObject_C") + bytes(21)
        + fields + bytes(9) + string("None") + bytes(4)
    )


class MortalShellSummaryTest(unittest.TestCase):
    def test_compares_same_slot_in_selected_commit_and_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_repo(repo)
            main = repo / "WorldState_0.sav"
            main.write_bytes(save_data(40, 18))
            commit_manual(repo, "parent")
            main.write_bytes(save_data(60, 7))
            (repo / "WorldState_1.sav").write_bytes(save_data(2, 0))
            selected = commit_manual(repo, "selected")
            main.write_bytes(b"live contents")

            first, second = summarize_mortal_shell(repo, selected)["slots"]
            self.assertEqual(first["play_time"], "1:00")
            self.assertTrue(first["has_previous"])
            self.assertEqual(first["items"][0]["quantity"], 7)
            self.assertEqual(first["items"][0]["delta"], -11)
            self.assertFalse(second["has_previous"])
            self.assertEqual(main.read_bytes(), b"live contents")
