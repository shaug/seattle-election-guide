"""Hold the post-election retrospective checklist to the repository it describes.

The checklist deliberately states rules rather than figures: a rule is checkable
against the schema and survives a cycle, while a count is stale the moment the
next election is released. Its worked findings belong in the retrospective note
it tells you to write, not here.

These tests pin the rules. Where one is a claim about committed evidence, they
assert the invariant the rule depends on rather than the number it produced.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from election_guide.evidence.models import CaptureManifest
from election_guide.evidence.storage import read_capture_manifest
from election_guide.release.compiler import read_release_ledger
from election_guide.release.models import ReleaseSourceExtract
from election_guide.scoring.impact import ConsensusImpactReport
from election_guide.serialization import read_json
from election_guide.sources.models import Source
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parents[1]
CHECKLIST_PATH = PROJECT_ROOT / "docs" / "POST_ELECTION_RETROSPECTIVE.md"
REGISTRY_PATH = PROJECT_ROOT / "config" / "sources" / "default.yaml"
LEDGER_PATH = PROJECT_ROOT / "data" / "releases" / "wa-2026-primary" / "source-decisions.yaml"
IMPACT_PATH = PROJECT_ROOT / "data" / "releases" / "wa-2026-primary" / "source-panel-impact.json"
DATASET_PATH = PROJECT_ROOT / "data" / "normalized" / "canonical-dataset.json"
EVIDENCE_MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests" / "evidence"

# Every path the checklist names that this repository commits. The checklist
# also names data/collection/refreshes/, data/overrides/, and
# data/review/decisions/, which are working directories the CLI writes to
# before compilation and which a cycle need not commit — the checklist says so
# where it names them.
NAMED_ARTIFACTS = (
    "config/sources/default.yaml",
    "config/calendar/elections.yaml",
    "config/hosting/site.yaml",
    "data/manifests/evidence/",
    "data/normalized/canonical-dataset.json",
    "data/normalized/<election-id>-inventory.json",
    "data/releases/<election-id>/manifests/",
    "data/releases/<election-id>/panel-snapshots.json",
    "data/releases/<election-id>/source-decisions.yaml",
    "data/releases/<election-id>/source-panel-impact.json",
    "docs/SOURCE_DISCOVERY.md",
    "docs/ELECTION_CALENDAR.md",
    "SOURCE_POLICY.md",
    "DECISIONS.md",
)


def _checklist() -> str:
    """Collapse the document's line wrapping so a claim can be matched as prose."""
    return " ".join(CHECKLIST_PATH.read_text(encoding="utf-8").split())


def _panel() -> list[Source]:
    return list(read_source_registry(REGISTRY_PATH).sources)


def _evidence_manifests() -> list[CaptureManifest]:
    return [read_capture_manifest(path) for path in sorted(EVIDENCE_MANIFEST_DIR.glob("*.json"))]


def _ledger_source_ids() -> set[str]:
    return {source.source_id for source in read_release_ledger(LEDGER_PATH).sources}


def test_checklist_names_artifacts_that_still_exist() -> None:
    checklist = _checklist()

    for named in NAMED_ARTIFACTS:
        assert named in checklist, f"checklist no longer names {named}"
        path = named.replace("<election-id>", "wa-2026-primary")
        assert (PROJECT_ROOT / path).exists(), f"checklist names a missing artifact: {path}"


# A per-cycle figure is a number bound to something the pipeline counts. Small
# numbers used structurally — "one panel change", "three outcomes matter" — are
# prose and stay. These are the nouns whose counts change every election.
COUNTED_NOUNS = (
    "races?|entries|sources?|decisions|overrides|manifests|versions|"
    "milestones|changes|captures|snapshots"
)
NUMBERS = (
    r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred"
)
# A number, optionally hyphenated and optionally with one adjective between,
# directly qualifying a counted noun.
PER_CYCLE_FIGURE = re.compile(
    rf"\b(?:{NUMBERS})(?:-(?:{NUMBERS}))?"
    rf"(?:\s+(?:[a-z]+\s+)?(?:{COUNTED_NOUNS})\b"  # "thirty-two races"
    rf"|\s+of\s+(?:{NUMBERS})\b"  # "the answer was one of four"
    rf"|:)",  # "recorded two: the Disability Mobility Initiative"
    re.IGNORECASE,
)


def test_checklist_states_rules_rather_than_this_cycle_s_figures() -> None:
    """A count about one cycle belongs in that cycle's note, not in the template.

    This is the guard that failed before. The document accumulated hand-derived
    figures and each one was wrong in a different way, because getting them
    right needs exactly the fluency the checklist exists to supply. A rule is
    checkable against the schema; a count is stale once the next election
    releases.
    """
    offenders = PER_CYCLE_FIGURE.findall(_checklist())

    assert not offenders, f"a per-cycle figure crept back into the checklist: {offenders}"


