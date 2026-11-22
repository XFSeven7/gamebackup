"""Read the local Steam achievement cache for this save's owning account."""

import os
import struct
from datetime import datetime
from pathlib import Path

import vdf
import winreg

_APP_ID = "1245620"


def _stats_dirs():
    seen = set()
    registry = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath", 0),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath", winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath", winreg.KEY_WOW64_64KEY),
    )
    for hive, key, entry, view in registry:
        try:
            with winreg.OpenKey(hive, key, access=winreg.KEY_READ | view) as steam:
                folder = Path(winreg.QueryValueEx(steam, entry)[0])
        except (OSError, TypeError):
            continue
        if folder.is_absolute() and folder not in seen:
            seen.add(folder)
            yield folder / "appcache" / "stats"
    if base := os.environ.get("ProgramFiles(x86)"):
        yield Path(base) / "Steam" / "appcache" / "stats"


def _read_cache(path: Path) -> dict:
    with path.open("rb") as source:
        data = source.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Steam 缓存超出预期大小")
    return vdf.binary_loads(data)


def _chinese(value: object, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("schinese") or value.get("english") or fallback
    return fallback


def _unlock_time(value: object) -> str:
    if type(value) is int and 0 < value <= 0xFFFFFFFF:
        try:
            return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            pass
    return ""


def _achievements(schema: dict, cached: dict) -> list[dict]:
    rows = []
    for group_id, group in schema.items():
        if not isinstance(group, dict) or not isinstance(group.get("bits"), dict):
            continue
        user = cached.get(group_id)
        progress = user.get("data") if isinstance(user, dict) else None
        timestamps = user.get("AchievementTimes", {}) if isinstance(user, dict) else {}
        for key, entry in group["bits"].items():
            if not key.isdecimal() or int(key) > 31 or not isinstance(entry, dict):
                continue
            internal = entry.get("name")
            if not isinstance(internal, str):
                continue
            unlocked = bool(progress & (1 << int(key))) if type(progress) is int else None
            display = entry.get("display")
            if not isinstance(display, dict):
                display = {}
            date = _unlock_time(timestamps.get(key)) if unlocked and isinstance(timestamps, dict) else ""
            description = _chinese(display.get("desc"))
            # API 1 clients display the description even if they do not render unlock timestamps separately.
            description = " · ".join(part for part in (description, f"解锁于 {date}" if date else "") if part)
            rows.append({
                "id": internal, "name": _chinese(display.get("name"), internal),
                "description": description,
                "target": 1, "value": int(unlocked) if unlocked is not None else None,
                "unlocked": unlocked, "unlocked_at": date,
            })
    return sorted(rows, key=lambda row: row["id"])


def steam_achievements(steam_id: int) -> list[dict]:
    if steam_id >> 32 != 0x01100001:
        return []
    account = steam_id & 0xFFFFFFFF
    for folder in _stats_dirs():
        try:
            schema = _read_cache(folder / f"UserGameStatsSchema_{_APP_ID}.bin")[_APP_ID]["stats"]
            cache_file = folder / f"UserGameStats_{account}_{_APP_ID}.bin"
            if not cache_file.is_file():
                continue
            cache = _read_cache(cache_file)["cache"]
            return _achievements(schema, cache)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, EOFError, struct.error):
            continue
    return []
