"""Non-destructive retention triage for explicitly inventoried operational payloads.

This consumes declarations, not live ownership/merge proof. A candidate is a request
for verification, never permission to remove anything. Source evidence is out of scope.
"""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RetentionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ElectionRetention(RetentionModel):
    phase: Literal["active", "closed"]
    closeout_receipts: list[str]

    def has_declared_closeout(self) -> bool:
        return self.phase == "closed" and {
            "certified-ingest",
            "accepted-release",
            "retrospective",
        }.issubset(self.closeout_receipts)


class OperationalArtifact(RetentionModel):
    id: str = Field(min_length=1)
    path: str
    kind: Literal[
        "operational",
        "election-operational",
        "source",
        "published",
        "receipt",
        "checkpoint",
        "unknown",
    ]
    elections: list[str] = Field(min_length=1)
    run_state: Literal["active", "completed", "unknown"]
    owner: str
    completion_receipt: str | None
    active_consumers: list[str]
    hold: str | None
    bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        # Inventories describe the separate run store, never repo data or .git.
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or len(path.parts) < 3
            or path.parts[0] != "runs"
            or value != path.as_posix()
        ):
            raise ValueError("artifact path must be canonical runs/<owner>/<payload>")
        return value


class RetentionInventory(RetentionModel):
    schema_version: Literal["1"]
    elections: dict[str, ElectionRetention]
    artifacts: list[OperationalArtifact]

    @model_validator(mode="after")
    def unique_artifacts(self) -> "RetentionInventory":
        ids = [artifact.id for artifact in self.artifacts]
        paths = [artifact.path for artifact in self.artifacts]
        if len(set(ids)) != len(ids) or len(set(paths)) != len(paths):
            raise ValueError("artifact IDs and paths must be unique")
        declared_paths = set(paths)
        if any(
            parent.as_posix() in declared_paths
            for path in paths
            for parent in PurePosixPath(path).parents
        ):
            raise ValueError("artifact paths must not overlap")
        return self


class RetentionEntry(RetentionModel):
    id: str
    path: str
    disposition: Literal["candidate", "retain"]
    reason: str
    bytes: int


class RetentionPlan(RetentionModel):
    schema_version: Literal["1"] = "1"
    deletion_authorized: Literal[False] = False
    basis: str = "Unverified inventory declarations; live verification required before any removal."
    candidate_bytes: int
    entries: list[RetentionEntry]


def retention_plan(inventory: RetentionInventory) -> RetentionPlan:
    entries: list[RetentionEntry] = []
    for item in sorted(inventory.artifacts, key=lambda artifact: artifact.id):
        reason = "completed operational payload; verify receipt, references and ownership"
        disposition: Literal["candidate", "retain"] = "candidate"
        if item.kind not in {"operational", "election-operational"}:
            reason = "source, product, receipt, checkpoint or unknown material is protected"
        elif (
            not item.owner.strip()
            or item.run_state != "completed"
            or not item.completion_receipt
            or not item.completion_receipt.strip()
        ):
            reason = "missing owner or completion receipt, or run is not completed"
        elif PurePosixPath(item.path).parts[1] != item.owner:
            reason = "artifact path and declared owner disagree"
        elif item.active_consumers or item.hold is not None:
            reason = "active consumer or explicit hold"
        elif any(election not in inventory.elections for election in item.elections):
            reason = "unresolved election reference"
        elif item.kind == "election-operational" and not all(
            inventory.elections[election].has_declared_closeout() for election in item.elections
        ):
            reason = "all referencing elections need certified ingest, acceptance and retrospective"
        else:
            entries.append(
                RetentionEntry(
                    id=item.id,
                    path=item.path,
                    disposition=disposition,
                    reason=reason,
                    bytes=item.bytes,
                )
            )
            continue
        entries.append(
            RetentionEntry(
                id=item.id, path=item.path, disposition="retain", reason=reason, bytes=item.bytes
            )
        )
    return RetentionPlan(
        candidate_bytes=sum(entry.bytes for entry in entries if entry.disposition == "candidate"),
        entries=entries,
    )
