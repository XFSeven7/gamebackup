"""托盘 + 主窗口入口。"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageDraw
import webview
import pystray

from backup import add_folder, backup_once, dir_nbytes, fork_branch, format_bytes, remove_item as drop_managed, repo_dir, restore, save_now as do_save_now
from config import find_item, load, save
from paths import WEBVIEW2_HELP, ui_index, webview2_installed
from scheduler import Scheduler
from steam import scan_installed_games
from store import add_tag, branch_exists, delete_line, delete_node as drop_node, graph, put_note, rename_line

# ponytail: GAMEBACKUP_ROOT 方便演示/截图，不碰用户真实数据。
ROOT = Path(os.environ["GAMEBACKUP_ROOT"]) if os.environ.get("GAMEBACKUP_ROOT") else (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "gamebackup"
)
UI = ui_index()
APP_TITLE = "存档助手 v1.1.0"


def _icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(61, 139, 253, 255))
    d.rectangle((28, 16, 36, 48), fill=(255, 255, 255, 255))
    d.polygon([(18, 34), (32, 50), (46, 34)], fill=(255, 255, 255, 255))
    return img


def _short_path(path: str, keep: int = 42) -> str:
    if len(path) <= keep:
        return path
    return path[:12] + "..." + path[-(keep - 15) :]


class Api:
    def __init__(self, scheduler: Scheduler):
        self.scheduler = scheduler
        self._pause_all = False

    def list_items(self) -> list[dict]:
        cfg = load(ROOT)
        out = []
        for it in cfg.items:
            row = asdict(it)
            row["available"] = Path(it.path).is_dir()
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

    def add_folder(self, path: str, name: str, steam_app_id: str = "") -> dict:
        p = Path(path)
        if not path or not p.is_dir():
            return {"ok": False, "error": "找不到这个文件夹"}
        try:
            if steam_app_id:
                games = scan_installed_games()
                game = next((game for game in games if game["app_id"] == steam_app_id), None)
                if not game:
                    return {"ok": False, "error": "找不到这个 Steam 游戏，请刷新列表后重试"}
                selected = p.resolve()
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

    def rename_item(self, item_id: str, name: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        it.name = name.strip() or it.name
        save(ROOT, cfg)
        return {"ok": True}

    def remove_item(self, item_id: str) -> dict:
        try:
            drop_managed(ROOT, item_id)
            return {"ok": True}
        except KeyError:
            return {"ok": False, "error": "没有找到这份存档"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
        return g

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
        self.scheduler.set_pause_all(self._pause_all)
        return {"ok": True, "paused": self._pause_all}

    def backup_now(self, item_id: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        return {"ok": True, **backup_once(ROOT, it)}

    def save_now(self, item_id: str) -> dict:
        cfg = load(ROOT)
        it = find_item(cfg, item_id)
        if not it:
            return {"ok": False, "error": "没有找到这份存档"}
        return do_save_now(ROOT, it)

    def graph_rev(self) -> dict:
        return {"rev": self.scheduler.generation}


def main() -> None:
    if not webview2_installed():
        ctypes.windll.user32.MessageBoxW(None, WEBVIEW2_HELP, APP_TITLE, 0x10)
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    scheduler = Scheduler(ROOT)
    scheduler.start()
    api = Api(scheduler)

    def show_window():
        if webview.windows:
            webview.windows[0].show()
            webview.windows[0].restore()
        else:
            webview.create_window(APP_TITLE, str(UI), js_api=api, width=1100, height=720)

    def quit_app(icon, _item):
        scheduler.stop()
        icon.stop()
        for w in list(webview.windows):
            w.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("打开窗口", lambda _i, _j: show_window(), default=True),
        pystray.MenuItem("暂停自动备份", lambda _i, _j: api.pause_all(True)),
        pystray.MenuItem("继续自动备份", lambda _i, _j: api.pause_all(False)),
        pystray.MenuItem("退出", quit_app),
    )
    icon = pystray.Icon("gamebackup", _icon_image(), APP_TITLE, menu)
    threading.Thread(target=icon.run, daemon=True).start()

    webview.create_window(APP_TITLE, str(UI), js_api=api, width=1100, height=720)
    webview.start()
    scheduler.stop()


if __name__ == "__main__":
    main()
