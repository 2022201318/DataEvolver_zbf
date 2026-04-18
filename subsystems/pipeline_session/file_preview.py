"""读取仓库内相对路径文件的前若干行/字符，供预览 API 使用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def preview_repo_file(
    root: Path,
    rel_path: str,
    *,
    max_lines: int = 80,
    max_chars: int = 96_000,
) -> dict[str, Any]:
    """
    安全读取 `root / rel_path`（禁止路径跳出 root）。
    返回 lines、截断标记与字符计数。
    """
    rel = rel_path.replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    root_res = root.resolve()
    if not str(target).startswith(str(root_res)) or not target.is_file():
        return {
            "ok": False,
            "error": "file_not_found_or_invalid",
            "path": rel_path,
            "lines": [],
            "truncated_lines": False,
            "truncated_chars": False,
            "char_count": 0,
            "has_more_lines": None,
        }

    lines_out: list[str] = []
    total_chars = 0
    truncated_chars = False

    with open(target, encoding="utf-8", errors="replace") as f:
        for _ in range(max_lines):
            line = f.readline()
            if line == "":
                break
            if total_chars + len(line) > max_chars:
                cut = max_chars - total_chars
                if cut > 0:
                    lines_out.append(line[:cut].rstrip("\n\r"))
                truncated_chars = True
                break
            total_chars += len(line)
            lines_out.append(line.rstrip("\n\r"))

        truncated_lines = False
        if not truncated_chars:
            nxt = f.readline()
            if nxt != "":
                truncated_lines = True

    return {
        "ok": True,
        "error": None,
        "path": rel,
        "lines": lines_out,
        "truncated_lines": truncated_lines,
        "truncated_chars": truncated_chars,
        "char_count": sum(len(s) for s in lines_out),
        "has_more_lines": truncated_lines or None,
    }
