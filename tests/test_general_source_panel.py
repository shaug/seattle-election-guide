import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.normalization.models import CanonicalDataset
from election_guide.publication import build_publication_bundle
from election_guide.release import verify_release_compilation
from election_guide.scoring import score_dataset
from election_guide.scoring.config import read_scoring_configuration
from election_guide.sources.catalog import (
    appended_panel_snapshot,
    read_panel_snapshot_catalog,
)
from election_guide.sources.panel import build_panel_snapshot
from election_guide.sources.registry import read_source_registry

PROJECT_ROOT = Path(__file__).parents[1]
PRIMARY_REGISTRY_PATH = PROJECT_ROOT / "config/sources/default.yaml"
GENERAL_REGISTRY_PATH = PROJECT_ROOT / "config/sources/wa-2026-general.yaml"
GENERAL_INVENTORY_PATH = PROJECT_ROOT / "data/normalized/wa-2026-general-inventory.json"
GENERAL_LEDGER_PATH = PROJECT_ROOT / "data/releases/wa-2026-general/source-decisions.yaml"
GENERAL_DATASET_PATH = PROJECT_ROOT / "data/normalized/wa-2026-general-canonical-dataset.json"
GENERAL_SNAPSHOT_ROOT = PROJECT_ROOT / "data/releases/wa-2026-general/snapshots"
GENERAL_MANIFEST_DIR = PROJECT_ROOT / "data/releases/wa-2026-general/manifests"
GENERAL_CATALOG_PATH = PROJECT_ROOT / "data/releases/wa-2026-general/panel-snapshots.json"

PRESERVED_SOURCE_FIELDS = (
    "code",
    "reporting_category_id",
    "selection_category_ids",
    "geographic_kind",
    "panel_role",
    "eligibility",
    "publisher_id",
    "overlap_group_ids",
)


