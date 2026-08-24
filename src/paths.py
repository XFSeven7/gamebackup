"""开发态和打包后的资源路径。"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

WEBVIEW2_HELP = (
    "需要先安装 Microsoft Edge WebView2\n\n"
    "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
)
_WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def ui_index() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "ui" / "index.html"
    return Path(__file__).resolve().parent.parent / "ui" / "index.html"


def webview2_installed() -> bool:
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
