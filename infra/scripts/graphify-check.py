#!/usr/bin/env python3
"""Tell a new session whether graphify's code map needs a refresh."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

OUT = Path("graphify-out")
GRAPH = OUT / "graph.json"
FLAG = OUT / "needs_update"
CODE_SUFFIXES = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".html",
    ".sql", ".toml", ".yaml", ".yml", ".json", ".sh",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> int:
    if not GRAPH.exists():
        print("[graph-check] graphify-out/graph.json is missing; run `make graph`.")
        return 0
    data = json.loads(GRAPH.read_text())
    built = data.get("built_at_commit")
    try:
        head = git("rev-parse", "HEAD")
        status = git("status", "--porcelain")
    except (OSError, subprocess.CalledProcessError):
        head, status = None, ""
    dirty_code = []
    dirty_docs = []
    for line in status.splitlines():
        path = line[3:].strip().strip('"')
        (dirty_code if Path(path).suffix.lower() in CODE_SUFFIXES else dirty_docs).append(path)
    if built and head and built != head:
        print(f"[graph-check] graph was built at {built[:12]}, current HEAD is {head[:12]}.")
    if dirty_code:
        print(f"[graph-check] {len(dirty_code)} uncommitted code/config file(s) changed; run `make graph`.")
    if FLAG.exists() or dirty_docs:
        print("[graph-check] documentation/non-code changes need semantic re-extraction; run `graphify extract .` when requested.")
    if not (built and head and built != head) and not dirty_code and not FLAG.exists() and not dirty_docs:
        print("[graph-check] graph is current for the checked-in code and working tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
