# 绿色 zip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打出 `gamebackup-win64.zip`：解压后双击 `gamebackup.exe` 即可使用，无需 Python/Git。

**Architecture:** 抽出 `ui_index()` / WebView2 检测，便于测试；PyInstaller `onedir` 把 `ui/` 打进 `_internal`；PowerShell 脚本安装构建依赖、打包并压缩 zip。备份根目录仍是 `%LOCALAPPDATA%\gamebackup`。

**Tech Stack:** Python 3.11、PyInstaller 6、PowerShell `Compress-Archive`

## Global Constraints

- 交付物文件名：`gamebackup-win64.zip`；exe 名：`gamebackup.exe`
- `onedir`，`console=False`；不写注册表、不做安装程序、不签名
- 备份数据默认 `%LOCALAPPDATA%\gamebackup`，不打进 zip
- Win10 缺 WebView2 时 MessageBox 中文说明，含 `https://go.microsoft.com/fwlink/p/?LinkId=2124703`，然后退出
- frozen 时 UI 从 `sys._MEIPASS/ui/index.html` 读；开发时从仓库 `ui/index.html` 读
- `dist/`、`build/` 不进 git；`gamebackup.spec` 要进 git（当前 `.gitignore` 的 `*.spec` 必须改掉）
- 界面与注释用中文；开发仍用 `python run.py`
- Windows 10/11 x64

## File map

- `src/paths.py` — `ui_index()`、`webview2_installed()`、`WEBVIEW2_HELP`
- `src/app.py` — 用上述函数；缺 WebView2 则 MessageBox 后 return
- `tests/test_paths.py` — 开发/frozen 路径、帮助文案、注册表缺失时判定
- `gamebackup.spec` — PyInstaller onedir
- `requirements-build.txt` — `pyinstaller>=6.0`
- `scripts/build.ps1` — 安装依赖、打包、打 zip
- `.gitignore` — 不再忽略 `gamebackup.spec`
- `README.md` — 一行打包说明

---

### Task 1: UI 路径

**Files:**
- Create: `src/paths.py`
- Create: `tests/test_paths.py`
- Modify: `src/app.py`（`UI = ui_index()`）

**Interfaces:**
- Produces: `ui_index() -> Path`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_paths.py
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from paths import ui_index


class PathsTest(unittest.TestCase):
    def test_dev_index_exists(self):
        p = ui_index()
        self.assertTrue(p.is_file())
        self.assertEqual(p.name, "index.html")

    def test_frozen_uses_meipass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "ui").mkdir()
            target = root / "ui" / "index.html"
            target.write_text("<html></html>", encoding="utf-8")
            old_frozen = getattr(sys, "frozen", None)
            old_mei = getattr(sys, "_MEIPASS", None)
            sys.frozen = True
            sys._MEIPASS = str(root)
            try:
                p = ui_index()
                self.assertEqual(p, target)
                self.assertTrue(p.is_file())
            finally:
                if old_frozen is None:
                    delattr(sys, "frozen")
                else:
                    sys.frozen = old_frozen
                if old_mei is None:
                    if hasattr(sys, "_MEIPASS"):
                        delattr(sys, "_MEIPASS")
                else:
                    sys._MEIPASS = old_mei


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2:** `C:\Users\Seven\scoop\apps\python\current\python.exe -m unittest tests.test_paths -v` 期望 FAIL（`paths` 不存在）
- [ ] **Step 3:** 实现 `src/paths.py`

```python
from __future__ import annotations

import sys
from pathlib import Path


def ui_index() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "ui" / "index.html"
    return Path(__file__).resolve().parent.parent / "ui" / "index.html"
```

`app.py`：`from paths import ui_index`，`UI = ui_index()`。

- [ ] **Step 4:** 再跑 `tests.test_paths` 期望 PASS；全量 `tests` 仍 PASS
- [ ] **Step 5:** 提交「打包后也能找到界面网页文件。」

---

### Task 2: 缺 WebView2 时中文提示

**Files:**
- Modify: `src/paths.py`
- Modify: `src/app.py`（`main` 开头检测）
- Modify: `tests/test_paths.py`

**Interfaces:**
- Produces: `WEBVIEW2_HELP: str`；`webview2_installed() -> bool`
- WebView2 Evergreen 客户端 GUID：`{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`

- [ ] **Step 1: 写失败测试**（同一文件追加）

```python
from unittest.mock import patch
from paths import WEBVIEW2_HELP, webview2_installed

def test_help_text(self):
    self.assertIn("Microsoft Edge WebView2", WEBVIEW2_HELP)
    self.assertIn("https://go.microsoft.com/fwlink/p/?LinkId=2124703", WEBVIEW2_HELP)

def test_missing_when_registry_empty(self):
    with patch("winreg.OpenKey", side_effect=OSError):
        self.assertFalse(webview2_installed())
```

（`webview2_installed` 必须 `import winreg` 后再 `OpenKey`，测试 patch `winreg.OpenKey` 或 `paths.winreg.OpenKey`，以后者为准。）

