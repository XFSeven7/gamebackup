"""Read-only Monster Hunter Wilds backup summaries."""

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from dulwich.errors import NotGitRepository
from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

from steam import _steam_root

from .save import read_save
from .steam_stats import steam_achievements


# Game IDs and Simplified Chinese names from https://docs.wilds.mhdb.io/.
_NAMES = json.loads(Path(__file__).with_name("names.json").read_text(encoding="utf-8"))
_WEAPONS = ("大剑", "片手剑", "双剑", "太刀", "大锤", "狩猎笛", "长枪", "铳枪",
            "斩斧", "盾斧", "操虫棍", "弓", "重弩", "轻弩")
_SAVE = b"data001Slot.bin"


def _item_counts(records):
    counts = Counter()
    for entry in records:
        if entry["ItemIdFixed"] and entry["Num"] > 0:
            counts[entry["ItemIdFixed"]] += entry["Num"]
    return counts


def _monsters(records):
    rows = {}
    names = _NAMES["monsters"]
    for entry in records:
        key = str(entry["FixedId"])
        kills, captures = entry["SlayingNum"], entry["CaptureNum"]
        name = names.get(key)
        if name is None and not (kills or captures):
            continue
        detail = f"讨伐 {kills} · 捕获 {captures}"
        smallest, largest = entry.get("MixSize"), entry.get("MaxSize")
        if (isinstance(smallest, (int, float)) and isinstance(largest, (int, float))
                and math.isfinite(largest) and 0 < smallest <= largest and smallest != 9999):
            detail += f"\n最小 {smallest:g} · 最大 {largest:g}"
        rows[key] = {"id": key, "name": name or f"未识别怪物（{key}）", "detail": detail,
                     "unlocked": bool(kills or captures), "kills": kills, "captures": captures}
    return sorted(rows.values(), key=lambda row: not row["unlocked"])


def _slot(index, fields):
    basic = fields.get("_BasicData", {})
    profile = fields.get("_HunterProfile", {})
    seconds = int(fields["PlayTime"])
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    reports = fields.get("_EnemyReport", {}).get("_Boss")
    monsters = _monsters(reports or [])
    inventory = fields.get("_Item", {})
    pouch = _item_counts(inventory.get("_PouchItem", []))
    box = _item_counts(inventory.get("_BoxItem", []))
    facts = {"猎人": basic.get("CharName") or f"存档槽 {index + 1}"}
    for label, key in (("随从艾露猫", "OtomoName"), ("鹭鹰龙", "SeikretName"), ("噗吱猪", "PugeeName")):
        if basic.get(key):
            facts[label] = basic[key]
    medal_record = profile.get("_Medal", {})
    if medals := medal_record.get("_Value"):
        count = min(len(medals) * 32, max(0, medal_record.get("_MaxElement", len(medals) * 32)))
        facts["游戏内勋章"] = sum(
            (word & ((1 << min(32, count - i * 32)) - 1)).bit_count()
            for i, word in enumerate(medals) if i * 32 < count
        )
    if reports is not None:
        facts["大型怪物讨伐"] = sum(row["kills"] for row in monsters)
        facts["大型怪物捕获"] = sum(row["captures"] for row in monsters)
    if "_PouchItem" in inventory:
        facts["随身道具种类"] = len(pouch)
    if "_BoxItem" in inventory:
        facts["道具箱种类"] = len(box)
    equipped = fields.get("_Equip", {}).get("_EquipIndex", {}).get("Index")
    if equipped:
        facts["已装备栏位"] = sum(slot >= 0 for slot in equipped)
    categories = profile.get("_QuestClearCounter", {}).get("_ClearNumPerCategory")
    if categories:
        facts["任务完成次数"] = sum(row.get("Num", 0) for row in categories)
        for key, label in (("MainWeaponUseNum", "主武器任务次数"), ("SubWeaponUseNum", "副武器任务次数")):
            counts = Counter()
            for category in categories:
                counts.update(dict(zip(_WEAPONS, category.get(key, []))))
            weapons = [f"{name} {counts[name]}" for name in _WEAPONS if counts[name]]
            if weapons:
                facts[label] = "、".join(weapons)
    names = _NAMES["items"]
    combined = pouch + box
    items = [{"name": names.get(str(item), f"道具 #{item}"), "quantity": count}
             for item, count in sorted(combined.items())]
    medal_count = facts.get("游戏内勋章")
    return {
        "index": index, "label": f"存档槽 {index + 1} · {facts['猎人']}",
        "hunter_id": fields["HunterId"], "seconds": seconds,
        "play_time": f"{hours}:{minutes:02d}:{secs:02d}", "facts": facts,
        "boss_progress": monsters, "items": items,
        "achievement_context": f"{facts['猎人']} · 游戏内勋章 {medal_count} 枚" if medal_count is not None else "",
    }


