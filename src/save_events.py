"""Compatibility entry points for built-in event detection."""

from pathlib import Path

from bundled_support import mortal_shell, onimusha
from config import ManagedFolder

ONIMUSHA_APP_ID = "2638890"
_BUILTIN = {"onimusha": onimusha, "mortal_shell": mortal_shell}


def summary_kind(item: ManagedFolder) -> str | None:
    if item.steam_app_id == ONIMUSHA_APP_ID:
        return "onimusha"
    if tuple(part.casefold() for part in Path(item.path).parts[-3:]) == (
        "mortalshell2", "saved", "savegames",
    ):
        return "mortal_shell"
    return None


def read_event_state(kind: str, snapshot: Path, tools_dir: Path) -> dict | None:
    parser = _BUILTIN.get(kind)
    return parser.read_event_state(snapshot, tools_dir) if parser else None


def major_events(kind: str, before: dict, after: dict) -> list[str]:
    parser = _BUILTIN.get(kind)
    return parser.major_events(before, after) if parser else []
