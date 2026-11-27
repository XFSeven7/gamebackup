"""Read the Steam DSSS container and the fields used in the Wilds summary."""

import struct
import zlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.decrepit.ciphers.modes import OFB

# Container and record format references:
# https://github.com/kvasszn/ree-save-editor/tree/main/src/save
_MASK_32 = (1 << 32) - 1
_MASK_64 = (1 << 64) - 1
_SKIP = object()


def murmur3(data: bytes) -> int:
    def rotate(word, bits):
        return ((word << bits) | (word >> (32 - bits))) & _MASK_32

    def mix(word):
        return (rotate((word * 0xCC9E2D51) & _MASK_32, 15) * 0x1B873593) & _MASK_32

    state = _MASK_32
    end = len(data) & ~3
    for (word,) in struct.iter_unpack("<I", memoryview(data)[:end]):
        state = (rotate(state ^ mix(word), 13) * 5 + 0xE6546B64) & _MASK_32
    state ^= mix(int.from_bytes(data[end:], "little")) ^ len(data)
    state = ((state ^ (state >> 16)) * 0x85EBCA6B) & _MASK_32
    state = ((state ^ (state >> 13)) * 0xC2B2AE35) & _MASK_32
    return state ^ (state >> 16)


def _next(state: int) -> int:
    word = (state + 0x9E3779B97F4A7C15) & _MASK_64
    word = ((word ^ (word >> 30)) * 0xBF58476D1CE4E5B9) & _MASK_64
    word = ((word ^ (word >> 27)) * 0x94D049BB133111EB) & _MASK_64
    return word ^ (word >> 31)


