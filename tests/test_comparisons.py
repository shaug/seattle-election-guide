"""The comparison display contract stays exact, ordered, and release-gated."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from election_guide.normalization.models import CanonicalDataset
from election_guide.publication.builder import build_publication_bundle
from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.scoring import read_scoring_configuration
from election_guide.scoring.engine import score_dataset
from election_guide.serialization import canonical_json_bytes, read_json

PROJECT_ROOT = Path(__file__).parent.parent
DATASET_PATH = PROJECT_ROOT / "data" / "normalized" / "canonical-dataset.json"
SCORING_CONFIG_PATH = PROJECT_ROOT / "config" / "scoring" / "default.yaml"
SNAPSHOT_ROOT = PROJECT_ROOT / "data" / "releases" / "wa-2026-primary" / "snapshots"
NOW = datetime(2026, 7, 23, 17, 10, tzinfo=UTC)


def _bundle() -> Any:
    dataset = CanonicalDataset.model_validate(read_json(DATASET_PATH))
    consensus = score_dataset(
        dataset,
        read_scoring_configuration(SCORING_CONFIG_PATH),
        computed_at=NOW,
    )
    return build_publication_bundle(
        dataset,
        consensus,
        git_commit="0" * 40,
        snapshot_root=SNAPSHOT_ROOT,
    )


def _payload() -> dict[str, Any]:
    return copy.deepcopy(_bundle().view_model.model_dump(mode="json"))


def test_comparisons_are_enabled_without_changing_personalization() -> None:
    view_model = _bundle().view_model
    before = canonical_json_bytes(view_model.personalization.model_dump(mode="json"))

    disabled = view_model.model_copy(
        update={
            "comparisons": view_model.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=False)}
            )
        }
    )

    assert view_model.comparisons.policy.enabled is True
    assert canonical_json_bytes(disabled.personalization.model_dump(mode="json")) == before


def test_display_index_matches_rendered_grouping_order_and_choice_labels() -> None:
    view_model = _bundle().view_model
    display_index = view_model.comparisons.display_index
    rendered = [
        (section_order, race_order, section, race)
        for section_order, section in enumerate(view_model.sections)
        for race_order, race in enumerate(section.races)
    ]

    assert [display.race_id for display in display_index] == [
        race.race_id for race in view_model.personalization.races
    ]
    assert len(display_index) == len({display.race_id for display in display_index})
    for display, (section_order, race_order, section, race), lens in zip(
        display_index,
        rendered,
        view_model.personalization.races,
        strict=True,
    ):
        assert (
            display.section_id,
            display.section_label,
            display.section_order,
            display.race_order,
        ) == (section.id, section.label, section_order, race_order)
        assert display.race_label == race.race_label
        names = display.candidate_names | display.measure_response_labels
        assert set(names) == set(lens.candidate_order)
        if display.race_type == "measure":
            assert display.candidate_names == {}
            assert display.measure_response_labels
        else:
            assert display.candidate_names
            assert display.measure_response_labels == {}


def test_baselines_match_published_consensus_and_every_allocation_resolves() -> None:
    view_model = _bundle().view_model
    published = {race.id: race for section in view_model.sections for race in section.races}
    lens_by_id = {race.race_id: race for race in view_model.personalization.races}

    for display in view_model.comparisons.display_index:
        race = published[display.race_id]
        assert display.baseline.leading_pick_ids == race.support_leader_candidate_ids
        assert display.baseline.share == race.winner_share
        assert display.baseline.explicit_source_count == race.explicit_endorsement_count
        names = display.candidate_names | display.measure_response_labels
        allocated = {
            candidate_id
            for cell in lens_by_id[display.race_id].cells
            for candidate_id in cell.allocation
        }
        assert allocated <= set(names)


def test_comparison_contract_round_trips_through_the_publication_schema() -> None:
    view_model = _bundle().view_model

    round_tripped = PublicationViewModel.model_validate_json(view_model.model_dump_json())

    assert round_tripped == view_model


def test_publication_rejects_a_missing_comparison_race() -> None:
    payload = _payload()
    payload["comparisons"]["display_index"].pop()

    with pytest.raises(
        ValidationError,
        match="must contain every personalization race exactly once",
    ):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_drifted_comparison_baseline() -> None:
    payload = _payload()
    payload["comparisons"]["display_index"][0]["baseline"]["explicit_source_count"] += 1

    with pytest.raises(ValidationError, match="must match published consensus"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_an_unlabeled_allocation_candidate() -> None:
    payload = _payload()
    display_by_id = {race["race_id"]: race for race in payload["comparisons"]["display_index"]}
    lens_race, allocated_id = next(
        (race, candidate_id)
        for race in payload["personalization"]["races"]
        for cell in race["cells"]
        for candidate_id in cell["allocation"]
        if candidate_id not in display_by_id[race["race_id"]]["baseline"]["leading_pick_ids"]
    )
    display = display_by_id[lens_race["race_id"]]
    display["candidate_names"].pop(allocated_id, None)
    display["measure_response_labels"].pop(allocated_id, None)

    with pytest.raises(
        ValidationError,
        match=r"must label every allocation candidate|must label every ballot choice",
    ):
        PublicationViewModel.model_validate(payload)
