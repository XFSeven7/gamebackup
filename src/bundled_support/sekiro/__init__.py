"""Summarize tracked Sekiro backups."""

import re
from functools import lru_cache
from pathlib import Path

from dulwich.errors import NotGitRepository
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from .achievements import steam_achievements
from .save import read_save


@lru_cache(maxsize=24)
def _parse(repo: Path, blob_id: bytes) -> tuple[list[dict], int]:
    with Repo(str(repo)) as history:
        blob = history[blob_id]
    if not isinstance(blob, Blob):
        raise ValueError("该节点没有可读取的《只狼》存档。")
    return read_save(blob.data)


def _snapshot(repo: Repo, commit: Commit) -> tuple[list[dict], int]:
    tree = repo[commit.tree]
    if not isinstance(tree, Tree) or b"S0000.sl2" not in tree:
        raise ValueError("该节点没有 S0000.sl2 存档。")
    return _parse(Path(repo.path), tree[b"S0000.sl2"][1])


def summarize(repo: Path, commit_id: str, _tools_dir: Path) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise ValueError("找不到这个存档节点。")
    previous = {}
    try:
        with Repo(str(repo.resolve())) as history:
            commit = history[commit_id.lower().encode("ascii")]
            if not isinstance(commit, Commit):
                raise ValueError("找不到这个存档节点。")
            slots, account = _snapshot(history, commit)
            if commit.parents:
                try:
                    parent = history[commit.parents[0]]
                    if isinstance(parent, Commit):
                        earlier, older_account = _snapshot(history, parent)
                        if account == older_account:
                            previous = {slot["index"]: slot for slot in earlier}
                except (KeyError, OSError, ValueError):
                    pass
    except (KeyError, OSError, NotGitRepository) as error:
        raise ValueError("无法打开《只狼》的这份备份。") from error

    for_summary = []
    for slot in slots:
        old = previous.get(slot["index"])
        if old is not None and old["seconds"] > slot["seconds"]:
            old = None
        changes = []
        if old is not None:
            for label, after in {**slot["facts"], "游玩时长": slot["play_time"]}.items():
                before = old["play_time"] if label == "游玩时长" else old["facts"].get(label)
                if before is not None and before != after:
                    changes.append({"label": label, "before": before, "after": after})
            if old["facts"]["当前周目"] == slot["facts"]["当前周目"]:
                alive = {boss["name"] for boss in old["boss_progress"] or [] if not boss["unlocked"]}
                defeated = [boss["name"] for boss in slot["boss_progress"] or []
                            if boss["unlocked"] and boss["name"] in alive]
                if defeated:
                    changes.append({"label": "新击败 Boss", "before": "无", "after": "、".join(defeated)})
        for_summary.append({**slot, "has_previous": old is not None, "changes": changes})
    return {"slots": for_summary, "achievements": steam_achievements(account)}


def available(_tools_dir: Path) -> bool:
    # Keep the API 1 host's regular backup schedule.
    return False


def read_event_state(_snapshot: Path, _tools_dir: Path) -> None:
    return None


def major_events(_before: dict, _after: dict) -> list[str]:
    return []
