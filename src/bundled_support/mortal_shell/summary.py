"""Read-only summaries of Mortal Shell 2 save snapshots."""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from dulwich.errors import NotGitRepository
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from .save import CURRENCY_NAMES, ITEM_NAMES as MORTAL_SHELL_ITEMS, read_slot as read_mortal_shell_slot


def _snapshot_commits(repo: Repo, commit_id: str):
    commit = repo[commit_id.lower().encode("ascii")]
    if not isinstance(commit, Commit):
        raise ValueError("找不到这个存档节点。")
    parent = None
    if commit.parents:
        try:
            parent = repo[commit.parents[0]]
        except (KeyError, OSError, ValueError):
            pass
    return commit, parent if isinstance(parent, Commit) else None


_MORTAL_SHELL_SLOTS = {
    b"WorldState_0.sav": (0, "存档槽 1"),
    b"WorldState_1.sav": (1, "存档槽 2"),
    b"WorldState_2.sav": (2, "存档槽 3"),
    b"Demo_WorldState_0.sav": (3, "试玩存档"),
}


@lru_cache(maxsize=64)
def _decode_mortal_shell_slot(repo_path: Path, blob_id: bytes) -> dict:
    with Repo(str(repo_path)) as history:
        blob = history[blob_id]
    if not isinstance(blob, Blob):
        raise ValueError("该节点的存档文件无法读取。")
    return read_mortal_shell_slot(blob.data)


def _mortal_shell_slots(history: Repo, commit: Commit | None) -> dict:
    tree = history[commit.tree] if commit is not None else None
    slots = {}
    if isinstance(tree, Tree):
        for filename, (index, label) in _MORTAL_SHELL_SLOTS.items():
            if filename not in tree:
                continue
            try:
                slot = _decode_mortal_shell_slot(Path(history.path), tree[filename][1])
            except (KeyError, OSError, ValueError, OverflowError):
                continue
            slots[index] = {**slot, "index": index, "label": label}
    return slots


def summarize_mortal_shell(repo: Path, commit_id: str, tools_dir: Path | None = None) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise ValueError("找不到这个存档节点。")
    try:
        with Repo(str(repo.resolve())) as history:
            commit, parent = _snapshot_commits(history, commit_id)
            slots = _mortal_shell_slots(history, commit)
            try:
                previous = _mortal_shell_slots(history, parent)
            except (KeyError, OSError, ValueError):
                previous = {}
    except (KeyError, OSError, NotGitRepository) as error:
        raise ValueError("找不到这个存档节点。") from error
    if not slots:
        raise ValueError("该节点没有可解析的《致命躯壳 2》世界存档。")

    summaries = []
    for index, slot in slots.items():
        old = previous.get(index)
        inventory = slot["inventory"]
        old_inventory = old["inventory"] if old is not None else Counter()
        items = [
            {
                "id": key, "name": MORTAL_SHELL_ITEMS.get(key, key),
                "quantity": inventory[key],
                "delta": inventory[key] - old_inventory[key] if old is not None else None,
            }
            for key in sorted(inventory.keys() | old_inventory.keys(), key=str.casefold)
            if inventory[key] or old_inventory[key]
        ]
        changes = []
        if old is not None:
            for label, value in {**slot["facts"], "重生点": slot["location"]}.items():
                if label in CURRENCY_NAMES.values():
                    continue  # Currency is already compared with the inventory.
                before = old["location"] if label == "重生点" else old["facts"].get(label)
                if before is not None and value is not None and before != value:
                    changes.append({"label": label, "before": before, "after": value})
        summaries.append({
            **{key: value for key, value in slot.items() if key != "inventory"},
            "has_previous": old is not None, "items": items, "changes": changes,
        })
    return {"slots": summaries}
