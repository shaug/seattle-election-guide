"""Admit archived publication data without deriving missing election facts (#721)."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import cast

from election_guide.hosting.models import DeployedElection
from election_guide.publication.models import PublicationViewModel
from election_guide.release.models import ReleaseManifest, ReleaseStatus
from election_guide.rendering.models import PagePresentation
from election_guide.results.models import ElectionResults, RaceResults


def validate_presentation_input(raw: object, status: ReleaseStatus) -> PublicationViewModel:
    """Validate the archive's own contract before current presentation consumes it."""
    schema = cast(dict[str, object], raw).get("schema_version") if isinstance(raw, dict) else None
    if not isinstance(schema, str) or schema not in {"1.9", "1.13", "1.14"}:
        raise ValueError("presentation requires an explicit supported publication schema")
    view = PublicationViewModel.model_validate(raw)
    metadata = view.metadata
    identities = (
        ("election", metadata.election_id, status.election_id),
        ("source panel", metadata.source_panel_id, status.source_panel_id),
        ("source panel hash", metadata.source_panel_hash, status.source_panel_hash),
        ("source", metadata.git_commit, status.git_commit),
        ("build time", metadata.generated_at, status.generated_at),
    )
    for label, stored, expected in identities:
        if stored != expected:
            raise ValueError(f"presentation archive {label} differs from release status")
    if metadata.data_as_of is not None and metadata.data_as_of != status.data_as_of:
        raise ValueError("presentation archive data cutoff differs from release status")
    if view.corrections is not None and view.corrections.election_id != metadata.election_id:
        raise ValueError("presentation Updates election differs from archive")
    results = view.results
    if results is None:
        return view
    if results.election_id != metadata.election_id:
        raise ValueError("presentation results election differs from archive")
    if isinstance(results, ElectionResults) and results.status == "counting":
        raise ValueError("presentation cannot consume legacy counting results")
    races = {race.id: race for section in view.sections for race in section.races}
    captures = {capture.evidence: capture for capture in results.captures}
    for tally in results.races:
        race = races.get(tally.race_id)
        if race is None:
            raise ValueError("presentation results reference an unknown archived race")
        labels = {candidate.id: candidate.label for candidate in race.candidates}
        if not labels or race.race_type is None:
            raise ValueError(
                "presentation results require the archived choice roster and race type"
            )
        if {outcome.choice_id for outcome in tally.outcomes} != set(labels):
            raise ValueError("presentation result choices differ from the archived roster")
        capture = captures.get(tally.capture_evidence)
        if capture is None or capture.kind == "election_night":
            raise ValueError("presentation results require their own admissible capture")
        if isinstance(results, ElectionResults):
            if race.race_type != "measure" and metadata.election_type is None:
                raise ValueError(
                    "presentation candidate outcomes require the archived election type"
                )
            if race.race_type == "measure" and (
                {label.strip().lower() for label in labels.values()} != {"yes", "no"}
                or sum(outcome.advanced for outcome in cast(RaceResults, tally).outcomes) != 1
            ):
                raise ValueError("presentation measure outcome is ambiguous")
    return view


def verify_presentation_identity(
    election: DeployedElection, manifest: ReleaseManifest, current_status: ReleaseStatus
) -> None:
    """Bind the two independent identities before inspecting any page claims."""
    presentation = election.presentation
    if presentation is None:
        raise ValueError("presentation provenance is missing")
    if (
        manifest.release_version != election.release_version
        or manifest.source_panel_id != election.source_panel_id
        or manifest.source_panel_hash != election.source_panel_hash
        or manifest.source_registry_hash != election.source_registry_hash
        or presentation.source_git_commit != current_status.git_commit
        or presentation.generated_at != current_status.generated_at
        or presentation.archive_git_commit != election.git_commit
        or presentation.archive_release_version != election.release_version
        or presentation.release_manifest_sha256 != election.release_manifest_sha256
        or presentation.publication_view_model_sha256
        != manifest.artifact_hashes.get("data/publication_view_model.json")
    ):
        raise ValueError("presentation provenance differs from current source or archive")


class _PresentationMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, list[str | None]] = {}
        self.in_head = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "head":
            self.in_head = True
        attributes = dict(attrs)
        name = attributes.get("name")
        if self.in_head and tag == "meta" and name is not None:
            self.values.setdefault(name, []).append(attributes.get("content"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False


def verify_page_presentation(document: str, presentation: PagePresentation) -> None:
    """Require each shared head claim exactly once, including unlinked detail pages."""
    parser = _PresentationMetadata()
    parser.feed(document)
    parser.close()
    for name, value in presentation.html_metadata.items():
        if parser.values.get(name) != [value]:
            raise ValueError(f"page presentation metadata differs: {name}")
