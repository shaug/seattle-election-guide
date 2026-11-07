"""Historical/synthetic format recognition; no current-source admission or network."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest

from election_guide.results import parse_preliminary_feed

FIXTURES = Path(__file__).parent / "fixtures/results"


def test_retained_nov6_pair_admits_complete_scope_without_fabricating_state_metadata() -> None:
    from election_guide.inventory.importer import read_inventory
    from election_guide.results import build_preliminary_results
    from election_guide.serialization import read_yaml

    root = Path(__file__).parents[1]
    plan = read_yaml(root / "config/results/wa-2026-general-preliminary.yaml")
    inventory = read_inventory(root / "data/normalized/wa-2026-general-inventory.json")
    results = build_preliminary_results(plan, inventory, repository_root=root)
    assert len(results.races) == 52 and sum(len(r.outcomes) for r in results.races) == 83
    ld32 = next(r for r in results.races if r.race_id == "ld-32-state-representative-1")
    assert ld32.authority_id == "wa-secretary-of-state"
    assert ld32.votes_counted == 49043  # Retained Nov6 State aggregate, not County's 24461.
    assert ld32.reported_at is None and ld32.export_generated_at is not None
    assert ld32.vote_total_basis == "complete_choice_sum"
    state = next(c for c in results.captures if c.authority_id == "wa-secretary-of-state")
    assert state.publisher_is_official_results is None
    council = next(r for r in results.races if r.race_id == "seattle-city-council-5")
    assert council.write_in_votes == 146 and len(council.outcomes) == 2
    assert council.write_in_overrides[0].publisher_is_write_in is False


@pytest.mark.parametrize("mutation", ["missing_override", "changed_flag", "changed_publisher"])
def test_reviewed_mapping_stops_on_unresolved_classification_or_identity(mutation: str) -> None:
    from election_guide.inventory.importer import read_inventory
    from election_guide.results import build_preliminary_results
    from election_guide.serialization import read_yaml

    root = Path(__file__).parents[1]
    plan = read_yaml(root / "config/results/wa-2026-general-preliminary.yaml")
    council = next(r for r in plan["races"] if r["race_id"] == "seattle-city-council-5")
    if mutation == "missing_override":
        council["write_in_overrides"] = []
    elif mutation == "changed_flag":
        council["write_in_overrides"][0]["publisher_is_write_in"] = True
    else:
        plan["sources"][0]["publisher_jurisdiction_id"] = "wrong-publisher"
    with pytest.raises(ValueError, match=r"mapping|Write-in|identity"):
        build_preliminary_results(
            plan,
            read_inventory(root / "data/normalized/wa-2026-general-inventory.json"),
            repository_root=root,
        )


def test_state_source_preserves_an_explicit_official_flag_if_one_is_supplied() -> None:
    raw = json.loads((FIXTURES / "wa-2026-general-historical-state.json").read_bytes())
    raw["isOfficialResults"] = True
    assert (
        parse_preliminary_feed(json.dumps(raw).encode(), format="statewide").is_official_results
        is True
    )


def test_county_feed_keeps_publisher_clock_and_county_scope_without_calling_winners() -> None:
    feed = parse_preliminary_feed(
        (FIXTURES / "wa-2026-general-historical-county.json").read_bytes(), format="county"
    )
    assert feed.election_date.isoformat() == "2026-11-03"
    assert feed.jurisdiction == "king-county-wa"
    assert feed.is_official_results is False
    contest = next(
        item for item in feed.contests.values() if "Congressional District 9" in item.name
    )
    assert contest.reported_at == datetime(2026, 11, 4, 4, 12, 12, 419061, tzinfo=UTC)
    assert contest.reporting_complete is None
    assert contest.votes_counted == sum(choice.votes for choice in contest.choices)
    assert sum(choice.is_write_in is True for choice in contest.choices) == 1
    assert not hasattr(contest, "winner")
    # Empty crossCounties is not converted into full district geography.
    assert feed.jurisdiction != "washington"


def test_state_feed_uses_the_state_aggregate_not_localresults_or_generation_asof() -> None:
    raw: dict[str, Any] = json.loads(
        (FIXTURES / "wa-2026-general-historical-state.json").read_bytes()
    )
    raw["localResults"] = [{"name": "County-only trap", "ballotItems": [{"id": "trap"}]}]
    feed = parse_preliminary_feed(json.dumps(raw).encode(), format="statewide")
    assert feed.jurisdiction == "washington"
    assert len(feed.contests) == 3 and "trap" not in feed.contests
    assert feed.generated_at == datetime(2026, 11, 4, 4, 16, 52, 597640, tzinfo=UTC)
    assert all(contest.reported_at is None for contest in feed.contests.values())
    assert all(contest.votes_counted is None for contest in feed.contests.values())
    assert feed.is_official_results is None


@pytest.mark.parametrize("bad", [-1, True, 1.5, "20"])
def test_source_counts_are_strict_nonnegative_integers(bad: object) -> None:
    raw: dict[str, Any] = json.loads(
        (FIXTURES / "wa-2026-general-historical-state.json").read_bytes()
    )
    raw["results"]["ballotItems"][0]["ballotOptions"][0]["voteCount"] = bad
    with pytest.raises(ValueError, match="nonnegative integer"):
        parse_preliminary_feed(json.dumps(raw).encode(), format="statewide")


def test_wrong_source_shape_and_duplicate_contest_ids_fail_closed() -> None:
    raw: dict[str, Any] = json.loads(
        (FIXTURES / "wa-2026-general-historical-state.json").read_bytes()
    )
    raw["results"]["ballotItems"].append(raw["results"]["ballotItems"][0])
    with pytest.raises(ValueError, match="duplicate contest"):
        parse_preliminary_feed(json.dumps(raw).encode(), format="statewide")
    with pytest.raises(ValueError):
        parse_preliminary_feed(b'{"ballotItems":[]}', format="statewide")


@pytest.mark.parametrize(
    "digest,format,expected",
    [
        ("eba2d525d864dc57a546b6552c8dffa629746a65351b7002b18b0819c115f68f", "county", 115),
        ("3de8a3aba113b76f933774e4b6f2de8319f370b329951ed0b8ca1242b62d4b8e", "statewide", 173),
    ],
)
def test_complete_historical_capture_format_is_supported_without_freshness_credit(
    digest: str, format: Literal["county", "statewide"], expected: int
) -> None:
    # Parse the full saved format, not only a favorable excerpt. This does NOT
    # review or admit current counts, whole-jurisdiction mapping or source clocks.
    original = Path(__file__).parents[1] / "data/evidence/official/sha256" / digest[:2] / digest
    feed = parse_preliminary_feed(original.read_bytes(), format=format)
    assert len(feed.contests) == expected
