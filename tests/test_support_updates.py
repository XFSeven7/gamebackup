import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from support_updates import MANIFEST_URL, check_support_updates, support_asset_url, verified_installed_descriptor


class SupportUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public_key = self.key.public_key().public_bytes_raw()

    def asset(self, version, api_min=1, api_max=1, *, extra=None, pack_id="onimusha"):
        descriptor = {"id": pack_id, "version": version, "api_min": api_min, "api_max": api_max}
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as pack:
            pack.writestr("support.json", json.dumps(descriptor))
            pack.writestr("__init__.py", "# package")
            if extra is not None:
                pack.writestr(extra, "unsafe file")
        archive = buffer.getvalue()
        descriptor.update({
            "url": support_asset_url(pack_id, version, version),
            "sha256": hashlib.sha256(archive).hexdigest(),
            "signature": base64.b64encode(self.key.sign(archive)).decode("ascii"),
        })
        return descriptor, archive

    def run_update(self, root, assets, active, api=1, validate=lambda *_: None):
        downloads = {row["url"]: archive for row, archive in assets}
        downloads[MANIFEST_URL] = json.dumps({"schema": 1, "packs": [row for row, _ in assets]}).encode()
        with patch("support_updates._download", side_effect=lambda url, *_: downloads[url]) as download:
            installed = check_support_updates(root, active, api, self.public_key, validate)
            urls = [call.args[0] for call in download.call_args_list]
        return installed, urls

    def test_picks_newest_compatible_version_and_keeps_signed_proof(self):
        seen = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            newer = self.asset("3.0.0", 2, 3)
            current = self.asset("2.0.0", 1, 2)
            older = self.asset("1.9.0")
            installed, urls = self.run_update(
                root, [newer, older, current], {"onimusha": "1.1.0"},
                validate=lambda path, descriptor: seen.append((path.is_dir(), descriptor["version"])),
            )
            target = root / "onimusha" / "2.0.0"
            self.assertEqual(installed, [target])
            self.assertEqual(urls, [MANIFEST_URL, current[0]["url"]])
            self.assertEqual(seen, [(True, "2.0.0")])
            self.assertEqual(verified_installed_descriptor(target, self.public_key), current[0])
            receipt = target / ".pack-receipt.json"
            archived = {**current[0], "url": "https://github.com/XFSeven7/gamebackup-support/releases/download/onimusha-v2.0.0/onimusha-v2.0.0.zip"}
            receipt.write_text(json.dumps(archived), encoding="utf-8")
            self.assertEqual(verified_installed_descriptor(target, self.public_key), archived)
            previous = {**current[0], "url": "https://github.com/XFSeven7/gamebackup/releases/download/support-onimusha-v2.0.0/onimusha-v2.0.0.zip"}
            receipt.write_text(json.dumps(previous), encoding="utf-8")
            self.assertEqual(verified_installed_descriptor(target, self.public_key), previous)
            receipt.write_text(json.dumps({**current[0], "api_min": 2}), encoding="utf-8")
            self.assertIsNone(verified_installed_descriptor(target, self.public_key))
            receipt.write_text(json.dumps(current[0]), encoding="utf-8")
            (target / "unexpected.py").write_text("tampered", encoding="utf-8")
            self.assertIsNone(verified_installed_descriptor(target, self.public_key))
            (target / "unexpected.py").unlink()
            (target / "__init__.py").write_text("tampered", encoding="utf-8")
            self.assertIsNone(verified_installed_descriptor(target, self.public_key))

    def test_bad_signature_and_validator_failure_can_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            invalid = self.asset("3.0.0")
            invalid[0]["signature"] = base64.b64encode(bytes(64)).decode("ascii")
            reject = self.asset("2.0.0")
            compatible = self.asset("1.1.0")

            def validate(path, descriptor):
                if descriptor["version"] == "2.0.0":
                    raise ImportError("runtime incompatible")

            installed, urls = self.run_update(root, [compatible, reject, invalid], {}, validate=validate)
            self.assertEqual(installed, [root / "onimusha" / "1.1.0"])
            self.assertEqual(urls, [MANIFEST_URL, invalid[0]["url"], reject[0]["url"], compatible[0]["url"]])
            self.assertEqual(list((root / "onimusha").iterdir()), installed)

    def test_does_not_fetch_downgrade_or_unofficial_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unofficial = self.asset("9.9.0")
            unofficial[0]["url"] = "https://github.com/Other/gamebackup-support/releases/download/v9/onimusha.zip"
            installed, urls = self.run_update(root, [unofficial, self.asset("1.0.0")], {"onimusha": "2.0.0"})
            self.assertEqual(installed, [])
            self.assertEqual(urls, [MANIFEST_URL])

    def test_feed_uses_main_repository_and_rejects_the_archived_feed_urls(self):
        self.assertEqual(
            MANIFEST_URL, "https://raw.githubusercontent.com/XFSeven7/gamebackup/main/game-support/manifest.json",
        )
        archived, archive = self.asset("2.0.0")
        archived["url"] = "https://github.com/XFSeven7/gamebackup-support/releases/download/onimusha-v2.0.0/onimusha-v2.0.0.zip"
        with tempfile.TemporaryDirectory() as temp:
            installed, urls = self.run_update(Path(temp), [(archived, archive)], {})
            self.assertEqual(installed, [])
            self.assertEqual(urls, [MANIFEST_URL])

    def test_two_games_can_share_release_tag_with_different_pack_versions(self):
        first, first_archive = self.asset("2.0.0")
        second, second_archive = self.asset("1.1.0", pack_id="mortal_shell")
        release = "https://github.com/XFSeven7/gamebackup/releases/download/support-v4.2.0"
        first["url"] = f"{release}/onimusha-v2.0.0.zip"
        second["url"] = f"{release}/mortal_shell-v1.1.0.zip"
        with tempfile.TemporaryDirectory() as temp:
            installed, _ = self.run_update(Path(temp), [(first, first_archive), (second, second_archive)], {})
            self.assertEqual({path.parent.name: path.name for path in installed},
                             {"onimusha": "2.0.0", "mortal_shell": "1.1.0"})

    def test_rejects_signed_archive_with_disallowed_paths_before_validation(self):
        for entry in ("../escape.py", "NUL.txt", "subdir/file:stream", "__INIT__.PY",
                      ".pack-receipt.json", "pkg/../runner.py"):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as temp:
                touched = []
                installed, _ = self.run_update(Path(temp), [self.asset("2.0.0", extra=entry)], {},
                                               validate=lambda *_: touched.append(True))
                self.assertEqual(installed, [])
                self.assertEqual(touched, [])

    def test_validator_cannot_publish_unsigned_extracted_files(self):
        with tempfile.TemporaryDirectory() as temp:
            def validate(path, _descriptor):
                (path / "later.py").write_text("unsigned", encoding="utf-8")

            installed, _ = self.run_update(Path(temp), [self.asset("2.0.0")], {}, validate=validate)
            self.assertEqual(installed, [])
            self.assertEqual(list((Path(temp) / "onimusha").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
