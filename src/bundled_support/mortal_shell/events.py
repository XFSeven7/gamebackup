"""Detect Mortal Shell 2 milestones across two snapshots."""

from pathlib import Path

from .save import read_slot
from .summary import _MORTAL_SHELL_SLOTS

_MORTAL_SHELL_EVENTS = {
    "击败 Boss": "击败 Boss {delta} 名",
    "已解锁登陆点": "解锁登陆点 {delta} 个",
    "已净化登陆点": "净化登陆点 {delta} 个",
    "已获得成就": "解锁成就 {delta} 项",
    "已解锁装备": "解锁装备 {delta} 件",
}


def read_event_state(snapshot: Path, tools_dir: Path) -> dict | None:
    slots = {}
    for filename, (index, _) in _MORTAL_SHELL_SLOTS.items():
        try:
            facts = read_slot((snapshot / filename.decode("ascii")).read_bytes())["facts"]
        except (OSError, ValueError, KeyError, OverflowError):
            continue
        slots[str(index)] = {key: facts[key] for key in _MORTAL_SHELL_EVENTS if key in facts}
    return slots or None


def major_events(before: dict, after: dict) -> list[str]:
    events = []
    for index, facts in after.items():
        previous = before.get(index, {})
        for key, label in _MORTAL_SHELL_EVENTS.items():
            if key in previous and key in facts and facts[key] > previous[key]:
                events.append(label.format(delta=facts[key] - previous[key]))
    return list(dict.fromkeys(events))
