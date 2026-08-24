"""对存档文件夹做指纹：没改动就可以跳过备份。"""

from __future__ import annotations

import hashlib
from pathlib import Path


def fingerprint(root: Path) -> str:
    """用相对路径、大小、mtime 生成稳定哈希。目录不存在则抛 FileNotFoundError。"""
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise FileNotFoundError(root)

    h = hashlib.sha256()
    files: list[Path] = []
    for p in root.rglob("*"):
        # ponytail: 不跟随目录链接，避免扫到盘符循环
        if p.is_symlink():
            continue
        if p.is_file():
            files.append(p)

    for p in sorted(files, key=lambda x: x.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        st = p.stat()
        h.update(rel.encode("utf-8", errors="surrogateescape"))
        h.update(b"\0")
        h.update(str(st.st_size).encode())
        h.update(b"\0")
        h.update(str(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))).encode())
        h.update(b"\n")
    return h.hexdigest()
