"""Behavior tests for archiving zone analytics before Cloudflare drops them.

Driven through the CLI, because the command is the surface the scheduled
workflow and the operator both use; asserting against the internals would pass
while the thing anyone actually runs was broken (issue #381).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.analytics import (
    ADAPTIVE_RETENTION_DAYS,
    ARCHIVE_DIR,
    GRAPHQL_ENDPOINT,
    RETENTION_DAYS,
    SOURCE_ADAPTIVE,
    SOURCE_DAILY,
    CloudflareZone,
    DailyRollup,
    archived_dates,
    missing_dates,
    write_rollup,
)
from election_guide.analytics.cloudflare import ADAPTIVE_QUERY, DAILY_QUERY
from election_guide.cli import app

PROJECT_ROOT = Path(__file__).parents[1]

# A dotted quad, and the `Mozilla/5.0 (...)` opening every real user-agent
# string carries. Shapes rather than exact values: the point is that nothing
# resembling one reaches a committed file, not that some specific address is
# absent.
#
# Applied to every grouping except `by_path`, which is exempt on purpose.
# `by_path` records the URL a requester asked for, and this zone is under
# continuous hostile scanning — 271 of the 640 paths archived so far are probes
# like `/.aws/credentials`. A bot requesting `/10.0.0.1/admin` would trip an
# address-shaped pattern while revealing nothing about any visitor, so scanning
# it can only produce false positives. What criterion 3 actually forbids is a
# *visitor's* address, agent, or browser, and that is excluded structurally:
# those dimensions are never requested and `extra="forbid"` rejects a field
# that could hold one. ARCHIVE_FIELDS below is that guarantee's real test.
IP_ADDRESS = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
USER_AGENT = re.compile(r"Mozilla/\d|AppleWebKit|Gecko/|Chrome/\d|Safari/\d")
REQUESTER_CHOSEN = ("by_path",)

# Exactly what an archived day may carry. Browser, OS, and user-agent
# groupings are excluded structurally rather than by scanning text for browser
# names: there is no such grouping to hold one, which is a stronger guarantee
# than a word list, and a word list would trip over `by_edge_status_code`
# anyway — Cloudflare's edge, not Microsoft's browser.
ARCHIVE_FIELDS = frozenset(
    {
        "schema_version",
        "date",
        "sources",
        "requests",
        "page_views",
        "uniques",
        "visits",
        "by_path",
        "by_country",
        "by_device_type",
        "by_edge_status_code",
    }
)
FORBIDDEN_FIELDS = ("by_client_ip", "by_user_agent", "by_browser")


def _gaps(days: Sequence[date]) -> list[tuple[date, date]]:
    """Every place a run of days skips one. The archive's whole job is having none."""
    return [(earlier, later) for earlier, later in pairwise(days) if (later - earlier).days != 1]


def _vetted_strings(document: dict[str, Any]) -> Iterator[str]:
    """Every string in an archived day except the requester-chosen groupings."""
    return _strings({k: v for k, v in document.items() if k not in REQUESTER_CHOSEN})


