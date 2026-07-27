"""The append-only per-election catalog of published panel snapshots.

A lens-enabled release migrates a link written against an older panel by
resolving that panel's snapshot here. Entries are therefore permanent: a
published snapshot may be appended but never edited or removed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator

from election_guide.serialization import read_json
from election_guide.sources.models import SourceModel
from election_guide.sources.panel import PanelSnapshot


class PanelSnapshotCatalog(SourceModel):
    """Every panel version ever published for one election, oldest first."""

    schema_version: Literal["1.0"] = "1.0"
    election_id: str = Field(min_length=1)
    snapshots: list[PanelSnapshot] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> PanelSnapshotCatalog:
        panel_ids = [snapshot.panel_id for snapshot in self.snapshots]
        if len(set(panel_ids)) != len(panel_ids):
            raise ValueError("panel snapshot catalog repeats a panel id")
        hashes = [snapshot.panel_hash for snapshot in self.snapshots]
        if len(set(hashes)) != len(hashes):
            raise ValueError("panel snapshot catalog repeats a panel hash")
        return self

    def snapshot_for(self, panel_id: str) -> PanelSnapshot | None:
        """Resolve a published panel id, or None when the link cannot migrate."""
        return next(
            (snapshot for snapshot in self.snapshots if snapshot.panel_id == panel_id), None
        )


def read_panel_snapshot_catalog(path: Path) -> PanelSnapshotCatalog:
    """Load a catalog and expose validation as a stable value error."""
    try:
        raw: Any = read_json(path)
        return PanelSnapshotCatalog.model_validate(raw)
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error


def appended_panel_snapshot(
    catalog: PanelSnapshotCatalog, snapshot: PanelSnapshot
) -> PanelSnapshotCatalog:
    """Return the catalog extended with one snapshot, refusing any rewrite.

    Republishing the current panel unchanged is a no-op so repeated builds stay
    deterministic; changing a published entry is rejected.
    """
    existing = catalog.snapshot_for(snapshot.panel_id)
    if existing is not None:
        if existing != snapshot:
            raise ValueError(
                f"published panel {snapshot.panel_id!r} cannot be rewritten; "
                "publish a new panel version instead"
            )
        return catalog
    if any(item.panel_hash == snapshot.panel_hash for item in catalog.snapshots):
        raise ValueError(
            f"panel {snapshot.panel_id!r} duplicates the hash of an already published panel"
        )
    return catalog.model_copy(update={"snapshots": [*catalog.snapshots, snapshot]})