def _decrypt(raw: bytes, size: int, account: int) -> bytes:
    state = 0x7A36955255266CED
    blocks = []
    for _ in range((size + 0x3FFF) // 0x4000):
        blocks.append(((state & 7) + 1) * 0x4000)
        state = _next(state)
    state = (state - account - 1) & _MASK_64
    offset = 16
    decoded = bytearray()
    for length in blocks:
        key, iv = bytearray(), bytearray()
        for _ in range(16):
            state = _next(state)
            key.append(state & 255)
            iv.append((state >> 8) & 255)
        for _ in range(0x210):
            state = _next(state)
        start = offset + 0x210
        offset = start + length
        if offset > len(raw) - 140:
            raise ValueError("存档区块长度不正确。")
        cipher = Cipher(algorithms.AES(bytes(key)), OFB(bytes(iv))).decryptor()
        decoded.extend(cipher.update(raw[start:offset])[:size - len(decoded)])
        if len(decoded) == size:
            break
    total, version, compressed_size, plain_size = struct.unpack_from("<QIIQ", decoded)
    if version != 1 or total != compressed_size + 16 or not 0 < plain_size <= 64 * 1024 * 1024:
        raise ValueError("存档压缩区块无法识别。")
    if compressed_size > len(decoded) - 24:
        raise ValueError("存档压缩区块不完整。")
    inflater = zlib.decompressobj(-15)
    payload = inflater.decompress(decoded[24:24 + compressed_size], plain_size + 1)
    if len(payload) != plain_size or not inflater.eof or inflater.unused_data:
        raise ValueError("存档解压校验失败。")
    return raw[:16] + payload


def _rules(**fields):
    return {murmur3(name.encode()): (name, child) for name, child in fields.items()}


_ITEM = _rules(ItemIdFixed=None, Num=None)
_SLOT = _rules(
    Active=None, HunterId=None, PlayTime=None,
    _BasicData=_rules(CharName=None, OtomoName=None, SeikretName=None, PugeeName=None),
    _EnemyReport=_rules(_Boss=_rules(FixedId=None, EnemyState=None, SlayingNum=None,
                                     CaptureNum=None, MixSize=None, MaxSize=None)),
    _Item=_rules(_PouchItem=_ITEM, _BoxItem=_ITEM),
    _Equip=_rules(_EquipIndex=_rules(Index=None)),
    _HunterProfile=_rules(
        _Medal=_rules(_Value=None, _MaxElement=None),
        _QuestClearCounter=_rules(_ClearNumPerCategory=_rules(Num=None, MainWeaponUseNum=None,
                                                             SubWeaponUseNum=None)),
    ),
)
_ROOT = _rules(_Data=_SLOT)
_SCALARS = {2: "?", 3: "b", 4: "B", 5: "h", 6: "H", 7: "i", 8: "I",
            9: "q", 10: "Q", 11: "f", 12: "d", 13: "B", 14: "H"}


class _Records:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 16

    def align(self, size):
        self.pos = (self.pos + size - 1) & ~(size - 1)

    def read(self, fmt):
        values = struct.unpack_from("<" + fmt, self.data, self.pos)
        self.pos += struct.calcsize("<" + fmt)
        return values[0] if len(values) == 1 else values

    def record(self, rules, depth=0):
        count, record_type = self.read("II")
        if depth > 32 or count > 512:
            raise ValueError("存档结构无法识别。")
        if depth == 0 and record_type != 0x827FCCDC:
            raise ValueError("该文件不是《怪物猎人：荒野》角色存档。")
        fields = {}
        for _ in range(count):
            key, kind = self.read("Ii")
            name, child = rules.get(key, ("", _SKIP)) if isinstance(rules, dict) else ("", _SKIP)
            value = self.value(kind, child, depth + 1)
            if name:
                fields[name] = value
            self.align(4)
        return fields

    def value(self, kind, rules, depth, size=None):
        if kind == 17:
            return self.record(rules, depth)
        if kind == -1:
            self.align(4)
            member, size, count, array_type = self.read("iIII")
            if count > 100_000 or array_type not in (0, 1):
                raise ValueError("存档列表长度不正确。")
            if array_type == 1:
                if self.read("I") == 0xFFEEFFEE:
                    self.pos += 4 * count
                else:
                    self.pos -= 4
                member, size = 17, None
            if rules is _SKIP and member in (1, 16, *_SCALARS):
                if count:
                    self.align(size)
                    self.pos += size * count
                result = None
            elif rules is _SKIP:
                for _ in range(count):
                    self.value(member, _SKIP, depth, size)
                result = None
            else:
                result = [self.value(member, rules, depth, size) for _ in range(count)]
            self.align(4)
            return result
        if kind == 15:
            self.align(4)
            length = self.read("I") * 2
            start = self.pos
            self.pos += length
            if self.pos > len(self.data):
                raise ValueError("存档字符串不完整。")
            if rules is not _SKIP:
                return self.data[start:self.pos].decode("utf-16-le").rstrip("\0")
            return None
        if size is None:
            self.align(4)
            size = self.read("I")
        if not size:
            raise ValueError("存档字段长度不正确。")
        self.align(size)
        if kind == 16:
            self.pos += size
            return None
        fmt = {1: "b", 2: "h", 4: "i", 8: "q"}.get(size) if kind == 1 else _SCALARS.get(kind)
        if fmt is None or size != struct.calcsize("<" + fmt):
            raise ValueError("存档字段类型无法识别。")
        return self.read(fmt)


def read_save(raw: bytes, accounts) -> tuple[list[dict], int]:
    if not 80 <= len(raw) <= 8 * 1024 * 1024 or raw[:12] != b"DSSS\x02\0\0\0\x18\0\0\0":
        raise ValueError("无法识别《怪物猎人：荒野》的 Steam 存档。")
    size, checksum = struct.unpack_from("<QI", raw, len(raw) - 12)
    if not 24 <= size <= len(raw) - 156 or murmur3(raw[:-4]) != checksum:
        raise ValueError("《怪物猎人：荒野》存档校验失败。")
    for account in accounts:
        try:
            records = _Records(_decrypt(raw, size, account))
            records.read("I")
            slots = records.record(_ROOT)["_Data"]
            if not 1 <= len(slots) <= 3:
                raise ValueError("无法识别角色存档槽。")
            return slots, account
        except (ValueError, zlib.error, struct.error, KeyError):
            continue
    raise ValueError("无法读取角色存档。请确认本机 Steam 中有这份存档所属的账号。")
