"""Behavior tests for probing cited source links for rot (O17)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from election_guide.sources import link_check
from election_guide.sources.link_check import (
    LinkCheckResult,
    LinkCheckTarget,
    check_link,
    link_check_targets,
    run_link_check,
)
from election_guide.sources.models import SourceRegistry
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parent.parent
REGISTRY_PATH = PROJECT_ROOT / "config" / "sources" / "default.yaml"


# --- link_check_targets -----------------------------------------------------


def test_link_check_targets_cover_every_source_with_a_citable_url() -> None:
    registry = read_source_registry(REGISTRY_PATH)

    targets = link_check_targets(registry)

    citable = [source for source in registry.sources if source.discovery.canonical_url is not None]
    assert len(targets) == len(citable)
    assert {target.source_id for target in targets} == {source.id for source in citable}


def test_link_check_targets_skip_a_restricted_source_with_no_canonical_url() -> None:
    registry = read_source_registry(REGISTRY_PATH)
    restricted = next(
        source for source in registry.sources if source.discovery.status == "access_restricted"
    )
    assert restricted.discovery.canonical_url is None  # the registry itself confirms this setup

    targets = link_check_targets(registry)

    assert restricted.id not in {target.source_id for target in targets}


def test_link_check_targets_are_sorted_by_source_id() -> None:
    registry = read_source_registry(REGISTRY_PATH)

    targets = link_check_targets(registry)

    assert [target.source_id for target in targets] == sorted(
        target.source_id for target in targets
    )


# --- check_link --------------------------------------------------------------


def test_check_link_reports_success_when_fetch_http_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _succeed(url: str, *, timeout_seconds: float) -> object:
        return object()

    monkeypatch.setattr(link_check, "fetch_http", _succeed)

    ok, error = check_link("https://example.org", timeout_seconds=5)

    assert ok is True
    assert error is None


def test_check_link_reports_the_collection_failure_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(url: str, *, timeout_seconds: float) -> object:
        raise ValueError("live collection returned HTTP 404")

    monkeypatch.setattr(link_check, "fetch_http", _raise)

    ok, error = check_link("https://example.org", timeout_seconds=5)

    assert ok is False
    assert error == "live collection returned HTTP 404"


# --- run_link_check ------------------------------------------------------


def _target(source_id: str, url: str) -> LinkCheckTarget:
    return LinkCheckTarget(source_id=source_id, source_name=source_id, url=url)


def _dummy_registry() -> SourceRegistry:
    """`link_check_targets` is monkeypatched in these tests, so the registry is never
    actually read; a `cast` placeholder keeps the call sites honestly typed."""
    return cast(SourceRegistry, object())


def _stub_targets(monkeypatch: pytest.MonkeyPatch, targets: list[LinkCheckTarget]) -> None:
    def _targets(registry: SourceRegistry) -> list[LinkCheckTarget]:
        return targets

    monkeypatch.setattr(link_check, "link_check_targets", _targets)


def _stub_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def _check(url: str, *, timeout_seconds: float) -> tuple[bool, str | None]:
        return True, None

    monkeypatch.setattr(link_check, "check_link", _check)


def test_run_link_check_checks_every_target_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [_target("a", "https://a.example"), _target("b", "https://b.example")]
    _stub_targets(monkeypatch, targets)

    def _check(url: str, *, timeout_seconds: float) -> tuple[bool, str | None]:
        return (True, None) if url == "https://a.example" else (False, "boom")

    monkeypatch.setattr(link_check, "check_link", _check)

    results = run_link_check(_dummy_registry(), timeout_seconds=1, delay_seconds=0)

    assert [result.target.source_id for result in results] == ["a", "b"]
    assert results[0] == LinkCheckResult(target=targets[0], ok=True, error=None)
    assert results[1] == LinkCheckResult(target=targets[1], ok=False, error="boom")


def test_run_link_check_pauses_between_requests_but_not_before_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets = [_target(letter, f"https://{letter}.example") for letter in "abc"]
    _stub_targets(monkeypatch, targets)
    _stub_all_ok(monkeypatch)
    sleeps: list[float] = []

    run_link_check(_dummy_registry(), timeout_seconds=1, delay_seconds=2.5, sleep=sleeps.append)

    assert sleeps == [2.5, 2.5]


def test_run_link_check_skips_the_pause_when_delay_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    targets = [_target("a", "https://a.example"), _target("b", "https://b.example")]
    _stub_targets(monkeypatch, targets)
    _stub_all_ok(monkeypatch)
    sleeps: list[float] = []

    run_link_check(_dummy_registry(), timeout_seconds=1, delay_seconds=0, sleep=sleeps.append)

    assert sleeps == []
