"""对存档文件夹做指纹：只看文件内容，时间戳变了不算改动。"""

from __future__ import annotations

import hashlib
from pathlib import Path


def _file_digest(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.digest()


def fingerprint(root: Path) -> str:
    """用相对路径和文件内容生成稳定哈希。目录不存在则抛 FileNotFoundError。"""
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise FileNotFoundError(root)

    h = hashlib.sha256()
    files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_symlink():
            continue
        if p.is_file():
            files.append(p)

    for p in sorted(files, key=lambda x: x.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8", errors="surrogateescape"))
        h.update(b"\0")
        h.update(_file_digest(p))
        h.update(b"\n")
    return h.hexdigest()
