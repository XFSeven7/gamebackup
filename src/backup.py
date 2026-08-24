"""一次备份、添加文件夹、回档。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from config import ManagedFolder, find_item, load, new_id, save
from fingerprint import fingerprint
from store import commit_auto, create_line, graph, init_repo, reset_to, worktree_has_changes
from sync import mirror


def repo_dir(root: Path, item_id: str) -> Path:
    return Path(root) / "repos" / item_id


def _write_item(root: Path, item: ManagedFolder) -> None:
    cfg = load(root)
    for i, it in enumerate(cfg.items):
        if it.id == item.id:
            cfg.items[i] = item
            save(root, cfg)
            return
    cfg.items.append(item)
    save(root, cfg)


def add_folder(root: Path, live_path: Path, name: str) -> ManagedFolder:
    root = Path(root)
    live_path = Path(live_path).resolve()
    cfg = load(root)
    item = ManagedFolder(id=new_id(), name=name or live_path.name, path=str(live_path))
    init_repo(repo_dir(root, item.id))
    cfg.items.append(item)
    save(root, cfg)
    backup_once(root, item)
    # backup_once 会写回指纹，重新读
    cfg = load(root)
    found = find_item(cfg, item.id)
    return found if found else item


def backup_once(root: Path, item: ManagedFolder) -> dict:
    live = Path(item.path)
    if item.paused:
        return {"skipped": True, "reason": "paused"}
    if not live.is_dir():
        return {"skipped": True, "reason": "missing"}
    try:
        fp = fingerprint(live)
    except OSError as e:
        return {"skipped": True, "reason": str(e)}
    if fp == item.last_fingerprint:
        return {"skipped": True, "reason": "unchanged"}
    repo = repo_dir(root, item.id)
    try:
        mirror(live, repo)
        if not worktree_has_changes(repo):
            item.last_fingerprint = fp
            _write_item(root, item)
            return {"skipped": True, "reason": "unchanged"}
        commit_auto(repo)
        item.last_fingerprint = fp
        _write_item(root, item)
        return {"skipped": False, "reason": "ok"}
    except OSError as e:
        return {"skipped": True, "reason": str(e)}


def restore(root: Path, item: ManagedFolder, commit_id: str, fork: bool) -> None:
    backup_once(root, item)
    repo = repo_dir(root, item.id)
    cfg = load(root)
    fresh = find_item(cfg, item.id) or item
    if fork:
        g = graph(repo, hide_auto=False, current_line=fresh.current_line)
        tip = g["current_id"]
        if tip:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            create_line(repo, tip, f"换档前-{stamp}")
    reset_to(repo, commit_id)
    live = Path(fresh.path)
    mirror(repo, live)
    fresh.last_fingerprint = fingerprint(live)
    item.last_fingerprint = fresh.last_fingerprint
    item.current_line = fresh.current_line
    _write_item(root, fresh)
