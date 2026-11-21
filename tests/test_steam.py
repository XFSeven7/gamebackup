import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import vdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from steam import scan_installed_games


class SteamScanTest(unittest.TestCase):
    def test_scans_multiple_libraries_and_skips_stale_or_broken_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Steam"
            second = Path(tmp) / "Library With Spaces"
            legacy = Path(tmp) / "Legacy Library"
            for library in (root, second, legacy):
                (library / "steamapps").mkdir(parents=True)
            (root / "steamapps" / "libraryfolders.vdf").write_text(
                vdf.dumps({"libraryfolders": {"0": {"path": str(root)}, "1": {"path": str(second)}}},
                          pretty=True),
                encoding="utf-8-sig",
            )
            (root / "config").mkdir()
            (root / "config" / "libraryfolders.vdf").write_text(
                vdf.dumps({"LibraryFolders": {"2": str(legacy)}}, pretty=True), encoding="utf-8",
            )

            def make_manifest(library, app_id, name, installed=True):
                steamapps = library / "steamapps"
                folder = f"Game {app_id}"
                (steamapps / f"appmanifest_{app_id}.acf").write_text(
                    vdf.dumps({"AppState": {"appID": app_id, "name": name, "installdir": folder}},
                              pretty=True),
                    encoding="utf-8",
                )
                path = steamapps / "common" / folder
                if installed:
                    path.mkdir(parents=True)
                return str(path)

            first_path = make_manifest(root, "100", "Alpha")
            second_path = make_manifest(second, "200", '测试 "游戏"')
            legacy_path = make_manifest(legacy, "300", "Legacy")
            make_manifest(second, "100", "Duplicate")
            make_manifest(second, "400", "Uninstalled", installed=False)
            make_manifest(legacy, "228980", "Steamworks Common Redistributables")
            (root / "steamapps" / "appmanifest_500.acf").write_text('"AppState"\n{', encoding="utf-8")

            with patch("steam._steam_root", return_value=root):
                games = scan_installed_games()
            self.assertEqual(games, [
                {"app_id": "100", "name": "Alpha", "path": first_path},
                {"app_id": "300", "name": "Legacy", "path": legacy_path},
                {"app_id": "200", "name": '测试 "游戏"', "path": second_path},
            ])

    def test_no_steam_installation_returns_empty_list(self):
        with patch("steam._steam_root", return_value=None):
            self.assertEqual(scan_installed_games(), [])
