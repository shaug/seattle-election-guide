"""Strict inputs and status records for a public election-guide release."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

REQUIRED_VALIDATION_REPORTS = frozenset({"publication", "rendering"})
REQUIRED_RELEASE_ARTIFACTS = frozenset(
    {
        "RELEASE_NOTES.md",
        "data/build_manifest.json",
        "data/canonical-dataset.json",
        "data/consensus.json",
        "data/endorsement_records.csv",
        "data/provenance_manifest.json",
        "data/publication_view_model.json",
        "data/race_summary.csv",
        "data/source_matrix.csv",
        "data/source_metadata.csv",
        "data/unresolved_review_items.csv",
        "data/validation_report.json",
        "release-manifest.json",
        "release-status.json",
        "validation/rendering/rendering_validation_report.json",
    }
)


class ReleaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReleaseDecision(ReleaseModel):
    race_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["endorsed", "no_endorsement", "declined_to_endorse"] = "endorsed"
    candidate_ids: list[str] = Field(default_factory=list)
    evidence_excerpt: str | None = Field(default=None, min_length=1, max_length=4_000)
    evidence_locator: str | None = Field(default=None, min_length=1, max_length=1_000)

    @field_validator("evidence_excerpt", "evidence_locator")
    @classmethod
    def strip_audit_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("release evidence text cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_decision(self) -> ReleaseDecision:
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("release decision repeats a candidate")
        if self.status == "endorsed" and not self.candidate_ids:
            raise ValueError("an endorsed release decision requires candidates")
        if self.status != "endorsed" and self.candidate_ids:
            raise ValueError(f"{self.status} release decision cannot name candidates")
        return self


class ReleaseSourceExtract(ReleaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    captured_at: AwareDatetime
    evidence_locator: str = Field(min_length=1, max_length=1_000)
    decisions: list[ReleaseDecision] = Field(min_length=1)

    @field_validator("evidence_locator")
    @classmethod
    def strip_evidence_locator(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source evidence locator cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_unique_races(self) -> ReleaseSourceExtract:
        race_ids = [decision.race_id for decision in self.decisions]
        if len(race_ids) != len(set(race_ids)):
            raise ValueError(f"release source {self.source_id!r} repeats a race")
        return self


class ReleaseLedger(ReleaseModel):
    schema_version: Literal["1.0"] = "1.0"
    election_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    data_as_of: AwareDatetime
    reviewer: str = Field(min_length=1, max_length=200)
    review_note: str = Field(min_length=1, max_length=4_000)
    sources: list[ReleaseSourceExtract] = Field(min_length=1)

    @field_validator("reviewer", "review_note")
    @classmethod
    def strip_review_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("release review text cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_sources(self) -> ReleaseLedger:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("release ledger repeats a source")
        if any(source.captured_at > self.data_as_of for source in self.sources):
            raise ValueError("release data timestamp cannot predate a source extract")
        return self


class SourceAccessStatus(ReleaseModel):
    source_id: str
    status: str
    requested_url: str
    note: str


class RaceCoverageStatus(ReleaseModel):
    race_id: str
    explicit_endorsement_count: int = Field(ge=0, strict=True)
    eligible_source_count: int = Field(ge=0, strict=True)
    missing_source_count: int = Field(ge=0, strict=True)
    warning_codes: list[str]


class ReleaseStatus(ReleaseModel):
    schema_version: Literal["1.0"] = "1.0"
    release_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    election_id: str
    data_as_of: AwareDatetime
    generated_at: AwareDatetime
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_count: int = Field(ge=0, strict=True)
    captured_source_count: int = Field(ge=0, strict=True)
    displayed_endorsement_count: int = Field(ge=0, strict=True)
    unresolved_review_count: int = Field(ge=0, strict=True)
    unresolved_high_severity_count: int = Field(ge=0, strict=True)
    restricted_capture_count: int = Field(ge=0, strict=True)
    source_access_failures: list[SourceAccessStatus]
    incomplete_races: list[RaceCoverageStatus]
    validation_reports: dict[str, bool]
    rendering_edition: Literal["concise", "concise_plus_detailed"]
    guide_html_artifact: str
    guide_pdf_artifact: str
    detailed_guide_pdf_artifact: str | None
    included_artifacts: list[str]
    warnings: list[str]

    @model_validator(mode="after")
    def validate_release_safety(self) -> ReleaseStatus:
        if self.generated_at < self.data_as_of:
            raise ValueError("release generation cannot predate its audited data")
        if self.source_count == 0:
            raise ValueError("a release requires at least one active source")
        if self.captured_source_count > self.source_count:
            raise ValueError("captured source count cannot exceed active source count")
        if self.captured_source_count + len(self.source_access_failures) > self.source_count:
            raise ValueError("captured sources and source failures exceed active source count")
        if self.displayed_endorsement_count == 0:
            raise ValueError("a release requires at least one displayed source decision")
        if self.unresolved_high_severity_count > self.unresolved_review_count:
            raise ValueError("high-severity review count cannot exceed all unresolved reviews")
        if self.unresolved_high_severity_count:
            raise ValueError("a release cannot contain unresolved high-severity review work")
        if self.restricted_capture_count:
            raise ValueError("a public release cannot depend on restricted captures")
        if frozenset(self.validation_reports) != REQUIRED_VALIDATION_REPORTS:
            raise ValueError("release validation report set is not canonical")
        if not all(self.validation_reports.values()):
            raise ValueError("a release requires every validation report to pass")
        if len(self.included_artifacts) != len(set(self.included_artifacts)):
            raise ValueError("release artifact paths must be unique")
        invalid_paths = [
            path
            for path in self.included_artifacts
            if PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or path != PurePosixPath(path).as_posix()
        ]
        if invalid_paths:
            raise ValueError(
                f"release artifact paths must be canonical and relative: {invalid_paths}"
            )
        guide_paths = [
            self.guide_html_artifact,
            self.guide_pdf_artifact,
            *(
                [self.detailed_guide_pdf_artifact]
                if self.detailed_guide_pdf_artifact is not None
                else []
            ),
        ]
        if any(
            PurePosixPath(path).parent != PurePosixPath("guide")
            or path != PurePosixPath(path).as_posix()
            for path in guide_paths
        ):
            raise ValueError("release guide artifacts must be canonical paths under guide/")
        if not self.guide_html_artifact.endswith(".html") or not self.guide_pdf_artifact.endswith(
            ".pdf"
        ):
            raise ValueError("release guide artifacts have invalid file types")
        if self.rendering_edition == "concise":
            if self.detailed_guide_pdf_artifact is not None:
                raise ValueError("concise release cannot name a detailed PDF")
        elif (
            self.detailed_guide_pdf_artifact is None
            or not self.detailed_guide_pdf_artifact.endswith(".pdf")
        ):
            raise ValueError("detailed rendering edition requires its PDF artifact")
        elif self.detailed_guide_pdf_artifact == self.guide_pdf_artifact:
            raise ValueError("concise and detailed PDF artifacts must be distinct")
        missing_guides = set(guide_paths) - set(self.included_artifacts)
        if missing_guides:
            raise ValueError(
                f"release is missing rendered guide artifacts: {sorted(missing_guides)}"
            )
        missing_artifacts = REQUIRED_RELEASE_ARTIFACTS - set(self.included_artifacts)
        if missing_artifacts:
            raise ValueError(f"release is missing required artifacts: {sorted(missing_artifacts)}")
        required_qa_prefixes = (
            "validation/rendering/pdf/pages/",
            "validation/rendering/screenshots/",
        )
        if self.rendering_edition == "concise_plus_detailed":
            required_qa_prefixes += ("validation/rendering/pdf/detailed-pages/",)
        missing_qa = [
            prefix
            for prefix in required_qa_prefixes
            if not any(path.startswith(prefix) for path in self.included_artifacts)
        ]
        if missing_qa:
            raise ValueError(f"release is missing rendered QA artifacts: {missing_qa}")
        if len(self.source_access_failures) > self.source_count:
            raise ValueError("source failure count cannot exceed active source count")
        access_source_ids = [status.source_id for status in self.source_access_failures]
        if len(access_source_ids) != len(set(access_source_ids)):
            raise ValueError("release source failures must be unique")
        incomplete_race_ids = [status.race_id for status in self.incomplete_races]
        if len(incomplete_race_ids) != len(set(incomplete_race_ids)):
            raise ValueError("incomplete release races must be unique")
        return self
