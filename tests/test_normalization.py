from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from election_guide.evidence.models import CaptureRequest, UnavailableRequest
from election_guide.evidence.storage import (
    ImmutableRecordError,
    read_capture_manifest,
    record_capture,
    record_unavailable,
)
from election_guide.inventory.importer import import_inventory, read_inventory
from election_guide.normalization.matching import (
    classify_endorsement_status,
    match_candidate,
    match_claim,
    match_race,
    normalize_claim,
    normalize_match_text,
)
from election_guide.normalization.models import (
    CanonicalDataset,
    NormalizedEndorsement,
    equal_allocation,
)
from election_guide.normalization.records import (
    list_records,
    new_extracted_claim,
    new_normalized_endorsement,
    new_override,
    new_review_decision,
    unresolved_review_items,
    write_record,
    write_review_decision,
    write_review_item,
)
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parent.parent
INVENTORY_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "inventory"
EVIDENCE_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "evidence"
INVENTORY_INPUTS = {
    "candidates": INVENTORY_FIXTURES / "candidates.csv",
    "pco_democrats": INVENTORY_FIXTURES / "pco-democrats.csv",
    "pco_republicans": INVENTORY_FIXTURES / "pco-republicans.csv",
    "precinct_crosswalk": INVENTORY_FIXTURES / "precinct-crosswalk.csv",
}
NOW = datetime(2026, 7, 19, 13, tzinfo=UTC)
SOURCE_REGISTRY = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")


def test_name_and_race_matching_use_authoritative_aliases() -> None:
    inventory = _fixture_inventory()

    assert normalize_match_text("  Rébecca O\u2019Neil (Becca) ") == "rebecca o neil becca"
    assert match_race("Municipal Court Judge Position No. 5", inventory).selected_id == (
        "municipal-court-5"
    )
    assert match_candidate("ada example", "municipal-court-5", inventory).selected_id == (
        "municipal-court-5--ada-example"
    )


def test_candidate_fuzzy_matching_never_crosses_race_boundaries() -> None:
    inventory = _fixture_inventory()

    result = match_candidate("Alex Exampel", "municipal-court-5", inventory)

    assert result.status == "unmatched"
    assert all(
        candidate.record_id.startswith("municipal-court-5--") for candidate in result.candidates
    )


def test_competing_candidate_matches_enter_review_instead_of_selecting() -> None:
    inventory = _fixture_inventory()
    payload = inventory.model_dump(mode="json")
    payload["races"][0]["choices"][0]["aliases"] = ["Preferred Candidate"]
    payload["races"][0]["choices"][1]["aliases"] = ["Preferred Candidate"]
    ambiguous_inventory = inventory.model_validate(payload)
    claim = _claim(raw_candidate_text="Preferred Candidate")

    outcome = match_claim(
        claim,
        ambiguous_inventory,
        created_at=NOW,
        source_registry=SOURCE_REGISTRY,
    )

    assert outcome.candidate_match is not None
    assert outcome.candidate_match.status == "ambiguous"
    assert outcome.candidate_match.selected_id is None
    assert outcome.review_item is not None
    assert outcome.review_item.reason == "candidate_ambiguous"


def test_extractor_flags_and_cardinality_contradictions_enter_review() -> None:
    inventory = _fixture_inventory()

    extractor_flagged = match_claim(
        _claim(raw_candidate_text="Ada Example", requires_review=True),
        inventory,
        created_at=NOW,
        source_registry=SOURCE_REGISTRY,
    )
    assert extractor_flagged.review_item is not None
    assert extractor_flagged.review_item.reason == "extraction_requires_review"

    no_endorsement_with_candidate = match_claim(
        _claim(raw_status_text="No endorsement", raw_candidate_text="Ada Example"),
        inventory,
        created_at=NOW,
        source_registry=SOURCE_REGISTRY,
    )
    assert no_endorsement_with_candidate.review_item is not None
    assert no_endorsement_with_candidate.review_item.reason == "semantics_ambiguous"

    for status in ("Dual endorsement", "Multiple endorsement"):
        outcome = match_claim(
            _claim(raw_status_text=status, raw_candidate_text="Ada Example"),
            inventory,
            created_at=NOW,
            source_registry=SOURCE_REGISTRY,
        )
        assert outcome.review_item is not None
        assert outcome.review_item.reason == "semantics_ambiguous"


