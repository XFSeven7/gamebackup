"""把源目录镜像到目标目录。不碰目标里的 .git，也不把源里的 .git 拷过去。"""

from __future__ import annotations

import shutil
from pathlib import Path


def _ignore_git(_dir: str, names: list[str]) -> list[str]:
    return [n for n in names if n == ".git"]


def _is_git_path(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    return parts[:1] == (".git",) or ".git" in parts


def mirror(src: Path, dst: Path) -> None:
    """dst 变成 src 的镜像。incoming 失败时不动 dst。"""
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        raise FileNotFoundError(src)

    incoming = dst.parent / f"{dst.name}.tmp-incoming"
    if incoming.exists():
        shutil.rmtree(incoming)
    try:
        shutil.copytree(src, incoming, ignore=_ignore_git, symlinks=False)
    except Exception:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)
        raise

    try:
        dst.mkdir(parents=True, exist_ok=True)
        _replace_tree(incoming, dst)
    finally:
        if incoming.exists():
            shutil.rmtree(incoming, ignore_errors=True)


def _replace_tree(incoming: Path, dst: Path) -> None:
    incoming_rels = {
        p.relative_to(incoming) for p in incoming.rglob("*") if not _is_git_path(p, incoming)
    }
    for p in sorted(dst.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if _is_git_path(p, dst):
            continue
        rel = p.relative_to(dst)
        if rel not in incoming_rels:
            if p.is_file() or p.is_symlink():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    shutil.rmtree(p, ignore_errors=True)

    for p in incoming.rglob("*"):
        if _is_git_path(p, incoming):
            continue
        target = dst / p.relative_to(incoming)
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif p.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
