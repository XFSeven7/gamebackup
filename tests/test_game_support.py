import base64
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from game_support import GameSupportRegistry
from support_updates import MANIFEST_URL, support_asset_url


class GameSupportTest(unittest.TestCase):
    def test_official_pack_activates_without_replacing_app_and_is_reverified_at_restart(self):
        key = Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes_raw()
        responses = {}
        rows = []
        for version, minimum, maximum in (("1.1.0", 1, 1), ("2.0.0", 2, 3)):
            metadata = {
                "id": "onimusha", "version": version, "api_min": minimum, "api_max": maximum,
                "name": "鬼武者", "notes": "调整摘要与分支说明",
                "match": {"steam_app_ids": ["2638890"]},
                "layout": {"sections": ["inventory", "facts"], "branch_labels": {"before": "战斗前"}},
            }
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as archive:
                archive.writestr("support.json", json.dumps(metadata))
                archive.writestr("__init__.py", "from .reader import summarize, read_event_state, major_events\n")
                archive.writestr("reader.py", """
def summarize(*args):
    return {"slots": [], "test": True}

def read_event_state(*args):
    return {}

def major_events(*args):
    return []
""")
            data = buffer.getvalue()
            url = support_asset_url("onimusha", version, "1.2.0")
            responses[url] = data
            rows.append({
                **{key: metadata[key] for key in ("id", "version", "api_min", "api_max")},
                "url": url, "sha256": hashlib.sha256(data).hexdigest(),
                "signature": base64.b64encode(key.sign(data)).decode("ascii"),
            })
        responses[MANIFEST_URL] = json.dumps({"schema": 1, "packs": rows}).encode()
        item = SimpleNamespace(steam_app_id="2638890", path="save")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = GameSupportRegistry(root, public)
            self.assertEqual(registry.for_item(item).version, "1.0.0")
            with patch("support_updates._download", side_effect=lambda url, *_: responses[url]) as download:
                candidates = registry.stage_updates()
                self.assertEqual([p.version for p in candidates], ["1.1.0"])
                self.assertEqual(download.call_count, 2)
                self.assertEqual(registry.for_item(item).version, "1.0.0")
                self.assertTrue(registry.activate(candidates))
                self.assertEqual(registry.stage_updates(), [])
            pack = registry.for_item(item)
            self.assertEqual(pack.info()["source"], "downloaded")
            self.assertEqual(pack.info()["notes"], "调整摘要与分支说明")
            self.assertEqual(pack.layout["sections"], ["inventory", "facts"])
            self.assertTrue(pack.module.summarize()["test"])
            installed = root / "onimusha" / "1.1.0"
            self.assertFalse(any(installed.rglob("__pycache__")))
            self.assertEqual(GameSupportRegistry(root, public).for_item(item).version, "1.1.0")
            (installed / "reader.py").write_text("raise AssertionError('unsigned')", encoding="utf-8")
            self.assertEqual(GameSupportRegistry(root, public).for_item(item).version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
