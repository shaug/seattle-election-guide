"""The published personalization contract and the panel-snapshot catalog."""

import copy
import json
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from election_guide.normalization.models import CanonicalDataset
from election_guide.publication.builder import build_publication_bundle
from election_guide.publication.lens_parity import (
    FIXTURE_COMMIT,
    FIXTURE_COMPUTED_AT,
    LENS_PARITY_SELECTIONS,
    build_parity_fixture,
    restricted_dataset,
)
from election_guide.publication.models import PublicationViewModel
from election_guide.scoring import read_scoring_configuration
from election_guide.scoring.engine import score_dataset
from election_guide.serialization import canonical_json_bytes, read_json
from election_guide.sources.catalog import (
    PanelSnapshotCatalog,
    appended_panel_snapshot,
    read_panel_snapshot_catalog,
)
from election_guide.sources.models import RetiredCode
from election_guide.sources.panel import build_panel_snapshot
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parent.parent
DATASET_PATH = PROJECT_ROOT / "data" / "normalized" / "canonical-dataset.json"
REGISTRY_PATH = PROJECT_ROOT / "config" / "sources" / "default.yaml"
CATALOG_PATH = PROJECT_ROOT / "data" / "releases" / "wa-2026-primary" / "panel-snapshots.json"
SNAPSHOT_ROOT = PROJECT_ROOT / "data" / "releases" / "wa-2026-primary" / "snapshots"
SCORING_CONFIG_PATH = PROJECT_ROOT / "config" / "scoring" / "default.yaml"
NOW = datetime(2026, 7, 23, 17, 10, tzinfo=UTC)


def _bundle(dataset: CanonicalDataset | None = None) -> Any:
    if dataset is None:
        dataset = CanonicalDataset.model_validate(read_json(DATASET_PATH))
    consensus = score_dataset(
        dataset, read_scoring_configuration(SCORING_CONFIG_PATH), computed_at=NOW
    )
    return build_publication_bundle(
        dataset, consensus, git_commit="0" * 40, snapshot_root=SNAPSHOT_ROOT
    )


def _view_model_payload() -> dict[str, Any]:
    return copy.deepcopy(_bundle().view_model.model_dump(mode="json"))


def test_release_policy_enables_personalization_and_defaults_to_audited() -> None:
    policy = _bundle().view_model.personalization.policy

    assert policy.enabled is True
    assert policy.default_mode == "audited"
    assert policy.modes == ["audited", "sources"]
    assert policy.selection_combination == "additive_union"
    assert policy.weighting == "equal"
    assert policy.url_schema_version == "1"
    assert policy.comparison_hidden_by_default is True
    assert policy.maximum_url_characters == 4096


def test_payload_identifies_and_excludes_comparison_sources() -> None:
    contract = _bundle().view_model.personalization
    times = next(source for source in contract.sources if source.panel_role == "comparison")

    assert contract.policy.comparison_source_codes == [times.code]
    assert times.selectable is False
    assert times.code not in {
        code for category in contract.categories for code in category.member_source_codes
    }
    assert next(item for item in contract.categories if item.id == "comparison").selectable is False


def test_payload_reconstructs_eligibility_and_exact_allocations() -> None:
    view_model = _bundle().view_model
    contract = view_model.personalization
    code_by_id = {source.id: source.code for source in contract.sources}
    races = {race.id: race for race in (r for s in view_model.sections for r in s.races)}

    for lens_race in contract.races:
        published = races[lens_race.race_id]
        eligible = {
            cell.source_id for cell in published.source_cells if cell.state != "not_applicable"
        }
        assert lens_race.eligible_source_codes == sorted(code_by_id[item] for item in eligible)
        for cell in lens_race.cells:
            source_id = next(key for key, code in code_by_id.items() if code == cell.source_code)
            origin = next(item for item in published.source_cells if item.source_id == source_id)
            assert cell.state == origin.state
            assert cell.allocation == origin.allocation
            total = sum(
                (Fraction(value) for value in cell.allocation.values()),
                Fraction(),
            )
            assert not cell.allocation or total == 1


def test_legislative_district_sources_stay_ineligible_for_other_districts() -> None:
    contract = _bundle().view_model.personalization
    code_by_id = {source.id: source.code for source in contract.sources}
    ld37 = code_by_id["37th-district-democrats"]
    races = {race.race_id: race for race in contract.races}

    assert ld37 in races["ld-37-state-senator"].eligible_source_codes
    assert ld37 not in races["ld-43-state-senator"].eligible_source_codes
    assert ld37 in races["us-house-7"].eligible_source_codes


def test_published_scoring_identity_matches_the_audited_policy() -> None:
    scoring = _bundle().view_model.personalization.scoring
    audited = read_scoring_configuration(SCORING_CONFIG_PATH)

    assert scoring.configuration_id == audited.id
    assert scoring.allocation == audited.allocation
    assert scoring.minimum_explicit_sources == audited.minimum_explicit_sources
    assert [item.grade for item in scoring.grades] == [rule.grade for rule in audited.grades]
    assert [item.minimum_share for item in scoring.grades] == [
        str(rule.minimum_share) for rule in audited.grades
    ]
    assert scoring.missing_coverage_enters_denominator is False
    assert scoring.no_endorsement_enters_denominator is False


