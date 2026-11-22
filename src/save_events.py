"""Read save milestones from the same snapshots that will be backed up."""

from pathlib import Path

from config import ManagedFolder
from onimusha_achievements import ACHIEVEMENTS_ZH
from save_summary import (
    _DECODE_LOCK,
    _MORTAL_SHELL_SLOTS,
    _SAVE_NAME,
    _new_onimusha_bosses,
    _onimusha_summary_tool,
    _read_onimusha_file,
    read_mortal_shell_slot,
)

ONIMUSHA_APP_ID = "2638890"

# Valid mission bits (app.MissionDef.IDBit, excluding INVALID and unused positions).
_ONIMUSHA_MISSION_MASK = 0xFFFC01F877005CFFFFF82

_MORTAL_SHELL_EVENTS = {
    "击败 Boss": "击败 Boss {delta} 名",
    "已解锁登陆点": "解锁登陆点 {delta} 个",
    "已净化登陆点": "净化登陆点 {delta} 个",
    "已获得成就": "解锁成就 {delta} 项",
    "已解锁装备": "解锁装备 {delta} 件",
}


def summary_kind(item: ManagedFolder) -> str | None:
    if item.steam_app_id == ONIMUSHA_APP_ID:
        return "onimusha"
    if tuple(part.casefold() for part in Path(item.path).parts[-3:]) == (
        "mortalshell2", "saved", "savegames",
    ):
        return "mortal_shell"
    return None


def read_event_state(kind: str, snapshot: Path, tools_dir: Path) -> dict | None:
    if kind == "onimusha":
        path = snapshot / _SAVE_NAME
        if not path.is_file():
            return None
        try:
            executable = _onimusha_summary_tool(tools_dir)
            with _DECODE_LOCK:
                slots, achievements, _ = _read_onimusha_file(path, executable)
        except (OSError, ValueError):
            return None
        return {
            "slots": {
                str(slot["index"]): {
                    key: slot[key] for key in ("goal", "mission_flags", "boss_progress")
                }
                for slot in slots
            },
            "achievements": {str(number): unlocked for number, (unlocked, _) in achievements.items()},
        }

    if kind == "mortal_shell":
        slots = {}
        for filename, (index, _) in _MORTAL_SHELL_SLOTS.items():
            try:
                facts = read_mortal_shell_slot((snapshot / filename.decode("ascii")).read_bytes())["facts"]
            except (OSError, ValueError, KeyError, OverflowError):
                continue
            slots[str(index)] = {key: facts[key] for key in _MORTAL_SHELL_EVENTS if key in facts}
        return slots or None

    return None


def _onimusha_events(before: dict, after: dict) -> list[str]:
    old_slots = before["slots"]
    missions = 0
    events = []
    for index, slot in after["slots"].items():
        old = old_slots.get(index)
        if old is None:
            continue
        # Boss progress is comparable only within the same slot.
        names = _new_onimusha_bosses({"index": index, **slot}, {"index": index, **old})
        for name in names:
            defeated = slot["goal"] != old["goal"] and old["goal"] == f"击败{name}"
            prefix = "击败" if defeated else "再战解锁"
            events.append(f"{prefix}：{name}")
        if slot["mission_flags"] is not None and old["mission_flags"] is not None:
            missions |= slot["mission_flags"] & ~old["mission_flags"] & _ONIMUSHA_MISSION_MASK
    if missions:
        events.append(f"完成任务 {missions.bit_count()} 项")
    for number, (name, _, _) in ACHIEVEMENTS_ZH.items():
        key = str(number)
        if before["achievements"].get(key) is False and after["achievements"].get(key) is True:
            events.append(f"成就解锁：{name}")
    return list(dict.fromkeys(events))


def major_events(kind: str, before: dict, after: dict) -> list[str]:
    if kind == "onimusha":
        return _onimusha_events(before, after)
    if kind != "mortal_shell":
        return []
    events = []
    for index, facts in after.items():
        previous = before.get(index, {})
        for key, label in _MORTAL_SHELL_EVENTS.items():
            if key in previous and key in facts and facts[key] > previous[key]:
                events.append(label.format(delta=facts[key] - previous[key]))
    return list(dict.fromkeys(events))
