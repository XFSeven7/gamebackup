"""Read the Steam achievement cache for the account named by the save."""

import os
import struct
import winreg
from datetime import datetime
from pathlib import Path

import vdf

_APP_ID = "814380"


def _stats_dirs():
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath", 0),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath", winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath", winreg.KEY_WOW64_64KEY),
    ]
    for hive, key, name, view in keys:
        try:
            with winreg.OpenKey(hive, key, access=winreg.KEY_READ | view) as config:
                path = Path(winreg.QueryValueEx(config, name)[0])
        except (OSError, TypeError):
            continue
        if path.is_absolute():
            yield path / "appcache" / "stats"
    if base := os.environ.get("ProgramFiles(x86)"):
        yield Path(base) / "Steam" / "appcache" / "stats"


def _load(path: Path) -> dict:
    with path.open("rb") as stream:
        data = stream.read(2_097_153)
    if len(data) > 2_097_152:
        raise ValueError("Steam 缓存超出预计大小")
    return vdf.binary_loads(data)


def _translation(value, fallback=""):
    if isinstance(value, dict):
        value = value.get("schinese") or value.get("english")
    return value if isinstance(value, str) else fallback


def _date(raw):
    if isinstance(raw, int) and 0 < raw <= 0xFFFFFFFF:
        try:
            return datetime.fromtimestamp(raw).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            pass
    return ""


def _rows(schema, cache):
    achievements = []
    for group, stat in schema.items():
        cached = cache.get(group, {})
        bits = cached.get("data")
        times = cached.get("AchievementTimes", {})
        for key, entry in stat.get("bits", {}).items():
            if not key.isascii() or not key.isdecimal() or int(key) > 31:
                continue
            unlocked = bool(bits & (1 << int(key))) if type(bits) is int else None
            date = _date(times.get(key)) if unlocked and isinstance(times, dict) else ""
            display = entry.get("display", {})
            description = _translation(display.get("desc"))
            if date:
                description = " · ".join(part for part in (description, f"解锁于 {date}") if part)
            achievements.append({
                "id": entry["name"], "name": _translation(display.get("name"), entry["name"]),
                "description": description, "unlocked": unlocked, "unlocked_at": date,
                "target": 1, "value": int(unlocked) if unlocked is not None else None,
            })
    return sorted(achievements, key=lambda row: row["id"])


def steam_achievements(steam_id: int) -> list[dict]:
    if steam_id >> 32 != 0x01100001:
        return []
    for folder in _stats_dirs():
        try:
            account = steam_id & 0xFFFFFFFF
            profile = _load(folder / f"UserGameStats_{account}_{_APP_ID}.bin")["cache"]
            schema = _load(folder / f"UserGameStatsSchema_{_APP_ID}.bin")[_APP_ID]["stats"]
            return _rows(schema, profile)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, EOFError, struct.error):
            continue
    return []
