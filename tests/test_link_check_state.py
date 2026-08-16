"""Behavior tests for persisting the previous run's failing-URL set (O17)."""

from __future__ import annotations

from pathlib import Path

from election_guide.sources.link_check_state import (
    EMPTY_STATE,
    LinkCheckState,
    read_link_check_state,
    write_link_check_state,
)


def test_reading_a_missing_state_file_returns_empty(tmp_path: Path) -> None:
    assert read_link_check_state(tmp_path / "missing.json") == EMPTY_STATE


def test_reading_a_corrupt_state_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")

    assert read_link_check_state(path) == EMPTY_STATE


def test_reading_a_state_file_with_an_unexpected_shape_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"unexpected_field": true}', encoding="utf-8")

    assert read_link_check_state(path) == EMPTY_STATE


def test_writing_then_reading_round_trips_the_failing_urls(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    state = LinkCheckState(failing_urls=("https://a.example", "https://b.example"))

    write_link_check_state(path, state)

    assert read_link_check_state(path) == state


def test_writing_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "deeply" / "nested" / "state.json"

    write_link_check_state(path, LinkCheckState())

    assert path.exists()
