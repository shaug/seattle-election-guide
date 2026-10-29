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
Every substantive change to the published aggregate or a position page belongs here,
including additions from routine refreshes even when the leading choice is
unchanged. Minor wording or typography with unchanged facts and behavior stays
in internal software/release history instead (#663). Existing storage and field
names remain compatible with immutable publication view models; `corrected_on`
is also the date of an addition.

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

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ElectionCorrections(CorrectionsModel):
    """`data/corrections/<election-id>.yaml`'s validated contract."""

    schema_version: Literal["1.0"] = "1.0"
    election_id: str = Field(min_length=1)
    entries: list[CorrectionEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_election_corrections(self) -> ElectionCorrections:
        if len(self.entries) != len(
            {(entry.corrected_on, entry.headline) for entry in self.entries}
        ):
            raise ValueError(
                f"corrections file for {self.election_id!r} repeats a (date, headline) entry"
            )
        return self
