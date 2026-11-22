"""Elden Ring PC BND4 character profiles and selected world flags."""

import hashlib
import struct

# Layout references:
# https://github.com/ClayAmore/EldenRingSaveTemplate/blob/master/SL2.bt
# https://github.com/soarqin/SoulsSaveManager/blob/master/src/common/ersave.c
_CHARACTER_START = 0x300
_CHARACTER_SIZE = 0x280010
_COMMON_START = _CHARACTER_START + 10 * _CHARACTER_SIZE
_COMMON_SIZE = 0x60010
_OCCUPIED = 0x1964  # Relative to the common block, including its checksum.
_PROFILE_SIZE = 0x24C
_FLAGS_SIZE = 0x1BF99F
_DLC_FORMAT_VERSION = 82
_STATS = ("生命力", "集中力", "耐力", "力气", "灵巧", "智力", "信仰", "感应")
_CLASSES = ("流浪骑士", "剑士", "勇者", "盗贼", "观星者", "预言家", "武士", "囚犯", "密使", "无用之人")

# Flag ID, block index and display name. The block values come from:
# https://github.com/zebbedaja/er-save-parser/blob/main/src/bst-map.ts
# https://github.com/zebbedaja/er-save-parser/blob/main/src/event-flags.ts
_BASE_BOSSES = (
    (10000850, 11067, "恶兆妖鬼玛尔基特"),
    (10000800, 11067, "接肢葛瑞克"),
    (14000800, 11274, "满月女王蕾娜菈"),
    (1252380800, 13686, "碎星拉塔恩"),
    (16000800, 11328, "亵渎君王拉卡德"),
    (11000800, 11103, "恶兆王蒙葛特"),
    (1252520800, 13983, "火焰巨人"),
    (13000850, 11247, "神皮双人组"),
    (13000800, 11247, "黑剑玛利喀斯"),
    (11050800, 11112, "初始之王葛孚雷"),
    (19000800, 11409, "拉达冈／艾尔登之兽"),
    (15000800, 11301, "米凯拉的锋刃玛莲妮亚"),
    (12050800, 11202, "鲜血君王蒙格"),
    (13000830, 11247, "龙王普拉顿桑克斯"),
    (12030850, 11184, "死龙弗尔桑克斯"),
)
_DLC_BOSSES = (
    (20000800, 12417, "神兽舞狮"),
    (2048440800, 1071, "双月骑士蕾菈娜"),
    (21010800, 12462, "穿刺者梅瑟莫"),
    (2044450800, 434, "花蕾圣女萝蜜娜"),
    (20010800, 12426, "约定之王拉塔恩"),
    (2054390800, 6300, "狂龙贝勒"),
    (22000800, 12489, "融泥骑士"),
    (25000800, 12507, "指头之母梅蒂尔"),
    (28000800, 12561, "癫火之王米德拉"),
)


