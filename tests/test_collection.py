import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

import election_guide.collection.refresh as collection_refresh
from election_guide.collection import (
    AdapterDecision,
    AdapterSpec,
    DecisionDiff,
    RefreshEvent,
    extract_decisions,
    read_adapter_spec,
    read_extraction_snapshot,
    refresh_source,
    validate_adapter,
)
from election_guide.collection.adapters import ExtractionError
from election_guide.collection.refresh import RefreshOrderError, semantic_diff
from election_guide.evidence.models import CaptureRequest
from election_guide.inventory.importer import read_inventory
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parent.parent
EVIDENCE_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "evidence"
COLLECTION_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "collection"
CHECKED_AT = datetime(2026, 7, 20, 7, 0, tzinfo=UTC)


def test_project_adapter_is_complete_and_inventory_validated() -> None:
    spec = read_adapter_spec(PROJECT_ROOT / "config" / "adapters" / "transit-riders-union.yaml")
    inventory = read_inventory(
        PROJECT_ROOT / "data" / "normalized" / "wa-2026-primary-inventory.json"
    )
    registry = read_source_registry(PROJECT_ROOT / "config" / "sources" / "default.yaml")

    validate_adapter(spec, inventory, registry)
    decisions = extract_decisions(
        spec,
        (COLLECTION_FIXTURES / "transit-riders-union.html").read_bytes(),
        media_type="text/html",
    )

    assert [decision.race_id for decision in decisions] == [
        "king-county-council-2",
        "ld-32-state-representative-1",
        "seattle-city-council-5",
    ]
    assert decisions[0].status == "dual_endorsement"


@pytest.mark.parametrize(
    ("kind", "filename", "media_type", "pattern"),
    [
        ("static_html", "static.html", "text/html", "Fixture Candidate"),
        ("dynamic_html", "static.html", "text/html", "Fixture Candidate"),
        ("pdf", "endorsements.pdf", "application/pdf", "Fixture 2026 Primary Endorsements"),
        (
            "image",
            "endorsement-card.svg",
            "image/svg+xml",
            r"Fixture Candidate\s+Seattle City Council District 5",
        ),
    ],
)
def test_every_adapter_kind_extracts_stable_local_fixture(
    kind: str, filename: str, media_type: str, pattern: str
) -> None:
    spec = _spec(kind, pattern)

    decisions = extract_decisions(
        spec, (EVIDENCE_FIXTURES / filename).read_bytes(), media_type=media_type
    )

    assert decisions[0].candidate_ids == ["seattle-city-council-5--nilu-jenks"]
    review_required = kind in {"static_html", "dynamic_html", "image"}
    assert decisions[0].requires_review is review_required
    assert decisions[0].extraction_confidence == ("0.99" if review_required else "1")


def test_raster_image_requires_explicit_reviewable_ocr() -> None:
    spec = _spec("image", "Fixture Candidate")

    with pytest.raises(ExtractionError, match="requires OCR"):
        extract_decisions(spec, b"not decoded by the adapter", media_type="image/png")

    decisions = extract_decisions(
        spec,
        b"not decoded by the adapter",
        media_type="image/png",
        ocr_text="Fixture Candidate",
        ocr_confidence="0.875",
    )
    assert decisions[0].requires_review is True
    assert decisions[0].extraction_confidence == "0.875"


def test_corrected_ocr_reprocesses_identical_image_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (2, 2), "white").save(source)
    paths = _refresh_paths(tmp_path)
    spec = AdapterSpec.model_validate(
        {
            "source_id": "transit-riders-union",
            "adapter_kind": "image",
            "extractor_version": "1.0.0",
            "complete": True,
            "decision_pattern": r"(?m)^.*Candidate$",
            "rules": [
                {
                    "race_id": "race-a",
                    "pattern": "First Candidate",
                    "candidate_ids": ["candidate-a"],
                    "evidence_locator": "OCR fixture A.",
                },
                {
                    "race_id": "race-b",
                    "pattern": "Second Candidate",
                    "candidate_ids": ["candidate-b"],
                    "evidence_locator": "OCR fixture B.",
                },
            ],
        }
    )

    first = refresh_source(
        spec,
        _image_request(CHECKED_AT),
        source,
        **paths,
        ocr_text="First Candidate",
        ocr_confidence="0.5",
    )
    corrected = refresh_source(
        spec,
        _image_request(CHECKED_AT + timedelta(minutes=1)),
        source,
        **paths,
        ocr_text="Second Candidate",
        ocr_confidence="0.99",
    )

    assert first.snapshot_id != corrected.snapshot_id
    assert corrected.content_changed is False
    assert [(item.race_id, item.kind) for item in corrected.diff] == [
        ("race-a", "removed"),
        ("race-b", "added"),
    ]
    assert len(list(paths["manifest_dir"].glob("*.json"))) == 1


