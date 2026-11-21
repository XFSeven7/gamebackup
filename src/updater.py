"""Fetch and stage the latest official Windows release."""

import ctypes
from dataclasses import dataclass
import hashlib
import json
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPOSITORY = "XFSeven7/gamebackup"
ASSET = "gamebackup-win64.zip"
MANAGED_FILES = ("gamebackup.exe", "_internal")
_VERSION = re.compile(r"v(\d+)\.(\d+)\.(\d+)", re.ASCII)
_is_reserved = getattr(ntpath, "isreserved", lambda part: PureWindowsPath(part).is_reserved())


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    url: str
    size: int
    sha256: str


def check_release(current: str) -> Release | None:
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "gamebackup"},
    )
    with urlopen(request, timeout=10) as response:
        data = json.load(response)
    tag = data.get("tag_name", "")
    installed = _VERSION.fullmatch(current)
    latest = _VERSION.fullmatch(tag)
    if (data.get("draft") or data.get("prerelease") or not installed or not latest
            or tuple(map(int, latest.groups())) <= tuple(map(int, installed.groups()))):
        return None
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET}"
    for asset in data.get("assets", []):
        if (asset.get("name") == ASSET and asset.get("state") == "uploaded"
                and asset.get("browser_download_url") == url):
            digest = re.fullmatch(r"sha256:([a-fA-F0-9]{64})", asset.get("digest") or "")
            size = asset.get("size")
            if digest and type(size) is int and size > 0:
                return Release(tag, data.get("body") or "", url, size, digest[1].lower())
    return None


def stage_release(release: Release, work: Path, progress) -> None:
    zip_path = work / ASSET
    received = 0
    sha256 = hashlib.sha256()
    request = Request(release.url, headers={"User-Agent": "gamebackup"})
    with urlopen(request, timeout=20) as response, zip_path.open("xb") as output:
        while chunk := response.read(256 * 1024):
            received += len(chunk)
            if received > release.size:
                raise ValueError("更新包大小与发布信息不符。")
            output.write(chunk)
            sha256.update(chunk)
            progress("downloading", received)
    progress("verifying", received)
    if received != release.size or sha256.hexdigest() != release.sha256:
        raise ValueError("更新包校验失败，请重新下载。")

    with ZipFile(zip_path) as archive:
        seen = set()
        members = []
        for entry in archive.infolist():
            name = entry.orig_filename.replace("\\", "/")
            parts = name.removesuffix("/").split("/")
            key = tuple(part.casefold() for part in parts)
            if (parts[0] != "gamebackup" or key in seen or any(
                not part or part.endswith((" ", ".")) or re.search(r'[\x00-\x1f<>:"\\|?*]', part)
                or _is_reserved(part) for part in parts
            )):
                raise ValueError("更新包中有无效的文件路径。")
            seen.add(key)
            if len(parts) > 1 and parts[1] in MANAGED_FILES:
                members.append((entry, parts, name.endswith("/")))
        files = {"/".join(parts) for _, parts, is_dir in members if not is_dir}
        if not {"gamebackup/gamebackup.exe", "gamebackup/_internal/ui/index.html"} <= files:
            raise ValueError("更新包缺少应用文件。")
        for entry, parts, is_dir in members:
            destination = work.joinpath(*parts)
            if is_dir:
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
    zip_path.unlink()


def start_installer(install: Path, work: Path) -> None:
    helper = work / "install-update.ps1"
    shutil.copyfile(install / "_internal" / "scripts" / helper.name, helper)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    set_dll_directory = ctypes.windll.kernel32.SetDllDirectoryW
    set_dll_directory(None)
    try:
        subprocess.Popen(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(helper)],
            cwd=install,
            env={**os.environ, "GAMEBACKUP_UPDATE_PID": str(os.getpid()), "PYINSTALLER_RESET_ENVIRONMENT": "1"},
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    finally:
        set_dll_directory(str(install / "_internal"))
