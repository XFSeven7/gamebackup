# gamebackup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出可运行的 Windows 桌面工具：手动添加多个存档文件夹，按分钟自动备份到隐藏 git 仓库，树形图上查看存档线、隐藏自动节点、开线与回档。

**Architecture:** 游戏目录与 git 仓库分离。Python 负责配置、指纹、复制、dulwich、定时任务；WebView2 页面负责列表和 SVG 树形图，通过 js api 调 Python。

**Tech Stack:** Python 3.11、dulwich、pywebview、pystray、Pillow、unittest、PyInstaller（稍后打包）

## Global Constraints

- Windows 10/11 x64；界面与代码注释用中文
- 不出现 commit/checkout/merge/HEAD 等用户文案；线名 `main` 显示为「主线」
- 游戏存档目录永不写入 `.git`
- 备份根目录默认 `%LOCALAPPDATA%\gamebackup`
- 默认间隔 60 秒，没改动不提交；自动提交信息以 `[auto]` 开头
- 默认隐藏自动备份节点；当前线高亮
- 默认恢复=先留「恢复前」线再复制回去；覆盖恢复要二次确认
- 允许多文件夹、自定义显示名（可重名，名下显示路径缩略）
- 不实现 Steam 扫描、云同步、内容 diff/合并、拖拽建线

## File map

- `src/fingerprint.py` — 文件夹指纹
- `src/sync.py` — 目录镜像复制（含删除多余文件）
- `src/store.py` — dulwich：初始化、提交、分支、标签、notes、图数据
- `src/config.py` — 已管理文件夹列表
- `src/backup.py` — 一次检测+备份、恢复、开线
- `src/scheduler.py` — 后台间隔任务
- `src/app.py` — 托盘 + WebView2 + 暴露给前端的 API
- `ui/index.html` `ui/app.js` `ui/style.css` — 主界面
- `tests/test_fingerprint.py` `tests/test_sync.py` `tests/test_store.py` `tests/test_backup.py` `tests/test_graph_filter.py`

---

### Task 1: 文件夹指纹

**Files:**
- Create: `src/fingerprint.py`
- Test: `tests/test_fingerprint.py`

**Interfaces:**
- Produces: `fingerprint(root: Path) -> str`（相对路径+大小+mtime 的稳定哈希；目录不存在则抛 `FileNotFoundError`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_fingerprint.py
import tempfile
import time
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fingerprint import fingerprint

class FingerprintTest(unittest.TestCase):
    def test_same_files_same_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.sav").write_bytes(b"abc")
            self.assertEqual(fingerprint(p), fingerprint(p))

    def test_content_change_changes_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            f = p / "a.sav"
            f.write_bytes(b"abc")
            h1 = fingerprint(p)
            time.sleep(0.05)
            f.write_bytes(b"abcd")
            self.assertNotEqual(h1, fingerprint(p))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2:** `python tests/test_fingerprint.py` 期望 FAIL（模块不存在）
- [ ] **Step 3:** 实现 `fingerprint`（遍历文件，忽略仓库无关；不跟随目录符号链接）
- [ ] **Step 4:** 再跑测试 PASS
- [ ] **Step 5:** Commit `feat: 存档文件夹指纹，未改动可跳过备份`

---

### Task 2: 目录同步复制