def test_source_scoped_matching_excludes_ineligible_races() -> None:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")
    raw_race_text = "Legislative District 34 State Senator"
    eligible_claim = _claim(
        source_id="34th-district-democrats",
        raw_race_text=raw_race_text,
        raw_candidate_text=None,
        raw_status_text="No endorsement",
    )
    ineligible_claim = _claim(
        source_id="32nd-district-democrats",
        raw_race_text=raw_race_text,
        raw_candidate_text=None,
        raw_status_text="No endorsement",
    )

    eligible_outcome = match_claim(
        eligible_claim,
        inventory,
        created_at=NOW,
        source_registry=registry,
    )
    ineligible_outcome = match_claim(
        ineligible_claim,
        inventory,
        created_at=NOW,
        source_registry=registry,
    )

    assert eligible_outcome.race_match.status == "matched"
    assert eligible_outcome.race_match.selected_id == "ld-34-state-senator"
    assert ineligible_outcome.race_match.status == "matched"
    assert ineligible_outcome.race_match.selected_id == "ld-34-state-senator"
    assert ineligible_outcome.review_item is not None
    assert ineligible_outcome.review_item.reason == "race_ineligible"


def test_source_scoped_matching_uses_ld_context_for_generic_office_labels() -> None:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")
    claim = _claim(
        source_id="32nd-district-democrats",
        raw_race_text="State Representative Pos. 1",
        raw_candidate_text=None,
        raw_status_text="No endorsement",
    )

    outcome = match_claim(
        claim,
        inventory,
        created_at=NOW,
        source_registry=registry,
    )

    assert outcome.race_match.status == "matched"
    assert outcome.race_match.selected_id == "ld-32-state-representative-1"
    assert outcome.review_item is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Endorsed", "endorsed"),
        ("Dual endorsement", "dual_endorsement"),
        ("Multiple endorsement", "multiple_endorsement"),
        ("No endorsement", "no_endorsement"),
        ("Declined to endorse", "declined_to_endorse"),
        ("Not covered", "not_covered"),
        ("Not published", "not_published"),
        ("Unverified", "unverified"),
        ("Source unavailable", "source_unavailable"),
        ("Ambiguous", "ambiguous"),
    ],
)
def test_endorsement_states_remain_distinct(raw: str, expected: str) -> None:
    assert classify_endorsement_status(raw) == expected


def test_exact_allocations_total_one_for_single_dual_and_multiple_decisions() -> None:
    for status, candidate_ids in (
        ("endorsed", ["candidate-a"]),
        ("dual_endorsement", ["candidate-a", "candidate-b"]),
        ("multiple_endorsement", ["candidate-a", "candidate-b", "candidate-c"]),
    ):
        endorsement = _endorsement(status=status, candidate_ids=candidate_ids)
        assert sum(endorsement.allocation.values(), start=Fraction(0)) == Fraction(1)

    three_way = _endorsement(
        status="multiple_endorsement",
        candidate_ids=["candidate-a", "candidate-b", "candidate-c"],
    )
    assert set(three_way.model_dump(mode="json")["allocation"].values()) == {"1/3"}


def test_endorsement_semantics_reject_inexact_or_incoherent_allocations() -> None:
    payload = _endorsement(status="endorsed", candidate_ids=["candidate-a"]).model_dump()
    payload["allocation"] = {"candidate-a": "1/2"}
    with pytest.raises(ValidationError, match="must total exactly one"):
        NormalizedEndorsement.model_validate(payload)


