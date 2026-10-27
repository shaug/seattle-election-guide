"""Ballot reading order is presentation data, independent of scores and membership."""

import json
from pathlib import Path
from typing import Any

import pytest

from election_guide.inventory.models import Inventory
from election_guide.normalization.models import CanonicalDataset
from election_guide.publication import build_publication_bundle
from election_guide.release.compiler import read_release_ledger
from election_guide.scoring import score_dataset
from election_guide.scoring.config import read_scoring_configuration

ROOT = Path(__file__).resolve().parents[1]
# Independently transcribed from the visually reviewed 12-page official composite (#609).
EXPECTED = [
    "initiative-26-645",
    "initiative-26-001",
    "initiative-26-638",
    "us-house-7",
    "us-house-9",
    "ld-11-state-representative-1",
    "ld-11-state-representative-2",
    "ld-32-state-senator",
    "ld-32-state-representative-1",
    "ld-32-state-representative-2",
    "ld-34-state-senator",
    "ld-34-state-representative-1",
    "ld-34-state-representative-2",
    "ld-36-state-senator",
    "ld-36-state-representative-1",
    "ld-36-state-representative-2",
    "ld-37-state-senator",
    "ld-37-state-representative-1",
    "ld-37-state-representative-2",
    "ld-43-state-senator",
    "ld-43-state-representative-1",
    "ld-43-state-representative-2",
    "ld-46-state-senator",
    "ld-46-state-representative-1",
    "ld-46-state-representative-2",
    "king-county-prosecuting-attorney",
    "king-county-assessor",
    "king-county-director-of-elections",
    "king-county-council-2",
    "king-county-council-4",
    "king-county-council-8",
    "supreme-court-justice-1",
    "supreme-court-justice-3",
    "supreme-court-justice-4",
    "supreme-court-justice-5",
    "supreme-court-justice-7",
    "court-of-appeals-division-1-district-1-judge-5",
    "court-of-appeals-division-1-district-1-judge-6",
    "king-county-district-court-west-judge-1",
    "king-county-district-court-west-judge-2",
    "king-county-district-court-west-judge-3",
    "king-county-district-court-west-judge-4",
    "king-county-district-court-west-judge-5",
    "seattle-city-council-5",
    "seattle-municipal-court-judge-1",
    "seattle-municipal-court-judge-2",
    "seattle-municipal-court-judge-3",
    "seattle-municipal-court-judge-4",
    "seattle-municipal-court-judge-5",
    "seattle-municipal-court-judge-6",
    "seattle-municipal-court-judge-7",
    "seattle-proposition-1-transit",
]
HEADINGS = [
    "State measures",
    "Federal",
    "State",
    "County",
    "State Supreme Court",
    "Court of Appeals, Division 1, District 1",
    "West Electoral District",
    "City of Seattle",
    "Seattle Municipal Court",
    "City of Seattle — measures",
]


def _legacy_order(inventory: Inventory) -> None:
    return None


@pytest.fixture(scope="module")
def general() -> tuple[CanonicalDataset, Any, Any]:
    dataset = CanonicalDataset.model_validate_json(
        (ROOT / "data/normalized/wa-2026-general-canonical-dataset.json").read_text()
    )
    report = score_dataset(
        dataset,
        read_scoring_configuration(ROOT / "config/scoring/default.yaml"),
        computed_at=read_release_ledger(
            ROOT / "data/releases/wa-2026-general/source-decisions.yaml"
        ).data_as_of,
        allow_unresolved=True,
    )
    bundle = build_publication_bundle(
        dataset,
        report,
        git_commit="ballot-order-test",
        snapshot_root=ROOT / "data/releases/wa-2026-general/snapshots",
    )
    return dataset, report, bundle


def test_general_bundle_follows_official_reading_order(general: Any) -> None:
    dataset, _, bundle = general
    assert len(EXPECTED) == len(set(EXPECTED)) == 52
    assert set(EXPECTED) == {race.id for race in dataset.inventory.races}
    assert [race.id for section in bundle.view_model.sections for race in section.races] == EXPECTED
    assert [section.label for section in bundle.view_model.sections] == HEADINGS
    assert [race.race_id for race in bundle.view_model.comparisons.display_index] == EXPECTED
    exported = json.loads(bundle.artifacts["publication_view_model.json"])
    assert [race["id"] for section in exported["sections"] for race in section["races"]] == EXPECTED


def test_mapping_rejects_missing_extra_duplicate_and_wrong_election(general: Any) -> None:
    from pydantic import ValidationError

    from election_guide.publication.ballot_order import BallotOrder, load_ballot_order

    dataset, _, _ = general
    order = load_ballot_order(dataset.inventory)
    assert order is not None
    for mutation, message in [
        ("missing", "complete inventory"),
        ("extra", "complete inventory"),
        ("duplicate", "duplicate ballot contest"),
        ("section", "duplicate ballot section"),
        ("position", "reading order"),
        ("election", "election does not match"),
        ("version", "Input should be '1'"),
    ]:
        payload = order.model_dump(mode="json")
        if mutation == "missing":
            payload["sections"][0]["contests"].pop()
        elif mutation == "extra":
            payload["sections"][-1]["contests"][0]["race_id"] = "unmapped-contest"
        elif mutation == "duplicate":
            payload["sections"][0]["contests"][1]["race_id"] = EXPECTED[0]
        elif mutation == "section":
            payload["sections"][1]["id"] = payload["sections"][0]["id"]
        elif mutation == "position":
            payload["sections"][0]["contests"].reverse()
        elif mutation == "election":
            payload["election_id"] = "wa-2026-primary"
        else:
            payload["schema_version"] = "2"
        with pytest.raises((ValidationError, ValueError), match=message):
            BallotOrder.model_validate(payload).validate_inventory(dataset.inventory)