def test_repeated_builds_serialize_the_contract_identically() -> None:
    first = canonical_json_bytes(_bundle().view_model.personalization.model_dump(mode="json"))
    second = canonical_json_bytes(_bundle().view_model.personalization.model_dump(mode="json"))

    assert first == second


def test_version_bindings_match_the_published_panel() -> None:
    view_model = _bundle().view_model
    registry = read_source_registry(REGISTRY_PATH)
    snapshot = build_panel_snapshot(registry)

    assert view_model.personalization.panel_id == snapshot.panel_id
    assert view_model.personalization.panel_version == snapshot.panel_version
    assert view_model.personalization.panel_hash == snapshot.panel_hash
    assert view_model.personalization.panel_hash == view_model.metadata.source_panel_hash


def test_publication_rejects_a_personalization_panel_that_drifts_from_metadata() -> None:
    payload = _view_model_payload()
    payload["personalization"]["panel_id"] = "wa-2026-primary-default-sources-v9"

    with pytest.raises(ValidationError, match="panel id must match publication metadata"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_stale_personalization_allocation() -> None:
    payload = _view_model_payload()
    race = next(
        item
        for item in payload["personalization"]["races"]
        if item["cells"] and any(cell["allocation"] for cell in item["cells"])
    )
    cell = next(item for item in race["cells"] if len(item["allocation"]) == 1)
    cell["allocation"] = {"substituted-candidate": "1"}

    with pytest.raises(ValidationError, match="allocation must match"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_scoring_identity_that_reorders_tie_resolution() -> None:
    payload = _view_model_payload()
    payload["personalization"]["scoring"]["tie_precedes_grade"] = False

    with pytest.raises(ValidationError, match="resolution order must match"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_scoring_identity_that_demotes_insufficient_coverage() -> None:
    payload = _view_model_payload()
    payload["personalization"]["scoring"]["insufficient_precedes_ordinary_grade"] = False

    with pytest.raises(ValidationError, match="resolution order must match"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_an_incomplete_personalization_race() -> None:
    payload = _view_model_payload()
    race = payload["personalization"]["races"][0]
    race["eligible_source_codes"] = race["eligible_source_codes"][:-1]

    with pytest.raises(ValidationError, match="one cell per eligible source"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_selectable_comparison_source() -> None:
    payload = _view_model_payload()
    times = next(
        item for item in payload["personalization"]["sources"] if item["panel_role"] == "comparison"
    )
    times["selectable"] = True

    with pytest.raises(ValidationError, match="selectability must follow its panel role"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_category_reserved_letter_in_a_source_code() -> None:
    payload = _view_model_payload()
    payload["personalization"]["sources"][0]["code"] = "Gstr"

    with pytest.raises(ValidationError, match="category-reserved"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_category_membership_that_ignores_current_sources() -> None:
    payload = _view_model_payload()
    category = next(item for item in payload["personalization"]["categories"] if item["selectable"])
    category["member_source_codes"] = category["member_source_codes"][:-1]

    with pytest.raises(ValidationError, match="must follow current membership"):
        PublicationViewModel.model_validate(payload)


def test_committed_panel_snapshot_catalog_publishes_the_current_panel() -> None:
    catalog = read_panel_snapshot_catalog(CATALOG_PATH)
    snapshot = build_panel_snapshot(read_source_registry(REGISTRY_PATH))

    assert catalog.election_id == "wa-2026-primary"
    assert catalog.snapshot_for(snapshot.panel_id) == snapshot
    assert catalog.snapshots[-1] == snapshot


def test_appending_the_current_panel_again_is_a_deterministic_no_op() -> None:
    catalog = read_panel_snapshot_catalog(CATALOG_PATH)
    snapshot = build_panel_snapshot(read_source_registry(REGISTRY_PATH))

    assert appended_panel_snapshot(catalog, snapshot) == catalog


def test_catalog_refuses_to_rewrite_a_published_panel() -> None:
    catalog = read_panel_snapshot_catalog(CATALOG_PATH)
    published = catalog.snapshots[-1]
    edited = published.model_copy(update={"panel_hash": "a" * 64})

    with pytest.raises(ValueError, match="cannot be rewritten"):
        appended_panel_snapshot(catalog, edited)


def test_catalog_appends_a_new_panel_version() -> None:
    catalog = read_panel_snapshot_catalog(CATALOG_PATH)
    published = catalog.snapshots[-1]
    successor = published.model_copy(
        update={
            "panel_id": "wa-2026-primary-default-sources-v4",
            "panel_version": "v4",
            "panel_hash": "b" * 64,
        }
    )

    appended = appended_panel_snapshot(catalog, successor)

    assert [item.panel_id for item in appended.snapshots] == [
        published.panel_id,
        successor.panel_id,
    ]
    assert appended.snapshot_for(published.panel_id) == published


def test_catalog_rejects_a_repeated_panel_hash() -> None:
    catalog = read_panel_snapshot_catalog(CATALOG_PATH)
    published = catalog.snapshots[-1]
    collision = published.model_copy(
        update={"panel_id": "wa-2026-primary-default-sources-v4", "panel_version": "v4"}
    )

    with pytest.raises(ValueError, match="duplicates the hash"):
        appended_panel_snapshot(catalog, collision)


def test_catalog_rejects_a_duplicated_panel_id() -> None:
    catalog = read_panel_snapshot_catalog(CATALOG_PATH)
    payload = catalog.model_dump(mode="json")
    payload["snapshots"] = [payload["snapshots"][0], copy.deepcopy(payload["snapshots"][0])]

    with pytest.raises(ValidationError, match="repeats a panel id"):
        PanelSnapshotCatalog.model_validate(payload)


def test_committed_lens_parity_fixture_matches_a_fresh_generation() -> None:
    """The client parity fixture must never drift from the audited engine."""
    committed = json.loads(
        (PROJECT_ROOT / "tests" / "js" / "fixtures" / "lens-parity.json").read_text(
            encoding="utf-8"
        )
    )
    dataset = CanonicalDataset.model_validate(read_json(DATASET_PATH))
    configuration = read_scoring_configuration(SCORING_CONFIG_PATH)
    computed_at = datetime.fromisoformat(FIXTURE_COMPUTED_AT)
    consensus = score_dataset(
        dataset,
        configuration,
        computed_at=computed_at,
        allow_unresolved=True,
    )
    bundle = build_publication_bundle(
        dataset, consensus, git_commit=FIXTURE_COMMIT, snapshot_root=SNAPSHOT_ROOT
    )

    regenerated = build_parity_fixture(
        dataset,
        configuration,
        bundle.view_model,
        LENS_PARITY_SELECTIONS,
        computed_at=computed_at,
    )

    assert json.loads(json.dumps(regenerated)) == committed


def test_lens_parity_selections_cover_every_named_acceptance_case() -> None:
    names = {selection.name for selection in LENS_PARITY_SELECTIONS}
    assert {
        "empty",
        "single-source",
        "two-sources-split",
        "category-overlap-union",
        "category-plus-member",
        "wrong-district",
        "comparison-refused",
        "full-panel",
    } <= names


def test_restricting_the_panel_cannot_promote_a_nonconsensus_source() -> None:
    """The parity oracle must never widen the panel it is asked to narrow."""
    dataset = CanonicalDataset.model_validate(read_json(DATASET_PATH))
    original = {source.id: source.panel_role for source in dataset.source_registry.sources}

    restricted = restricted_dataset(dataset, set(original))

    for source in restricted.source_registry.sources:
        assert source.panel_role == original[source.id]


def _retired_source_code(dataset: CanonicalDataset) -> tuple[CanonicalDataset, str]:
    """Retire one currently-unused four-character code and return the mutated dataset."""
    registry = dataset.source_registry
    retired_code = "zret"
    tombstone = RetiredCode(
        code=retired_code,
        kind="source",
        former_id="a-retired-source",
        retired_in_panel=registry.id,
        reason="Publication discontinued.",
    )
    mutated_registry = registry.model_copy(
        update={"retired_codes": [*registry.retired_codes, tombstone]}
    )
    return dataset.model_copy(update={"source_registry": mutated_registry}), retired_code


def test_retired_codes_are_published_for_client_migration() -> None:
    dataset, retired_code = _retired_source_code(
        CanonicalDataset.model_validate(read_json(DATASET_PATH))
    )
    bundle = _bundle(dataset)

    tombstones = bundle.view_model.personalization.retired_codes
    assert len(tombstones) == 1
    assert tombstones[0].code == retired_code
    assert tombstones[0].kind == "source"
    assert tombstones[0].former_id == "a-retired-source"

    # A retired code cannot also be live; the contract's own validator would
    # catch a code reused after being retired.
    live_codes = {source.code for source in bundle.view_model.personalization.sources} | {
        category.code for category in bundle.view_model.personalization.categories
    }
    assert retired_code not in live_codes


def test_publication_rejects_duplicate_retired_codes() -> None:
    payload = _view_model_payload()
    payload["personalization"]["retired_codes"] = [
        {"code": "zret", "kind": "source", "former_id": "a", "reason": "r"},
        {"code": "zret", "kind": "source", "former_id": "b", "reason": "r"},
    ]

    with pytest.raises(ValidationError, match="retired codes must be unique"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_retired_code_still_in_live_use() -> None:
    payload = _view_model_payload()
    live_source_code = payload["personalization"]["sources"][0]["code"]
    payload["personalization"]["retired_codes"] = [
        {"code": live_source_code, "kind": "source", "former_id": "a", "reason": "r"},
    ]

    with pytest.raises(ValidationError, match="are still live"):
        PublicationViewModel.model_validate(payload)


def test_publication_rejects_a_retired_code_whose_family_contradicts_its_kind() -> None:
    payload = _view_model_payload()
    payload["personalization"]["retired_codes"] = [
        {"code": "zret", "kind": "category", "former_id": "a", "reason": "r"},
    ]

    with pytest.raises(ValidationError, match="must start with 'G'"):
        PublicationViewModel.model_validate(payload)
