"""Read the tagged GVAS and Sparta world records used by Mortal Shell 2."""

import math
import struct
from collections import Counter
from datetime import datetime, timedelta, timezone


class _Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.offset = 0

    def take(self, size):
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise ValueError("Truncated Sparta save")
        value = self.data[self.offset:end]
        self.offset = end
        return value

    def number(self, fmt="i"):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))[0]

    def string(self):
        size = self.number()
        if size == 0:
            return ""
        width = 2 if size < 0 else 1
        raw = self.take(abs(size) * width).tobytes()
        if raw[-width:] != bytes(width):
            raise ValueError("Invalid FString")
        return raw[:-width].decode("utf-16-le" if width == 2 else "utf-8")

    def count(self):
        count = self.number()
        if not 0 <= count <= len(self.data) - self.offset:
            raise ValueError("Invalid Sparta collection length")
        return count

    def property_type(self, depth=0):
        if depth > 8:
            raise ValueError("Too many nested property types")
        self.string()
        for _ in range(self.count()):
            self.property_type(depth + 1)

    def properties(self):
        fields = {}
        while (name := self.string()) != "None":
            self.property_type()
            size = self.number()
            flags = self.number("B")
            if flags & ~31:
                raise ValueError("Unsupported property flags")
            if flags & 1:
                self.take(4)
            if flags & 2:
                self.take(16)
            fields[name] = self.take(size)
        return fields

    def map(self, read_key, read_value):
        if self.number() != 0:
            raise ValueError("Unsupported map delta")
        return {read_key(self): read_value(self) for _ in range(self.count())}


def _actor_values(root, key, read_value):
    if key not in root:
        return {}
    actors = _Reader(root[key]).map(_Reader.string, _Reader.properties)
    player = actors.get("Sparta_Player", {})
    return _Reader(player["Map"]).map(_Reader.string, read_value) if "Map" in player else {}


def _tag(reader):
    return _Reader(reader.properties()["TagName"]).string()


def _weapon_level(reader):
    stats = reader.properties()["PermanentStats"]
    return _Reader(stats).map(_tag, _Reader.number).get("UpgradeStat.Weapon.Level")


def _asset_id(path):
    return path.rsplit(".", 1)[-1].removeprefix("ID_").removesuffix("_C")


CURRENCY_NAMES = {"Gold": "钱币", "Gloom": "幽质", "Glimpses": "瞬悟"}

# 简中名称参考 https://ms2db.com/zh-Hans/装备/物品。
# 存档中的旧版物品和地图碎片用能从内部 ID 确认的描述。
ITEM_NAMES = {
    **CURRENCY_NAMES,
    "Ancient_Artifact": "远古遗物",
    "Artifact_MarshPearl": "沼泽珍珠",
    "Artifact_TwinSesters": "双生姐妹遗物",
    "Common_Old_Artifact": "普通旧遗物",
    "Epic_Old_Artifact": "史诗旧遗物",
    "FastTravel": "地母之息",
    "IceCrown": "无玷之冠",
    "MapPiece_City_1": "城市地图碎片 1",
    "MapPiece_City_4": "城市地图碎片 4",
    "MapPiece_City_5": "城市地图碎片 5",
    "MapPiece_Forest_1": "森林地图碎片 1",
    "MapPiece_Forest_2": "森林地图碎片 2",
    "MapPiece_Forest_3": "森林地图碎片 3",
    "MapPiece_Forest_4": "森林地图碎片 4",
    "MapPiece_Forest_5": "森林地图碎片 5",
    "MapUnlock": "鲁克的地图",
    "Map_SideArm_Crossbow": "被遗忘的十字弩位置图",
    "Map_Weapon_AxeDagger": "斧子与匕首位置图",
    "Ovum": "圣卵",
    "PP_Bloodseed": "血种",
    "PP_Effigy_Burned": "烧焦的人偶",
    "PP_Gear_Strange": "奇异齿轮",
    "PP_Grisha": "格力煞残渣",
    "PP_HealingAmount": "突触血管",
    "PP_HealingCharge": "天尊腺体",
    "PP_Mango": "芒果",
    "PP_MartyrAsh": "殉教者的骨灰",
    "PP_Moonshine_Inferior": "常见私酿酒",
    "PP_Mushroom_Weltcap": "檐盖菇",
    "PP_ParadoxicalScripture": "悖论经文",
    "PP_Sheep": "羊头图腾",
    "PP_Tarspore": "露孢菌",
    "PP_Trollweed": "山怪草",
    "Rare_Old_Artifact": "稀有旧遗物",
    "SacredGland_Snow": "解冻腺体",
    "Specimen": "提取的样本",
    "TFM_01_Ventrium": "心石",
    "TFM_02_Laterite": "红石",
    "TFM_03_Dorsalite": "背甲石",
    "Tarcore": "余露核心",
    "Tarforge_ForgeMode_Sidearm": "黑曜石车床",
    "Tarforge_ForgeMode_Weapon": "穆拉迪恩促动器",
    "ThestusFlame": "泰斯特斯之焰",
    "VratkoFeetPic_01": "维拉克托的自我习作",
}


