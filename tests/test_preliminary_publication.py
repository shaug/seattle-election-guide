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
    assert entry.slug == "preliminary-results-2026-11-06-190000"
    assert "winner" not in entry.headline.lower()
    assert current.races[0].outcomes[0].votes == previous.races[0].outcomes[0].votes - 1


@pytest.mark.parametrize(
    "checked_at,want",
    [
        ("2026-11-08T00:43:49+00:00", "November 7, 2026 at 4:43 p.m."),
        ("2026-11-07T07:21:55+00:00", "November 6, 2026 at 11:21 p.m."),
        ("2026-07-05T07:00:59+00:00", "July 5, 2026 at 12:00 a.m."),
        ("2026-07-05T19:00:59+00:00", "July 5, 2026 at 12:00 p.m."),
        ("2026-11-08T20:09:59+00:00", "November 8, 2026 at 12:09 p.m."),
        ("2026-11-08T09:43:49+09:00", "November 7, 2026 at 4:43 p.m."),
    ],
)
def test_update_body_uses_source_check_time_in_pacific_minutes(checked_at: str, want: str) -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].outcomes[0].votes -= 1
    assert current.races[0].votes_counted is not None
    current.races[0].votes_counted -= 1
    original = current.model_dump(mode="json")
    check_time = datetime.fromisoformat(checked_at)
    assert all(c.captured_at != check_time for c in current.captures)
    assert current.races[0].export_generated_at != check_time
    assert current.races[0].reported_at != check_time

    entry = publisher().build_preliminary_update(previous, current, checked_at=check_time)

    assert entry is not None
    assert entry.headline == "Updated preliminary counts for 1 contest."
    assert entry.body == (
        "Updated the unofficial counts for 1 contest, using each contest's complete "
        "jurisdiction. Publisher count and export times remain separate from source "
        "verification times. No certification or outcome is inferred. "
        f"Results checked {want} Pacific."
    )
    assert current.model_dump(mode="json") == original


def test_changed_publisher_clock_without_tally_change_does_not_create_update() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    assert current.races[0].export_generated_at is not None
    current.races[0].export_generated_at += timedelta(seconds=1)
    current = PreliminaryElectionResults.model_validate(current.model_dump())
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is None
    assert current.races[0].reported_at is None
    assert current.races[0].export_generated_at != NOW


def test_failed_refresh_without_tally_change_does_not_create_update() -> None:
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
    assert entry is None
    assert current.races == previous.races


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


@pytest.mark.parametrize("changed", [False, True])
def test_verification_uses_original_byte_identity_not_new_capture_ids(changed: bool) -> None:
    import inspect

    previous = snapshot()
    current = previous.model_copy(deep=True)
    old_reference = current.races[0].capture_evidence
    new_reference = "data/manifests/evidence/new-capture.json"
    capture = next(c for c in current.captures if c.evidence == old_reference)
    current.captures.append(
        capture.model_copy(update={"evidence": new_reference, "captured_at": NOW})
    )
    current.races[0].capture_evidence = new_reference
    current.races[0].coverage_evidence = new_reference
    hashes = {r.capture_evidence: "0" * 64 for r in previous.races}
    hashes[new_reference] = ("1" if changed else "0") * 64
    assert (
        "original_hashes" in inspect.signature(publisher().build_preliminary_update).parameters
    ), "original evidence identity is missing from publication planning"
    entry = publisher().build_preliminary_update(
        previous, current, checked_at=NOW, original_hashes=hashes
    )
    assert entry is None


def test_automatic_update_passes_the_complete_historical_prefix_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import test_updates_history

    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].outcomes[0].votes -= 1
    assert current.races[0].votes_counted is not None
    current.races[0].votes_counted -= 1
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None
    for election in ("wa-2026-primary", "wa-2026-general"):
        (tmp_path / f"{election}.yaml").write_bytes(
            (ROOT / f"data/corrections/{election}.yaml").read_bytes()
        )
    publisher().append_preliminary_update(tmp_path / "wa-2026-general.yaml", entry)
    monkeypatch.setattr(test_updates_history, "UPDATES_DIR", tmp_path)
    test_updates_history.test_election_only_migration_preserves_every_complete_original()


