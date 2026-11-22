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
from onimusha_achievements import ACHIEVEMENTS_ZH, COMBAT_ACHIEVEMENTS_ZH
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

# Paths in Universal Save Editor's JSON for the map, mirror and mystery save fields.
_ONIMUSHA_PROGRESS_FIELDS = (
    ("exploration", "传送镜", "/#7efc175b/_ReleasedIndex"),
    ("exploration", "到访区域", "/#62b8a2f4/_VisitArea"),
    ("mystery", "异闻解锁", "/_MysteryParam/#6858d6b7"),
    ("mystery", "异闻已汇报", "/_MysteryParam/#a9abfbb2"),
)
# app.MissionDef.IDBit entries for the game's sidemissionstory and
# sidemissioncommon assets, respectively. Other clear flags count main missions.
_ONIMUSHA_COLLECTION_MISSION_BITS = {
    16: (24, 27, 45, 46, 48, 49, 50, 75),
    18: (44, 55, 56, 57, 58, 59, 60, 70, 71, 74, 76, 77, 78, 79, 80, 81, 82, 83),
}
_ONIMUSHA_GENMA_NOTE_IDS = frozenset(
    item for item, name in ITEM_NAMES_ZH.items() if name.startswith("幻魔杂记（")
)
# app.MysteryDef.SUB_IDBit reserves bit 0. The 36 rescue flags start at bit 1.
_ONIMUSHA_LION_DOG_MASK = (1 << 37) - 2


