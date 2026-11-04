"""A failed Chrome startup keeps its error and bounded, non-secret Linux facts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import IO, Any, cast

import pytest

from election_guide.rendering import browser
from election_guide.rendering.browser import (
    _wait_for_devtools_endpoint,  # pyright: ignore[reportPrivateUsage]
)


class PendingChrome:
    pid = 321

    def poll(self) -> None:
        return None


def write_process(root: Path, pid: int, parent: int, *, rss: int = 2048) -> Path:
    directory = root / str(pid)
    directory.mkdir(parents=True)
    (directory / "status").write_text(
        "Name:\tstatus-secret-sentinel\n"
        f"Pid:\t{pid}\nTgid:\t{pid}\nPPid:\t{parent}\n"
        f"State:\tS (sleeping)\nThreads:\t3\nVmRSS:\t{rss} kB\nFDSize:\t64\n"
    )
    (directory / "environ").write_text("TOKEN=environment-secret-sentinel")
    (directory / "cmdline").write_text("command-secret-sentinel")
    thread = directory / "task" / str(pid)
    thread.mkdir(parents=True)
    (thread / "status").write_text(f"Pid:\t{pid}\nTgid:\t{pid}\nState:\tS (sleeping)\n")
    (thread / "wchan").write_text("futex_wait_queue\n")
    (thread / "children").write_text("")
    return directory


def failure_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, platform: str = "linux"
) -> str:
    moments = iter([0.0, 16.0])
    monkeypatch.setattr(browser.time, "monotonic", lambda: next(moments, 16.0))
    monkeypatch.setattr(browser.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(browser.os, "getloadavg", lambda: (1.0, 0.5, 0.25))
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=bus-secret-sentinel")
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(browser, "_STARTUP_PROC_ROOT", tmp_path / "proc", raising=False)
    process = cast(subprocess.Popen[bytes], PendingChrome())
    with pytest.raises(TimeoutError) as raised:
        _wait_for_devtools_endpoint(process, tmp_path / "profile", launched_at=0.0)
    assert str(raised.value) == "Chrome did not expose its DevTools endpoint"
    (note,) = raised.value.__notes__
    assert "process=running" in note and "endpoint=missing" in note
    assert len(note.encode()) <= 1024
    assert "secret-sentinel" not in note
    return note


def test_startup_timeout_reports_linux_wait_and_child_resource_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proc"
    parent = write_process(root, 321, 8)
    write_process(root, 322, 321, rss=512)
    (parent / "task/321/children").write_text("322\n")
    note = failure_note(tmp_path, monkeypatch)
    assert "pid=321" in note and "state=S" in note
    assert "ppid=8" in note and "rss_kb=2048" in note and "fd_slots=64" in note
    assert "tid=321:S:futex_wait_queue" in note
    assert "pid=322" in note and "ppid=321" in note and "rss_kb=512" in note


def test_non_linux_startup_does_not_read_proc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proc"
    write_process(root, 321, 8)
    original_open = Path.open

    def forbidden_proc_read(path: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        if path.is_relative_to(root):
            pytest.fail("non-Linux startup must not inspect proc")
        return cast(IO[Any], original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", forbidden_proc_read)
    note = failure_note(tmp_path, monkeypatch, platform="darwin")
    assert "linux=not-linux" in note


def test_missing_linux_process_keeps_timeout_and_existing_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = failure_note(tmp_path, monkeypatch)
    assert "linux=" in note and "pid=321:unavailable" in note
    assert "cpu_count=4" in note and "load=1.00,0.50,0.25" in note


def test_linux_process_sample_never_follows_a_reparented_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proc"
    parent = write_process(root, 321, 8)
    write_process(root, 322, 999, rss=98765)
    (parent / "task/321/children").write_text("322\n")
    note = failure_note(tmp_path, monkeypatch)
    assert "pid=322:unavailable" in note
    assert "rss_kb=98765" not in note and "ppid=999" not in note


def test_linux_process_and_thread_sampling_has_a_small_output_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proc"
    parent = write_process(root, 321, 8)
    for child in range(322, 342):
        write_process(root, child, 321)
    (parent / "task/321/children").write_text(" ".join(str(i) for i in range(322, 342)))
    for tid in range(400, 420):
        thread = parent / "task" / str(tid)
        thread.mkdir()
        (thread / "status").write_text(f"Pid:\t{tid}\nTgid:\t321\nState:\tS (sleeping)\n")
        (thread / "wchan").write_text("wait_channel_" + "x" * 200)
    original_open = Path.open
    status_reads: list[Path] = []

    def bounded_reads(path: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        if path.is_relative_to(root):
            assert path.name in {"status", "wchan", "children"}
            if path.name == "status":
                status_reads.append(path)
        return cast(IO[Any], original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", bounded_reads)
    note = failure_note(tmp_path, monkeypatch)
    assert "pid=321" in note
    assert 1 <= len(re.findall(r"\bpid=\d+", note)) <= 3
    assert note.count("tid=") <= 9
    assert "sample" in note
    assert len(status_reads) <= 12
    assert len({path.relative_to(root).parts[0] for path in status_reads}) <= 3


def test_unreadable_linux_status_never_masks_the_startup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proc"
    write_process(root, 321, 8)
    original_open = Path.open

    def unreadable(path: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        if path == root / "321/status":
            raise PermissionError("read-secret-sentinel")
        return cast(IO[Any], original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", unreadable)
    note = failure_note(tmp_path, monkeypatch)
    assert "pid=321:unavailable" in note