- [ ] **Step 2:** 跑测试期望 FAIL（符号不存在）
- [ ] **Step 3:** `paths.py` 增加：

```python
WEBVIEW2_HELP = (
    "需要先安装 Microsoft Edge WebView2\n\n"
    "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
)
_WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def webview2_installed() -> bool:
    import winreg

    tails = (
        rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_GUID}",
        rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WEBVIEW2_GUID}",
    )
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for tail in tails:
            try:
                with winreg.OpenKey(hive, tail):
                    return True
            except OSError:
                continue
    return False
```

`app.py` 的 `main()` 开头：

```python
from paths import WEBVIEW2_HELP, ui_index, webview2_installed
import ctypes

def main() -> None:
    if not webview2_installed():
        ctypes.windll.user32.MessageBoxW(None, WEBVIEW2_HELP, "存档备份", 0x10)
        return
    ...
```

- [ ] **Step 4:** `tests.test_paths` PASS；全量 tests PASS
- [ ] **Step 5:** 提交「没有网页组件时用中文说明，避免只抛英文错误。」

---

### Task 3: PyInstaller 配置与打包脚本

**Files:**
- Create: `gamebackup.spec`
- Create: `requirements-build.txt`
- Create: `scripts/build.ps1`
- Modify: `.gitignore`（去掉或否定 `*.spec`）
- Modify: `README.md`

- [ ] **Step 1:** `.gitignore` 改为忽略产物、保留 spec：

```
dist/
build/
```

删掉 `*.spec` 这一行（本仓库只提交 `gamebackup.spec`）。

- [ ] **Step 2:** `requirements-build.txt`：

```
pyinstaller>=6.0
```

- [ ] **Step 3:** `gamebackup.spec`（项目根；`onedir`；`console=False`；`datas` 打入 `ui`；`pathex` 含 `src`，因为 `run.py` 是 `from app import main`）：

```python
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[(str(root / "ui"), "ui")],
    hiddenimports=[
        "webview",
        "webview.platforms.edgechromium",
        "pystray._win32",
        "PIL",
        "dulwich",
        "dulwich.porcelain",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gamebackup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="gamebackup",
)
```

- [ ] **Step 4:** `scripts/build.ps1`：

```powershell
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = "C:\Users\Seven\scoop\apps\python\current\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
& $Py -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Py -m PyInstaller --noconfirm --clean gamebackup.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$OutDir = Join-Path $Root "dist\gamebackup"
$Zip = Join-Path $Root "dist\gamebackup-win64.zip"
if (-not (Test-Path (Join-Path $OutDir "gamebackup.exe"))) {
    Write-Error "没有生成 gamebackup.exe"
    exit 1
}
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path $OutDir -DestinationPath $Zip
Write-Host "ok $Zip"
```

脚本里的 Python 路径：若 `python` 在 PATH 上可用就用 `python`，不要把开发机 Scoop 路径写死进仓库。改为：

```powershell
$Py = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $Py) { $Py = "C:\Users\Seven\scoop\apps\python\current\python.exe" }
```

更稳：优先 `py -3.11`，否则 `python`。计划落地时用：

```powershell
$Py = "python"
```

本机执行时若 PATH 的 python 不是 Scoop 3.11，调用方传入或脚本检测。实现时脚本开头：

```powershell
if ($env:GAMEBACKUP_PYTHON) { $Py = $env:GAMEBACKUP_PYTHON }
elseif (Test-Path "C:\Users\Seven\scoop\apps\python\current\python.exe") {
    $Py = "C:\Users\Seven\scoop\apps\python\current\python.exe"
} else { $Py = "python" }
```

（给朋友的是 zip 不是脚本；脚本只给本仓库打包用，写 Scoop 回退可以。）

- [ ] **Step 5:** README 开发段落后加：

```text
打包绿色 zip（Windows）：

powershell -File scripts/build.ps1
```

产物在 `dist/gamebackup-win64.zip`。

- [ ] **Step 6:** 提交「加上 PyInstaller 绿色包脚本，解压即可双击运行。」

---

### Task 4: 打出 zip 并核对

**Files:** 无新源码（跑脚本）

- [ ] **Step 1:** 停掉正在跑的 `run.py`（避免文件占用）
- [ ] **Step 2:** `powershell -File scripts/build.ps1`（需较长时间；`block_until_ms` 足够大）
- [ ] **Step 3:** 确认存在：
  - `dist/gamebackup/gamebackup.exe`
  - `dist/gamebackup/_internal/ui/index.html`
  - `dist/gamebackup-win64.zip`
- [ ] **Step 4:** 解压 zip 到临时目录，确认顶层是 `gamebackup/gamebackup.exe`
- [ ] **Step 5:** 手工启动一次 `dist/gamebackup/gamebackup.exe`，确认窗口和托盘出现（然后退出）。不要把 `dist/` 提交进 git。