def _onimusha_flag_array(values: dict, path: str) -> int | None:
    size = values.get(path + "/_MaxElement")
    if type(size) is not int or not 0 < size <= 256:
        return None
    words = [values.get(f"{path}/_Value/{i}") for i in range((size + 31) // 32)]
    if any(type(word) is not int for word in words):
        return None
    flags = sum((word & 0xffffffff) << (i * 32) for i, word in enumerate(words))
    return flags & ((1 << size) - 1)


def _onimusha_achievement_states(values: dict, game_path: str) -> dict:
    root = game_path + "/_SystemSaveData/_Data/_Achievement"
    states = {}
    for achievement in ACHIEVEMENTS_ZH:
        path = f"{root}/{achievement}"
        state = values.get(path + "/IsUnlocked")
        if values.get(path + "/#78cfd7e7") == achievement and state in (0, 1):  # EnumId
            count = values.get(path + "/Count")
            states[achievement] = (bool(state), count if type(count) is int and count >= 0 else None)
    return states


def _onimusha_achievement_summary(states: dict, collections: dict) -> list[dict]:
    achievements = []
    for number, (name, description, target) in ACHIEVEMENTS_ZH.items():
        unlocked, count = states.get(number, (None, None))
        count = collections.get(number, count)
        value = count
        if unlocked:
            value = target
        elif unlocked is False and target == 1:
            value = 0
        elif count is not None:
            value = min(count, target)
        achievements.append({
            "id": number, "name": name, "description": description,
            "target": target, "value": value, "unlocked": unlocked,
        })
    return achievements


def _onimusha_progress(values: dict, slot_path: str, achievements: dict) -> dict:
    flags = {}
    for kind, name, suffix in _ONIMUSHA_PROGRESS_FIELDS:
        path = slot_path + "/_Data" + suffix
        if kind == "exploration":
            flags[name] = _onimusha_flag_array(values, path)
        else:
            word = values.get(path)
            flags[name] = word & 0xffffffffffffffff if type(word) is int else None

    known = unlocked = 0
    for achievement in COMBAT_ACHIEVEMENTS_ZH:
        if achievement in achievements:
            known |= 1 << achievement
            if achievements[achievement][0]:
                unlocked |= 1 << achievement
    return {"flags": flags, "combat_known": known, "combat_unlocked": unlocked}


def _new_onimusha_progress(current: dict, previous: dict) -> list[dict]:
    milestones = []
    for kind, name, _ in _ONIMUSHA_PROGRESS_FIELDS:
        new = current["flags"].get(name)
        old = previous["flags"].get(name)
        if new is not None and old is not None and (added := (new & ~old).bit_count()):
            milestones.append({"kind": kind, "text": f"{name} +{added}（累计 {new.bit_count()}）"})

    newly_unlocked = current["combat_unlocked"] & (previous["combat_known"] & ~previous["combat_unlocked"])
    milestones.extend(
        {"kind": "achievement", "text": f"战斗成就：{name}"}
        for number, name in COMBAT_ACHIEVEMENTS_ZH.items()
        if newly_unlocked & (1 << number)
    )
    return milestones


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


def _onimusha_from_values(values: dict) -> tuple[list[dict], dict, dict]:
    slots = {}
    game_path = ""
    last_index = -1
    for pointer, time in values.items():
        match = _PLAY_TIME.fullmatch(pointer)
        if not match:
            continue
        slot_path, number = match.groups()
        game_path = "/" + slot_path.split("/")[1]
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
            "mission_flags": _onimusha_flag_array(values, slot_path + "/_Data/_StoryParam/#71379cfa"),
        }
    if last_index < 0:
        raise ValueError("未识别到《鬼武者》存档槽，请确认摘要工具和游戏版本。")

    note_ids = {}
    for pointer, item_id in values.items():
        match = _ITEM_ID.fullmatch(pointer)
        if not match or type(item_id) is not int:
            continue
        slot = slots.get(match[1])
        if slot is None:
            continue
        notes = note_ids.setdefault(match[1], set())
        if item_id == 0:
            continue
        quantity = values.get(pointer.removesuffix("ItemID") + "EquipNum")
        carried = type(quantity) is int and quantity > 0
        if carried:
            slot["inventory"][item_id] += quantity
        if item_id in _ONIMUSHA_GENMA_NOTE_IDS:
            stored = values.get(pointer.removesuffix("ItemID") + "BoxNum")
            if carried or (type(stored) is int and stored > 0):
                notes.add(item_id)

    def saved_order(slot: dict) -> tuple[datetime, int]:
        try:
            saved = datetime.strptime(slot["saved_at"], _ONIMUSHA_SAVE_TIME)
        except ValueError:
            saved = datetime.min
        return saved, slot["index"]

    # Achievements belong to the snapshot's shared system data, not a save slot.
    achievements = _onimusha_achievement_states(values, game_path)
    for slot_path, slot in slots.items():
        index = slot["index"]
        slot["label"] = "自动存档" if index == last_index else f"存档槽 {index + 1}"
        if index == last_index:
            slot["progress"] = _onimusha_progress(values, slot_path, achievements)
    ordered = sorted(slots, key=lambda path: saved_order(slots[path]), reverse=True)
    collections = dict.fromkeys((*_ONIMUSHA_COLLECTION_MISSION_BITS, 23, 24))
    if ordered:
        selected = ordered[0]
        data = selected + "/_Data"
        missions = slots[selected]["mission_flags"]
        if missions is not None:
            collections.update(
                (number, sum(bool(missions & (1 << bit)) for bit in bits))
                for number, bits in _ONIMUSHA_COLLECTION_MISSION_BITS.items()
            )
        rescued = values.get(data + "/_MysteryParam/#6858d6b7")
        if type(rescued) is int:
            collections[23] = (rescued & _ONIMUSHA_LION_DOG_MASK).bit_count()
        if selected in note_ids:
            collections[24] = len(note_ids[selected])
    return [slots[path] for path in ordered], achievements, collections


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


def _read_onimusha_file(path: Path, executable: Path) -> tuple[list[dict], dict, dict]:
    try:
        result = subprocess.run(
            [str(executable), "list", str(path), "--json"],
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
    return _onimusha_from_values(values)


@lru_cache(maxsize=32)
def _decode_onimusha(repo_path: Path, blob_id: bytes, executable: Path, tool_version: int) -> tuple[list[dict], dict, dict]:
    with Repo(str(repo_path)) as repo:
        blob = repo[blob_id]
    if not isinstance(blob, Blob):
        raise ValueError("该节点的存档文件无法读取。")
    with tempfile.TemporaryDirectory(prefix="gamebackup-summary-") as temp:
        copy = Path(temp) / _SAVE_NAME
        copy.write_bytes(blob.data)
        return _read_onimusha_file(copy, executable)


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


def _new_onimusha_bosses(slot: dict | None, previous: dict | None) -> list[str]:
    if slot is None or previous is None or slot["index"] != previous["index"]:
        return []
    old_locked = {boss["name"] for boss in previous["boss_progress"] or [] if not boss["unlocked"]}
    return [
        boss["name"] for boss in slot["boss_progress"] or []
        if boss["unlocked"] and boss["name"] in old_locked
    ]


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
            slots, achievements, collections = _decode_onimusha(repo, current_blob, executable, tool_version)
            previous_slots = {}
            if previous_blob is not None:
                try:
                    prior_slots, _, _ = _decode_onimusha(repo, previous_blob, executable, tool_version)
                    previous_slots = {slot["index"]: slot for slot in prior_slots}
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
        summaries.append({
            **{key: value for key, value in slot.items() if key not in ("inventory", "progress", "mission_flags")},
            "has_previous": previous is not None,
            "previous_goal": previous["goal"] if previous is not None else None,
            "souls_delta": souls - old_souls if souls is not None and old_souls is not None else None,
            "boss_unlocked": _new_onimusha_bosses(slot, previous),
            "items": items,
        })
    return {"slots": summaries, "achievements": _onimusha_achievement_summary(achievements, collections)}


_BOSS_INDEX = "gamebackup-onimusha-progress-v2.json"


def load_onimusha_boss_index(repo: Path) -> dict:
    try:
        entries = json.loads((repo / ".git" / _BOSS_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(entries, dict):
        return {}
    return {
        key: slot for key, slot in entries.items()
        if slot is None or (
            isinstance(slot, dict) and type(slot.get("index")) is int
            and isinstance(slot.get("goal"), str)
            and "boss_progress" in slot
            and (
                slot.get("boss_progress") is None or (
                    isinstance(slot["boss_progress"], list) and all(
                        isinstance(boss, dict) and isinstance(boss.get("name"), str)
                        and type(boss.get("unlocked")) is bool for boss in slot["boss_progress"]
                    )
                )
            )
            and _valid_onimusha_progress(slot.get("progress"))
        )
    }


def _valid_onimusha_progress(progress: object) -> bool:
    return (
        isinstance(progress, dict) and isinstance(progress.get("flags"), dict)
        and all(value is None or (type(value) is int and value >= 0) for value in progress["flags"].values())
        and all(type(progress.get(key)) is int and progress[key] >= 0 for key in ("combat_known", "combat_unlocked"))
    )


def save_onimusha_boss_index(repo: Path, index: dict) -> None:
    git_dir = repo / ".git"
    with tempfile.TemporaryDirectory(prefix="boss-index-", dir=git_dir) as directory:
        pending = Path(directory) / _BOSS_INDEX
        pending.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        pending.replace(git_dir / _BOSS_INDEX)


def onimusha_boss_nodes(repo: Path, nodes: list[dict], index: dict) -> set[str]:
    """Annotate raw graph nodes and return blob IDs that still need decoding."""
    blobs = {}
    with Repo(str(repo)) as history:
        for node in nodes:
            try:
                commit = history[node["id"].encode("ascii")]
                blobs[node["id"]] = _blob_id(history, commit).decode("ascii")
            except (KeyError, OSError, ValueError):
                continue
    needed = set()
    for node in nodes:
        if not node["parents"]:
            continue
        child = blobs.get(node["id"])
        parent = blobs.get(node["parents"][0])
        if not child or not parent or child == parent:
            continue
        needed.update((child, parent))
        current = index.get(child)
        previous = index.get(parent)
        if current is None or previous is None or current["index"] != previous["index"]:
            continue
        if progress := _new_onimusha_progress(current["progress"], previous["progress"]):
            node["progress_milestones"] = progress
        names = _new_onimusha_bosses(current, previous)
        if not names:
            continue
        defeated = []
        if previous["goal"] != current["goal"]:
            defeated = [name for name in names if previous["goal"] == f"击败{name}"]
        node["boss_milestone"] = {"names": names, "defeated": defeated}
    return needed - index.keys()


def scan_onimusha_boss_index(repo: Path, tools_dir: Path, missing: set[str], should_stop) -> dict:
    executable = _onimusha_summary_tool(tools_dir)
    tool_version = executable.stat().st_mtime_ns
    index = {}
    for blob in missing:
        if should_stop():
            break
        try:
            # Release the lock between snapshots so a selected-node summary can load.
            with _DECODE_LOCK:
                slots, _, _ = _decode_onimusha(repo, blob.encode("ascii"), executable, tool_version)
        except (KeyError, OSError, ValueError):
            continue
        slot = next((slot for slot in slots if slot["label"] == "自动存档"), None)
        index[blob] = (
            {key: slot[key] for key in ("index", "goal", "boss_progress", "progress")}
            if slot is not None else None
        )
    return index


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
