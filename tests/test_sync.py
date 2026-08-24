import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sync import mirror


class MirrorTest(unittest.TestCase):
    def test_copies_and_deletes_extra(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            dst = Path(d) / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "a.sav").write_bytes(b"1")
            (dst / "old.sav").write_bytes(b"gone")
            (src / "sub").mkdir()
            (src / "sub" / "b.sav").write_bytes(b"2")
            mirror(src, dst)
            self.assertEqual((dst / "a.sav").read_bytes(), b"1")
            self.assertEqual((dst / "sub" / "b.sav").read_bytes(), b"2")
            self.assertFalse((dst / "old.sav").exists())

    def test_keeps_dst_git_dir(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            dst = Path(d) / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "a.sav").write_bytes(b"1")
            git = dst / ".git"
            git.mkdir()
            (git / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
            mirror(src, dst)
            self.assertTrue((git / "HEAD").exists())
            self.assertEqual((dst / "a.sav").read_bytes(), b"1")

    def test_does_not_copy_src_git(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src"
            dst = Path(d) / "dst"
            src.mkdir()
            (src / "a.sav").write_bytes(b"1")
            (src / ".git").mkdir()
            (src / ".git" / "HEAD").write_text("nope", encoding="utf-8")
            mirror(src, dst)
            self.assertFalse((dst / ".git").exists())


if __name__ == "__main__":
    unittest.main()
