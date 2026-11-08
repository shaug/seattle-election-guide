"""Validated per-election corrections contract (docs/RESULTS.md, "The
corrections page"; issue #290).

Storage path (decided by this ticket, no separate ratification required per
its own scope): one file per election at `data/corrections/<election-id>.yaml`,
loaded by `election_guide.corrections.loader.load_rendering_corrections` the
same way `data/results/<election-id>.yaml` is loaded by
`election_guide.results.loader.load_rendering_results`. The election's
corrections page renders -- and is linked in the nav -- only while this file
exists and carries at least one entry (docs/RESULTS.md, Rendering: "results
render as a state, not an option"; the same posture governs Corrections).

The public page is Updates (issue #551; docs/RESULTS.md, "The updates page").
Election-information changes belong here: endorsements, source coverage and
results, including information corrections caused by software. Software feature,
layout, preparation and unchanged verification history belongs with GitHub releases
(#676). Schema1.1 adds explicit topics/actions; legacy1.0 remains readable without
invented metadata. Existing storage and `(corrected_on, headline)` identity remain
compatible with immutable view models; `corrected_on` is guide-publication date.
Schema1.2 persists reviewed slugs and retired-route aliases without changing that
audit identity or inventing routing metadata in older immutable snapshots (#677).

Entries here are hand-authored (an editor writes a headline and body prose
directly), which is why nothing here cross-validates against the ballot
inventory the way `results/models.py` does -- there is no ballot choice to
resolve. `provenance` is deliberately a generic list of labeled links rather
than a structure that names "capture" or "supersedes": the amended-results
auto-entry (consuming #283's own `ElectionResults.supersedes` citation) is an
explicit follow-up *after* #283 lands, not built here, and a generic
label/url pair is exactly the shape that follow-up can populate with two
capture links without this schema changing shape underneath it.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

UpdateTopic = Literal["endorsements", "sources", "results"]
UpdateAction = Literal["added", "changed", "correction", "withdrawn", "certified", "coverage"]


def validate_update_slug(value: str) -> str:
    """One durable URL segment; reject encoding and path ambiguity rather than quoting it."""
    if value == "index" or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None:
        raise ValueError("update slug must be a nonreserved lowercase ASCII hyphenated segment")
    return value


class CorrectionsModel(BaseModel):
    """Reject undeclared fields so schema drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class CorrectionProvenanceLink(CorrectionsModel):
    """One citation rendered on a correction entry's own provenance line --
    the mockup's "supersedes capture 9f3c…e2 → capture 41ab…77"
    (`docs/design/RESULTS_FINALIZATION_2026-08-02.html`, "The corrections
    log"). `label` is the rendered link text; `url` is checked as a safe
    HTTP(S) address or a root-relative affected-page link before it is written
    into markup (`rendering.documents._require_web_url`)."""

    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class CorrectionEntry(CorrectionsModel):
    """One dated corrections-page entry: what a published page asserted, and
    what changed. `headline` is the bold lead sentence the mockup's entries
    open with ("Amended result, State Representative (LD 32, Pos. 1)."); `body`
    is the prose that follows it in the same paragraph. `provenance` is empty
    for an entry with nothing to cite (the mockup's endorsement-attribution
    entry carries none) and non-empty for one that does (its amended-results
    entry carries two capture links)."""

    corrected_on: date
    headline: str = Field(min_length=1)
    body: str = Field(min_length=1)
    provenance: list[CorrectionProvenanceLink] = Field(
        default_factory=list[CorrectionProvenanceLink]
    )
    topics: list[UpdateTopic] = Field(default_factory=list[UpdateTopic])
    actions: list[UpdateAction] = Field(default_factory=list[UpdateAction])
    slug: str | None = None
    redirect_from: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def validate_metadata(self) -> CorrectionEntry:
        if len(set(self.topics)) != len(self.topics) or len(set(self.actions)) != len(self.actions):
            raise ValueError("update topics and actions cannot repeat")
        if self.slug is not None:
            validate_update_slug(self.slug)
        for alias in self.redirect_from:
            validate_update_slug(alias)
        if self.redirect_from and self.slug is None:
            raise ValueError("update slug redirects require a canonical slug")
        return self

    @model_serializer(mode="wrap")
    def serialize_metadata(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Legacy snapshots keep their original shape; absent metadata is not invented."""
        result = handler(self)
        for field in ("topics", "actions", "slug", "redirect_from"):
            if field in result and not result[field]:
                del result[field]
        return result


class ElectionCorrections(CorrectionsModel):
    """`data/corrections/<election-id>.yaml`'s validated contract."""

    schema_version: Literal["1.0", "1.1", "1.2"] = "1.0"
    election_id: str = Field(min_length=1)
    entries: list[CorrectionEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_election_corrections(self) -> ElectionCorrections:
        if self.schema_version in {"1.1", "1.2"} and any(
            not entry.topics or not entry.actions for entry in self.entries
        ):
            raise ValueError("election-information updates require topics and actions")
        if self.schema_version == "1.2" and any(entry.slug is None for entry in self.entries):
            raise ValueError("permalink Updates require an authored slug for every entry")
        slugs = [
            slug
            for entry in self.entries
            for slug in ([entry.slug] if entry.slug is not None else []) + entry.redirect_from
        ]
        if len(set(slugs)) != len(slugs):
            raise ValueError(
                "update slugs and retired slug aliases cannot repeat within an election"
            )
        if len(self.entries) != len(
            {(entry.corrected_on, entry.headline) for entry in self.entries}
        ):
            raise ValueError(
                f"corrections file for {self.election_id!r} repeats a (date, headline) entry"
            )
        return self
