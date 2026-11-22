"""Read-only analysis of native Elden Ring PC saves."""

import json
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from dulwich.errors import NotGitRepository
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from .achievements import steam_achievements
from .save import read_save, save_account


@lru_cache(maxsize=24)
def _slots(repo: Path, blob_id: bytes) -> tuple[list[dict], int]:
    with Repo(str(repo)) as history:
        blob = history[blob_id]
    if not isinstance(blob, Blob):
        raise ValueError("该节点没有可读取的《艾尔登法环》存档。")
    return read_save(blob.data), save_account(blob.data)


def _blob_id(history: Repo, commit_id: bytes) -> bytes:
    commit = history[commit_id]
    if not isinstance(commit, Commit):
        raise ValueError("找不到这个存档节点。")
    tree = history[commit.tree]
    if not isinstance(tree, Tree) or b"ER0000.sl2" not in tree:
        raise ValueError("该节点没有 ER0000.sl2 存档。")
    return tree[b"ER0000.sl2"][1]


def _read_commit(history: Repo, commit_id: bytes) -> tuple[list[dict], int]:
    return _slots(Path(history.path), _blob_id(history, commit_id))


def _same_character(slot: dict, old: dict) -> bool:
    return slot["label"] == old["label"] and slot["seconds"] >= old["seconds"]


def _new_kills(slot: dict, old: dict | None) -> list[str]:
    if old is None or not _same_character(slot, old):
        return []
    current_journey = slot["facts"].get("当前周目")
    if not current_journey or current_journey != old["facts"].get("当前周目"):
        return []
    previously_alive = {boss["name"] for boss in old["boss_progress"] or [] if not boss["unlocked"]}
    return [boss["name"] for boss in slot["boss_progress"] or []
            if boss["unlocked"] and boss["name"] in previously_alive]


def summarize(repo: Path, commit_id: str, _tools_dir: Path) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise ValueError("找不到这个存档节点。")
    try:
        with Repo(str(repo.resolve())) as history:
            key = commit_id.lower().encode("ascii")
            slots, account = _read_commit(history, key)
            commit = history[key]
            previous = {}
            if commit.parents:
                try:
                    older, _ = _read_commit(history, commit.parents[0])
                    previous = {slot["index"]: slot for slot in older}
                except (KeyError, OSError, ValueError):
                    pass
    except (KeyError, OSError, NotGitRepository) as error:
        raise ValueError("无法打开《艾尔登法环》的这份备份。") from error

    result = []
    for slot in slots:
        old = previous.get(slot["index"])
        if old is not None and not _same_character(slot, old):
            old = None
        changes = []
        if old is not None:
            for label, value in slot["facts"].items():
                before = old["facts"].get(label)
                if before is not None and before != value:
                    changes.append({"label": label, "before": before, "after": value})
            if slot["seconds"] != old["seconds"]:
                changes.append({"label": "游玩时长", "before": old["play_time"], "after": slot["play_time"]})
        result.append({
            "index": slot["index"], "label": slot["label"], "play_time": slot["play_time"],
            "facts": slot["facts"], "has_previous": old is not None, "changes": changes,
            "boss_progress": slot["boss_progress"], "boss_unlocked": _new_kills(slot, old),
        })
    return {"slots": result, "achievements": steam_achievements(account)}


def _index_path(repo: Path, version: str | None) -> Path:
    safe_version = version if version and re.fullmatch(r"\d+\.\d+\.\d+", version) else "1"
    return repo / ".git" / f"gamebackup-elden-ring-boss-{safe_version}.json"


def load_index(repo: Path, *, cache_version: str | None = None) -> dict:
    try:
        value = json.loads(_index_path(repo, cache_version).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {key: slots for key, slots in value.items() if slots is None or (
        isinstance(slots, list) and all(
            isinstance(slot, dict) and type(slot.get("index")) is int
            and isinstance(slot.get("label"), str) and type(slot.get("seconds")) is int
            and isinstance(slot.get("facts"), dict) and "boss_progress" in slot
            and (slot["boss_progress"] is None or (
                isinstance(slot["boss_progress"], list) and all(
                    isinstance(boss, dict) and isinstance(boss.get("name"), str)
                    and type(boss.get("unlocked")) is bool for boss in slot["boss_progress"]
                )
            )) for slot in slots
        )
    )}


def save_index(repo: Path, index: dict, *, cache_version: str | None = None) -> None:
    path = _index_path(repo, cache_version)
    with tempfile.TemporaryDirectory(dir=path.parent) as temp:
        pending = Path(temp) / path.name
        pending.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        pending.replace(path)


def annotate_nodes(repo: Path, nodes: list[dict], index: dict) -> set[str]:
    needed = set()
    blobs = {}
    with Repo(str(repo)) as history:
        for node in nodes:
            try:
                blobs[node["id"]] = _blob_id(history, node["id"].encode("ascii")).decode("ascii")
            except (KeyError, OSError, ValueError):
                continue
    for node in nodes:
        if not node["parents"]:
            continue
        current = blobs.get(node["id"])
        previous = blobs.get(node["parents"][0])
        if not current or not previous or current == previous:
            continue
        needed.update((current, previous))
        prior = {slot["index"]: slot for slot in index.get(previous) or []}
        names = list(dict.fromkeys(
            name for slot in index.get(current) or []
            for name in _new_kills(slot, prior.get(slot["index"]))
        ))
        if names:
            node["boss_milestone"] = {"names": names, "defeated": names}
    return needed - index.keys()


def scan_index(repo: Path, _tools_dir: Path, missing: set[str], should_stop) -> dict:
    decoded = {}
    for name in missing:
        if should_stop():
            break
        try:
            slots, _ = _slots(repo, name.encode("ascii"))
            decoded[name] = [{
                "index": slot["index"], "label": slot["label"], "seconds": slot["seconds"],
                "facts": {"当前周目": slot["facts"].get("当前周目")}, "boss_progress": slot["boss_progress"],
            } for slot in slots]
        except (KeyError, OSError, ValueError):
            decoded[name] = None
    return decoded


def index_available(_tools_dir: Path) -> bool:
    return True


def available(_tools_dir: Path) -> bool:
    # The API 1 host uses this check for event-only backup. Keep timed backups.
    return False


def read_event_state(_snapshot: Path, _tools_dir: Path) -> None:
    return None


def major_events(_before: dict, _after: dict) -> list[str]:
    return []
