"""已管理文件夹列表，存在备份根目录的 config.json。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ManagedFolder:
    id: str
    name: str
    path: str
    current_line: str = "main"
    paused: bool = False
    last_fingerprint: str = ""
    steam_app_id: str = ""


@dataclass
class AppConfig:
    interval_sec: int = 15
    items: list[ManagedFolder] = field(default_factory=list)


def config_path(root: Path) -> Path:
    return Path(root) / "config.json"


def load(root: Path) -> AppConfig:
    p = config_path(root)
    if not p.exists():
        return AppConfig()
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = [ManagedFolder(**it) for it in raw.get("items", [])]
    interval = int(raw.get("interval_sec", 15))
    # ponytail: 旧默认 60s，没有设置项；只迁这一档，别动用户以后可能设的更长间隔。
    if interval == 60:
        interval = 15
        cfg = AppConfig(interval_sec=interval, items=items)
        save(root, cfg)
        return cfg
    return AppConfig(interval_sec=interval, items=items)


def save(root: Path, cfg: AppConfig) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "interval_sec": cfg.interval_sec,
        "items": [asdict(it) for it in cfg.items],
    }
    config_path(root).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def find_item(cfg: AppConfig, item_id: str) -> ManagedFolder | None:
    for it in cfg.items:
        if it.id == item_id:
            return it
    return None
