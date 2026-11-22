"""Verify and install official game support packages without replacing the app."""

import base64
from collections import defaultdict
import hashlib
from http.client import HTTPException
import io
import json
import ntpath
from pathlib import Path, PureWindowsPath
import re
import shutil
import stat
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MANIFEST_URL = "https://raw.githubusercontent.com/XFSeven7/gamebackup-support/main/manifest.json"
_ASSET = re.compile(
    r"https://github\.com/XFSeven7/gamebackup-support/releases/download/"
    r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}/[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}\.zip"
)
_ASSET_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}
_ID = re.compile(r"[a-z][a-z0-9_]{0,47}", re.ASCII)
_VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})", re.ASCII)
_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", re.ASCII)
_IS_RESERVED = getattr(ntpath, "isreserved", lambda part: PureWindowsPath(part).is_reserved())
_MANIFEST_LIMIT = 256 * 1024
_ARCHIVE_LIMIT = 16 * 1024 * 1024
_UNPACKED_LIMIT = 64 * 1024 * 1024
_ALLOWED_FILES = {".py", ".json", ".tsv", ".csv", ".txt", ".md", ".toml", ".exe", ".dll", ".pyd"}
_PROOF_FILES = {".pack.zip", ".pack-receipt.json"}


def parse_version(value: object) -> tuple[int, int, int] | None:
    matched = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if matched:
        major, minor, patch = map(int, matched.groups())
        return major, minor, patch
    return None


def _approved_asset_url(url: str) -> bool:
    if _ASSET.fullmatch(url):
        return True
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.netloc in _ASSET_HOSTS


class _TrustedRedirect(HTTPRedirectHandler):
    def __init__(self, allowed):
        self.allowed = allowed

    def redirect_request(self, request, fp, code, message, headers, new_url):
        if not self.allowed(new_url):
            raise OSError("游戏支持包的下载地址不受信任。")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def _download(url: str, limit: int, allowed) -> bytes:
    client = build_opener(_TrustedRedirect(allowed))
    request = Request(url, headers={"User-Agent": "gamebackup-support"})
    data = bytearray()
    deadline = time.monotonic() + 25
    with client.open(request, timeout=10) as response:
        if not allowed(response.geturl()):
            raise OSError("游戏支持包的下载地址不受信任。")
        while chunk := response.read1(min(128 * 1024, limit + 1 - len(data))):
            data.extend(chunk)
            if len(data) > limit or time.monotonic() > deadline:
                raise OSError("游戏支持包的下载超出大小或时间限制。")
    return bytes(data)


def _descriptor(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    keys = ("id", "version", "api_min", "api_max", "url", "sha256", "signature")
    if not data.keys() >= set(keys):
        return None
    pack_id, version, api_min, api_max, url, checksum, signature = (data[key] for key in keys)
    if not (
        isinstance(pack_id, str) and _ID.fullmatch(pack_id) and not _IS_RESERVED(pack_id)
        and parse_version(version) is not None and type(api_min) is int and type(api_max) is int
        and 1 <= api_min <= api_max
        and isinstance(url, str) and _ASSET.fullmatch(url)
        and isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum)
        and isinstance(signature, str) and len(signature) == 88
    ):
        return None
    try:
        if len(base64.b64decode(signature, validate=True)) != 64:
            return None
    except ValueError:
        return None
    return {key: data[key] for key in keys}


def _authenticate(data: bytes, row: dict, key: Ed25519PublicKey) -> None:
    if len(data) > _ARCHIVE_LIMIT or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ValueError("游戏支持包的校验和不匹配。")
    key.verify(base64.b64decode(row["signature"], validate=True), data)


def _archive_members(archive: ZipFile) -> tuple[dict, set[str]]:
    files = {}
    directories = set()
    seen = set()
    expanded = 0
    members = archive.infolist()
    if len(members) > 512:
        raise ValueError("游戏支持包包含过多文件。")
    for entry in members:
        name = entry.orig_filename.replace("\\", "/")
        is_dir = name.endswith("/")
        parts = name.removesuffix("/").split("/")
        lower = tuple(part.casefold() for part in parts)
        mode = stat.S_IFMT(entry.external_attr >> 16)
        if (
            len(parts) > 12 or lower in seen or entry.flag_bits & 1
            or mode not in (0, stat.S_IFDIR if is_dir else stat.S_IFREG)
            or any(not _PART.fullmatch(part) or part.endswith(".") or _IS_RESERVED(part) for part in parts)
            or "__pycache__" in lower
        ):
            raise ValueError("游戏支持包包含不允许的归档路径。")
        seen.add(lower)
        relative = "/".join(parts)
        directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
        if is_dir:
            if entry.file_size:
                raise ValueError("游戏支持包包含无效的目录。")
            directories.add(relative)
            continue
        if Path(relative).suffix.casefold() not in _ALLOWED_FILES:
            raise ValueError("游戏支持包包含不支持的文件类型。")
        expanded += entry.file_size
        if expanded > _UNPACKED_LIMIT:
            raise ValueError("游戏支持包解压后超出大小限制。")
        files[relative] = entry
    paths = [*files, *directories]
    if (
        not {"support.json", "__init__.py"} <= files.keys()
        or len({name.casefold() for name in paths}) != len(paths)
    ):
        raise ValueError("游戏支持包缺少入口文件或包含重名路径。")
    return files, directories


