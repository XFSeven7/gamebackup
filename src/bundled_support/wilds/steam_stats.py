"""Read Wilds achievement state from the matching local Steam profile."""

from datetime import datetime

import vdf

APP_ID = "2246340"


def _text(value, fallback=""):
    if isinstance(value, dict):
        value = value.get("schinese") or value.get("english")
    return value if isinstance(value, str) else fallback


def _date(value):
    if type(value) is int and 0 < value <= 0xFFFFFFFF:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    return ""


def achievement_rows(schema, cache):
    rows = []
    for group, stat in schema.items():
        cached = cache.get(group, {})
        bits = cached.get("data")
        times = cached.get("AchievementTimes", {})
        for key, entry in stat.get("bits", {}).items():
            if not key.isascii() or not key.isdecimal() or len(key) > 2 or int(key) > 31:
                continue
            unlocked = bool(bits & (1 << int(key))) if type(bits) is int else None
            display = entry.get("display", {})
            date = _date(times.get(key)) if unlocked else ""
            description = _text(display.get("desc"))
            if date:
                description = " · ".join(part for part in (description, f"解锁于 {date}") if part)
            rows.append({
                "id": entry["name"], "name": _text(display.get("name"), entry["name"]),
                "description": description, "unlocked": unlocked,
                "target": 1, "value": int(unlocked) if unlocked is not None else None,
                "unlocked_at": date,
            })
    return rows


def _read_vdf(path):
    with path.open("rb") as file:
        raw = file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Steam 缓存文件超出预计大小。")
    return vdf.binary_loads(raw)


def steam_achievements(root, account):
    stats = root / "appcache" / "stats"
    try:
        schema = _read_vdf(stats / f"UserGameStatsSchema_{APP_ID}.bin")[APP_ID]["stats"]
    except (OSError, ValueError, KeyError, EOFError, TypeError, AttributeError):
        return []
    try:
        profile = account & 0xFFFFFFFF
        cache = _read_vdf(stats / f"UserGameStats_{profile}_{APP_ID}.bin")["cache"]
    except (OSError, ValueError, KeyError, EOFError, TypeError, AttributeError):
        cache = {}
    try:
        return achievement_rows(schema, cache)
    except (ValueError, TypeError, AttributeError, KeyError, OSError, OverflowError):
        return []
