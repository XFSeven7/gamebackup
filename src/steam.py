"""读取本机 Steam 库和已安装应用的清单。"""

from __future__ import annotations

import os
import winreg
from pathlib import Path

import vdf


def _steam_root() -> Path | None:
    key = r"Software\Valve\Steam"
    for hive, name, view in (
        (winreg.HKEY_CURRENT_USER, "SteamPath", 0),
        (winreg.HKEY_LOCAL_MACHINE, "InstallPath", winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, "InstallPath", winreg.KEY_WOW64_64KEY),
    ):
        try:
            with winreg.OpenKey(hive, key, access=winreg.KEY_READ | view) as registry:
                value, _ = winreg.QueryValueEx(registry, name)
        except OSError:
            continue
        if isinstance(value, str) and value:
            root = Path(os.path.expandvars(value))
            if root.is_absolute() and (root / "steamapps").is_dir():
                return root

    for name in ("ProgramFiles(x86)", "ProgramFiles"):
        if base := os.environ.get(name):
            root = Path(base) / "Steam"
            if (root / "steamapps").is_dir():
                return root
    return None


def _read_vdf(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8-sig") as file:
            return {key.lower(): value for key, value in vdf.load(file).items()}
    except (OSError, UnicodeError, SyntaxError):
        return {}


def _libraries(root: Path) -> set[Path]:
    libraries = {root}
    for directory in ("steamapps", "config"):
        folders = _read_vdf(root / directory / "libraryfolders.vdf").get("libraryfolders")
        if not isinstance(folders, dict):
            continue
        for key, entry in folders.items():
            if not key.isdecimal():
                continue
            path = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(path, str) and path and Path(path).is_absolute():
                libraries.add(Path(path))
    return libraries


def _save_folder(accounts: list[Path], app_id: str, install_path: Path) -> str:
    home = Path.home()
    bases = [home / "Documents", home / "Saved Games", home / "AppData" / "LocalLow", install_path]
    bases.extend(Path(value) for key in ("APPDATA", "LOCALAPPDATA") if (value := os.environ.get(key)))
    candidates = set()
    for account in accounts:
        app_data = account / app_id
        entries = _read_vdf(app_data / "remotecache.vdf").get(app_id)
        if not isinstance(entries, dict):
            continue
        files = [Path(name) for name, details in entries.items() if isinstance(details, dict)]
        remote = app_data / "remote"
        for base in (remote, *bases):
            try:
                base_path = base.resolve()
                parents = []
                for file in files:
                    if file.anchor or ".." in file.parts:
                        continue
                    local_file = base_path / file
                    if local_file.is_file():
                        resolved = local_file.resolve()
                        if resolved.is_relative_to(base_path):
                            parents.append(resolved.parent)
                if parents:
                    directory = Path(os.path.commonpath(parents))
                    if base == remote or directory != base_path:
                        candidates.add(directory)
            except OSError:
                continue
    return str(candidates.pop()) if len(candidates) == 1 else ""


def scan_installed_games() -> list[dict[str, str]]:
    root = _steam_root()
    if root is None:
        return []
    try:
        accounts = [p for p in (root / "userdata").iterdir() if p.name.isdecimal() and p.is_dir()]
    except OSError:
        accounts = []

    games: dict[str, dict[str, str]] = {}
    for library in (root, *sorted(_libraries(root) - {root})):
        steamapps = library / "steamapps"
        try:
            manifests = list(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            app_id = manifest.stem.removeprefix("appmanifest_")
            if not app_id.isdecimal() or app_id == "228980" or app_id in games:
                continue
            state = _read_vdf(manifest).get("appstate")
            if not isinstance(state, dict):
                continue
            state = {key.lower(): value for key, value in state.items()}
            name = state.get("name")
            folder = state.get("installdir")
            if state.get("appid") != app_id or not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(folder, str) or not folder or folder in (".", "..") or Path(folder).name != folder:
                continue
            install_path = steamapps / "common" / folder
            try:
                if install_path.is_dir():
                    games[app_id] = {
                        "app_id": app_id,
                        "name": name,
                        "path": str(install_path),
                        "save_path": _save_folder(accounts, app_id, install_path),
                    }
            except OSError:
                continue
    return sorted(games.values(), key=lambda game: (game["name"].casefold(), game["path"]))
