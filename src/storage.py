"""备份目录设置和迁移。"""

from __future__ import annotations

import hashlib
import json
import msvcrt
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from config import load


def default_backup_root() -> Path:
    if override := os.environ.get("GAMEBACKUP_ROOT"):
        return Path(override).absolute()
    return (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "gamebackup").absolute()


def _location_file(default_root: Path) -> Path:
    return default_root.with_name(default_root.name + "-location.json")


def backup_root(default_root: Path) -> Path:
    try:
        data = json.loads(_location_file(default_root).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default_root
    path = Path(data["backup_root"])
    if not path.is_absolute():
        raise ValueError("备份位置设置必须是绝对路径。")
    return path


@contextmanager
def lock_backup_instance(default_root: Path):
    lock_path = _location_file(default_root).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError("存档助手已在运行，请从系统托盘打开。") from error
        yield


def _write_location(default_root: Path, destination: Path) -> None:
    target = _location_file(default_root)
    with tempfile.TemporaryDirectory(
        prefix=".gamebackup-location-", dir=target.parent, ignore_cleanup_errors=True,
    ) as temp:
        pending = Path(temp) / target.name
        with pending.open("w", encoding="utf-8") as file:
            json.dump({"backup_root": str(destination)}, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        pending.replace(target)


def _directory_contents(root: Path) -> dict[Path, bytes | None]:
    entries = {}
    directories = [root]
    while directories:
        for path in directories.pop().iterdir():
            info = path.lstat()
            if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError(f"备份目录含链接或占位文件，无法安全迁移：{path.relative_to(root)}")
            if stat.S_ISDIR(info.st_mode):
                entries[path.relative_to(root)] = None
                directories.append(path)
            else:
                digest = hashlib.sha256()
                with path.open("rb") as file:
                    for chunk in iter(lambda: file.read(1024 * 1024), b""):
                        digest.update(chunk)
                entries[path.relative_to(root)] = digest.digest()
    return entries


def migrate_backup(source: Path, destination: Path, *, default_root: Path) -> str | None:
    """在应用持有数据锁时，把完整备份迁到新位置。返回旧目录清理警告。"""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        return None
    if source == Path(source.anchor) or destination == Path(destination.anchor):
        raise ValueError("请选择磁盘下的一个文件夹。")
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("新旧备份目录不能互相包含。")
    settings = _location_file(default_root).resolve()
    if settings.is_relative_to(source) or settings.is_relative_to(destination):
        raise ValueError("请选择不包含存档助手位置设置的文件夹。")
    for item in load(source).items:
        live = Path(item.path).resolve()
        if live.is_relative_to(source) or live.is_relative_to(destination) or destination.is_relative_to(live):
            raise ValueError(f"备份迁移位置与「{item.name}」的游戏存档目录重叠。")

    existed = destination.exists()
    if existed and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("请选择空文件夹，避免覆盖已有文件。")
    if not source.is_dir() or not destination.parent.is_dir():
        raise ValueError("找不到源备份目录或目标文件夹的上级目录。")

    expected = _directory_contents(source)
    with tempfile.TemporaryDirectory(
        prefix=".gamebackup-move-", dir=destination.parent, ignore_cleanup_errors=True,
    ) as temp:
        staged = Path(temp) / "backup"
        shutil.copytree(source, staged, symlinks=True)
        if _directory_contents(staged) != expected:
            raise ValueError("备份文件校验失败，仍在使用原目录。")
        if existed:
            destination.rmdir()
        try:
            staged.rename(destination)
        except OSError:
            if existed:
                destination.mkdir(exist_ok=True)
            raise
        try:
            _write_location(default_root, destination)
        except OSError:
            destination.rename(staged)
            if existed:
                destination.mkdir()
            raise

    try:
        if source.resolve() != source:
            raise OSError("原路径发生变化")
        shutil.rmtree(source)
    except OSError:
        return f"已切换到新目录。原目录还有文件未清理：\n{source}"
    return None