def test_content_derived_record_ids_reject_tampering() -> None:
    claim = _claim()
    payload = claim.model_dump(mode="json")
    payload["evidence_excerpt"] = "Changed after the record ID was assigned."

    with pytest.raises(ValidationError, match="record ID must equal its canonical content hash"):
        type(claim).model_validate(payload)

    payload = _endorsement(status="no_endorsement", candidate_ids=[]).model_dump()
    payload["candidate_ids"] = ["candidate-a"]
    payload["allocation"] = {"candidate-a": "1"}
    with pytest.raises(ValidationError, match="cannot carry candidates"):
        NormalizedEndorsement.model_validate(payload)

    payload = _endorsement(status="endorsed", candidate_ids=["candidate-a"]).model_dump()
    payload["normalization_confidence"] = 0.9
    with pytest.raises(ValidationError, match="must use an exact"):
        NormalizedEndorsement.model_validate(payload)

    payload = _endorsement(status="endorsed", candidate_ids=["candidate-a"]).model_dump()
    payload["normalization_confidence"] = True
    payload["allocation"] = {"candidate-a": True}
    with pytest.raises(ValidationError, match="must use an exact"):
        NormalizedEndorsement.model_validate(payload)


def test_review_decisions_and_overrides_are_append_only_audit_records(tmp_path: Path) -> None:
    claim = _claim(raw_candidate_text="Preferred Candidate")
    outcome = match_claim(
        claim,
        _fixture_inventory(),
        created_at=NOW,
        source_registry=SOURCE_REGISTRY,
    )
    assert outcome.review_item is not None
    queue_dir = tmp_path / "queue"
    decisions_dir = tmp_path / "decisions"
    overrides_dir = tmp_path / "overrides"
    write_review_item(outcome.review_item, queue_dir)
    assert unresolved_review_items(queue_dir, decisions_dir) == [outcome.review_item]

    later_outcome = match_claim(
        claim,
        _fixture_inventory(),
        created_at=NOW + timedelta(minutes=1),
        source_registry=SOURCE_REGISTRY,
    )
    assert later_outcome.review_item is not None
    with pytest.raises(ImmutableRecordError, match="refusing to overwrite"):
        write_review_item(later_outcome.review_item, queue_dir)

    decision = new_review_decision(
        review_item_id=outcome.review_item.id,
        action="reject",
        author="reviewer",
        reason="No candidate in the race matches the source text.",
        evidence="Screenshot 1",
        created_at=NOW,
    )
    assert write_review_decision(decision, decisions_dir) == write_review_decision(
        decision, decisions_dir
    )
    assert unresolved_review_items(queue_dir, decisions_dir) == []

    conflicting = new_review_decision(
        review_item_id=outcome.review_item.id,
        action="approve",
        author="other-reviewer",
        reason="A conflicting terminal decision must lose the atomic claim.",
        evidence="Screenshot 1",
        created_at=NOW,
        resolution={
            "race_id": "municipal-court-5",
            "status": "endorsed",
            "candidate_ids": ["municipal-court-5--ada-example"],
            "allocation": {"municipal-court-5--ada-example": "1"},
        },
    )
    with pytest.raises(ImmutableRecordError, match="refusing to overwrite"):
        write_review_decision(conflicting, decisions_dir)

    override = new_override(
        target_record_id="endorsement-0123456789abcdef",
        field="status",
        old_value="ambiguous",
        new_value="no_endorsement",
        reason="The source explicitly says it made no endorsement.",
        evidence="Capture heading, paragraph 2",
        author="reviewer",
        created_at=NOW,
    )
    write_record(override, overrides_dir)
    loaded = list_records(overrides_dir, type(override))[0]
    assert loaded.old_value == "ambiguous"
    assert loaded.new_value == "no_endorsement"
    assert loaded.reason
    assert loaded.evidence
    assert loaded.author == "reviewer"
    assert loaded.created_at == NOW


