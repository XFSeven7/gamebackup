import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from paths import WEBVIEW2_HELP, ui_index, webview2_installed


class PathsTest(unittest.TestCase):
    def test_dev_index_exists(self):
        p = ui_index()
        self.assertTrue(p.is_file())
        self.assertEqual(p.name, "index.html")

    def test_frozen_uses_meipass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "ui").mkdir()
            target = root / "ui" / "index.html"
            target.write_text("<html></html>", encoding="utf-8")
            old_frozen = getattr(sys, "frozen", None)
            old_mei = getattr(sys, "_MEIPASS", None)
            sys.frozen = True
            sys._MEIPASS = str(root)
            try:
                p = ui_index()
                self.assertEqual(p, target)
                self.assertTrue(p.is_file())
            finally:
                if old_frozen is None:
                    delattr(sys, "frozen")
                else:
                    sys.frozen = old_frozen
                if old_mei is None:
                    if hasattr(sys, "_MEIPASS"):
                        delattr(sys, "_MEIPASS")
                else:
                    sys._MEIPASS = old_mei

    def test_help_text(self):
        self.assertIn("Microsoft Edge WebView2", WEBVIEW2_HELP)
        self.assertIn("https://go.microsoft.com/fwlink/p/?LinkId=2124703", WEBVIEW2_HELP)

    def test_missing_when_registry_empty(self):
        with patch("paths.winreg.OpenKey", side_effect=OSError):
            self.assertFalse(webview2_installed())


if __name__ == "__main__":
    unittest.main()
