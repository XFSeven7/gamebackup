"""Create the signed game packs for one support release."""

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.hazmat.primitives.serialization import load_pem_private_key

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from game_support import BUNDLED_SUPPORT, SUPPORT_PUBLIC_KEY
from support_updates import parse_version, support_asset_url


def build_zip(source: Path, output: Path) -> bytes:
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if path.is_file() and "__pycache__" not in relative.parts and path.suffix not in (".pyc", ".pyo"):
                archive.write(path, relative.as_posix())
    return output.read_bytes()


def main() -> None:
    default_key = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "gamebackup-release-signing" / "game-support-ed25519.pem"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_version", help="Version for the shared support-v… tag")
    parser.add_argument("--key", type=Path, default=default_key)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "game-support")
    parser.add_argument("--previous-manifest", type=Path, default=ROOT / "game-support" / "manifest.json")
    args = parser.parse_args()

    if parse_version(args.release_version) is None:
        parser.error("请输入发布版本号，例如 1.1.0")
    manifest = json.loads(args.previous_manifest.read_text(encoding="utf-8"))
    known_versions = {(row["id"], row["version"]) for row in manifest["packs"]}
    pending = []
    for source in sorted(BUNDLED_SUPPORT.iterdir()):
        descriptor = source / "support.json"
        if not descriptor.is_file():
            continue
        metadata = json.loads(descriptor.read_text(encoding="utf-8-sig"))
        identity = {key: metadata[key] for key in ("id", "version", "api_min", "api_max")}
        if identity["id"] != source.name or parse_version(identity["version"]) is None:
            parser.error(f"支持包编号或版本无效：{descriptor}")
        if (identity["id"], identity["version"]) not in known_versions:
            pending.append((source, identity))
    if not pending:
        parser.error("没有新版本的游戏支持包，请先提高需要发布的支持包版本")

    private_key = load_pem_private_key(args.key.read_bytes(), password=None)
    if private_key.public_key().public_bytes_raw() != SUPPORT_PUBLIC_KEY:
        parser.error("签名密钥与应用内置的公钥不匹配")
    release_dir = args.out / f"support-v{args.release_version}"
    release_dir.mkdir(parents=True, exist_ok=True)
    for source, identity in pending:
        pack_id, version = identity["id"], identity["version"]
        output = release_dir / f"{pack_id}-v{version}.zip"
        data = build_zip(source, output)
        manifest["packs"].append({
            **identity,
            "url": support_asset_url(pack_id, version, args.release_version),
            "sha256": hashlib.sha256(data).hexdigest(),
            "signature": base64.b64encode(private_key.sign(data)).decode("ascii"),
        })
        print(output)
    manifest_path = release_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__":
    main()