def test_map_is_validated_before_publication_subset_and_unmapped_elections_fall_back(
    general: Any,
) -> None:
    from election_guide.publication.ballot_order import load_ballot_order

    dataset, _, _ = general
    inventory = dataset.inventory.model_copy(deep=True)
    inventory.races[0].publication_eligible = False
    assert load_ballot_order(inventory) is not None
    inventory.races.pop()
    with pytest.raises(ValueError, match="complete inventory"):
        load_ballot_order(inventory)
    inventory.election.id = "wa-2028-general"
    assert load_ballot_order(inventory) is None


def test_ordering_preserves_scores_sources_choices_filters_and_input_data(
    general: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from election_guide.publication import builder
    from election_guide.rendering.context import filter_scope_groups

    dataset, report, bundle = general
    before = dataset.model_dump_json()
    monkeypatch.setattr(builder, "load_ballot_order", _legacy_order)
    legacy = build_publication_bundle(
        dataset,
        report,
        git_commit="ballot-order-test",
        snapshot_root=ROOT / "data/releases/wa-2026-general/snapshots",
    )
    new_races = {r.id: r for section in bundle.view_model.sections for r in section.races}
    old_races = {r.id: r for section in legacy.view_model.sections for r in section.races}
    assert new_races.keys() == old_races.keys()
    assert any(r.explicit_endorsement_count == 0 for r in new_races.values())
    for race_id, race in new_races.items():
        assert race.model_dump(exclude={"section_id", "section_label"}) == old_races[
            race_id
        ].model_dump(exclude={"section_id", "section_label"})
    assert bundle.view_model.sources == legacy.view_model.sources
    assert bundle.artifacts["consensus.json"] == legacy.artifacts["consensus.json"]
    assert {r.race_id: r for r in bundle.view_model.personalization.races} == {
        r.race_id: r for r in legacy.view_model.personalization.races
    }
    assert {r.id for s in bundle.view_model.public_view().sections for r in s.races} == {
        r.id for s in legacy.view_model.public_view().sections for r in s.races
    }
    assert filter_scope_groups(bundle.view_model) == filter_scope_groups(legacy.view_model)
    for token in ["state", "city", "other", "Legislative District 43"]:
        selected = [
            r.id for s in bundle.view_model.sections for r in s.races if token in r.filter_tokens
        ]
        assert selected == [rid for rid in EXPECTED if rid in set(selected)]
        assert set(selected) == {
            rid for rid, race in old_races.items() if token in race.filter_tokens
        }
    assert dataset.model_dump_json() == before


def test_primary_publication_artifacts_stay_on_legacy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from election_guide.publication import builder
    from tests.test_personalization import _bundle  # pyright: ignore[reportPrivateUsage]

    before = _bundle()
    monkeypatch.setattr(builder, "load_ballot_order", _legacy_order)
    assert _bundle().artifacts == before.artifacts


def test_rendered_guide_overview_print_and_comparisons_share_sequence(general: Any) -> None:
    import re

    from election_guide.rendering import read_rendering_configuration, render_html_document
    from election_guide.rendering.context import comparison_sections
    from election_guide.rendering.documents import render_comparison_document

    _, _, bundle = general
    vm = bundle.view_model.public_view()
    visible = [r.id for s in vm.guide_sections for r in s.races]
    assert visible == [rid for rid in EXPECTED if rid in set(visible)]
    sections = comparison_sections(vm)
    assert [row.race_id for s in sections for row in s.rows] == visible
    html = render_html_document(
        vm, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    )
    assert re.findall(r'data-publication-race-id="([^"]+)"', html) == visible
    # Compact overview and print reuse these same cards; CSS changes presentation, not order.
    assert "@media print" in html
    compare = render_comparison_document(vm, public_site_url="https://seattleelections.guide")
    assert re.findall(r'data-comparison-race="([^"]+)"', compare) == visible


def test_missing_mapped_file_never_silently_uses_legacy_order(
    general: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from election_guide.publication.ballot_order import BALLOT_ORDER_FILES, load_ballot_order

    dataset, _, _ = general
    monkeypatch.setitem(BALLOT_ORDER_FILES, "wa-2026-general", tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        load_ballot_order(dataset.inventory)


def test_comparison_saved_section_filters_keep_their_previous_membership(general: Any) -> None:
    _, _, bundle = general
    displays = bundle.view_model.comparisons.display_index
    assert {r.race_id for r in displays if getattr(r, "filter_section_id", None) == "other"} == {
        "court-of-appeals-division-1-district-1-judge-5",
        "court-of-appeals-division-1-district-1-judge-6",
        *[f"king-county-district-court-west-judge-{n}" for n in range(1, 6)],
    }
    assert {r.race_id for r in displays if getattr(r, "filter_section_id", None) == "city"} == {
        "seattle-city-council-5",
        "seattle-proposition-1-transit",
        *[f"seattle-municipal-court-judge-{n}" for n in range(1, 8)],
    }
