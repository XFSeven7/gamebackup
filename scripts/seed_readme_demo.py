"""生成 README 截图用的模拟存档数据（不碰用户真实 %LOCALAPPDATA%）。"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from backup import add_folder, dir_nbytes, format_bytes, repo_dir, save_now  # noqa: E402
from config import find_item, load, save  # noqa: E402
from dulwich.repo import Repo  # noqa: E402

from store import add_tag, commit_auto, fork_node, graph, put_note  # noqa: E402
from sync import mirror  # noqa: E402

DEMO_ROOT = ROOT / "docs" / "_demo_root"
OUT_JS = ROOT / "docs" / "readme-demo" / "demo-data.js"
LIVE = DEMO_ROOT / "live"


def _bump(live: Path, text: str) -> None:
    live.mkdir(parents=True, exist_ok=True)
    (live / "save.dat").write_text(text, encoding="utf-8")
    time.sleep(1.05)


def _item(root: Path, item_id: str):
    return find_item(load(root), item_id)


def _attach_head(repo: Path, line: str) -> None:
    """只挂回分支，不用 porcelain.reset（它会误改其它分支 tip）。"""
    r = Repo(str(repo))
    r.refs.set_symbolic_ref(b"HEAD", b"refs/heads/" + line.encode("utf-8"))


def _auto(root: Path, item_id: str, live: Path) -> str:
    it = _item(root, item_id)
    repo = repo_dir(root, item_id)
    _attach_head(repo, it.current_line)
    mirror(live, repo)
    return commit_auto(repo)


def _manual(root: Path, item_id: str, live: Path, note: str = "") -> str:
    it = _item(root, item_id)
    repo = repo_dir(root, item_id)
    _attach_head(repo, it.current_line)
    save_now(root, it)
    tip = graph(repo, hide_auto=False, current_line=it.current_line)["current_id"]
    if note:
        put_note(repo, tip, note)
        _attach_head(repo, it.current_line)
        tip = graph(repo, hide_auto=False, current_line=it.current_line)["current_id"]
    return tip


def _set_line(root: Path, item_id: str, line: str) -> None:
    cfg = load(root)
    it = find_item(cfg, item_id)
    it.current_line = line
    save(root, cfg)
    _attach_head(repo_dir(root, item_id), line)


def _seed_elden(root: Path) -> str:
    live = LIVE / "EldenRing"
    _bump(live, "start")
    item = add_folder(root, live, "艾尔登法环")
    iid = item.id
    repo = repo_dir(root, iid)

    _bump(live, "stormveil-1")
    _auto(root, iid, live)
    _bump(live, "stormveil-2")
    _auto(root, iid, live)

    _bump(live, "godrick")
    godrick = _manual(root, iid, live, "手动保存 · 击败葛瑞克")
    add_tag(repo, godrick, "击败葛瑞克")

    # 主线继续往前（全程留在 main，避免 checkout 其它线时 dulwich reset 误改 main）
    _bump(live, "liurnia")
    _auto(root, iid, live)
    _bump(live, "academy")
    _manual(root, iid, live, "手动保存 · 雷亚卢卡利亚")

    # 从葛瑞克开探索支线
    _cid, side = fork_node(repo, godrick, "探索支线")
    _set_line(root, iid, side)
    put_note(repo, _cid, "探索支线")
    _attach_head(repo, side)
    _bump(live, "ranni-1")
    _auto(root, iid, live)
    _bump(live, "ranni-2")
    _manual(root, iid, live, "手动保存 · 菈妮支线")

    # 从葛瑞克开二周目（当前线）
    _cid, branch = fork_node(repo, godrick, "二周目")
    _set_line(root, iid, branch)
    put_note(repo, _cid, "二周目开荒")
    _attach_head(repo, branch)
    _bump(live, "ngplus-1")
    _auto(root, iid, live)
    _bump(live, "ngplus-2")
    _manual(root, iid, live, "手动保存 · 二周目石城")
    return iid


def _seed_stardew(root: Path) -> str:
    live = LIVE / "StardewValley"
    _bump(live, "spring-1")
    item = add_folder(root, live, "星露谷物语")
    iid = item.id
    for i in range(3):
        _bump(live, f"spring-{i + 2}")
        _auto(root, iid, live)
    _bump(live, "summer")
    tip = _manual(root, iid, live, "手动保存 · 夏天第一天")
    add_tag(repo_dir(root, iid), tip, "夏天到了")
    _bump(live, "fall")
    _auto(root, iid, live)
    return iid


def _seed_sekiro(root: Path) -> str:
    live = LIVE / "Sekiro"
    _bump(live, "ashina")
    item = add_folder(root, live, "只狼")
    iid = item.id
    for i in range(2):
        _bump(live, f"ashina-{i + 2}")
        _auto(root, iid, live)
    _bump(live, "genichiro")
    _manual(root, iid, live, "手动保存 · 弦一郎前")
    cfg = load(root)
    it = find_item(cfg, iid)
    it.paused = True
    save(root, cfg)
    return iid


_FAKE_PATH = {
    "艾尔登法环": r"C:\Users\Player\AppData\Roaming\EldenRing\123456789",
    "星露谷物语": r"C:\Users\Player\AppData\Roaming\StardewValley\Saves",
    "只狼": r"C:\Users\Player\AppData\Roaming\Sekiro\123456789",
}


def _item_row(root: Path, it) -> dict:
    nbytes = dir_nbytes(repo_dir(root, it.id))
    path = _FAKE_PATH.get(it.name, it.path)
    short = path if len(path) <= 42 else path[:12] + "..." + path[-(42 - 15) :]
    return {
        "id": it.id,
        "name": it.name,
        "path": path,
        "path_short": short,
        "current_line": it.current_line,
        "paused": it.paused,
        "available": True,
        "size_bytes": nbytes,
        "size_text": format_bytes(nbytes),
    }


def build() -> dict:
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)
    DEMO_ROOT.mkdir(parents=True)
    OUT_JS.parent.mkdir(parents=True, exist_ok=True)

    elden = _seed_elden(DEMO_ROOT)
    stardew = _seed_stardew(DEMO_ROOT)
    sekiro = _seed_sekiro(DEMO_ROOT)

    cfg = load(DEMO_ROOT)
    order = {elden: 0, stardew: 1, sekiro: 2}
    cfg.items.sort(key=lambda x: order.get(x.id, 99))
    save(DEMO_ROOT, cfg)

    items = [_item_row(DEMO_ROOT, it) for it in cfg.items]
    graphs: dict[str, dict] = {}
    for it in cfg.items:
        repo = repo_dir(DEMO_ROOT, it.id)
        for hide in (True, False):
            key = f"{it.id}:{'1' if hide else '0'}"
            g = graph(repo, hide_auto=hide, current_line=it.current_line)
            g["ok"] = True
            g["item_name"] = it.name
            graphs[key] = g

    payload = {"items": items, "graphs": graphs, "selectedId": elden}
    OUT_JS.write_text(
        "window.README_DEMO = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    n = len(graphs[f"{elden}:1"]["nodes"])
    print(f"demo root: {DEMO_ROOT}")
    print(f"wrote: {OUT_JS} (elden hidden-auto nodes={n})")
    return payload


if __name__ == "__main__":
    build()