def _strings(value: Any) -> Iterator[str]:
    """Every string anywhere in a decoded archive document, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in cast(dict[str, Any], value).items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in cast(list[Any], value):
            yield from _strings(item)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's real token leak into a test run.

    Every test here either stubs the transport or is asserting the
    missing-credential path, so a token present in the ambient environment can
    only make a test pass for the wrong reason — or, worse, spend a real
    request against the live zone.
    """
    monkeypatch.delenv("CLOUDFLARE_ANALYTICS_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)


def _rollup(day: date, *, requests: int = 100, enriched: bool = True) -> DailyRollup:
    """One day of plausible aggregates, in the shape the archive stores.

    `enriched` is the difference between a day the eight-day adaptive dataset
    still covered and an older one the thirty-day daily dataset alone answered.
    """
    detail: dict[str, Any] = (
        {
            "visits": 10,
            "by_path": [
                {"key": "/", "requests": requests - 40},
                {"key": "/about/", "requests": 40},
            ],
            "by_device_type": [{"key": "desktop", "requests": requests}],
        }
        if enriched
        else {}
    )
    return DailyRollup.model_validate(
        {
            "date": day.isoformat(),
            "sources": [SOURCE_DAILY, SOURCE_ADAPTIVE] if enriched else [SOURCE_DAILY],
            "requests": requests,
            "page_views": requests // 2,
            "uniques": requests // 4,
            "by_country": [{"key": "US", "requests": requests}],
            "by_edge_status_code": [{"key": 200, "requests": requests}],
            **detail,
        }
    )


def _available(
    today: date, offsets: Iterable[int], *, enriched: bool = True
) -> dict[date, DailyRollup]:
    """The days Cloudflare can still answer, named by how far back each one is."""
    days = [today - timedelta(days=offset) for offset in offsets]
    return {day: _rollup(day, enriched=enriched) for day in days}


class StubZone:
    """A Cloudflare zone that answers from a fixture instead of the network."""

    def __init__(self, available: Mapping[date, DailyRollup]) -> None:
        self.available = available
        self.queried: list[date] = []

    def archive_day(self, day: date, *, as_of: date) -> DailyRollup | None:
        self.queried.append(day)
        return self.available.get(day)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the archive at a scratch directory and stay out of the repo."""
    destination = tmp_path / "analytics"
    monkeypatch.chdir(tmp_path)
    yield destination


def _install(monkeypatch: pytest.MonkeyPatch, zone: StubZone) -> None:
    """Replace the live transport, leaving every other code path real."""
    monkeypatch.setenv("CLOUDFLARE_ANALYTICS_TOKEN", "test-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "test-zone")
    monkeypatch.setattr("election_guide.cli.open_analytics_zone", lambda: zone)


def test_export_writes_one_named_day(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A named UTC date becomes exactly one file carrying that day's rollups."""
    day = date(2026, 8, 4)
    _install(monkeypatch, StubZone({day: _rollup(day, requests=5400)}))

    result = runner.invoke(
        app, ["analytics", "export", "--date", "2026-08-04", "--archive-dir", str(archive)]
    )

    assert result.exit_code == 0, result.output
    written = sorted(archive.glob("*.json"))
    assert [path.name for path in written] == ["2026-08-04.json"]
    document = json.loads(written[0].read_text(encoding="utf-8"))
    assert document["date"] == "2026-08-04"
    assert document["requests"] == 5400
    assert document["sources"] == [SOURCE_DAILY, SOURCE_ADAPTIVE]
    assert {entry["key"] for entry in document["by_path"]} == {"/", "/about/"}
    assert [entry["key"] for entry in document["by_country"]] == ["US"]
    assert [entry["key"] for entry in document["by_device_type"]] == ["desktop"]
    assert [entry["key"] for entry in document["by_edge_status_code"]] == [200]


def test_reexport_leaves_the_file_byte_identical(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second export of an archived day rewrites nothing and re-queries nothing.

    Byte-identity holds because an archived day is never fetched again, not
    because Cloudflare is assumed to return stable aggregates forever.
    """
    day = date(2026, 8, 4)
    zone = StubZone({day: _rollup(day)})
    _install(monkeypatch, zone)
    arguments = ["analytics", "export", "--date", "2026-08-04", "--archive-dir", str(archive)]

    assert runner.invoke(app, arguments).exit_code == 0
    first = (archive / "2026-08-04.json").read_bytes()
    assert zone.queried == [day]

    assert runner.invoke(app, arguments).exit_code == 0
    assert (archive / "2026-08-04.json").read_bytes() == first
    assert zone.queried == [day], "an archived day must not be queried again"


def test_backfill_covers_the_window_without_gaps(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every in-window day through yesterday is archived; today never is.

    Today is excluded because a day still in progress would archive a partial
    count and then never be revisited.
    """
    today = date(2026, 8, 16)
    zone = StubZone(_available(today, range(0, RETENTION_DAYS + 1)))
    _install(monkeypatch, zone)

    result = runner.invoke(
        app,
        ["analytics", "export", "--as-of", today.isoformat(), "--archive-dir", str(archive)],
    )

    assert result.exit_code == 0, result.output
    written = sorted(path.stem for path in archive.glob("*.json"))
    expected = [
        (today - timedelta(days=offset)).isoformat() for offset in range(RETENTION_DAYS, 0, -1)
    ]
    assert written == expected
    assert today.isoformat() not in written
    assert _gaps([date.fromisoformat(stem) for stem in written]) == []


def test_backfill_resumes_over_an_existing_archive(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run fills only the days it is missing, which is what makes the schedule safe."""
    today = date(2026, 8, 16)
    zone = StubZone(_available(today, range(1, RETENTION_DAYS + 1)))
    _install(monkeypatch, zone)
    arguments = [
        "analytics",
        "export",
        "--as-of",
        today.isoformat(),
        "--archive-dir",
        str(archive),
    ]

    assert runner.invoke(app, arguments).exit_code == 0
    first_pass = list(zone.queried)
    assert len(first_pass) == RETENTION_DAYS

    (archive / "2026-08-15.json").unlink()
    zone.queried.clear()
    assert runner.invoke(app, arguments).exit_code == 0

    assert zone.queried == [date(2026, 8, 15)]


def test_a_day_with_no_traffic_is_archived_as_zero_not_left_as_a_gap(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interior empty day is a fact about the site; a gap would be a fact about us.

    Cloudflare answers identically for a day past the retention window and a
    day nobody visited. Anything older having data is what tells the two
    apart — so this day is inside the window, and its zero is real.
    """
    today = date(2026, 8, 16)
    quiet = date(2026, 8, 10)
    available = _available(today, range(1, RETENTION_DAYS + 1))
    del available[quiet]
    _install(monkeypatch, StubZone(available))

    result = runner.invoke(
        app,
        ["analytics", "export", "--as-of", today.isoformat(), "--archive-dir", str(archive)],
    )

    assert result.exit_code == 0, result.output
    document = json.loads((archive / f"{quiet.isoformat()}.json").read_text(encoding="utf-8"))
    assert document["requests"] == 0
    assert document["page_views"] == 0
    assert document["by_country"] == []
    # Zero for what the daily dataset measured, `null` for what only the
    # adaptive dataset could have measured. A quiet day still answers the first
    # question and still cannot answer the second.
    assert document["visits"] is None
    assert document["by_path"] is None
    assert _gaps(sorted(date.fromisoformat(p.stem) for p in archive.glob("*.json"))) == []


def test_an_aged_out_day_is_skipped_even_when_older_days_are_already_archived(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive's own history must not be mistaken for evidence about the window.

    The discriminator between "aged out" and "no traffic" is whether some older
    day is readable *now*. Seeded from the whole archive instead, it would be
    pinned to the oldest file ever written — and since no candidate is ever
    older than the window floor, every empty answer would read as a real zero
    and this skip could never fire again.
    """
    today = date(2026, 9, 25)
    # A long outage: the archive stops well before the current window opens.
    for offset in range(60, 55, -1):
        stale = today - timedelta(days=offset)
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"{stale.isoformat()}.json").write_text("{}", encoding="utf-8")
    # Cloudflare can still answer only the newest few days of that window.
    available = _available(today, range(1, 4), enriched=False)
    _install(monkeypatch, StubZone(available))

    result = runner.invoke(
        app,
        ["analytics", "export", "--as-of", today.isoformat(), "--archive-dir", str(archive)],
    )

    assert result.exit_code == 0, result.output
    fresh = sorted(
        date.fromisoformat(path.stem)
        for path in archive.glob("*.json")
        if date.fromisoformat(path.stem) >= today - timedelta(days=RETENTION_DAYS)
    )
    assert fresh == sorted(available), (
        "days Cloudflare could no longer answer were archived as zero-traffic days"
    )


def test_days_past_the_window_are_skipped_rather_than_zeroed(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The oldest edge answers empty because it aged out, and must not be recorded as zero.

    `RETENTION_DAYS` is an observation, not a documented guarantee
    (docs/MONITORING.md), so the window's true edge drifts within a day or two
    of it. Writing zeros there would invent traffic history that was simply
    never readable.
    """
    today = date(2026, 8, 16)
    # The three oldest in-window candidates have aged out by the time this runs.
    available = _available(today, range(1, RETENTION_DAYS - 2))
    _install(monkeypatch, StubZone(available))

    result = runner.invoke(
        app,
        ["analytics", "export", "--as-of", today.isoformat(), "--archive-dir", str(archive)],
    )

    assert result.exit_code == 0, result.output
    archived = sorted(date.fromisoformat(path.stem) for path in archive.glob("*.json"))
    assert archived == sorted(available)
    assert _gaps(archived) == []


def test_missing_token_exits_non_zero_and_writes_nothing(runner: CliRunner, archive: Path) -> None:
    """No credential means a loud failure, not an empty archive."""
    result = runner.invoke(
        app, ["analytics", "export", "--date", "2026-08-04", "--archive-dir", str(archive)]
    )

    assert result.exit_code != 0
    assert "CLOUDFLARE_ANALYTICS_TOKEN" in result.output
    assert not archive.exists() or list(archive.glob("*.json")) == []


def test_unauthorized_token_exits_non_zero_and_writes_nothing(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected credential is reported, and no partial file survives it."""

    class Rejecting:
        def archive_day(self, day: date, *, as_of: date) -> DailyRollup | None:
            raise ValueError("Cloudflare rejected the analytics credential (HTTP 403)")

    monkeypatch.setenv("CLOUDFLARE_ANALYTICS_TOKEN", "wrong-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "test-zone")
    monkeypatch.setattr("election_guide.cli.open_analytics_zone", lambda: Rejecting())

    result = runner.invoke(
        app, ["analytics", "export", "--date", "2026-08-04", "--archive-dir", str(archive)]
    )

    assert result.exit_code != 0
    assert "CLOUDFLARE_ANALYTICS_TOKEN" in result.output
    assert not archive.exists() or list(archive.glob("*.json")) == []


def test_excluded_dimensions_never_reach_an_archived_file(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The archive model refuses the three identifying dimensions outright.

    This repository is public, so a committed IP or user-agent string would be
    permanent and unretractable from forks (issue #381, non-goals).
    """
    day = date(2026, 8, 4)
    _install(monkeypatch, StubZone({day: _rollup(day)}))
    runner.invoke(
        app, ["analytics", "export", "--date", "2026-08-04", "--archive-dir", str(archive)]
    )

    document = json.loads((archive / "2026-08-04.json").read_text(encoding="utf-8"))
    assert set(document) == ARCHIVE_FIELDS, "an archived day grew a field nobody vetted"
    for value in _vetted_strings(document):
        assert IP_ADDRESS.search(value) is None, value
        assert USER_AGENT.search(value) is None, value

    for field in FORBIDDEN_FIELDS:
        with pytest.raises(ValueError):
            DailyRollup.model_validate({**_rollup(day).model_dump(mode="json"), field: []})


def test_rewriting_an_archived_day_with_different_bytes_is_refused(tmp_path: Path) -> None:
    """The writer, not the caller, is what makes an archived day immutable.

    `analytics_export` never reaches an archived day, so this guard cannot fire
    on any path the exporter takes — which is exactly why it belongs in the
    writer, where a future second caller cannot forget it.
    """
    day = date(2026, 8, 14)
    write_rollup(tmp_path, _rollup(day, requests=100))
    write_rollup(tmp_path, _rollup(day, requests=100))  # identical bytes: accepted

    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_rollup(tmp_path, _rollup(day, requests=999))


def test_a_probe_shaped_path_is_archived_rather_than_refused(
    runner: CliRunner, archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The URL a scanner asked for is not a visitor's identity, and is stored as-is.

    Screening it instead would be a false positive with real cost: this zone is
    scanned continuously, and a refusal that skipped the day would leave a hole
    that `test_committed_archive_has_no_gaps` then treats as a failure — inside
    the archive workflow's own pre-commit gate, which would stop the archive
    advancing at all. Criterion 3 is met structurally, by never requesting an
    identifying dimension; see ARCHIVE_FIELDS.
    """
    day = date(2026, 8, 14)
    probed = DailyRollup.model_validate(
        {
            **_rollup(day).model_dump(mode="json"),
            "by_path": [{"key": "/10.0.0.1/admin", "requests": 3}],
        }
    )
    _install(monkeypatch, StubZone({day: probed}))

    result = runner.invoke(
        app, ["analytics", "export", "--date", day.isoformat(), "--archive-dir", str(archive)]
    )

    assert result.exit_code == 0, result.output
    document = json.loads((archive / f"{day.isoformat()}.json").read_text(encoding="utf-8"))
    assert [entry["key"] for entry in document["by_path"]] == ["/10.0.0.1/admin"]
    assert set(document) == ARCHIVE_FIELDS, "the structural guarantee is what criterion 3 rests on"


def test_committed_archive_carries_no_identifying_data() -> None:
    """Every file actually committed to this repository, not just a fixture.

    The test above proves the writer cannot emit these; this one proves nothing
    ever did, including anything added by hand or by a future change.
    """
    for path in sorted((PROJECT_ROOT / ARCHIVE_DIR).glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert set(document) == ARCHIVE_FIELDS, path
        for value in _vetted_strings(document):
            assert IP_ADDRESS.search(value) is None, f"{path}: {value}"
            assert USER_AGENT.search(value) is None, f"{path}: {value}"


def test_committed_archive_has_no_gaps() -> None:
    """The archive is a contiguous run of days, which is the whole deliverable."""
    stems = sorted(path.stem for path in (PROJECT_ROOT / ARCHIVE_DIR).glob("*.json"))
    if len(stems) < 2:
        pytest.skip("fewer than two archived days")
    assert _gaps([date.fromisoformat(stem) for stem in stems]) == []


def _canned(by_query: dict[str, dict[str, Any]]) -> Any:
    """Stand in for `urlopen`, answering each query with its own canned body.

    Keyed by a fragment of the GraphQL operation name, because the client sends
    two different queries per day and they must not be answered alike.
    """

    class Response:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *exception: object) -> None:
            return None

    def urlopen(request: Any, timeout: float | None = None) -> Response:
        assert request.get_header("Authorization") == "Bearer secret-token"
        assert request.full_url == GRAPHQL_ENDPOINT
        sent = json.loads(request.data.decode("utf-8"))["query"]
        for marker, payload in by_query.items():
            if marker in sent:
                return Response(payload)
        raise AssertionError(f"no canned answer for query: {sent[:80]}")

    return urlopen


def _zone(payload: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"viewer": {"zones": [payload]}}}


DAILY_ANSWER = _zone(
    {
        "httpRequests1dGroups": [
            {
                "sum": {
                    "requests": 5400,
                    "pageViews": 812,
                    "countryMap": [
                        {"clientCountryName": "US", "requests": 5300},
                        {"clientCountryName": "CA", "requests": 100},
                    ],
                    "responseStatusMap": [
                        {"edgeResponseStatus": 200, "requests": 4000},
                        {"edgeResponseStatus": 404, "requests": 1400},
                    ],
                },
                "uniq": {"uniques": 226},
            }
        ]
    }
)

ADAPTIVE_ANSWER = _zone(
    {
        "total": [{"sum": {"visits": 812}}],
        "byPath": [
            {"count": 110, "dimensions": {"clientRequestPath": "/"}},
            {"count": 60, "dimensions": {"clientRequestPath": "/favicon-32.png"}},
        ],
        "byDeviceType": [{"count": 299, "dimensions": {"clientDeviceType": "desktop"}}],
    }
)


def test_both_datasets_combine_into_one_archived_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """The merge, against the shapes Cloudflare actually returns.

    Every CLI test here stubs above this layer, which would leave the one piece
    that talks to Cloudflare unexercised until it ran for real — and it is two
    differently-shaped datasets, not one.
    """
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _canned({"ZoneDailyTotals": DAILY_ANSWER, "ZoneAdaptiveDetail": ADAPTIVE_ANSWER}),
    )

    zone = CloudflareZone(zone_tag="zone", token="secret-token")
    rollup = zone.archive_day(date(2026, 8, 14), as_of=date(2026, 8, 16))

    assert rollup is not None
    assert rollup.sources == (SOURCE_DAILY, SOURCE_ADAPTIVE)
    assert (rollup.requests, rollup.page_views, rollup.uniques) == (5400, 812, 226)
    assert rollup.visits == 812
    # Heaviest first, so the archived order never depends on Cloudflare's.
    assert [count.key for count in rollup.by_country] == ["US", "CA"]
    assert [count.key for count in rollup.by_edge_status_code] == [200, 404]
    assert rollup.by_path is not None
    assert [count.key for count in rollup.by_path] == ["/", "/favicon-32.png"]
    assert rollup.by_device_type is not None
    assert [count.key for count in rollup.by_device_type] == ["desktop"]


def test_a_day_past_the_adaptive_window_keeps_its_daily_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Beyond eight days the rich dataset refuses, and the day is archived anyway.

    This is the case the whole two-dataset design exists for: the 2026-08-04
    primary is long past the adaptive window, and archiving it with fewer
    groupings is the only way it survives at all.
    """
    refusal = {
        "data": None,
        "errors": [
            {
                "message": 'zone "z" cannot request data older than 1w1d',
                "extensions": {"code": "quota"},
            }
        ],
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _canned({"ZoneDailyTotals": DAILY_ANSWER, "ZoneAdaptiveDetail": refusal}),
    )

    zone = CloudflareZone(zone_tag="zone", token="secret-token")
    # Inside the window by date arithmetic, so the client still asks and must
    # absorb the refusal rather than fail the run.
    rollup = zone.archive_day(date(2026, 8, 9), as_of=date(2026, 8, 16))

    assert rollup is not None
    assert rollup.sources == (SOURCE_DAILY,)
    assert rollup.requests == 5400
    assert rollup.visits is None
    assert rollup.by_path is None, "None, not empty: the question was unanswerable"
    assert rollup.by_device_type is None
    assert [count.key for count in rollup.by_country] == ["US", "CA"]


def test_an_old_day_never_asks_the_adaptive_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backfill reaching back thirty days must not spend a doomed request per day."""
    asked: list[str] = []

    def recording(request: Any, timeout: float | None = None) -> Any:
        asked.append(json.loads(request.data.decode("utf-8"))["query"])
        return _canned({"ZoneDailyTotals": DAILY_ANSWER})(request, timeout)

    monkeypatch.setattr("urllib.request.urlopen", recording)

    zone = CloudflareZone(zone_tag="zone", token="secret-token")
    zone.archive_day(date(2026, 7, 25), as_of=date(2026, 8, 16))

    assert len(asked) == 1
    assert "ZoneAdaptiveDetail" not in asked[0]


def test_a_graphql_error_names_the_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloudflare reports an unauthorized query as HTTP 200 carrying `errors`.

    A run that only checked the status code would read this as a day with no
    traffic and archive a zero — the exact silent failure the archive exists
    to prevent.
    """
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _canned({"ZoneDailyTotals": {"data": None, "errors": [{"message": "auth error"}]}}),
    )

    zone = CloudflareZone(zone_tag="zone", token="secret-token")
    with pytest.raises(ValueError) as failure:
        zone.archive_day(date(2026, 8, 4), as_of=date(2026, 8, 16))

    assert "auth error" in str(failure.value)
    assert "CLOUDFLARE_ANALYTICS_TOKEN" in str(failure.value)


def test_a_day_outside_every_window_reads_as_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Past the daily dataset's retention there are simply no rows, and no error."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _canned({"ZoneDailyTotals": _zone({"httpRequests1dGroups": []})}),
    )

    zone = CloudflareZone(zone_tag="zone", token="secret-token")

    assert zone.archive_day(date(2026, 1, 1), as_of=date(2026, 8, 16)) is None


def test_no_query_asks_for_an_identifying_dimension() -> None:
    """The exclusion is enforced where it is cheapest to verify: the requests themselves.

    Filtering identifying data out after the fact would mean it had already
    crossed the wire and could be reinstated by a one-line slip. Nothing
    downstream needs to filter, because nothing upstream asks. All four
    dimensions below exist in the adaptive dataset and were confirmed live.
    """
    for dimension in ("clientIP", "userAgent", "userAgentBrowser", "userAgentOS", "browserMap"):
        assert dimension not in ADAPTIVE_QUERY, f"the export asks Cloudflare for {dimension}"
        assert dimension not in DAILY_QUERY, f"the export asks Cloudflare for {dimension}"


def test_the_adaptive_window_is_shorter_than_the_archive_window() -> None:
    """The premise of the two-dataset design, kept honest as a constant.

    If these ever became equal, one dataset would do and the merge would be
    dead weight.
    """
    assert ADAPTIVE_RETENTION_DAYS < RETENTION_DAYS


def test_missing_dates_excludes_what_is_archived(tmp_path: Path) -> None:
    """The planning half decides what to fetch; nothing about it touches a network."""
    (tmp_path / "2026-08-14.json").write_text("{}", encoding="utf-8")
    archived = archived_dates(tmp_path)

    assert archived == frozenset({date(2026, 8, 14)})
    planned = missing_dates(as_of=date(2026, 8, 16), archived=archived)

    assert date(2026, 8, 14) not in planned
    assert date(2026, 8, 15) in planned
    assert date(2026, 8, 16) not in planned, "today is still in progress"
    assert min(planned) == date(2026, 7, 17)


def _workflow() -> Any:
    """The archive workflow, loaded the way every other workflow test here loads one.

    `BaseLoader` leaves every scalar a string, which is what the assertions
    below compare against — and it also leaves the `on:` key as `"on"` rather
    than resolving it to the boolean `True`, which is what unquoted `on` means
    to a standard YAML loader.
    """
    path = PROJECT_ROOT / ".github" / "workflows" / "analytics.yml"
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_workflow_runs_on_a_schedule_and_can_commit() -> None:
    """The archive has to advance with nobody watching, so the schedule is the feature."""
    workflow = _workflow()
    triggers = workflow["on"]

    assert triggers["schedule"], "an unscheduled archive cannot outrun the retention window"
    assert all(entry["cron"] for entry in triggers["schedule"])
    assert "workflow_dispatch" in triggers, "a missed day needs a manual catch-up"
    assert workflow["permissions"]["contents"] == "write", "the run commits what it archives"
    assert workflow["concurrency"]["cancel-in-progress"] == "false", (
        "two runs archiving the same day would race on one commit"
    )


def test_workflow_passes_the_credential_by_secret() -> None:
    """Both credentials reach the run through the environment, never through interpolation.

    A token interpolated into the `run:` script itself would be expanded by the
    runner before the shell ever saw it, which is how a secret ends up in a
    build log.
    """
    steps = [step for job in _workflow()["jobs"].values() for step in job["steps"]]
    environments = [step.get("env", {}) for step in steps]

    assert [
        env["CLOUDFLARE_ANALYTICS_TOKEN"]
        for env in environments
        if "CLOUDFLARE_ANALYTICS_TOKEN" in env
    ] == ["${{ secrets.CLOUDFLARE_ANALYTICS_TOKEN }}"]
    assert [env["CLOUDFLARE_ZONE_ID"] for env in environments if "CLOUDFLARE_ZONE_ID" in env] == [
        "${{ secrets.CLOUDFLARE_ZONE_ID }}"
    ]
    for step in steps:
        assert "secrets." not in step.get("run", ""), (
            f"{step.get('name')!r} interpolates a secret into its script"
        )


def _commit_step_script() -> str:
    """The committed shell the workflow actually runs to commit an archived day."""
    steps = [step for job in _workflow()["jobs"].values() for step in job["steps"]]
    script = next(step["run"] for step in steps if "git commit" in step.get("run", ""))
    assert isinstance(script, str)
    return script


def _archive_repository(tmp_path: Path) -> Path:
    """A clone with an origin to push to, standing in for the runner's checkout."""
    origin = tmp_path / "origin.git"
    working = tmp_path / "checkout"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)], check=True
    )
    subprocess.run(["git", "clone", "-q", str(origin), str(working)], check=True)
    for name, value in (("user.email", "t@example.test"), ("user.name", "Test")):
        subprocess.run(["git", "-C", str(working), "config", name, value], check=True)
    (working / "data" / "analytics").mkdir(parents=True)
    (working / "data" / "analytics" / "2026-08-15.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(working), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(working), "commit", "-qm", "base"], check=True)
    subprocess.run(["git", "-C", str(working), "push", "-q", "origin", "HEAD"], check=True)
    return working


def _run_commit_step(working: Path) -> subprocess.CompletedProcess[str]:
    """Run the committed script with the workflow's own environment.

    The branch name comes from the workflow's `env:` block rather than a
    literal here, so renaming it there cannot leave this test proving something
    about a branch the workflow no longer uses.
    """
    workflow = _workflow()
    environment = {key: str(value) for key, value in workflow["env"].items()}
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _commit_step_script()],
        cwd=working,
        capture_output=True,
        text=True,
        env={**os.environ, **environment},
    )


