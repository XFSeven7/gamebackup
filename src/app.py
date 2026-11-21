"""托盘 + 主窗口入口。"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from dataclasses import asdict
from functools import wraps
from pathlib import Path

from PIL import Image
import webview
import pystray

from backup import add_folder, backup_once, dir_nbytes, fork_branch, format_bytes, remove_item as drop_managed, repo_dir, restore, save_now as do_save_now
from config import find_item, load, save
from paths import WEBVIEW2_HELP, ui_index, webview2_installed
from save_summary import summarize_onimusha
from scheduler import Scheduler
from steam import scan_installed_games
from storage import backup_root, default_backup_root, lock_backup_instance, migrate_backup
from store import add_tag, branch_exists, delete_line, delete_node as drop_node, graph, put_note, rename_line

DEFAULT_ROOT = default_backup_root()
ROOT = backup_root(DEFAULT_ROOT)
UI = ui_index()
ICON_PATH = UI.with_name("gamebackup.ico")
APP_TITLE = "存档助手 v1.1.1"
ONIMUSHA_APP_ID = "2638890"


def _icon_image() -> Image.Image:
    with Image.open(ICON_PATH, formats=["ICO"]) as icon:
        return icon.ico.getimage((64, 64)).convert("RGBA")


def _short_path(path: str, keep: int = 42) -> str:
    if len(path) <= keep:
        return path
    return path[:12] + "..." + path[-(keep - 15) :]


def _data_operation(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        with self._scheduler.data_lock:
            return method(self, *args, **kwargs)
    return run


class Api:
    def __init__(self, scheduler: Scheduler):
        self._scheduler = scheduler
        self._pause_all = False

    @_data_operation
    def backup_location(self) -> dict:
        return {"path": str(ROOT)}

    @_data_operation
    def move_backup_location(self, path: str) -> dict:
        global ROOT
        try:
            destination = Path(path)
            if not destination.is_absolute():
                raise ValueError("请选择备份文件夹。")
            destination = destination.resolve()
            warning = migrate_backup(ROOT, destination, default_root=DEFAULT_ROOT)
        except (OSError, ValueError) as error:
            return {"ok": False, "error": f"迁移未完成，仍在使用原目录。\n{error}"}
        ROOT = destination
        self._scheduler.root = destination
        return {"ok": True, "path": str(destination), "warning": warning}

    @_data_operation
    def list_items(self) -> list[dict]:
        cfg = load(ROOT)
        out = []
        for it in cfg.items:
            row = asdict(it)
            row["available"] = Path(it.path).is_dir()
            row["summary_supported"] = it.steam_app_id == ONIMUSHA_APP_ID
            row["path_short"] = _short_path(it.path)
            nbytes = dir_nbytes(repo_dir(ROOT, it.id))
            row["size_bytes"] = nbytes
            row["size_text"] = format_bytes(nbytes)
            out.append(row)
        return out

    def scan_steam_games(self) -> list[dict[str, str]]:
        return scan_installed_games()

    def pick_folder(self, directory: str = "") -> str:
        wins = webview.windows
        if not wins:
            return ""
        result = wins[0].create_file_dialog(webview.FOLDER_DIALOG, directory=directory)
        if not result:
            return ""
        return str(result[0])

    @_data_operation
    def add_folder(self, path: str, name: str, steam_app_id: str = "") -> dict:
        p = Path(path)
        if not path or not p.is_dir():
            return {"ok": False, "error": "找不到这个文件夹"}
        try:
            selected = p.resolve()
            backup_dir = ROOT.resolve()
            if selected.is_relative_to(backup_dir) or backup_dir.is_relative_to(selected):
                return {"ok": False, "error": "存档文件夹不能与备份目录重叠"}
            if steam_app_id:
                games = scan_installed_games()
                game = next((game for game in games if game["app_id"] == steam_app_id), None)
                if not game:
                    return {"ok": False, "error": "找不到这个 Steam 游戏，请刷新列表后重试"}
                if any(Path(entry["path"]).resolve().is_relative_to(selected) for entry in games):
                    return {"ok": False, "error": "选中的是游戏安装目录或其上级，请改选实际存档所在的文件夹"}
                for other in games:
                    if other["app_id"] == steam_app_id or not other.get("save_path"):
                        continue
                    other_save = Path(other["save_path"])
                    if selected.is_relative_to(other_save) or other_save.is_relative_to(selected):
                        return {"ok": False, "error": f"所选目录与「{other['name']}」的存档重叠，请重新选择。"}
            item = add_folder(ROOT, p, name.strip() or p.name, steam_app_id)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "item": asdict(item)}

    @_data_operation
    def open_item_folder(self, item_id: str) -> dict:
        item = find_item(load(ROOT), item_id)
        if not item:
            return {"ok": False, "error": "没有找到这份存档"}
        folder = Path(item.path)
        if not folder.is_dir():
            return {"ok": False, "error": "找不到这个存档文件夹"}
        try:
            os.startfile(folder)
        except OSError as e:
            return {"ok": False, "error": f"无法打开存档文件夹\n{e}"}
        return {"ok": True}

    @_data_operation
    def rename_item(self, item_id: str, name: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        it.name = name.strip() or it.name
        save(ROOT, cfg)
        return {"ok": True}

    @_data_operation
    def remove_item(self, item_id: str) -> dict:
        try:
            drop_managed(ROOT, item_id)
            return {"ok": True}
        except KeyError:
            return {"ok": False, "error": "没有找到这份存档"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def graph(self, item_id: str, hide_auto: bool) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        repo = repo_dir(ROOT, it.id)
        if not (repo / ".git").exists():
            return {"ok": False, "error": "这份存档还没备份过"}
        g = graph(repo, hide_auto=bool(hide_auto), current_line=it.current_line)
        g["ok"] = True
        g["item_name"] = it.name
        g["summary_supported"] = it.steam_app_id == ONIMUSHA_APP_ID
        return g

    @_data_operation
    def node_summary(self, item_id: str, commit_id: str) -> dict:
        it = find_item(load(ROOT), item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        if it.steam_app_id != ONIMUSHA_APP_ID:
            return {"ok": False, "error": "这个游戏暂不支持存档摘要"}
        try:
            summary = summarize_onimusha(repo_dir(ROOT, it.id), commit_id, ROOT / "tools")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, **summary}

    @_data_operation
    def restore(self, item_id: str, commit_id: str, fork: bool) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        try:
            restore(ROOT, it, commit_id, fork=bool(fork))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def create_line(self, item_id: str, commit_id: str, name: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        name = name.strip() or ("新进度")
        try:
            fork_branch(ROOT, it, commit_id, name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def tag(self, item_id: str, commit_id: str, name: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        name = name.strip()
        if not name:
            return {"ok": False, "error": "请起个名字"}
        try:
            add_tag(repo_dir(ROOT, it.id), commit_id, name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def set_note(self, item_id: str, commit_id: str, text: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        try:
            put_note(repo_dir(ROOT, it.id), commit_id, text)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def rename_line(self, item_id: str, old: str, new: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        new = new.strip()
        if not new:
            return {"ok": False, "error": "请输入名字"}
        try:
            rename_line(repo_dir(ROOT, it.id), old, new)
            if it.current_line == old:
                it.current_line = new
                save(ROOT, cfg)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def delete_line(self, item_id: str, name: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        try:
            delete_line(repo_dir(ROOT, it.id), name)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @_data_operation
    def delete_node(self, item_id: str, commit_id: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        try:
            drop_node(repo_dir(ROOT, it.id), commit_id)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if not branch_exists(repo_dir(ROOT, it.id), it.current_line):
            it.current_line = "main"
            save(ROOT, cfg)
        return {"ok": True}

    @_data_operation
    def pause_item(self, item_id: str, paused: bool) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        it.paused = bool(paused)
        save(ROOT, cfg)
        return {"ok": True}

    def pause_all(self, paused: bool) -> dict:
        self._pause_all = bool(paused)
        self._scheduler.set_pause_all(self._pause_all)
        return {"ok": True, "paused": self._pause_all}

    @_data_operation
    def backup_now(self, item_id: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        return {"ok": True, **backup_once(ROOT, it)}

    @_data_operation
    def save_now(self, item_id: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        return do_save_now(ROOT, it)

    def graph_rev(self) -> dict:
        return {"rev": self._scheduler.generation}


def main() -> None:
    if not webview2_installed():
        ctypes.windll.user32.MessageBoxW(None, WEBVIEW2_HELP, APP_TITLE, 0x10)
        return
    global ROOT
    with lock_backup_instance(DEFAULT_ROOT):
        ROOT = backup_root(DEFAULT_ROOT)
        if ROOT != DEFAULT_ROOT and not ROOT.is_dir():
            raise ValueError(f"备份目录暂不可用，请连接存放备份的磁盘后重试。\n{ROOT}")
        _run_app()


def _run_app() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    scheduler = Scheduler(ROOT)
    scheduler.start()
    api = Api(scheduler)
    exiting = threading.Event()
    window = webview.create_window(APP_TITLE, str(UI), js_api=api, width=1100, height=720)

    def on_window_closing(sender, event):
        if not exiting.is_set() and event.CloseReason.ToString() == "UserClosing":
            event.Cancel = True
            sender.Hide()

    def bind_window_closing(window):
        window.native.FormClosing += on_window_closing

    window.events.before_show += bind_window_closing

    def show_window(_icon, _item):
        if not exiting.is_set():
            window.show()
            window.restore()

    def quit_app(_icon, _item):
        if not exiting.is_set():
            exiting.set()
            window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("打开窗口", show_window, default=True),
        pystray.MenuItem("暂停自动备份", lambda _i, _j: api.pause_all(True)),
        pystray.MenuItem("继续自动备份", lambda _i, _j: api.pause_all(False)),
        pystray.MenuItem("退出", quit_app),
    )
    icon = pystray.Icon("gamebackup", _icon_image(), APP_TITLE, menu)
    tray_thread = threading.Thread(target=icon.run, daemon=True)
    tray_thread.start()

    try:
        webview.start(icon=str(ICON_PATH))
    finally:
        scheduler.stop()
        icon.stop()
        tray_thread.join(timeout=5)


if __name__ == "__main__":
    main()