def _changes(slot, old):
    changes = []
    for label, after in {**slot["facts"], "游玩时长": slot["play_time"]}.items():
        before = old["play_time"] if label == "游玩时长" else old["facts"].get(label)
        if before is not None and before != after:
            changes.append({"label": label, "before": before, "after": after})
    if "大型怪物讨伐" in old["facts"]:
        earlier = {row["id"]: row for row in old["boss_progress"]}
        for row in slot["boss_progress"]:
            for action, key in (("讨伐", "kills"), ("捕获", "captures")):
                before = earlier.get(row["id"], {}).get(key, 0)
                if row[key] > before:
                    changes.append({"label": f"{action} · {row['name']}", "before": before, "after": row[key]})
    return changes


def _catalog_row(row):
    # API 1 releases display only the name. Keep counters visible in those clients.
    counts = row["detail"].splitlines()[0]
    return {**row, "display_name": row["name"], "name": f"{row['name']} · {counts}"}


def _blob_id(history, commit):
    if not isinstance(commit, Commit):
        raise ValueError("找不到这个存档节点。")
    tree = history[commit.tree]
    if not isinstance(tree, Tree):
        raise ValueError("找不到这个存档节点。")
    if _SAVE in tree:
        return tree[_SAVE][1]
    for folder in (b"remote", b"win64_save"):
        if folder in tree:
            tree = history[tree[folder][1]]
            if isinstance(tree, Tree) and _SAVE in tree:
                return tree[_SAVE][1]
            if not isinstance(tree, Tree):
                break
    raise ValueError("没有找到角色存档 data001Slot.bin。")


@lru_cache(maxsize=20)
def _snapshot(repo, blob_id, accounts):
    with Repo(str(repo)) as history:
        blob = history[blob_id]
        if not isinstance(blob, Blob):
            raise ValueError("该节点没有可读取的角色存档。")
        slots, account = read_save(blob.data, accounts)
    try:
        result = [_slot(i, fields) for i, fields in enumerate(slots) if fields.get("Active") == 1]
    except (AttributeError, KeyError, OverflowError, TypeError) as error:
        raise ValueError("无法识别这份备份里的角色记录。") from error
    if not result:
        raise ValueError("该备份没有已创建的猎人。")
    return result, account


def _accounts(root):
    try:
        return tuple(0x0110000100000000 + int(folder.name) for folder in sorted((root / "userdata").iterdir())
                     if folder.is_dir() and folder.name.isascii() and folder.name.isdecimal()
                     and 0 < int(folder.name) <= 0xFFFFFFFF)
    except OSError:
        return ()


def summarize(repo: Path, commit_id: str, _tools_dir: Path) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_id):
        raise ValueError("找不到这个存档节点。")
    root = _steam_root()
    accounts = _accounts(root) if root is not None else ()
    previous = {}
    try:
        with Repo(str(repo.resolve())) as history:
            commit = history[commit_id.lower().encode("ascii")]
            path = Path(history.path)
            slots, account = _snapshot(path, _blob_id(history, commit), accounts)
            if commit.parents:
                try:
                    parent = history[commit.parents[0]]
                    older, _ = _snapshot(path, _blob_id(history, parent), (account,))
                    previous = {slot["hunter_id"]: slot for slot in older if slot["hunter_id"]}
                except (KeyError, OSError, ValueError):
                    pass
    except (KeyError, OSError, NotGitRepository) as error:
        raise ValueError("无法打开《怪物猎人：荒野》的这份备份。") from error
    result = []
    for slot in slots:
        old = previous.get(slot["hunter_id"])
        if old is not None and old["seconds"] > slot["seconds"]:
            old = None
        result.append({**{key: value for key, value in slot.items() if key != "hunter_id"},
                       "boss_progress": [_catalog_row(row) for row in slot["boss_progress"]],
                       "has_previous": old is not None, "changes": _changes(slot, old) if old else []})
    return {"slots": result, "achievements": steam_achievements(root, account)}


def available(_tools_dir):
    return False


def read_event_state(_snapshot, _tools_dir):
    return None


def major_events(_before, _after):
    return []