def _check_identity(archive: ZipFile, files: dict, row: dict) -> None:
    entry = files["support.json"]
    if entry.file_size > _MANIFEST_LIMIT:
        raise ValueError("游戏支持包的说明文件超出大小限制。")
    metadata = json.loads(archive.read(entry))
    if not isinstance(metadata, dict) or any(
        type(metadata.get(name)) is not type(row[name]) or metadata.get(name) != row[name]
        for name in ("id", "version", "api_min", "api_max")
    ):
        raise ValueError("游戏支持包的说明文件与更新清单不匹配。")


def _extract(archive: ZipFile, files: dict, directories: set[str], destination: Path) -> None:
    for directory in directories:
        (destination / directory).mkdir(parents=True, exist_ok=True)
    for name, entry in files.items():
        with archive.open(entry) as source, (destination / name).open("xb") as output:
            shutil.copyfileobj(source, output)


def _read_limited(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("游戏支持包的文件无效。")
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("游戏支持包的文件超出大小限制。")
    return data


def _match_extracted(
    archive: ZipFile, path: Path, files: dict, directories: set[str], *, has_proof: bool = False,
) -> bool:
    actual = set()
    root = path.resolve()
    for item in path.rglob("*"):
        relative = item.relative_to(path).as_posix()
        if item.is_symlink() or item.resolve() != root / relative:
            return False
        if has_proof and relative in _PROOF_FILES and item.is_file():
            continue
        actual.add(relative)
        if item.is_dir():
            if relative not in directories:
                return False
            continue
        if relative not in files or not item.is_file():
            return False
        with item.open("rb") as disk, archive.open(files[relative]) as signed:
            while data := signed.read(128 * 1024):
                if disk.read(len(data)) != data:
                    return False
            if disk.read(1):
                return False
    return actual == files.keys() | directories


def verified_installed_descriptor(path: Path, public_key: bytes) -> dict | None:
    """Revalidate an installed package's signed bytes before loading its code."""
    try:
        if not path.is_dir() or path.is_symlink() or path.resolve().parent != path.parent.resolve():
            return None
        row = _descriptor(json.loads(_read_limited(path / ".pack-receipt.json", 4096)))
        if row is None or (row["id"], row["version"]) != (path.parent.name, path.name):
            return None
        data = _read_limited(path / ".pack.zip", _ARCHIVE_LIMIT)
        _authenticate(data, row, Ed25519PublicKey.from_public_bytes(public_key))
        with ZipFile(io.BytesIO(data)) as archive:
            files, directories = _archive_members(archive)
            _check_identity(archive, files, row)
            return row if _match_extracted(archive, path, files, directories, has_proof=True) else None
    except (OSError, ValueError, InvalidSignature, BadZipFile, RuntimeError, NotImplementedError):
        return None


def _install(pack_root: Path, row: dict, key: Ed25519PublicKey, validate) -> Path | None:
    game = pack_root / row["id"]
    target = game / row["version"]
    if target.exists() or game.is_symlink() or game.resolve().parent != pack_root.resolve():
        return None
    data = _download(row["url"], _ARCHIVE_LIMIT, _approved_asset_url)
    _authenticate(data, row, key)
    game.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=game) as workspace, ZipFile(io.BytesIO(data)) as archive:
        staging = Path(workspace) / row["version"]
        staging.mkdir()
        files, directories = _archive_members(archive)
        _check_identity(archive, files, row)
        _extract(archive, files, directories, staging)
        if validate(staging, row) is False or not _match_extracted(archive, staging, files, directories):
            return None
        (staging / ".pack.zip").write_bytes(data)
        (staging / ".pack-receipt.json").write_text(json.dumps(row), encoding="utf-8")
        staging.rename(target)
    return target


def check_support_updates(
    pack_root: Path, versions: dict[str, str], api_version: int, public_key: bytes, validate,
) -> list[Path]:
    """Try the newest compatible update for each game, keeping older packages usable."""
    try:
        key = Ed25519PublicKey.from_public_bytes(public_key)
        data = json.loads(_download(MANIFEST_URL, _MANIFEST_LIMIT, lambda url: url == MANIFEST_URL))
    except (OSError, ValueError, HTTPException):
        return []
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
        return []
    rows = data.get("packs")
    if not isinstance(rows, list):
        return []
    candidates = defaultdict(list)
    for entry in rows:
        row = _descriptor(entry)
        if row is None or not row["api_min"] <= api_version <= row["api_max"]:
            continue
        previous = parse_version(versions.get(row["id"]))
        version = parse_version(row["version"])
        if previous is None or version > previous:
            candidates[row["id"]].append((version, row))

    installed = []
    for rows in candidates.values():
        for _, row in sorted(rows, key=lambda pair: pair[0], reverse=True):
            try:
                target = _install(pack_root, row, key, validate)
            except Exception:
                # An individual download, validator, or disk write cannot break the current parser.
                continue
            if target is not None:
                installed.append(target)
                break
    return installed
