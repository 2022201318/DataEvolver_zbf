"""工作流单步执行时在 stderr 显示动态等待行（旋转 + 已用时间），非 TTY 自动降级。"""

from __future__ import annotations

import os
import sys
import threading
import time


def progress_line_enabled() -> bool:
    if os.environ.get("DATAEVOLVER_NO_PROGRESS", "").strip().lower() in ("1", "true", "yes"):
        return False
    return sys.stderr.isatty()


class step_running_display:
    """在 `advance_workflow` 等长任务期间更新一行进度（stderr）。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self._stop = threading.Event()
        self._t0 = 0.0
        self._thread: threading.Thread | None = None

    def __enter__(self) -> step_running_display:
        self._t0 = time.monotonic()
        if not progress_line_enabled():
            return self
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self) -> None:
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while not self._stop.wait(0.1):
            elapsed = time.monotonic() - self._t0
            if elapsed < 60.0:
                tim = f"{elapsed:.1f}s"
            else:
                m, s = int(elapsed // 60), int(elapsed % 60)
                tim = f"{m}m{s:02d}s"
            msg = f"\r\033[K{frames[i % len(frames)]} {self.label}  ·  {tim}"
            try:
                sys.stderr.write(msg)
                sys.stderr.flush()
            except OSError:
                break
            i += 1

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if progress_line_enabled():
            try:
                sys.stderr.write("\r\033[K")
                sys.stderr.flush()
            except OSError:
                pass
        return False

    def elapsed_sec(self) -> float:
        return max(0.0, time.monotonic() - self._t0)
