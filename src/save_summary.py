"""Read-only summaries of save snapshots."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dulwich.errors import NotGitRepository
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from mortal_shell_save import CURRENCY_NAMES, ITEM_NAMES as MORTAL_SHELL_ITEMS, read_slot as read_mortal_shell_slot
from onimusha_items_zh import ITEM_NAMES_ZH

_SAVE_NAME = "data001Slot.bin"
_PLAY_TIME = re.compile(r"^(/[^/]+/[^/]+/([0-9]+))/_Data/_ResourceData/PlayTime$")
_ITEM_ID = re.compile(r"^(/[^/]+/[^/]+/[0-9]+)/_Data/_Items/[0-9]+/ItemID$")
_ONIMUSHA_SAVE_TIME = "%m/%d/%Y %H:%M:%S"
# Fixed IDs from app.RematchBoss.ID_Fixed, ordered by the story route.
# https://github.com/seifhassine/REasy/blob/master/resources/data/enums/oniwots_enums.json
# https://onimushawots.wiki/guides
_ONIMUSHA_BOSS_NAMES = {
    354: "佐佐木巌流",
    12224: "大唾拉",
    28045: "罗掌愿",
    30569: "百秽",
    26446: "畏风",
    5865: "鵺（青＆赤）",
    30616: "大鵺",
    5370: "百秽（强化）",
    26515: "怒伐天",
    28128: "怒伐天（强化）",
    30875: "弁庆",
    17004: "抚雷",
    6309: "酒吞童子",
    16869: "畏风＆抚雷",
    21015: "佐佐木巌流（变异）",
    21579: "道狂",
    6164: "弁庆（完全武装）",
    17066: "源义经",
}
# Avoid running multiple memory-intensive parsers when the user clicks through nodes quickly.
_DECODE_LOCK = Lock()


def _onimusha_boss_progress(values: dict, slot_path: str) -> list[dict] | None:
    root = slot_path + "/_Data/_BossRematch"
    # This flag array follows the save's BossID array, whose order differs from the menu.
    flag_path = root + "/#d54d09c5"
    size = values.get(flag_path + "/_MaxElement")
    if type(size) is not int or not 0 < size <= 256:
        return None
    ids = [values.get(f"{root}/BossID/{index}") for index in range(size)]
    words = [values.get(f"{flag_path}/_Value/{index}") for index in range((size + 31) // 32)]
    if any(type(boss) is not int for boss in ids) or len(set(ids)) != size:
        return None
    if any(type(word) is not int for word in words):
        return None
    available = {boss for index, boss in enumerate(ids) if words[index // 32] & (1 << (index % 32))}
    story_order = [boss for boss in _ONIMUSHA_BOSS_NAMES if boss in ids]
    story_order.extend(boss for boss in ids if boss not in _ONIMUSHA_BOSS_NAMES)
    return [
        {"name": _ONIMUSHA_BOSS_NAMES.get(boss, f"Boss #{boss}"), "unlocked": boss in available}
        for boss in story_order
    ]


def _slots_from_values(values: dict) -> list[dict]:
    slots = {}
    last_index = -1
    for pointer, time in values.items():
        match = _PLAY_TIME.fullmatch(pointer)
        if not match:
            continue
        slot_path, number = match.groups()
        index = int(number)
        last_index = max(last_index, index)
        if type(time) not in (int, float) or time <= 0:
            continue
        detail = values.get(slot_path + "/Detail")
        subtitle = values.get(slot_path + "/Subtitle")
        detail = detail.split("\t", 3) if isinstance(detail, str) else []
        subtitle = subtitle.split("\t", 1) if isinstance(subtitle, str) else []
        saved_at, play_time, difficulty, goal = (detail + [""] * 4)[:4]
        chapter, location = (subtitle + [""] * 2)[:2]
        souls = values.get(slot_path + "/_Data/_ResourceData/SoulAmount")
        slots[slot_path] = {
            "index": index, "saved_at": saved_at, "chapter": chapter, "location": location,
            "goal": goal, "play_time": play_time, "difficulty": difficulty,
            "souls": souls if type(souls) is int else None, "inventory": Counter(),
            "boss_progress": _onimusha_boss_progress(values, slot_path),
        }
    if last_index < 0:
        raise ValueError("未识别到《鬼武者》存档槽，请确认摘要工具和游戏版本。")

    for pointer, item_id in values.items():
        match = _ITEM_ID.fullmatch(pointer)
        if not match or type(item_id) is not int or item_id == 0:
            continue
        slot = slots.get(match[1])
        quantity = values.get(pointer.removesuffix("ItemID") + "EquipNum")
        if slot is not None and type(quantity) is int and quantity > 0:
            slot["inventory"][item_id] += quantity

    def saved_order(slot: dict) -> tuple[datetime, int]:
        try:
            saved = datetime.strptime(slot["saved_at"], _ONIMUSHA_SAVE_TIME)
        except ValueError:
            saved = datetime.min
        return saved, slot["index"]

    for slot in slots.values():
        index = slot["index"]
        slot["label"] = "自动存档" if index == last_index else f"存档槽 {index + 1}"
    return sorted(slots.values(), key=saved_order, reverse=True)


def _blob_id(repo: Repo, commit: Commit) -> bytes:
    tree = repo[commit.tree]
    if not isinstance(tree, Tree):
        raise ValueError("无法读取该节点的备份目录。")
    return tree[_SAVE_NAME.encode("ascii")][1]


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


@lru_cache(maxsize=32)
def _decode_slots(repo_path: Path, blob_id: bytes, executable: Path, tool_version: int) -> list[dict]:
    with Repo(str(repo_path)) as repo:
        blob = repo[blob_id]
    if not isinstance(blob, Blob):
        raise ValueError("该节点的存档文件无法读取。")
    try:
        with tempfile.TemporaryDirectory(prefix="gamebackup-summary-") as temp:
            copy = Path(temp) / _SAVE_NAME
            copy.write_bytes(blob.data)
            result = subprocess.run(
                [str(executable), "list", str(copy), "--json"],
                capture_output=True, encoding="utf-8-sig", check=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        values = json.loads(result.stdout)
    except subprocess.TimeoutExpired as error:
        raise ValueError("读取存档摘要超时，请重试。") from error
    except (OSError, UnicodeError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ValueError("摘要工具无法解析这版存档，请检查工具和存档版本。") from error
    if not isinstance(values, dict):
        raise ValueError("摘要工具返回的数据格式有误。")
    return _slots_from_values(values)


def _item_names(path: Path) -> dict[int, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return {}
    names = {}
    for line in text.splitlines():
        number, _, name = line.partition("\t")
        if number.removeprefix("-").isdecimal() and name:
            names[int(number)] = name
    return names


def _onimusha_summary_tool(tools_dir: Path) -> Path:
    executable = (tools_dir / "UniversalSaveEditor.exe").resolve()
    if not executable.is_file():
        raise ValueError("请先运行 scripts/install-summary-tools.ps1 安装存档摘要工具。")
    return executable


def summarize_onimusha(repo: Path, commit_id: str, tools_dir: Path) -> dict:
    executable = _onimusha_summary_tool(tools_dir)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise ValueError("找不到这个存档节点。")

    repo = repo.resolve()
    try:
        with Repo(str(repo)) as history:
            commit, parent = _snapshot_commits(history, commit_id)
            current_blob = _blob_id(history, commit)
            previous_blob = None
            if parent is not None:
                try:
                    previous_blob = _blob_id(history, parent)
                except (KeyError, OSError, ValueError):
                    pass
        with _DECODE_LOCK:
            tool_version = executable.stat().st_mtime_ns
            slots = _decode_slots(repo, current_blob, executable, tool_version)
            previous_slots = {}
            if previous_blob is not None:
                try:
                    previous_slots = {
                        slot["index"]: slot
                        for slot in _decode_slots(repo, previous_blob, executable, tool_version)
                    }
                except (KeyError, OSError, ValueError):
                    pass
    except (KeyError, OSError, NotGitRepository) as error:
        raise ValueError("该节点没有可读取的《鬼武者》存档文件。") from error

    names = _item_names(tools_dir / "onimusha_items.tsv")
    names.update(ITEM_NAMES_ZH)
    summaries = []
    for slot in slots:
        previous = previous_slots.get(slot["index"])
        inventory = slot["inventory"]
        old_inventory = previous["inventory"] if previous is not None else Counter()
        souls = slot["souls"]
        old_souls = previous["souls"] if previous is not None else None
        items = [
            {
                "id": item_id, "name": names.get(item_id, f"物品 #{item_id}"),
                "quantity": inventory[item_id],
                "delta": inventory[item_id] - old_inventory[item_id] if previous is not None else None,
            }
            for item_id in inventory.keys() | old_inventory.keys()
        ]
        items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
        old_bosses = previous["boss_progress"] if previous is not None else None
        old_locked = {boss["name"] for boss in old_bosses or [] if not boss["unlocked"]}
        summaries.append({
            **{key: value for key, value in slot.items() if key != "inventory"},
            "has_previous": previous is not None,
            "previous_goal": previous["goal"] if previous is not None else None,
            "souls_delta": souls - old_souls if souls is not None and old_souls is not None else None,
            "boss_unlocked": [
                boss["name"] for boss in slot["boss_progress"] or []
                if boss["unlocked"] and boss["name"] in old_locked
            ],
            "items": items,
        })
    return {"slots": summaries}


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


def summarize_mortal_shell(repo: Path, commit_id: str) -> dict:
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
