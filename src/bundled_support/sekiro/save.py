"""Read the native PC Sekiro BND4 save; the caller never modifies it."""

import hashlib
import struct

# https://github.com/darthdemono/sl2-analyzer/blob/main/sl2/sdt.py
# https://github.com/indudewetrust/sekiro-checklist/blob/main/sekiro_checklist/sl2.py
_BOSSES = {
    9301: "鬼形部", 9302: "蝴蝶夫人", 9303: "苇名弦一郎", 9305: "观猴、闻猴、言猴",
    9304: "狮子猿", 9306: "破戒僧（幻影）", 9307: "无首狮子猿", 9308: "巨型忍者 枭",
    9309: "宫内破戒僧", 9310: "樱龙", 9312: "剑圣 苇名一心", 9313: "怨恨之鬼",
    9317: "义父", 9315: "永真", 9316: "苇名一心",
}
_ENDINGS = {6830: "斩断不死", 6831: "复归常人", 6832: "龙之还乡", 6833: "修罗"}


def _u32(data: memoryview, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _entry(data: memoryview, index: int) -> memoryview:
    header = 0x40 + 0x20 * index
    marker, size, _, start, name_at = struct.unpack_from("<QIIII", data, header)
    name = f"USER_DATA{index:03}".encode("utf-16-le")
    if (marker != 0xFFFFFFFF00000050 or start < 0x300 or size <= 16 or start + size > len(data)
            or data[name_at:name_at + len(name)] != name):
        raise ValueError("无法识别《只狼》的存档区块。")
    payload = data[start + 16:start + size]
    if hashlib.md5(payload, usedforsecurity=False).digest() != data[start:start + 16]:
        raise ValueError("《只狼》存档区块校验失败。")
    return payload


def _flag(slot: memoryview, flag: int) -> bool:
    block, bit = divmod(flag, 1000)
    # The game stores each 32-bit word little-endian, with its highest bit first.
    byte = 52 + 128 * block + ((bit // 8) ^ 3)
    return bool(slot[byte] & (0x80 >> (bit % 8)))


def _facts(slot: memoryview) -> tuple[dict, list[dict] | None]:
    facts = {"当前周目": f"第 {slot[0x33F34] + 1} 周目", "持有金钱": _u32(slot, 0x344D0)}
    for name, offset, limit in (("攻击力", 0x3449C, 99), ("体力等级", 0x34498, 20)):
        value = _u32(slot, offset)
        if 1 <= value <= limit:
            facts[name] = value
    for name, offset in (("生命上限", 0x34470), ("架势上限", 0x3448C)):
        value = _u32(slot, offset)
        if value and value == _u32(slot, offset + 4):
            facts[name] = value
    if 1 <= slot[0x34562] <= 10:
        facts["伤药葫芦上限"] = slot[0x34562]

    if _u32(slot, 0) != 0xFFFFFFFF or _u32(slot, 4) != 1000 or _u32(slot, 0x30) != 212480:
        return facts, None
    endings = [name for flag, name in _ENDINGS.items() if _flag(slot, flag)]
    facts["存档记录的结局"] = "、".join(endings) or "无"
    bosses = [{"name": name, "unlocked": _flag(slot, flag)} for flag, name in _BOSSES.items()]
    return facts, bosses


def read_save(raw: bytes) -> tuple[list[dict], int]:
    data = memoryview(raw)
    if len(data) < 0x300 or data[:4] != b"BND4" or _u32(data, 12) not in (11, 12):
        raise ValueError("请选择包含 S0000.sl2 的《只狼》PC 备份。")
    menu = _entry(data, 10)
    if len(menu) < 222 or any(flag not in (0, 1) for flag in menu[212:222]):
        raise ValueError("无法读取《只狼》的存档槽列表。")
    account = struct.unpack_from("<Q", menu, 36)[0]
    slots = []
    for index, occupied in enumerate(menu[212:222]):
        if not occupied:
            continue
        try:
            payload = _entry(data, index)
        except ValueError:
            continue
        if len(payload) != 0x100000 or struct.unpack_from("<Q", payload, 0x33E54)[0] != account:
            continue
        seconds = _u32(payload, 0x33F80)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        facts, bosses = _facts(payload)
        slots.append({
            "index": index, "label": f"存档槽 {index + 1}", "seconds": seconds,
            "play_time": f"{hours}:{minutes:02d}:{secs:02d}", "facts": facts, "boss_progress": bosses,
        })
    if not slots:
        raise ValueError("这份《只狼》备份没有可读取的存档槽。")
    return slots, account
