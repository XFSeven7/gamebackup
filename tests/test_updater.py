import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from updater import Release, check_release, stage_release


def release_data(tag="v1.2.0"):
    return {
        "tag_name": tag,
        "body": "## 更新\n\n- 新增存档分支",
        "assets": [{
            "name": "gamebackup-win64.zip",
            "state": "uploaded",
            "size": 123,
            "digest": "sha256:" + "a" * 64,
            "browser_download_url":
                f"https://github.com/XFSeven7/gamebackup/releases/download/{tag}/gamebackup-win64.zip",
        }],
    }


def package(extra=None):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("gamebackup/gamebackup.exe", "new")
        archive.writestr("gamebackup/_internal/ui/index.html", "new")
        if extra:
            archive.writestr(extra, "unexpected")
    return buffer.getvalue()


class UpdaterTest(unittest.TestCase):
    def test_release_uses_latest_windows_asset_and_keeps_notes(self):
        data = release_data()
        with patch("updater.urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as request:
            release = check_release("v1.1.9")
        self.assertTrue(request.call_args.args[0].full_url.endswith("/releases/latest"))
        self.assertEqual(release.version, "v1.2.0")
        self.assertEqual(release.notes, data["body"])
        self.assertEqual(release.size, 123)

    def test_previews_and_non_newer_releases_are_skipped(self):
        for tag in ("v1.9.0-rc.1", "v1.1.1", "v1.1.0"):
            with self.subTest(tag=tag), patch(
                "updater.urlopen", return_value=io.BytesIO(json.dumps(release_data(tag)).encode())
            ):
                self.assertIsNone(check_release("v1.1.1"))

    def test_invalid_asset_url_is_rejected(self):
        data = release_data()
        data["assets"][0]["browser_download_url"] = "https://example.com/file.zip"
        with patch("updater.urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
            self.assertIsNone(check_release("v1.1.1"))

    def stage(self, data, work, digest=None):
        statuses = []
        release = Release("v1.2.0", "", "https://github.com/test", len(data),
                          digest or hashlib.sha256(data).hexdigest())
        with patch("updater.urlopen", return_value=io.BytesIO(data)):
            stage_release(release, work, lambda *status: statuses.append(status))
        return statuses

    def test_download_reports_bytes_and_stages_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            data = package()
            self.assertEqual(self.stage(data, work), [("downloading", len(data)), ("verifying", len(data))])
            self.assertEqual((work / "gamebackup/gamebackup.exe").read_text(), "new")
            self.assertTrue((work / "gamebackup/_internal/ui/index.html").is_file())

    def test_checksum_mismatch_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            with self.assertRaises(ValueError):
                self.stage(package(), work, "0" * 64)
            self.assertFalse((work / "gamebackup").exists())

    def test_accepts_backslashes_from_windows_compress_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            data = package()
            for filename in (b"gamebackup/gamebackup.exe", b"gamebackup/_internal/ui/index.html"):
                data = data.replace(filename, filename.replace(b"/", b"\\"))
            self.stage(data, work)
            self.assertTrue((work / "gamebackup/_internal/ui/index.html").is_file())

    def test_invalid_windows_archive_paths_are_rejected(self):
        for member in ("gamebackup\\..\\escape.exe", "gamebackup/_internal/NUL.txt",
                       "gamebackup/_internal/UI/INDEX.HTML", "gamebackup/_internal/file:stream"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                with self.assertRaises(ValueError):
                    self.stage(package(member), work)
                self.assertFalse((work / "gamebackup").exists())