def _number(data, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _name(data, offset: int) -> str:
    return bytes(data[offset:offset + 32]).decode("utf-16-le").split("\0", 1)[0].strip()


def _valid_block(block: memoryview) -> bool:
    return hashlib.md5(block[16:], usedforsecurity=False).digest() == block[:16]


def _character_offset(block: memoryview) -> int:
    offset = 0x30
    entries = 0x13FE if _number(block, 16) < _DLC_FORMAT_VERSION else 0x1400
    for _ in range(entries):
        category = _number(block, offset) >> 28
        offset += 8
        if category == 8:
            offset += 13
        elif category == 9:
            offset += 8
    return offset


def _world_offsets(block: memoryview, character: int) -> tuple[int, int] | None:
    # Skip the character stats, equipment and held items to the projectile list.
    cursor = character + 0x280 + 0x124 + 16 + 12 * (0xA80 + 0x180) + 116 + 140 + 24
    projectiles = _number(block, cursor)
    if projectiles > (len(block) - cursor) // 8:
        return None
    # Projectile entries are followed by the equipment, face, storage and gestures.
    cursor += 4 + projectiles * 8 + 156 + 12 + 303 + 16 + 12 * (0x780 + 0x80) + 256
    regions = _number(block, cursor)
    if regions > (len(block) - cursor) // 4:
        return None
    regions_end = cursor + 4 + regions * 4
    # ClearCount sits 0x44 bytes after the 0x29-byte mount block.
    # https://github.com/oisis/EldenRing-SaveForge/blob/main/backend/core/offset_defs.go
    clear_count = regions_end + 0x29 + 0x44
    cursor = regions_end + 40 + 77
    menu_size = _number(block, cursor + 4)
    if menu_size > 0x10000:
        return None
    cursor += 8 + menu_size + 52 + 0x1B588
    tutorial_size = _number(block, cursor + 4)
    if tutorial_size > 0x10000:
        return None
    death = cursor + 8 + tutorial_size + 3
    flag_end = death + 26 + _FLAGS_SIZE
    if (flag_end >= len(block) or block[flag_end] != 0 or block[death + 8] not in (0, 1)
            or _number(block, death + 9) not in (0, 8)):
        return None
    return death, clear_count


def _boss_progress(block: memoryview, flags: int, bosses: tuple, group: str) -> list[dict]:
    progress = []
    for flag, block_index, name in bosses:
        byte, bit = divmod(flag % 1000, 8)
        progress.append({
            "name": name, "unlocked": bool(block[flags + block_index * 125 + byte] & (0x80 >> bit)),
            "group": group,
        })
    return progress


def _boss_facts(progress: list[dict], label: str) -> dict:
    defeated = [row["name"] for row in progress if row["unlocked"]]
    return {
        f"{label}精选首领（本周目）": f"{len(defeated)}/{len(progress)}",
        f"{label}已击败": "、".join(defeated) or "无",
    }


def _character_facts(block: memoryview, name: str, level: int) -> tuple[dict, list[dict] | None]:
    if not _valid_block(block):
        return {}, None
    try:
        character = _character_offset(block)
        if _name(block, character + 0x94) != name or _number(block, character + 0x60) != level:
            return {}, None
        facts = {}
        job = block[character + 0xB7]
        if job < len(_CLASSES):
            facts["初始职业"] = _CLASSES[job]
        facts.update(zip(_STATS, struct.unpack_from("<8I", block, character + 0x34)))
        facts["持有卢恩"] = _number(block, character + 0x64)
        facts["累计获得卢恩"] = _number(block, character + 0x68)
    except (IndexError, struct.error, UnicodeError):
        return {}, None
    try:
        world = _world_offsets(block, character)
        if world is not None:
            death, clear_count_offset = world
            clear_count = _number(block, clear_count_offset)
            journey = f"第 {clear_count + 1} 周目"
            facts["当前周目"] = f"{journey}（NG+{clear_count}）" if clear_count else journey
            facts["死亡次数"] = _number(block, death)
            bosses = _boss_progress(block, death + 26, _BASE_BOSSES, "本体")
            facts.update(_boss_facts(bosses, "本体"))
            if _number(block, 16) >= _DLC_FORMAT_VERSION:
                expansion = _boss_progress(block, death + 26, _DLC_BOSSES, "黄金树幽影")
                facts.update(_boss_facts(expansion, "黄金树幽影"))
                bosses.extend(expansion)
            return facts, bosses
    except (IndexError, struct.error, UnicodeError):
        pass
    return facts, None


def save_account(data: bytes) -> int:
    return struct.unpack_from("<Q", data, _COMMON_START + 20)[0]


def read_save(data: bytes) -> list[dict]:
    view = memoryview(data)
    if len(view) < _COMMON_START + _COMMON_SIZE or view[:4] != b"BND4" or _number(view, 12) != 12:
        raise ValueError("无法识别该 PC 存档。请选择包含 ER0000.sl2 的备份。")
    common = view[_COMMON_START:_COMMON_START + _COMMON_SIZE]
    if not _valid_block(common):
        raise ValueError("《艾尔登法环》角色列表校验失败，请选择另一份备份。")

    slots = []
    for index, occupied in enumerate(common[_OCCUPIED:_OCCUPIED + 10]):
        if occupied != 1:
            continue
        profile = _OCCUPIED + 10 + index * _PROFILE_SIZE
        try:
            name = _name(common, profile)
        except UnicodeError:
            continue
        level, seconds = struct.unpack_from("<II", common, profile + 34)
        if not name or not 1 <= level <= 713:
            continue
        hours, rest = divmod(seconds, 3600)
        minutes, remainder = divmod(rest, 60)
        start = _CHARACTER_START + index * _CHARACTER_SIZE
        facts, progress = _character_facts(view[start:start + _CHARACTER_SIZE], name, level)
        slots.append({
            "index": index, "label": f"槽 {index + 1} · {name}", "seconds": seconds,
            "play_time": f"{hours}:{minutes:02d}:{remainder:02d}", "facts": {"等级": level, **facts},
            "boss_progress": progress,
        })
    if not slots:
        raise ValueError("这份《艾尔登法环》备份没有可读取的角色。")
    return slots
