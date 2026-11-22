"""Load versioned game support packs through the host's supported API."""

from __future__ import annotations

import hashlib
import importlib.abc
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

from support_updates import check_support_updates, parse_version, verified_installed_descriptor

SUPPORT_API = 1
SUPPORT_PUBLIC_KEY = bytes.fromhex("46ded59007f0854a0109d710ec675a3bce644f48f854416ad645019ca3e9b415")
BUNDLED_SUPPORT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "bundled_support"
_MODULE_PREFIX = "_gamebackup_support_"
_ID = re.compile(r"[a-z][a-z0-9_]{0,47}", re.ASCII)
_ENTRY_POINTS = ("summarize", "read_event_state", "major_events")
_INDEX_POINTS = ("load_index", "annotate_nodes", "scan_index", "save_index")


def version_key(value: str) -> tuple[int, int, int]:
    version = parse_version(value)
    if version is None:
        raise ValueError("无效的游戏支持包版本")
    return version


class _SourceLoader(SourceFileLoader):
    def get_code(self, fullname):
        return self.source_to_code(self.get_data(self.path), self.path)


class _PackFinder(importlib.abc.MetaPathFinder):
    """Read only source files from the pack. Do not consume or write bytecode caches."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(_MODULE_PREFIX) or not path:
            return None
        basename = fullname.rsplit(".", 1)[-1]
        for location in path:
            package = Path(location) / basename / "__init__.py"
            source = Path(location) / (basename + ".py")
            if package.is_file():
                return _source_spec(fullname, package, is_package=True)
            if source.is_file():
                return _source_spec(fullname, source)
        # Do not let the default loader fall back to unsigned bytecode or native modules.
        raise ModuleNotFoundError(fullname, name=fullname)


def _source_spec(fullname: str, source: Path, *, is_package: bool = False):
    return importlib.util.spec_from_file_location(
        fullname, source, loader=_SourceLoader(fullname, str(source)),
        submodule_search_locations=[str(source.parent)] if is_package else None,
    )


sys.meta_path.insert(0, _PackFinder())


def _layout(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for group in ("tabs", "labels", "branch_labels"):
        labels = value.get(group)
        if isinstance(labels, dict):
            result[group] = {
                key: text for key, text in labels.items()
                if isinstance(text, str) and 0 < len(text) <= 120
            }
    sections = value.get("sections")
    if isinstance(sections, list):
        result["sections"] = list(dict.fromkeys(
            section for section in sections if section in ("goal", "facts", "boss", "changes", "inventory")
        ))
    return result


@dataclass(frozen=True)
class GameSupport:
    id: str
    name: str
    version: str
    notes: str
    source: str
    layout: dict
    steam_app_ids: tuple[str, ...]
    path_suffix: tuple[str, ...]
    module: ModuleType

    @property
    def has_index(self) -> bool:
        return all(callable(getattr(self.module, name, None)) for name in _INDEX_POINTS)

    def available(self, tools_dir: Path) -> bool:
        check = getattr(self.module, "available", None)
        return bool(check(tools_dir)) if callable(check) else True

    def index_available(self, tools_dir: Path) -> bool:
        check = getattr(self.module, "index_available", None)
        return bool(check(tools_dir)) if callable(check) else self.available(tools_dir)

    def info(self) -> dict:
        return {"id": self.id, "name": self.name, "version": self.version,
                "notes": self.notes, "source": self.source}


def _string_list(values: object) -> tuple[str, ...]:
    if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
        return ()
    return tuple(values)


def _read_pack(path: Path, receipt: dict | None = None, *, probe: bool = False) -> GameSupport:
    metadata = json.loads((path / "support.json").read_text(encoding="utf-8-sig"))
    if not isinstance(metadata, dict):
        raise ValueError("无效的游戏支持包描述")
    pack_id, version = metadata.get("id"), metadata.get("version")
    if not isinstance(pack_id, str) or not _ID.fullmatch(pack_id):
        raise ValueError("无效的游戏支持包编号")
    version_key(version)
    minimum, maximum = metadata.get("api_min"), metadata.get("api_max")
    if type(minimum) is not int or type(maximum) is not int or not minimum <= SUPPORT_API <= maximum:
        raise ValueError("游戏支持包与当前应用接口不兼容")
    if receipt is not None and any(receipt.get(key) != metadata.get(key) for key in (
        "id", "version", "api_min", "api_max",
    )):
        raise ValueError("游戏支持包描述与发布清单不符")
    name, notes, match = metadata.get("name"), metadata.get("notes"), metadata.get("match")
    if not isinstance(name, str) or not name or not isinstance(notes, str) or not isinstance(match, dict):
        raise ValueError("游戏支持包缺少必要信息")
    steam_app_ids = _string_list(match.get("steam_app_ids"))
    path_suffix = tuple(part.casefold() for part in _string_list(match.get("path_suffix")))
    if not steam_app_ids and not path_suffix:
        raise ValueError("游戏支持包缺少识别条件")
    key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    module_name = _MODULE_PREFIX + key
    spec = _source_spec(module_name, path / "__init__.py", is_package=True)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        if any(not callable(getattr(module, entry, None)) for entry in _ENTRY_POINTS):
            raise ValueError("游戏支持包缺少解析入口")
    except Exception:
        _forget_module(module_name)
        raise
    if probe:
        _forget_module(module_name)
    return GameSupport(pack_id, name, version, notes, "builtin" if receipt is None else "downloaded",
                       _layout(metadata.get("layout")), steam_app_ids, path_suffix, module)


def _forget_module(module_name: str) -> None:
    for key in tuple(sys.modules):
        if key == module_name or key.startswith(module_name + "."):
            sys.modules.pop(key, None)


@lru_cache(maxsize=1)
def _bundled_packs() -> tuple[GameSupport, ...]:
    return tuple(_read_pack(path) for path in sorted(BUNDLED_SUPPORT.iterdir()) if (path / "support.json").is_file())


class GameSupportRegistry:
    def __init__(self, install_root: Path | None = None, public_key: bytes = SUPPORT_PUBLIC_KEY):
        self.install_root = install_root
        self.public_key = public_key
        self._packs = {pack.id: pack for pack in _bundled_packs()}
        if install_root and install_root.is_dir():
            paths = (folder for folder in install_root.glob("*/*") if parse_version(folder.name))
            for folder in sorted(paths, key=lambda path: version_key(path.name), reverse=True):
                if folder.is_dir():
                    pack = self._load_installed(folder)
                    if pack is not None:
                        self.activate((pack,))

    def _load_installed(self, folder: Path) -> GameSupport | None:
        try:
            current = self._packs.get(folder.parent.name)
            if current is not None and version_key(folder.name) <= version_key(current.version):
                return None
            receipt = verified_installed_descriptor(folder, self.public_key)
            if receipt is not None:
                return _read_pack(folder, receipt)
        except Exception:
            # Failed packs leave the active or bundled version in use.
            pass
        return None

    def for_item(self, item) -> GameSupport | None:
        packs = self._packs.values()
        for pack in packs:
            if item.steam_app_id and item.steam_app_id in pack.steam_app_ids:
                return pack
        parts = tuple(part.casefold() for part in Path(item.path).parts)
        return next((pack for pack in packs if pack.path_suffix and
                     parts[-len(pack.path_suffix):] == pack.path_suffix), None)

    def describe(self) -> list[dict]:
        return [pack.info() for pack in self._packs.values()]

    def stage_updates(self) -> list[GameSupport]:
        if self.install_root is None:
            return []
        found = check_support_updates(
            self.install_root, {pack.id: pack.version for pack in self._packs.values()},
            SUPPORT_API, self.public_key, lambda path, receipt: _read_pack(path, receipt, probe=True),
        )
        return [pack for folder in found if (pack := self._load_installed(folder)) is not None]

    def activate(self, packs) -> bool:
        updated = self._packs.copy()
        changed = False
        for pack in packs:
            active = updated.get(pack.id)
            if active is None or version_key(pack.version) > version_key(active.version):
                updated[pack.id] = pack
                changed = True
        self._packs = updated
        return changed
