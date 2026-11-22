"""后台按间隔给每个已管理文件夹做备份。"""

from __future__ import annotations

import threading
from pathlib import Path

from backup import backup_once
from config import DEFAULT_INTERVAL_SEC, load


class Scheduler:
    def __init__(self, root: Path, on_tick=None):
        self.root = Path(root)
        self.on_tick = on_tick
        self._timer: threading.Timer | None = None
        self._pause_all = False
        self._stopped = False
        self._lock = threading.Lock()
        self.data_lock = threading.RLock()
        self.generation = 0

    def start(self) -> None:
        with self._lock:
            self._stopped = False
        self._arm(0.5)

    def stop(self) -> None:
        with self.data_lock, self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def set_pause_all(self, paused: bool) -> None:
        self._pause_all = paused

    def _arm(self, delay: float) -> None:
        with self._lock:
            if self._stopped:
                return
            self._timer = threading.Timer(delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self) -> None:
        with self.data_lock:
            if self._stopped:
                return
            try:
                if not self._pause_all:
                    cfg = load(self.root)
                    bumped = False
                    for item in cfg.items:
                        r = backup_once(self.root, item, events_only=True)
                        if not r.get("skipped"):
                            bumped = True
                    if bumped:
                        self.generation += 1
                    if self.on_tick:
                        self.on_tick()
                interval = max(10, load(self.root).interval_sec)
            except Exception:
                interval = DEFAULT_INTERVAL_SEC
            self._arm(interval)