def test_canonical_dataset_validates_cross_entity_provenance(tmp_path: Path) -> None:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")
    request = CaptureRequest.model_validate(
        {
            "source_id": "the-stranger",
            "requested_url": "https://www.thestranger.com/endorsements/fixture",
            "canonical_url": "https://www.thestranger.com/endorsements/fixture",
            "retrieved_at": "2026-07-19T12:00:00Z",
            "http_status": 200,
            "media_type": "text/html",
            "title": "Fixture endorsements",
            "published_at": "2026-07-02",
            "capture_method": "static_html",
            "redistribution": "permitted",
            "redistribution_note": "Repository-authored fixture.",
        }
    )
    capture = read_capture_manifest(
        record_capture(
            request,
            EVIDENCE_FIXTURES / "static.html",
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )
    )
    claim = new_extracted_claim(
        capture_id=capture.id,
        source_id="the-stranger",
        raw_race_text="King County Assessor",
        raw_candidate_text="Rob Foxcurran",
        raw_status_text="Endorsed",
        raw_notes=None,
        evidence_excerpt="Rob Foxcurran for King County Assessor",
        evidence_locator="Endorsement list, item 1",
        extractor="fixture",
        extractor_version="1.0",
        extraction_confidence="1",
        requires_review=False,
    )
    endorsement = new_normalized_endorsement(
        election_id=inventory.election.id,
        race_id="king-county-assessor",
        source_id="the-stranger",
        status="endorsed",
        candidate_ids=["king-county-assessor--rob-foxcurran"],
        allocation={"king-county-assessor--rob-foxcurran": "1"},
        published_at="2026-07-02",
        source_capture_id=capture.id,
        extracted_claim_id=claim.id,
        normalization_confidence="1",
        manually_verified=True,
        reviewer="fixture-reviewer",
        reviewed_at=NOW,
        notes=None,
    )

    dataset = CanonicalDataset(
        inventory=inventory,
        source_registry=registry,
        captures=[capture],
        claims=[claim],
        endorsements=[endorsement],
    )
    assert dataset.endorsements[0].candidate_ids == ["king-county-assessor--rob-foxcurran"]

    normalized = normalize_claim(
        claim,
        inventory,
        capture,
        created_at=NOW,
        source_registry=registry,
    )
    assert normalized.match.review_item is None
    assert normalized.endorsement is not None
    assert normalized.endorsement.status == "endorsed"
    assert normalized.endorsement.allocation == {"king-county-assessor--rob-foxcurran": Fraction(1)}

    invalid_fields = endorsement.model_dump(mode="json", exclude={"id"})
    invalid_fields["candidate_ids"] = ["candidate-from-another-race"]
    invalid_fields["allocation"] = {"candidate-from-another-race": "1"}
    invalid_endorsement = new_normalized_endorsement(**invalid_fields)
    payload = dataset.model_dump(mode="json")
    payload["endorsements"] = [invalid_endorsement.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="candidates outside its race"):
        CanonicalDataset.model_validate(payload)

    contradictory_claim = new_extracted_claim(
        **{
            **claim.model_dump(mode="json", exclude={"id"}),
            "raw_status_text": "Not covered",
            "raw_candidate_text": None,
        }
    )
    contradictory_fields = endorsement.model_dump(mode="json", exclude={"id"})
    contradictory_fields["extracted_claim_id"] = contradictory_claim.id
    contradictory = new_normalized_endorsement(**contradictory_fields)
    with pytest.raises(ValidationError, match="departs from its claim"):
        CanonicalDataset(
            inventory=inventory,
            source_registry=registry,
            captures=[capture],
            claims=[contradictory_claim],
            endorsements=[contradictory],
        )

    orphan = new_override(
        target_record_id="endorsement-0000000000000000",
        field="notes",
        old_value=None,
        new_value="Reviewed",
        reason="Fixture orphan.",
        evidence="Fixture",
        author="reviewer",
        created_at=NOW,
    )
    with pytest.raises(ValidationError, match="references unknown target"):
        CanonicalDataset(
            inventory=inventory,
            source_registry=registry,
            captures=[capture],
            claims=[claim],
            endorsements=[endorsement],
            overrides=[orphan],
        )

    valid_override = new_override(
        target_record_id=endorsement.id,
        field="notes",
        old_value=None,
        new_value="Reviewer annotation.",
        reason="Preserve a reviewed normalization note.",
        evidence="Fixture",
        author="reviewer",
        created_at=NOW,
    )
    overridden = CanonicalDataset(
        inventory=inventory,
        source_registry=registry,
        captures=[capture],
        claims=[claim],
        endorsements=[endorsement],
        overrides=[valid_override],
    )
    assert overridden.overrides == [valid_override]
    assert overridden.effective_records()[endorsement.id].model_dump(mode="json")["notes"] == (
        "Reviewer annotation."
    )

    contradictory_override = new_override(
        target_record_id=claim.id,
        field="raw_status_text",
        old_value="Endorsed",
        new_value="Not covered",
        reason="Fixture semantic contradiction.",
        evidence="Fixture",
        author="reviewer",
        created_at=NOW,
    )
    with pytest.raises(ValidationError, match="departs from its claim"):
        CanonicalDataset(
            inventory=inventory,
            source_registry=registry,
            captures=[capture],
            claims=[claim],
            endorsements=[endorsement],
            overrides=[contradictory_override],
        )

    review_claim = new_extracted_claim(
        **{
            **claim.model_dump(mode="json", exclude={"id"}),
            "raw_candidate_text": "Unknown Person",
        }
    )
    review_outcome = match_claim(
        review_claim,
        inventory,
        created_at=NOW,
        source_registry=registry,
    )
    assert review_outcome.review_item is not None
    impossible_decision = new_review_decision(
        review_item_id=review_outcome.review_item.id,
        action="approve",
        author="reviewer",
        reason="This status contradicts the captured evidence availability.",
        evidence="Fixture",
        created_at=NOW,
        resolution={
            "race_id": "king-county-assessor",
            "status": "source_unavailable",
            "candidate_ids": [],
            "allocation": {},
        },
    )
    with pytest.raises(ValidationError, match="requires an unavailable capture"):
        CanonicalDataset(
            inventory=inventory,
            source_registry=registry,
            captures=[capture],
            claims=[review_claim],
            endorsements=[],
            review_items=[review_outcome.review_item],
            review_decisions=[impossible_decision],
        )