**Files:**
- Create: `src/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Produces: `mirror(src: Path, dst: Path) -> None`：dst 变成 src 的完整镜像；失败时 dst 不应处于半更新（先写到 `dst.parent / (dst.name + ".incoming")` 再替换，Windows 下若 dst 存在则先镜像进 incoming 再逐文件覆盖+删多余）。第一版采用：复制到 `dst.tmp-incoming`，成功后再把文件拆进 dst 并删多余；若 incoming 阶段失败则不动 dst。

- [ ] 测试：新增、修改、删除文件后 dst 与 src 一致；src 中途失败（只测 incoming 失败不动 dst：对只读文件可跳过，改为断言 mirror 后文件集相等）
- [ ] 实现 `mirror`
- [ ] Commit `feat: 游戏目录与仓库工作区镜像复制`

---

### Task 3: git 仓库与图数据

**Files:**
- Create: `src/store.py`
- Test: `tests/test_store.py` `tests/test_graph_filter.py`

**Interfaces:**
- Produces:
  - `init_repo(path: Path) -> None`
  - `commit_auto(path: Path, message: str | None = None) -> str` 返回 commit id；message 默认带 `[auto]`
  - `commit_manual(path: Path, message: str) -> str` 不带 `[auto]`
  - `create_line(path: Path, from_id: str, name: str) -> None`
  - `checkout_line(path: Path, name: str) -> None`
  - `put_note(path: Path, commit_id: str, text: str) -> None`
  - `add_tag(path: Path, commit_id: str, name: str) -> None`
  - `graph(path: Path, hide_auto: bool, current_line: str) -> dict`

`graph` 返回：

```python
{
  "nodes": [{"id": str, "parents": [str], "time": int, "message": str, "auto": bool, "note": str, "tags": [str]}],
  "lines": [{"name": str, "tip": str, "display": str}],  # main -> 主线
  "current_line": str,
  "current_id": str,
}
```

`hide_auto=True` 时仍保留：每条线 tip、有 tag、有 note、非 auto 的节点；被隐藏节点的边接到最近保留的祖先。

- [ ] 测试：两次相同工作区不强制本任务去重（去重在 backup 层用指纹）
- [ ] 测试：`hide_auto` 后 auto 节点消失，tip 仍在
- [ ] 实现 store
- [ ] Commit `feat: 隐藏 git 仓库与树形图数据`

---

### Task 4: 配置与一次备份/恢复

**Files:**
- Create: `src/config.py` `src/backup.py`
- Test: `tests/test_backup.py`

**Interfaces:**
- `load/save(config_path)` 
- `ManagedFolder(id, name, path, current_line, paused)`
- `backup_once(root, item) -> {"skipped": bool, "reason": str}`
- `restore(root, item, commit_id, fork: bool) -> None`  
  `fork=True`：先备份当前，再从当前 tip 建「恢复前-时间」线，再 checkout 目标并 mirror 回游戏目录。  
  `fork=False`：覆盖恢复。
- `add_folder(root, live_path, name) -> ManagedFolder`：建 id、init repo、立刻 backup_once

- [ ] 测试两个临时文件夹互不影响；默认恢复后原进度仍能在「恢复前-*」线上
- [ ] Commit `feat: 多文件夹配置与回档`

---

### Task 5: 主界面 + 托盘

**Files:**
- Create: `src/app.py` `src/scheduler.py` `ui/index.html` `ui/app.js` `ui/style.css` `requirements.txt`

**Interfaces（暴露给 JS，方法名稳定）：**
- `list_items()`, `add_folder(path, name)`, `rename_item(id, name)`
- `graph(id, hide_auto)`, `restore(id, commit_id, fork)`, `create_line(id, commit_id, name)`
- `tag(id, commit_id, name)`, `set_note(id, commit_id, text)`
- `pause_item(id, paused)`, `pause_all(paused)`, `pick_folder() -> path`

UI：左侧列表（名+路径缩略，不可用标红），右侧 SVG 树，开关「显示自动备份」默认关，双击=默认恢复，右键菜单。无文件夹时大按钮「选择存档文件夹」。

- [ ] 手工：添加文件夹、改名、看图、开线、恢复
- [ ] Commit `feat: 托盘与树形图主界面`

---

### Task 6: 错误与设置（第一版收尾）

路径不可用标红并跳过；占用文件跳过；磁盘满托盘提示；回档确认框提示云存档可能覆盖；设置里改备份根目录与间隔（改根目录只影响新数据，第一版不允许热迁移已有 repos，避免复杂）。

- [ ] Commit `feat: 路径失效与回档确认提示`
