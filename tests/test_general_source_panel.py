from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.release import verify_release_compilation
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
        "source registry: valid (48 proposed; 42 consensus, 1 comparison, 5 excluded)"
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


def test_general_panel_snapshot_preserves_frozen_identity_contract() -> None:
    registry = read_source_registry(GENERAL_REGISTRY_PATH)
    committed_catalog = read_panel_snapshot_catalog(GENERAL_CATALOG_PATH)
    current_projection = build_panel_snapshot(registry)

    assert committed_catalog.election_id == "wa-2026-general"
    assert len(committed_catalog.snapshots) == 1
    published = committed_catalog.snapshots[0]
    assert published.panel_id == "wa-2026-general-default-sources-v1"
    assert published.panel_hash == (
        "b0fb2a603bd98da49d3282d2daa0cb55ff56e0bbdd46104c8b5a4a441b747a95"
    )
    assert current_projection == published
    assert appended_panel_snapshot(committed_catalog, current_projection) == committed_catalog


def test_general_panel_preserves_primary_selection_contract() -> None:
    primary = read_source_registry(PRIMARY_REGISTRY_PATH)
    general = read_source_registry(GENERAL_REGISTRY_PATH)

    assert general.id == "wa-2026-general-default-sources-v1"
    assert general.election_id == "wa-2026-general"
    assert general.research_cutoff == general.frozen_at
    assert general.frozen_at > datetime(2026, 9, 4, tzinfo=UTC)
    assert general.categories == primary.categories
    assert general.retired_codes == primary.retired_codes
    assert general.overlap_groups == primary.overlap_groups
    assert [source.id for source in general.sources] == [source.id for source in primary.sources]

    primary_by_id = {source.id: source for source in primary.sources}
    for general_source in general.sources:
        primary_source = primary_by_id[general_source.id]
        for field in PRESERVED_SOURCE_FIELDS:
            assert getattr(general_source, field) == getattr(primary_source, field), (
                general_source.id,
                field,
            )
