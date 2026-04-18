#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
子进程入口：加载 `operator_stub.py`，按 JSONL 文件执行 `run(records, context)`。

用法（由调度器调用，勿手改）：
  python subprocess_bridge.py <operator_stub.py> <input.jsonl> <output.jsonl> <repo_root>

与旧版 DataEvolver「每步独立子进程 + stdin/stdout JSONL」对齐；大数据用临时文件避免管道阻塞。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                records.append(obj)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) < 4:
        print(
            "Usage: subprocess_bridge.py <stub.py> <in.jsonl> <out.jsonl> <repo_root>",
            file=sys.stderr,
        )
        return 2
    stub_path = Path(argv[0]).resolve()
    in_path = Path(argv[1]).resolve()
    out_path = Path(argv[2]).resolve()
    root = Path(argv[3]).resolve()

    if not stub_path.is_file():
        print(f"stub not found: {stub_path}", file=sys.stderr)
        return 1
    if not str(stub_path).startswith(str(root)):
        print("stub path escapes repo root", file=sys.stderr)
        return 1
    if not in_path.is_file():
        print(f"input not found: {in_path}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(root))

    name = f"_bridge_stub_{stub_path.stem}"
    spec = importlib.util.spec_from_file_location(name, stub_path)
    if spec is None or spec.loader is None:
        print("cannot load spec", file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_fn = getattr(mod, "run", None)
    if not callable(run_fn):
        print("stub has no run()", file=sys.stderr)
        return 1

    records = _load_jsonl(in_path)
    ctx: dict[str, Any] = {"root": str(root), "subprocess": True}
    step_dir = stub_path.parent
    prev_cwd = os.getcwd()
    try:
        os.chdir(step_dir)
        out = run_fn(records, ctx)
    finally:
        try:
            os.chdir(prev_cwd)
        except OSError:
            pass
    if out is None:
        out = []
    if not isinstance(out, list):
        print(f"run() must return list, got {type(out)}", file=sys.stderr)
        return 1
    for j, item in enumerate(out):
        if item is not None and not isinstance(item, dict):
            print(f"records[{j}] must be dict", file=sys.stderr)
            return 1
    _write_jsonl(out_path, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