def test_rule_mismatch_fails_instead_of_inventing_a_decision() -> None:
    spec = _spec("static_html", "Missing Candidate")
    spec.decision_pattern = "Fixture Candidate"

    with pytest.raises(ExtractionError, match="coverage does not match"):
        extract_decisions(
            spec,
            (EVIDENCE_FIXTURES / "static.html").read_bytes(),
            media_type="text/html",
        )


def test_complete_adapter_rejects_an_unconfigured_decision() -> None:
    spec = _spec("static_html", "Fixture Candidate")
    spec.decision_pattern = r"(?m)^.*Candidate$"

    with pytest.raises(ExtractionError, match="coverage does not match"):
        extract_decisions(
            spec,
            b"<p>Fixture Candidate</p><p>Unexpected Candidate</p>",
            media_type="text/html",
        )


def test_refresh_is_immutable_incremental_and_semantic(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    paths = _refresh_paths(tmp_path)

    created = _refresh(
        _spec("static_html", "Fixture Candidate"),
        _request(CHECKED_AT),
        source,
        paths,
    )
    unchanged = _refresh(
        _spec("static_html", "Fixture Candidate"),
        _request(CHECKED_AT + timedelta(minutes=1)),
        source,
        paths,
    )
    source.write_text("<p>Updated Fixture Candidate</p>", encoding="utf-8")
    content_only = _refresh(
        _spec("static_html", "Updated Fixture Candidate"),
        _request(CHECKED_AT + timedelta(minutes=2)),
        source,
        paths,
    )
    changed_spec = _spec("static_html", "Updated Fixture Candidate")
    changed_spec.rules[0].candidate_ids = ["seattle-city-council-5--replacement"]
    changed = _refresh(
        changed_spec,
        _request(CHECKED_AT + timedelta(minutes=3)),
        source,
        paths,
    )

    assert created.status == "created"
    assert [item.kind for item in created.diff] == ["added"]
    assert unchanged.status == "unchanged"
    assert unchanged.snapshot_id == created.snapshot_id
    assert content_only.status == "updated" and content_only.diff == []
    assert changed.content_changed is False
    assert [item.kind for item in changed.diff] == ["changed"]
    assert len(list(paths["manifest_dir"].glob("*.json"))) == 2
    assert len(list(paths["extraction_dir"].glob("*.json"))) == 3
    assert len(list(paths["refresh_dir"].glob("*.json"))) == 4


def test_failed_extraction_keeps_last_verified_snapshot_and_reuses_capture(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.html"
    paths = _refresh_paths(tmp_path)
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    created = _refresh(
        _spec("static_html", "Fixture Candidate"), _request(CHECKED_AT), source, paths
    )
    source.write_text("<p>New wording</p>", encoding="utf-8")
    failed = _refresh(
        _spec("static_html", "Fixture Candidate"),
        _request(CHECKED_AT + timedelta(minutes=1)),
        source,
        paths,
    )
    recovered = _refresh(
        _spec("static_html", "New wording"),
        _request(CHECKED_AT + timedelta(minutes=2)),
        source,
        paths,
    )

    assert failed.status == "failed"
    assert failed.previous_snapshot_id == created.snapshot_id
    assert failed.snapshot_id is None
    assert len(list(paths["extraction_dir"].glob("*.json"))) == 2
    assert len(list(paths["manifest_dir"].glob("*.json"))) == 2
    assert recovered.status == "updated"


def test_refresh_classifies_a_disappearing_known_decision_as_removed(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    paths = _refresh_paths(tmp_path)
    spec = AdapterSpec.model_validate(
        {
            "source_id": "transit-riders-union",
            "adapter_kind": "static_html",
            "extractor_version": "1.0.0",
            "complete": True,
            "decision_pattern": r"(?m)^.*Candidate$",
            "rules": [
                {
                    "race_id": "race-a",
                    "pattern": "First Candidate",
                    "candidate_ids": ["candidate-a"],
                    "evidence_locator": "First fixture decision.",
                },
                {
                    "race_id": "race-b",
                    "pattern": "Second Candidate",
                    "candidate_ids": ["candidate-b"],
                    "evidence_locator": "Second fixture decision.",
                },
            ],
        }
    )
    source.write_text("<p>First Candidate</p><p>Second Candidate</p>", encoding="utf-8")
    _refresh(spec, _request(CHECKED_AT), source, paths)
    source.write_text("<p>First Candidate</p>", encoding="utf-8")

    event = _refresh(spec, _request(CHECKED_AT + timedelta(minutes=1)), source, paths)

    assert [(item.race_id, item.kind) for item in event.diff] == [("race-b", "removed")]


def test_orphan_snapshot_never_becomes_the_committed_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    paths = _refresh_paths(tmp_path)
    initial_spec = _spec("static_html", "Fixture Candidate")
    initial = _refresh(initial_spec, _request(CHECKED_AT), source, paths)
    changed_spec = _spec("static_html", "Fixture Candidate")
    changed_spec.rules[0].candidate_ids = ["seattle-city-council-5--replacement"]
    original_write_event = collection_refresh._write_event  # pyright: ignore[reportPrivateUsage]

    def fail_event_write(event: RefreshEvent, directory: Path) -> RefreshEvent:
        del event, directory
        raise OSError("injected event failure")

    monkeypatch.setattr(collection_refresh, "_write_event", fail_event_write)
    with pytest.raises(OSError, match="injected event failure"):
        _refresh(
            changed_spec,
            _request(CHECKED_AT + timedelta(minutes=1)),
            source,
            paths,
        )
    monkeypatch.setattr(collection_refresh, "_write_event", original_write_event)

    recovered = _refresh(
        changed_spec,
        _request(CHECKED_AT + timedelta(minutes=2)),
        source,
        paths,
    )

    assert recovered.previous_snapshot_id == initial.snapshot_id
    assert [item.kind for item in recovered.diff] == ["changed"]


def test_refresh_rejects_same_second_history_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    paths = _refresh_paths(tmp_path)
    _refresh(_spec("static_html", "Fixture Candidate"), _request(CHECKED_AT), source, paths)

    with pytest.raises(RefreshOrderError, match="must be later"):
        _refresh(
            _spec("static_html", "Fixture Candidate"),
            _request(CHECKED_AT),
            source,
            paths,
        )

    assert len(list(paths["extraction_dir"].glob("*.json"))) == 1
    assert len(list(paths["refresh_dir"].glob("*.json"))) == 1


def test_unchanged_refresh_verifies_stored_capture(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    paths = _refresh_paths(tmp_path)
    initial = _refresh(
        _spec("static_html", "Fixture Candidate"), _request(CHECKED_AT), source, paths
    )
    manifest = json.loads(
        (paths["manifest_dir"] / f"{initial.capture_id}.json").read_text(encoding="utf-8")
    )
    (paths["storage_root"] / manifest["storage_reference"]).unlink()

    event = _refresh(
        _spec("static_html", "Fixture Candidate"),
        _request(CHECKED_AT + timedelta(minutes=1)),
        source,
        paths,
    )

    assert event.status == "failed"
    assert event.previous_snapshot_id == initial.snapshot_id
    assert "stored capture verification failed" in (event.error or "")


def test_changed_refresh_verifies_its_previous_capture(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    paths = _refresh_paths(tmp_path)
    initial = _refresh(
        _spec("static_html", "Fixture Candidate"), _request(CHECKED_AT), source, paths
    )
    manifest = json.loads(
        (paths["manifest_dir"] / f"{initial.capture_id}.json").read_text(encoding="utf-8")
    )
    (paths["storage_root"] / manifest["storage_reference"]).unlink()
    source.write_text("<p>Updated Fixture Candidate</p>", encoding="utf-8")

    event = _refresh(
        _spec("static_html", "Updated Fixture Candidate"),
        _request(CHECKED_AT + timedelta(minutes=1)),
        source,
        paths,
    )

    assert event.status == "failed"
    assert event.previous_snapshot_id == initial.snapshot_id
    assert len(list(paths["extraction_dir"].glob("*.json"))) == 1


def test_semantic_diff_reports_added_changed_and_removed() -> None:
    first = _decision("race-a", "candidate-a")
    old = _decision("race-b", "candidate-b")
    changed = _decision("race-b", "candidate-c")
    removed = _decision("race-c", "candidate-d")

    diff = semantic_diff([old, removed], [first, changed])

    assert [(item.race_id, item.kind) for item in diff] == [
        ("race-a", "added"),
        ("race-b", "changed"),
        ("race-c", "removed"),
    ]


def test_changed_diff_rejects_identical_semantics() -> None:
    decision = _decision("race-a", "candidate-a")

    with pytest.raises(ValidationError, match="must alter decision semantics"):
        DecisionDiff(kind="changed", race_id="race-a", before=decision, after=decision)


def test_hidden_html_and_svg_text_are_not_extracted() -> None:
    html_spec = _spec("static_html", "Visible Candidate")
    html = b"<p hidden>Visible Candidate</p><p>Visible Candidate</p>"
    svg_spec = _spec("image", "Visible Candidate")
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg">
      <text style="display:none">Visible Candidate</text>
      <text>Visible Candidate</text>
    </svg>"""

    html_decisions = extract_decisions(html_spec, html, media_type="text/html")
    svg_decisions = extract_decisions(svg_spec, svg, media_type="image/svg+xml")
    assert len(html_decisions) == 1 and html_decisions[0].requires_review
    assert len(svg_decisions) == 1 and svg_decisions[0].requires_review


def test_stylesheet_visibility_requires_review_and_hidden_void_tags_do_not_leak() -> None:
    spec = _spec("static_html", "Visible Candidate")
    artifact = b"""
      <style>.hidden { display: none }</style>
      <br hidden>
      <p class="hidden">Visible Candidate</p>
    """

    decisions = extract_decisions(spec, artifact, media_type="text/html")

    assert len(decisions) == 1
    assert decisions[0].requires_review is True
    assert decisions[0].extraction_confidence == "0.99"


def test_adapter_validation_uses_canonical_eligibility_and_discovery_media() -> None:
    inventory = read_inventory(
        PROJECT_ROOT / "data" / "normalized" / "wa-2026-primary-inventory.json"
    )
    registry = read_source_registry(PROJECT_ROOT / "config" / "sources" / "default.yaml")
    ineligible_race = next(race for race in inventory.races if not race.publication_eligible)
    ineligible = _spec("static_html", "Fixture Candidate")
    ineligible.rules[0].race_id = ineligible_race.id
    ineligible.rules[0].candidate_ids = [ineligible_race.choices[0].id]

    with pytest.raises(ValueError, match="outside source eligibility"):
        validate_adapter(ineligible, inventory, registry)

    wrong_media = _spec("static_html", "Fixture Candidate")
    wrong_media.source_id = "washington-state-labor-council"
    with pytest.raises(ValueError, match="conflicts with discovered media type"):
        validate_adapter(wrong_media, inventory, registry)


def test_snapshot_reader_rejects_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>Fixture Candidate</p>", encoding="utf-8")
    paths = _refresh_paths(tmp_path)
    event = _refresh(_spec("static_html", "Fixture Candidate"), _request(CHECKED_AT), source, paths)
    snapshot_path = paths["extraction_dir"] / f"{event.snapshot_id}.json"
    raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    raw["extractor_version"] = "9.9.9"
    snapshot_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="identity does not match"):
        read_extraction_snapshot(snapshot_path)


def _spec(kind: str, pattern: str) -> AdapterSpec:
    return AdapterSpec.model_validate(
        {
            "source_id": "transit-riders-union",
            "adapter_kind": kind,
            "extractor_version": "1.0.0",
            "complete": True,
            "decision_pattern": pattern,
            "rules": [
                {
                    "race_id": "seattle-city-council-5",
                    "pattern": pattern,
                    "candidate_ids": ["seattle-city-council-5--nilu-jenks"],
                    "evidence_locator": "Fixture decision.",
                }
            ],
        }
    )


def _decision(race_id: str, candidate_id: str) -> AdapterDecision:
    return AdapterDecision(
        race_id=race_id,
        status="endorsed",
        candidate_ids=[candidate_id],
        evidence_excerpt="Fixture",
        evidence_locator="Fixture",
        requires_review=False,
        extraction_confidence="1",
    )


def _request(retrieved_at: datetime) -> CaptureRequest:
    return CaptureRequest(
        source_id="transit-riders-union",
        requested_url="https://example.com/endorsements",
        canonical_url="https://example.com/endorsements",
        retrieved_at=retrieved_at,
        http_status=200,
        media_type="text/html",
        title="Fixture endorsements",
        capture_method="static_html",
        redistribution="permitted",
        redistribution_note="Test fixture.",
    )


def _image_request(retrieved_at: datetime) -> CaptureRequest:
    return CaptureRequest(
        source_id="transit-riders-union",
        requested_url="https://example.com/endorsements.png",
        canonical_url="https://example.com/endorsements.png",
        retrieved_at=retrieved_at,
        http_status=200,
        media_type="image/png",
        title="Fixture endorsements",
        capture_method="image",
        redistribution="permitted",
        redistribution_note="Test fixture.",
    )


def _refresh_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "storage_root": tmp_path / "snapshots",
        "manifest_dir": tmp_path / "manifests",
        "extraction_dir": tmp_path / "extractions",
        "refresh_dir": tmp_path / "refreshes",
    }


def _refresh(
    spec: AdapterSpec,
    request: CaptureRequest,
    source: Path,
    paths: dict[str, Path],
) -> RefreshEvent:
    return refresh_source(
        spec,
        request,
        source,
        storage_root=paths["storage_root"],
        manifest_dir=paths["manifest_dir"],
        extraction_dir=paths["extraction_dir"],
        refresh_dir=paths["refresh_dir"],
    )