def test_the_figure_guard_catches_what_it_was_written_for() -> None:
    """Every phrasing that carried a per-cycle figure in an earlier revision."""
    for phrasing in (
        "the report lists thirty-two races",
        "forty-three selectable sources produced forty-one entries",
        "recorded thirty-one decisions",
        "Six races changed a grade",
        "went through four versions",
        "its forty-eight sources are forty-two consensus",
        "For the 2026 primary the answer was one of four",
        "The 2026 primary recorded two: the Disability Mobility Initiative",
    ):
        assert PER_CYCLE_FIGURE.search(phrasing), f"guard would have missed: {phrasing}"

    for prose in (
        "the deterministic scoring impact of one panel change",
        "Three outcomes matter, and they are different problems",
        "reached and silent two cycles running",
        "roughly thirty days past election day",
    ):
        assert not PER_CYCLE_FIGURE.search(prose), f"guard is too broad: {prose}"


def test_an_excluded_source_cannot_carry_eligibility() -> None:
    """The reason the checklist says not to count excluded sources as gaps."""
    excluded = next(source for source in _panel() if source.panel_role == "excluded")
    payload = excluded.model_dump(mode="json")
    payload["eligibility"] = {
        "kind": "all_seattle_ballot_races",
        "rationale": "Made eligible to prove the validator rejects it.",
    }

    with pytest.raises(ValidationError, match="must have no eligibility"):
        Source.model_validate(payload)

    assert "`eligibility: {kind: none}` and can never contribute a decision" in _checklist()


def test_the_ledger_schema_forbids_an_empty_decision_list() -> None:
    """The checklist tells the reader not to look for one; keep that true."""
    payload = read_release_ledger(LEDGER_PATH).sources[0].model_dump(mode="json")
    payload["decisions"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        ReleaseSourceExtract.model_validate(payload)

    assert "Do not look for an empty `decisions` list" in _checklist()


def test_the_impact_report_is_attributed_from_its_before_side() -> None:
    """The registry notes carry no timestamps, so the before hashes are the key."""
    impact = ConsensusImpactReport.model_validate(read_json(IMPACT_PATH))
    expansion = (PROJECT_ROOT / "docs" / "SOURCE_PANEL_EXPANSION_2026-07-23.md").read_text(
        encoding="utf-8"
    )

    assert impact.before.dataset_hash in expansion
    assert impact.before.input_hash in expansion
    # The after side was regenerated under later inputs, which is why the
    # checklist says to match on before rather than after.
    assert impact.after.dataset_hash not in expansion

    assert "match `before.dataset_hash` and" in _checklist()
    assert "the registry's `notes` carry no" in _checklist()


def test_every_unledgered_source_fits_one_of_the_three_branches() -> None:
    """The classification must be exhaustive over the evidence actually committed."""
    by_id = {source.id: source for source in _panel()}
    ledger_ids = _ledger_source_ids()

    availability: dict[str, set[str]] = {}
    for manifest in _evidence_manifests():
        availability.setdefault(manifest.source_id, set()).add(manifest.availability)

    unclassified: list[str] = []
    for source_id, source in by_id.items():
        if not source.is_selectable or source_id in ledger_ids:
            continue
        states = availability.get(source_id, set())
        unreachable = states == {"unavailable"} and source.discovery.status == "access_restricted"
        silent = "captured" in states and source.discovery.status == "not_found"
        never_attempted = not states
        if not (unreachable or silent or never_attempted):
            unclassified.append(source_id)

    assert not unclassified, f"the checklist's three branches do not cover {unclassified}"

    checklist = _checklist()
    for branch in ("Unreachable.", "Reached and silent.", "Never attempted."):
        assert branch in checklist


def test_a_source_that_moved_need_not_have_an_evidence_manifest() -> None:
    """The checklist's stated reason for reading the registry, not the manifests."""
    moved = {source.id for source in _panel() if source.discovery.redirect_chain}
    assert moved, "no committed source records a move, so the rule is unexercised"

    with_evidence = {manifest.source_id for manifest in _evidence_manifests()}
    assert not (moved & with_evidence)

    assert "the registry rather than the manifests is the place to look" in _checklist()


def test_a_capture_manifest_redirect_is_not_a_move() -> None:
    """The trap the checklist names by example, because a reader will hit it."""
    redirected = {
        manifest.source_id
        for manifest in _evidence_manifests()
        if manifest.availability == "captured" and manifest.redirect_chain
    }
    assert redirected == {"11th-district-democrats"}

    eleventh = next(source for source in _panel() if source.id == "11th-district-democrats")
    assert eleventh.discovery.requested_url == eleventh.discovery.canonical_url
    assert not eleventh.discovery.redirect_chain

    assert "Do not read a `redirect_chain` in a *capture manifest* as a move" in _checklist()


def test_the_impact_report_fields_the_checklist_names_are_real() -> None:
    """Naming a field that does not exist sends the reader looking for nothing."""
    impact = ConsensusImpactReport.model_validate(read_json(IMPACT_PATH))
    present = {field for change in impact.changes for field in change.changed_fields}

    checklist = _checklist()
    for field in (
        "eligible_source_count",
        "missing_source_count",
        "warnings",
        "grade",
        "winner_candidate_ids",
        "winner_share",
    ):
        assert field in present, f"the impact report no longer reports {field}"
        assert f"`{field}`" in checklist


def test_corrections_live_in_the_canonical_dataset() -> None:
    """Section 5 sends the reader to the record, not to the working directories."""
    dataset: Any = read_json(DATASET_PATH)

    assert "review_decisions" in dataset
    assert "overrides" in dataset

    checklist = _checklist()
    assert "Read `review_decisions` and `overrides` in" in checklist
    assert "They are working directories; the canonical dataset is the record." in checklist
