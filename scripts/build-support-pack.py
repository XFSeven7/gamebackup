"""Create a game support ZIP and its signed GitHub update manifest entry."""

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


def main() -> None:
    default_key = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "gamebackup-release-signing" / "game-support-ed25519.pem"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id", choices=sorted(path.name for path in BUNDLED_SUPPORT.iterdir() if (path / "support.json").is_file()))
    parser.add_argument("--key", type=Path, default=default_key)
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "game-support")
    parser.add_argument("--previous-manifest", type=Path)
    args = parser.parse_args()

    source = BUNDLED_SUPPORT / args.id
    metadata = json.loads((source / "support.json").read_text(encoding="utf-8-sig"))
    identity = {key: metadata[key] for key in ("id", "version", "api_min", "api_max")}
    private_key = load_pem_private_key(args.key.read_bytes(), password=None)
    if private_key.public_key().public_bytes_raw() != SUPPORT_PUBLIC_KEY:
        parser.error("签名密钥与应用内置的公钥不匹配")
    args.out.mkdir(parents=True, exist_ok=True)
    tag = f"{args.id}-v{metadata['version']}"
    output = args.out / f"{tag}.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if path.is_file() and "__pycache__" not in relative.parts and path.suffix not in (".pyc", ".pyo"):
                archive.write(path, relative.as_posix())
    data = output.read_bytes()
    entry = {
        **identity,
        "url": f"https://github.com/XFSeven7/gamebackup-support/releases/download/{tag}/{output.name}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "signature": base64.b64encode(private_key.sign(data)).decode("ascii"),
    }
    manifest = {"schema": 1, "packs": []}
    if args.previous_manifest:
        manifest = json.loads(args.previous_manifest.read_text(encoding="utf-8"))
    existing = [row for row in manifest["packs"] if (row["id"], row["version"]) == (args.id, metadata["version"])]
    if not existing:
        manifest["packs"].append(entry)
    elif existing != [entry]:
        parser.error("同版本的已发布文件不一致，请提高支持包版本号")
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    print(manifest_path)


if __name__ == "__main__":
    main()