def test_canonical_dataset_rejects_alias_collisions_within_a_race(tmp_path: Path) -> None:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    payload = inventory.model_dump(mode="json")
    payload["races"][0]["choices"][0]["aliases"] = ["Shared Alias"]
    payload["races"][0]["choices"][1]["aliases"] = ["shared alias"]
    colliding = inventory.model_validate(payload)
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")

    with pytest.raises(ValidationError, match=r"candidate alias .* collides"):
        CanonicalDataset(
            inventory=colliding,
            source_registry=registry,
            captures=[],
            claims=[],
            endorsements=[],
        )


def test_unavailable_source_state_uses_only_metadata_provenance(tmp_path: Path) -> None:
    inventory = read_inventory(PROJECT_ROOT / "data/normalized/wa-2026-primary-inventory.json")
    registry = read_source_registry(PROJECT_ROOT / "config/sources/default.yaml")
    reason = "The official page denied unattended access."
    capture = read_capture_manifest(
        record_unavailable(
            UnavailableRequest.model_validate(
                {
                    "source_id": "seattle-times-editorial-board",
                    "requested_url": "https://www.seattletimes.com/opinion/editorials/",
                    "retrieved_at": "2026-07-19T12:00:00Z",
                    "http_status": 403,
                    "media_type": "text/html",
                    "capture_method": "unavailable",
                    "browser_required": False,
                    "redistribution": "restricted",
                    "redistribution_note": "No source content was retained.",
                    "unavailable_reason": reason,
                }
            ),
            tmp_path / "manifests",
        )
    )
    claim = new_extracted_claim(
        capture_id=capture.id,
        source_id=capture.source_id,
        raw_race_text="King County Assessor",
        raw_candidate_text=None,
        raw_status_text="Source unavailable",
        raw_notes=None,
        evidence_excerpt=reason,
        evidence_locator="Unavailable capture metadata",
        extractor="availability-record",
        extractor_version="1.0",
        extraction_confidence="1",
        requires_review=False,
    )
    endorsement = new_normalized_endorsement(
        election_id=inventory.election.id,
        race_id="king-county-assessor",
        source_id=capture.source_id,
        status="source_unavailable",
        candidate_ids=[],
        allocation={},
        published_at=None,
        source_capture_id=capture.id,
        extracted_claim_id=claim.id,
        normalization_confidence="1",
        manually_verified=False,
        notes=None,
    )

    dataset = CanonicalDataset(
        inventory=inventory,
        source_registry=registry,
        captures=[capture],
        claims=[claim],
        endorsements=[endorsement],
    )
    assert dataset.endorsements[0].status == "source_unavailable"

    with pytest.raises(ValueError, match="cannot predate capture retrieval"):
        normalize_claim(
            claim,
            inventory,
            capture,
            created_at=datetime(2026, 7, 19, 11, tzinfo=UTC),
            source_registry=registry,
        )

    unsafe_claim = new_extracted_claim(
        **{
            **claim.model_dump(mode="json", exclude={"id"}),
            "raw_notes": "An uncaptured paragraph allegedly said something else.",
        }
    )
    with pytest.raises(ValueError, match="contains uncaptured content"):
        normalize_claim(
            unsafe_claim,
            inventory,
            capture,
            created_at=NOW,
            source_registry=registry,
        )

    invalid_fields = endorsement.model_dump(mode="json", exclude={"id"})
    invalid_fields["status"] = "not_covered"
    invalid = new_normalized_endorsement(**invalid_fields)
    with pytest.raises(ValidationError, match="must preserve unavailable provenance"):
        CanonicalDataset(
            inventory=inventory,
            source_registry=registry,
            captures=[capture],
            claims=[claim],
            endorsements=[invalid],
        )


