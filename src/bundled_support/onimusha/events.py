"""Detect Onimusha milestones across two snapshots."""

from pathlib import Path

from .achievements import ACHIEVEMENTS_ZH
from .summary import (
    _DECODE_LOCK,
    _SAVE_NAME,
    _new_onimusha_bosses,
    _onimusha_summary_tool,
    _read_onimusha_file,
)

# Valid mission bits (app.MissionDef.IDBit, excluding INVALID and unused positions).
_ONIMUSHA_MISSION_MASK = 0xFFFC01F877005CFFFFF82

def read_event_state(snapshot: Path, tools_dir: Path) -> dict | None:
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


def major_events(before: dict, after: dict) -> list[str]:
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
