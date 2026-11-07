"""Automatic candidates preserve source clocks and use the normal review path."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

import pytest

from election_guide.results.loader import read_results
from election_guide.results.models import PreliminaryElectionResults, PreliminaryRefreshFailure

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 11, 7, 3, tzinfo=UTC)


def publisher():
    assert find_spec("election_guide.results.publication") is not None, (
        "hourly publication planning is missing"
    )
    return import_module("election_guide.results.publication")


def snapshot() -> PreliminaryElectionResults:
    value = read_results(ROOT / "data/results/wa-2026-general.yaml")
    assert isinstance(value, PreliminaryElectionResults)
    return value


def test_unchanged_verification_does_not_invent_an_information_update() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.captures[-1].captured_at = NOW
    assert publisher().build_preliminary_update(previous, current, checked_at=NOW) is None
    assert current.races == previous.races


def test_corrected_lower_votes_are_reported_without_clamping_or_winner_claims() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].outcomes[0].votes -= 1
    assert current.races[0].votes_counted is not None
    current.races[0].votes_counted -= 1
    current = PreliminaryElectionResults.model_validate(current.model_dump())
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None and entry.topics == ["results"] and entry.actions == ["changed"]
    assert "1 contest" in entry.body and "unofficial" in entry.body.lower()
    assert "count" in entry.body.lower() and "export" in entry.body.lower()
    assert entry.corrected_on.isoformat() == "2026-11-06"
    assert "winner" not in entry.headline.lower()
    assert current.races[0].outcomes[0].votes == previous.races[0].outcomes[0].votes - 1


def test_changed_publisher_clock_is_information_but_retrieval_is_not_count_time() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    assert current.races[0].export_generated_at is not None
    current.races[0].export_generated_at += timedelta(seconds=1)
    current = PreliminaryElectionResults.model_validate(current.model_dump())
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None
    assert current.races[0].reported_at is None
    assert current.races[0].export_generated_at != NOW


def test_failed_refresh_announces_unavailability_while_preserving_all_counts() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.failed_refreshes.append(
        PreliminaryRefreshFailure(
            authority_id=current.captures[0].authority_id,
            checked_at=NOW,
            evidence="data/manifests/evidence/test-denied.json",
        )
    )
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None and "unavailable" in entry.body.lower()
    assert current.races == previous.races
    assert "preserv" in entry.body.lower()


def test_certified_inputs_cannot_enter_the_preliminary_publisher() -> None:
    certified = read_results(ROOT / "data/results/wa-2026-primary.yaml")
    with pytest.raises(ValueError, match="preliminary"):
        publisher().build_preliminary_update(certified, snapshot(), checked_at=NOW)


@pytest.mark.parametrize(
    "name", [".github/workflows/ci.yml", "data/results/wa-2026-primary.yaml", "../outside"]
)
def test_publication_cannot_stage_code_primary_or_outside_files(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="publication scope"):
        publisher().validate_preliminary_publication_paths(tmp_path, [name])


def test_publication_accepts_only_existing_scoped_result_and_evidence_files(tmp_path: Path) -> None:
    names = [
        "data/results/wa-2026-general.yaml",
        "data/manifests/evidence/one.json",
        "data/evidence/official/original.json",
        "config/hosting/site.yaml",
        "data/corrections/wa-2026-general.yaml",
    ]
    for name in names:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"original")
    assert publisher().validate_preliminary_publication_paths(tmp_path, names) == tuple(names)
    (tmp_path / names[0]).unlink()
    with pytest.raises(ValueError, match=r"missing|deleted"):
        publisher().validate_preliminary_publication_paths(tmp_path, names)


def test_oversized_or_symlinked_evidence_stops_before_git_push(tmp_path: Path) -> None:
    name = "data/evidence/official/oversized.json"
    p = tmp_path / name
    p.parent.mkdir(parents=True)
    with p.open("wb") as f:
        f.truncate(100 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="100 MiB"):
        publisher().validate_preliminary_publication_paths(tmp_path, [name])
    p.unlink()
    p.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="symlink"):
        publisher().validate_preliminary_publication_paths(tmp_path, [name])


def test_append_update_retains_whole_previous_text_and_is_idempotent(tmp_path: Path) -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].outcomes[0].votes -= 1
    assert current.races[0].votes_counted is not None
    current.races[0].votes_counted -= 1
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None
    p = tmp_path / "updates.yaml"
    original = (ROOT / "data/corrections/wa-2026-general.yaml").read_bytes()
    p.write_bytes(original)
    assert publisher().append_preliminary_update(p, entry) is True
    appended = p.read_bytes()
    assert appended.startswith(original)
    assert publisher().append_preliminary_update(p, entry) is False
    assert p.read_bytes() == appended