def test_the_commit_step_commits_a_newly_archived_day(tmp_path: Path) -> None:
    """Run the committed script for real against a day the export just wrote.

    Every archived day is a new file and never a modification, so a change
    check that only compares tracked paths — `git diff --quiet` — reports
    "nothing to commit" on precisely the runs that archived something, and
    exits 0. The schedule would then go green every day while the archive
    stayed frozen, which is the whole failure this workflow exists to prevent.
    """
    working = _archive_repository(tmp_path)
    (working / "data" / "analytics" / "2026-08-16.json").write_text(
        '{"date": "2026-08-16"}', encoding="utf-8"
    )

    result = _run_commit_step(working)

    assert result.returncode == 0, result.stderr
    committed = subprocess.run(
        ["git", "-C", str(working), "show", "--name-only", "--format=", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "data/analytics/2026-08-16.json" in committed
    branch = _workflow()["env"]["ARCHIVE_BRANCH"]
    local = subprocess.run(
        ["git", "-C", str(working), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    origin = working.parent / "origin.git"
    pushed = subprocess.run(
        ["git", "-C", str(origin), "rev-parse", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert local == pushed, "the archived day was committed but never pushed"

    # `main` is protected and requires review (CONTRIBUTING.md), so a direct
    # push there fails every single day — silently freezing the archive while
    # the job goes red for nobody.
    default = subprocess.run(
        ["git", "-C", str(origin), "rev-parse", "refs/heads/main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert default != local, "the archive pushed straight to the protected default branch"


def test_the_commit_step_makes_no_empty_commit(tmp_path: Path) -> None:
    """The other half: a run that archived nothing must not commit.

    The schedule fires daily forever, and an empty commit per day would be
    noise in a repository whose history is its audit trail.
    """
    working = _archive_repository(tmp_path)
    before = subprocess.run(
        ["git", "-C", str(working), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    result = _run_commit_step(working)

    assert result.returncode == 0, result.stderr
    after = subprocess.run(
        ["git", "-C", str(working), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert before == after
    assert "nothing new to commit" in result.stdout


def test_the_archived_days_are_checked_before_they_are_pushed() -> None:
    """The gate runs in the producing run, because it cannot run afterwards.

    The archive's pull request is opened by `GITHUB_TOKEN`, and GitHub starts
    no workflow run for an event that token triggered — so `ci.yml` never sees
    the archive branch. Without a check here, the committed-tree assertions
    would first execute after the merge, against a file already on `main`, and
    would then fail on every later pull request that inherited it.
    """
    steps = [step for job in _workflow()["jobs"].values() for step in job["steps"]]
    scripts = [step.get("run", "") for step in steps]
    export = next(index for index, script in enumerate(scripts) if "analytics export" in script)
    checked = next(index for index, script in enumerate(scripts) if "pytest" in script)
    committed = next(index for index, script in enumerate(scripts) if "git commit" in script)

    assert export < checked < committed, (
        "the archived days must be checked after they are written and before they are pushed"
    )
    assert "tests/test_analytics.py" in scripts[checked]


def test_hosting_doc_inventories_the_new_credential() -> None:
    """A credential nobody documented is one nobody can rotate (issue #381)."""
    hosting = (PROJECT_ROOT / "docs" / "HOSTING.md").read_text(encoding="utf-8")
    row = next(
        (line for line in hosting.splitlines() if "CLOUDFLARE_ANALYTICS_TOKEN" in line),
        None,
    )
    assert row is not None, "the credential inventory does not list the analytics token"
    assert "Analytics" in row and "Read" in row, "the row does not state the token's scope"
    assert "Rotat" in row or "rotat" in row, "the row does not state a rotation expectation"


def test_monitoring_doc_records_the_no_data_recheck() -> None:
    """#381 folds the 'No data' recheck in here, per chart, with a verdict.

    Naming the six groupings is not enough — `docs/MONITORING.md` already named
    them when it recorded them as empty. What this ticket owes is an answer for
    each one, so the assertion is that each carries a verdict word.
    """
    monitoring = (PROJECT_ROOT / "docs" / "MONITORING.md").read_text(encoding="utf-8")
    heading = "### The “No data” groupings, rechecked"
    assert heading in monitoring, "no recheck section; the six groupings still have no answer"
    section = monitoring.split(heading, 1)[1].split("\n## ", 1)[0]

    for grouping in (
        "browser",
        "operating system",
        "user agent",
        "HTTP version",
        "cache status",
        "origin status code",
    ):
        line = next(
            (
                candidate
                for candidate in section.splitlines()
                if grouping.lower() in candidate.lower()
            ),
            None,
        )
        assert line is not None, f"the recheck does not mention {grouping}"
        assert "populates" in line or "still empty" in line, (
            f"the recheck names {grouping} without saying whether it populates: {line!r}"
        )