def read_slot(data):
    reader = _Reader(data)
    if reader.take(4) != b"GVAS" or reader.number() != 3:
        raise ValueError("Unsupported GVAS version")
    reader.number()  # UE4 package version
    if reader.number() < 1012:
        raise ValueError("Missing complete property types")
    reader.take(10)  # Engine version and changelist
    reader.string()  # Engine branch
    reader.number()  # Custom version format
    reader.take(reader.count() * 20)
    if reader.string() != "/Script/Sparta.SpartaSaveGame":
        raise ValueError("Unexpected save class")
    reader.take(1)
    root = reader.properties()
    reader.take(4)

    player = None
    narrative = {}
    for _ in range(reader.count()):
        name = reader.string()
        reader.take(21)  # Object GUID and record metadata
        fields = reader.properties()
        reader.take(4)
        if name.endswith(".BP_SpartaPlayerSaveObject_C"):
            player = fields
        elif name.endswith(".BPSO_QuestLogComponent_C"):
            narrative = fields
    if player is None:
        raise ValueError("Sparta player record not found")
    reader.take(5)
    status = reader.properties()
    reader.take(4)
    if reader.offset != len(data):
        raise ValueError("Unsupported Sparta world trailer")

    def number(fields, key, fmt="i", default=None):
        if key not in fields:
            return default
        value = _Reader(fields[key]).number(fmt)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Invalid Sparta numeric value")
        return value

    ints = _actor_values(root, "ActorInts", _Reader.number)
    names = _actor_values(root, "ActorNames", _Reader.string)
    location = names.get("RespawnPlayerStart") or names.get("ProloguePlayerStart")
    seconds = number(player, "TotalPlayTimeSeconds", "f")
    play_time = ""
    if seconds is not None:
        if seconds < 0:
            raise ValueError("Invalid play time")
        hours, remainder = divmod(round(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        play_time = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
    ticks = number(player, "LastSaveDateTime", "q")
    saved_at = ""
    if ticks:
        utc = datetime(1, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
        saved_at = utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    inventory = Counter()
    if "DropItems" in player:
        for path, quantity in _Reader(player["DropItems"]).map(_Reader.string, _Reader.number).items():
            inventory[_asset_id(path)] += quantity
    weapons = _Reader(player["WeaponStats"]).map(_tag, _weapon_level) if "WeaponStats" in player else {}
    levels = {key.replace(".", "").casefold(): level for key, level in weapons.items()}
    facts = {
        "死亡次数": number(player, "TotalDeaths", default=0),
        "开箱次数": ints.get("ChestOpened", 0),
        "击败 Boss": ints.get("Game.State.BossesDefeated", 0),
        "已解锁登陆点": number(player, "UnlockedLandingAreas", default=0),
        "已净化登陆点": number(player, "CleansedLandingAreas", default=0),
        "已获得成就": 0,
        "叙事标签": number(narrative, "NarrativeTags", default=0),
        **{name: inventory[key] for key, name in CURRENCY_NAMES.items()},
        "待回收幽质": number(player, "LostGloomAmount", default=0),
        "累计幽质": number(player, "CumulativeGloom", default=0),
        "生命": number(status, "Health", "d"),
        "躯壳生命": number(status, "ShellHealth", "d"),
        "Resolve": number(status, "Resolve", "d"),
        "剩余治疗次数": number(status, "HealCurrentCharges", "d"),
    }
    if "EarnedAchievements" in player:
        achievements = _Reader(player["EarnedAchievements"]).map(_Reader.string, lambda r: r.number("B"))
        facts["已获得成就"] = sum(bool(earned) for earned in achievements.values())
    if "EquipmentUnlockState" in player:
        unlocks = _Reader(player["EquipmentUnlockState"]).map(_tag, lambda r: r.number("B"))
        facts["已解锁装备"] = sum(bool(unlocked) for unlocked in unlocks.values())

    for label, key, prefix in (
        ("躯壳", "ActiveShellItemDefinition", "Shell_"),
        ("武器", "ActiveWeaponItemDefinition", ""),
        ("副武器", "ActiveSidearmItemDefinition", "Sidearm_"),
        ("印记", "ActiveSealItemDefinition", "Seal_"),
        ("黑暗形态", "ActiveDarkFormItemDefinition", "Darkform_"),
    ):
        if key in player:
            name = _asset_id(_Reader(player[key]).string()).removeprefix(prefix)
            level = None
            if label in ("武器", "副武器"):
                level = levels.get("weapon" + name.replace("_", "").casefold())
            facts[label] = f"{name} +{level}" if level else name
    return {
        "play_time": play_time, "location": location, "saved_at": saved_at,
        "facts": {key: value for key, value in facts.items() if value is not None},
        "inventory": inventory,
    }