def _fixture_inventory():
    return import_inventory(
        INVENTORY_FIXTURES / "config.yaml",
        INVENTORY_INPUTS,
    )


def _claim(**updates: Any):
    fields: dict[str, Any] = {
        "capture_id": "capture-the-stranger-20260719T120000Z-0123456789ab",
        "source_id": "the-stranger",
        "raw_race_text": "Municipal Court Judge Position No. 5",
        "raw_candidate_text": "Unknown Person",
        "raw_status_text": "Endorsed",
        "raw_notes": None,
        "evidence_excerpt": "Fixture endorsement excerpt.",
        "evidence_locator": "Fixture heading, line 1",
        "extractor": "fixture",
        "extractor_version": "1.0",
        "extraction_confidence": "1",
        "requires_review": False,
    }
    fields.update(updates)
    return new_extracted_claim(**fields)


def _endorsement(*, status: str, candidate_ids: list[str]):
    review_item_id = "review-0123456789abcdef" if status in {"unverified", "ambiguous"} else None
    return new_normalized_endorsement(
        election_id="fixture-primary",
        race_id="fixture-race",
        source_id="the-stranger",
        status=status,
        candidate_ids=candidate_ids,
        allocation=equal_allocation(candidate_ids) if candidate_ids else {},
        published_at="2026-07-02",
        source_capture_id="capture-the-stranger-20260719T120000Z-0123456789ab",
        extracted_claim_id="claim-0123456789abcdef",
        normalization_confidence="1",
        manually_verified=False,
        review_item_id=review_item_id,
        notes=None,
    )
