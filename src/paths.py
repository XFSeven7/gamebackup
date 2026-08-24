"""开发态和打包后的资源路径。"""

from __future__ import annotations

import sys
from pathlib import Path


def ui_index() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "ui" / "index.html"
    return Path(__file__).resolve().parent.parent / "ui" / "index.html"