@pytest.mark.parametrize(
    "topics,actions", [(["endorsements"], ["changed"]), (["results"], ["added"])]
)
def test_historical_prefix_audit_rejects_an_unrelated_automatic_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, topics: list[str], actions: list[str]
) -> None:
    from tests import test_updates_history

    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].outcomes[0].votes -= 1
    assert current.races[0].votes_counted is not None
    current.races[0].votes_counted -= 1
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None
    entry.topics = topics
    entry.actions = actions
    for election in ("wa-2026-primary", "wa-2026-general"):
        (tmp_path / f"{election}.yaml").write_bytes(
            (ROOT / f"data/corrections/{election}.yaml").read_bytes()
        )
    publisher().append_preliminary_update(tmp_path / "wa-2026-general.yaml", entry)
    monkeypatch.setattr(test_updates_history, "UPDATES_DIR", tmp_path)
    with pytest.raises(AssertionError):
        test_updates_history.test_election_only_migration_preserves_every_complete_original()


@pytest.mark.parametrize("field", ["reported_at", "reporting_complete"])
def test_source_metadata_alone_never_generates_result_update(field: str) -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    race = current.races[0]
    if field == "reported_at":
        race.reported_at = race.export_generated_at
    elif field == "reporting_complete":
        race.reporting_complete = not race.reporting_complete
    assert publisher().build_preliminary_update(previous, current, checked_at=NOW) is None


def test_reordering_identical_choice_counts_does_not_create_update() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    next(r for r in current.races if len(r.outcomes) > 1).outcomes.reverse()
    assert publisher().build_preliminary_update(previous, current, checked_at=NOW) is None


@pytest.mark.parametrize("change", ["increase", "redistribute", "write-in", "ballots"])
def test_actual_tally_changes_create_update_even_without_new_leader(change: str) -> None:
    previous = snapshot()
    if change == "ballots":
        previous.races[0].vote_total_basis = "authority_stated"
        previous.races[0].ballots_counted = previous.races[0].votes_counted
        previous.races[0].votes_counted = None
    current = previous.model_copy(deep=True)
    race = current.races[0]
    if change == "ballots":
        assert race.ballots_counted is not None
        race.ballots_counted += 1
    elif change == "redistribute":
        race = next(r for r in current.races if len(r.outcomes) > 1)
        race.outcomes[0].votes -= 1
        race.outcomes[1].votes += 1
    else:
        if change == "write-in":
            race.write_in_votes += 1
        else:
            race.outcomes[0].votes += 1
        assert race.votes_counted is not None
        race.votes_counted += 1
    current = PreliminaryElectionResults.model_validate(current.model_dump())
    entry = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    assert entry is not None
    assert entry.headline == "Updated preliminary counts for 1 contest."
    assert "source/reporting metadata or retained originals" not in entry.body


def test_metadata_only_new_capture_still_requires_verified_originals() -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].capture_evidence = "data/manifests/evidence/unverified.json"
    with pytest.raises(ValueError, match="verified original hashes"):
        publisher().build_preliminary_update(previous, current, checked_at=NOW)


def test_two_genuine_same_minute_updates_keep_distinct_publication_identities(
    tmp_path: Path,
) -> None:
    previous = snapshot()
    current = previous.model_copy(deep=True)
    current.races[0].outcomes[0].votes -= 1
    assert current.races[0].votes_counted is not None
    current.races[0].votes_counted -= 1
    first = publisher().build_preliminary_update(previous, current, checked_at=NOW)
    second = publisher().build_preliminary_update(
        previous, current, checked_at=NOW + timedelta(seconds=1)
    )
    assert first is not None and second is not None
    path = tmp_path / "updates.yaml"
    path.write_bytes((ROOT / "data/corrections/wa-2026-general.yaml").read_bytes())
    assert publisher().append_preliminary_update(path, first)
    assert publisher().append_preliminary_update(path, second)
    assert first.headline == second.headline and first.body == second.body
    assert first.slug == "preliminary-results-2026-11-06-190000"
    assert second.slug == "preliminary-results-2026-11-06-190001"
