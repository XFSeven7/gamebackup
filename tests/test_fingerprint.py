import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fingerprint import fingerprint


class FingerprintTest(unittest.TestCase):
    def test_same_files_same_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.sav").write_bytes(b"abc")
            self.assertEqual(fingerprint(p), fingerprint(p))

    def test_content_change_changes_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "a.sav"
            f.write_bytes(b"abc")
            h1 = fingerprint(p)
            time.sleep(0.05)
            f.write_bytes(b"abcd")
            self.assertNotEqual(h1, fingerprint(p))

    def test_missing_dir_raises(self):
        with self.assertRaises(FileNotFoundError):
            fingerprint(Path(tempfile.gettempdir()) / "gamebackup-no-such-dir")


if __name__ == "__main__":
    unittest.main()