def test_general_source_registry_validates_through_cli() -> None:
    result = CliRunner().invoke(
        app,
        [
            "sources",
            "validate",
            str(GENERAL_REGISTRY_PATH),
            "--inventory-path",
            str(GENERAL_INVENTORY_PATH),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == (
        "source registry: valid (51 proposed; 45 consensus, 1 comparison, 5 excluded)"
    )


def test_general_release_compilation_reproduces_committed_artifacts() -> None:
    dataset = verify_release_compilation(
        GENERAL_LEDGER_PATH,
        GENERAL_INVENTORY_PATH,
        GENERAL_REGISTRY_PATH,
        GENERAL_DATASET_PATH,
        GENERAL_SNAPSHOT_ROOT,
        GENERAL_MANIFEST_DIR,
    )

    assert dataset.source_registry == read_source_registry(GENERAL_REGISTRY_PATH)


def test_compiled_general_guide_includes_washingtoncan_initiative_recommendations(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "canonical-dataset.json"
    result = CliRunner().invoke(
        app,
        [
            "release",
            "compile",
            str(GENERAL_LEDGER_PATH),
            "--inventory-path",
            str(GENERAL_INVENTORY_PATH),
            "--registry-path",
            str(GENERAL_REGISTRY_PATH),
            "--output-path",
            str(output_path),
            "--snapshot-root",
            str(tmp_path / "snapshots"),
            "--manifest-dir",
            str(tmp_path / "manifests"),
        ],
    )

    assert result.exit_code == 0, result.output
    dataset = json.loads(output_path.read_text())
    recommendations = {
        endorsement["race_id"]: endorsement["candidate_ids"]
        for endorsement in dataset["endorsements"]
        if endorsement["source_id"] == "washington-community-action-network"
    }
    assert recommendations == {
        "us-house-7": ["us-house-7--pramila-jayapal"],
        "ld-11-state-representative-1": ["ld-11-state-representative-1--david-hackney"],
        "initiative-26-001": ["initiative-26-001--no"],
        "initiative-26-638": ["initiative-26-638--no"],
        "initiative-26-645": ["initiative-26-645--no"],
        "king-county-council-2": ["king-county-council-2--rebecca-saldana"],
        "king-county-council-8": ["king-county-council-8--teresa-mosqueda"],
        "ld-37-state-senator": ["ld-37-state-senator--chipalo-street"],
    }


def test_general_panel_snapshot_preserves_frozen_identity_contract() -> None:
    registry = read_source_registry(GENERAL_REGISTRY_PATH)
    committed_catalog = read_panel_snapshot_catalog(GENERAL_CATALOG_PATH)
    current_projection = build_panel_snapshot(registry)

    assert committed_catalog.election_id == "wa-2026-general"
    assert len(committed_catalog.snapshots) == 2
    published = committed_catalog.snapshots[0]
    assert published.panel_id == "wa-2026-general-default-sources-v1"
    assert published.panel_hash == (
        "b0fb2a603bd98da49d3282d2daa0cb55ff56e0bbdd46104c8b5a4a441b747a95"
    )
    assert current_projection == committed_catalog.snapshots[-1]
    assert current_projection.panel_id == "wa-2026-general-default-sources-v2"
    assert current_projection.panel_hash != published.panel_hash
    old_democrats = next(item for item in published.categories if item.code == "Gdem")
    current_democrats = next(item for item in current_projection.categories if item.code == "Gdem")
    assert "ydwa" not in old_democrats.member_source_codes
    assert current_democrats.member_source_codes == sorted(
        [*old_democrats.member_source_codes, "ydwa"]
    )
    assert (
        published.sources
        == build_panel_snapshot(read_source_registry(PRIMARY_REGISTRY_PATH)).sources
    )
    assert appended_panel_snapshot(committed_catalog, current_projection) == committed_catalog


def test_general_panel_preserves_primary_selection_contract() -> None:
    primary = read_source_registry(PRIMARY_REGISTRY_PATH)
    general = read_source_registry(GENERAL_REGISTRY_PATH)

    assert general.id == "wa-2026-general-default-sources-v2"
    assert general.election_id == "wa-2026-general"
    assert general.research_cutoff == general.frozen_at
    assert general.frozen_at > datetime(2026, 9, 4, tzinfo=UTC)
    assert general.categories == primary.categories
    assert general.retired_codes == primary.retired_codes
    assert general.overlap_groups[1:] == primary.overlap_groups
    affiliation = general.overlap_groups[0]
    assert affiliation.id == "nondriver-affiliation"
    assert set(affiliation.member_ids) == {"disability-mobility-initiative", "nondriver-action"}
    assert [source.id for source in general.sources[:48]] == [
        source.id for source in primary.sources
    ]
    assert {source.id: source.code for source in general.sources[48:]} == {
        "young-democrats-of-washington": "ydwa",
        "nondriver-action": "nact",
        "citizens-against-aipac-corruption": "caac",
    }

    primary_by_id = {source.id: source for source in primary.sources}
    for general_source in general.sources[:48]:
        primary_source = primary_by_id[general_source.id]
        for field in PRESERVED_SOURCE_FIELDS:
            if (
                general_source.id == "disability-mobility-initiative"
                and field == "overlap_group_ids"
            ):
                assert general_source.overlap_group_ids == ["nondriver-affiliation"]
                assert general_source.panel_role == "excluded"
                continue
            assert getattr(general_source, field) == getattr(primary_source, field), (
                general_source.id,
                field,
            )


def test_general_additions_preserve_verified_choices_and_coendorsement_allocations() -> None:
    dataset = json.loads(GENERAL_DATASET_PATH.read_text())
    assessment = json.loads(
        (
            PROJECT_ROOT / "data/review/source-assessments/wa-2026-general-20261011/decisions.json"
        ).read_text()
    )
    admitted = {
        "young-democrats-of-washington",
        "nondriver-action",
        "citizens-against-aipac-corruption",
    }
    by_key = {(row["source_id"], row["race_id"]): row for row in dataset["endorsements"]}
    dual_count = 0
    for source in assessment["sources"]:
        if source["source_id"] not in admitted:
            continue
        for decision in source["decisions"]:
            row = by_key[source["source_id"], decision["race_id"]]
            assert row["candidate_ids"] == decision["candidate_ids"]
            if len(row["candidate_ids"]) == 2:
                assert set(row["allocation"].values()) == {"1/2"}
                dual_count += 1
    assert dual_count == 3
    assert sum(row["source_id"] in admitted for row in dataset["endorsements"]) == 21
    tech = by_key["tech-4-taxes", "initiative-26-645"]
    assert tech["candidate_ids"] == ["initiative-26-645--no"]
    assert tech["allocation"] == {"initiative-26-645--no": "1"}
    assert len(dataset["endorsements"]) == 925
    assert not {"king-county-republican-party", "progressive-voters-guide"} & {
        row["source_id"] for row in dataset["endorsements"]
    }


def test_october18_additions_do_not_inherit_earlier_source_provenance() -> None:
    approval = json.loads(
        (PROJECT_ROOT / "data/review/approvals/wa-2026-general-2026-10-18.json").read_text()
    )
    dataset = json.loads(GENERAL_DATASET_PATH.read_text())
    by_key = {(row["source_id"], row["race_id"]): row for row in dataset["endorsements"]}
    approved_at = datetime.fromisoformat(approval["reviewed_at"])

    for decision in approval["approved_decisions"]:
        key = (decision["source_id"], decision["race_id"])
        row = by_key[key]
        assert datetime.fromisoformat(row["reviewed_at"]) >= approved_at, key
        if not approval["prior_source_reviews"].get(decision["source_id"]):
            continue
        original = json.loads(
            (
                PROJECT_ROOT / "data/manifests/evidence" / f"{decision['capture_id']}.json"
            ).read_text()
        )
        compiled = json.loads(
            (GENERAL_MANIFEST_DIR / f"{row['source_capture_id']}.json").read_text()
        )
        assert datetime.fromisoformat(compiled["retrieved_at"]) >= datetime.fromisoformat(
            original["retrieved_at"]
        ), key


@pytest.mark.parametrize(
    ("source_id", "race_id", "publication_url", "retained_race_id", "retained_url"),
    [
        (
            "46th-district-democrats",
            "seattle-proposition-1-transit",
            "https://www.46dems.org/2026_46th_district_dems_endorsed_candidates_positions",
            "us-house-7",
            "https://www.46dems.org/2026_46th_district_dems_endorsed_candidates_positions",
        ),
        (
            "11th-district-democrats",
            "king-county-director-of-elections",
            "https://us17.campaign-archive.com/?u=c75f17fe2b6e715cad36922d4&id=65cbd68a41",
            "us-house-9",
            "https://us17.campaign-archive.com/?u=c75f17fe2b6e715cad36922d4&id=c0097e484d",
        ),
        (
            "seattle-democratic-socialists",
            "initiative-26-645",
            "https://seattledsa.org/event/nseattlecanvass/",
            "ld-37-state-representative-2",
            "https://seattledsa.org/event/jaelynn-scott-37ld-campaign-kick-off-canvass/",
        ),
        *[
            (
                "transit-riders-union",
                race_id,
                "https://transitriders.org/2026-general-election-endorsements/",
                "king-county-council-2",
                "https://transitriders.org/transit-riders-union-2026-general-election-endorsements/",
            )
            for race_id in (
                "seattle-proposition-1-transit",
                "initiative-26-645",
                "initiative-26-001",
                "initiative-26-638",
            )
        ],
        *[
            (
                "seattle-times-editorial-board",
                race_id,
                "https://www.seattletimes.com/opinion/editorials/"
                "unendorseables-these-lawmakers-once-received-times-endorsements-not-this-time/",
                "ld-37-state-representative-2",
                "https://www.seattletimes.com/opinion/editorials/",
            )
            for race_id in (
                "ld-36-state-senator",
                "ld-37-state-senator",
                "ld-46-state-senator",
            )
        ],
    ],
)
def test_new_endorsement_receipts_open_the_approved_publication(
    source_id: str,
    race_id: str,
    publication_url: str,
    retained_race_id: str,
    retained_url: str,
) -> None:
    dataset = CanonicalDataset.model_validate_json(GENERAL_DATASET_PATH.read_bytes())
    report = score_dataset(
        dataset,
        read_scoring_configuration(PROJECT_ROOT / "config/scoring/default.yaml"),
        computed_at=max(row.reviewed_at for row in dataset.endorsements if row.reviewed_at),
    )
    bundle = build_publication_bundle(
        dataset, report, git_commit="receipt-regression", snapshot_root=GENERAL_SNAPSHOT_ROOT
    )
    cells = {
        (cell.source_id, race.id): cell
        for section in bundle.view_model.sections
        for race in section.races
        for cell in race.source_cells
    }
    assert cells[source_id, race_id].evidence_url == publication_url
    assert cells[source_id, retained_race_id].evidence_url == retained_url
    exported = {
        (row["source_id"], row["race_id"]): row
        for row in csv.DictReader(io.StringIO(bundle.artifacts["endorsement_records.csv"].decode()))
    }
    assert exported[source_id, race_id]["evidence_url"] == publication_url
    assert exported[source_id, retained_race_id]["evidence_url"] == retained_url
