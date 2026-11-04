"""Bounded Linux facts for a Chrome startup failure, never an environment dump."""

from __future__ import annotations

import sys
from itertools import islice
from pathlib import Path


def _read_limited(path: Path, limit: int = 4096) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("proc field exceeds diagnostic bound")
    return data.decode("ascii")


def _status(path: Path) -> dict[str, str]:
    try:
        text = _read_limited(path)
    except (OSError, ValueError, UnicodeError):
        return {}
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        parts = value.split()
        if not parts:
            continue
        token = parts[0]
        if key == "State" and len(token) == 1 and token.isalpha() and token.isascii():
            fields[key] = token
        elif (
            key in {"Pid", "Tgid", "PPid", "Threads", "VmRSS", "FDSize"}
            and len(token) <= 16
            and token.isascii()
            and token.isdecimal()
            and (key != "VmRSS" or parts[1:] == ["kB"])
        ):
            fields[key] = str(int(token))
    return fields


def _thread_sample(directory: Path, pid: int) -> str:
    try:
        entries = list(islice((directory / "task").iterdir(), 4))
    except OSError:
        entries = []
    tids = [pid]
    tids.extend(sorted(int(p.name) for p in entries if p.name.isdecimal() and p.name != str(pid)))
    rows: list[str] = []
    for tid in tids[:3]:
        thread = directory / "task" / str(tid)
        status = _status(thread / "status")
        if status.get("Pid") != str(tid) or status.get("Tgid") != str(pid):
            continue
        try:
            wait = _read_limited(thread / "wchan", 128).strip()
            if not wait or not wait.isascii() or not all(c.isalnum() or c == "_" for c in wait):
                wait = "unavailable"
        except (OSError, ValueError, UnicodeError):
            wait = "unavailable"
        rows.append(f"tid={tid}:{status.get('State', '?')}:{wait[:32]}")
    return "|".join(rows) or "unavailable"


def linux_startup_process_facts(pid: int, root: Path) -> str:
    """Sample at most three related processes and three threads each before cleanup."""
    if sys.platform != "linux":
        return "not-linux"
    queue: list[tuple[int, int | None]] = [(pid, None)]
    seen: set[int] = set()
    rows: list[str] = []
    while queue and len(rows) < 3:
        current, parent = queue.pop(0)
        if current <= 0 or current in seen:
            continue
        seen.add(current)
        directory = root / str(current)
        status = _status(directory / "status")
        if status.get("Pid") != str(current) or (
            parent is not None and status.get("PPid") != str(parent)
        ):
            rows.append(f"pid={current}:unavailable")
            continue
        rows.append(
            f"pid={current} state={status.get('State', '?')} ppid={status.get('PPid', '?')} "
            f"threads={status.get('Threads', '?')} rss_kb={status.get('VmRSS', '?')} "
            f"fd_slots={status.get('FDSize', '?')} waits=[{_thread_sample(directory, current)}]"
        )
        try:
            children = _read_limited(directory / "task" / str(current) / "children", 512)
        except (OSError, ValueError, UnicodeError):
            continue
        remaining = 3 - len(rows) - len(queue)
        child_ids = [int(s) for s in children.split() if s.isdecimal() and len(s) <= 10]
        queue.extend((child, current) for child in child_ids[: max(0, remaining)])
    result = "sample=[" + "; ".join(rows) + "]"
    return result if len(result) <= 650 else result[:634] + " truncated=true"
