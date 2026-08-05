"""Derived presentation values for one publication view model.

Every label, count, share, and accessible summary a page shows is computed
here, so the Jinja templates and the rendered-HTML validator cannot disagree
about one (docs/FRONTEND.md, The data contract). Nothing in this module renders
markup, loads a template, or touches the filesystem.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from election_guide.publication.models import (
    PublicationChoiceEndorsements,
    PublicationRace,
    PublicationSource,
    PublicationViewModel,
    SourceCell,
)
from election_guide.publication.personalization import (
    PersonalizationCell,
    PersonalizationRace,
    PersonalizationSource,
)
from election_guide.rendering.payload import (
    FilterScope,
    RaceCandidateDisplay,
    RaceCandidateEndorsements,
    RaceDetailDisplay,
    RaceDisplay,
    RaceSourceRow,
)


@dataclass(frozen=True)
class ComparisonCellView:
    signal: str
    kind: str
    choice_labels: tuple[str, ...]
    leading_pick_ids: tuple[str, ...]
    share: str | None = None
    explicit_source_count: int | None = None
    agreement: str = "neutral"


@dataclass(frozen=True)
class ComparisonRowView:
    race_id: str
    race_label: str
    cells: tuple[ComparisonCellView, ...]
    differs: bool


@dataclass(frozen=True)
class FilterScopeGroupView:
    """One `<optgroup>` of the guide's Ballot filter. `label` is `None` for the
    ungrouped leading option."""

    label: str | None
    options: tuple[FilterScope, ...]


@dataclass(frozen=True)
class ComparisonSectionView:
    section_id: str
    section_label: str
    rows: tuple[ComparisonRowView, ...]


@dataclass(frozen=True)
class MeterEndorsement:
    """One tallying source cell, as the segmented meter counts it.

    `candidate_ids` and `candidate_labels` are `SourceCell`'s own fields,
    carried through unchanged. `source_label` is not: a cell names its source
    by `source_id`, not by display name, so building this record looks the
    source up (`meter_endorsements`, below) rather than handing the cell
    straight through. A cell naming nobody — a source that looked and
    declined — is admitted here and carries no block and no denominator weight,
    which is the rule rather than an omission (docs/METER_V2.md, Counting and
    the denominator).
    """

    source_label: str
    candidate_ids: tuple[str, ...]
    candidate_labels: tuple[str, ...]


@dataclass(frozen=True)
class MeterBlock:
    """One rectangle of the segmented meter, in rendered order.

    Declarative on purpose: every surface that draws meter v2 — the card, the
    compact ballot, the race headline, the print edition, and the social card
    Python draws — consumes this list verbatim, so anything a renderer would
    otherwise re-derive from a block's neighbours is decided once, here.

    `type` is `"solid"` (one candidate's own endorsement) or `"split"` (one
    block divided horizontally between the candidates it names). `width` is in
    units: one endorsement is one unit, and the track is divided by the sum, so
    a surface needs no second traversal to size a block. `candidate_ids` is in
    standings order, which for a split is top to bottom.

    The four flags carry the tongue rule (docs/METER_V2.md, Splits: placement
    and the tongue rule). `band_start`/`band_end` mark the first and last split
    of a band. `tongue_corner_start`/`tongue_corner_end` mark where that band
    edge actually rounds its interior corner — a band edge that is also the
    meter's own outer edge stays square, so the frame's radius is the only
    curve there. They are two facts rather than one because they differ exactly
    at the meter's ends, and deriving the second from the first is the check
    each of the five surfaces would otherwise have to repeat.
    """

    type: str
    width: int
    candidate_ids: tuple[str, ...]
    source_label: str
    band_start: bool
    band_end: bool
    tongue_corner_start: bool
    tongue_corner_end: bool


@dataclass(frozen=True)
class MeterBlockRender:
    """One `MeterBlock`, with everything a template needs to paint it.

    The Python and JavaScript renderers both consume this verbatim rather than
    deriving colors or seam mixes from a block's neighbours themselves — the
    same reason `MeterBlock` itself is precomputed (docs/METER_V2.md,
    Implementation notes). `style` is the complete inline `style` attribute
    value, built once here so the two template layers stay pure iteration:
    a Jinja macro and a lit-html template that both merely write `style="{{
    render.style }}"` cannot spell one block's paint two ways.

    Each seam is two half colors, not one: a boundary between two different
    splits in one band shares its top half's color (the same leader) but not
    its bottom half's (a different partner each), so a single shared hairline
    color would paint one half of the edge the wrong color (`_meter_block_
    facing`/`_meter_seam_declarations` carry this pairing). `style` carries a
    flat, transitionable `--meter-seam-*-color` when both halves agree, or a
    two-stop `border-image` gradient, `--meter-seam-*-image`, when they do
    not — docs/METER_V2.md says the seam *colors* are normative and its own
    border-image mechanism is not ("any technique producing a 1px seam of the
    specified mixes satisfies the spec"), so this only reaches for a gradient
    where a flat color cannot express two colors on one edge.
    """

    type: str
    width: int
    style: str
    band_start: bool
    band_end: bool
    tongue_corner_start: bool
    tongue_corner_end: bool
    source_label: str
    decision: str
    # Which candidate(s) this block belongs to (one for a solid block, two for
    # a split), carried through from `MeterBlock.candidate_ids` unchanged.
    # Nothing in `meter_block_renders` reads it — it exists so a template can
    # write it as a `data-meter-candidates` attribute, which is the whole of
    # what the race page's candidate-context treatment needs to find "this
    # candidate's blocks" among a meter it does not otherwise touch (#315).
    # Defaulted so the many hand-built `MeterBlockRender`s in tests that
    # predate this field still construct without naming it.
    candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeterCandidateChip:
    """One candidate's chip (docs/METER_V2.md, the mockup's chips section; #315): the
    race page's trigger surface for the shared headline meter's
    candidate-context treatment. Every standing candidate gets one, in the
    meter's own order, holding the same color its blocks use, its display
    label, and its exact tally in the caption's own count format — a
    candidate with no endorsements has no block and, for the same reason, no
    chip either.

    A plain data record like `MeterBlockRender`, built once by `meter_view` so
    the audited Jinja twin and the client's own render read one decision
    rather than two: which candidates get a chip, in what order, wearing which
    color and which count, is decided here and nowhere else.
    """

    candidate_id: str
    label: str
    color: str
    count_label: str


@dataclass(frozen=True)
class MeterView:
    """Everything one meter chrome needs to render itself (docs/METER_V2.md).

    Built once per race per render by `meter_view`, so the audited Jinja twin,
    the validator, and the client's own mirrored builder all read the same
    decisions instead of three surfaces re-deriving them from a race
    (I56 — no two meters on the site may disagree about one share).
    """

    na: bool
    no_majority: bool
    low_fill: bool
    degraded: bool
    fill_percent: int | None
    percentage_label: str
    accessible_label: str
    blocks: tuple[MeterBlockRender, ...]
    # Empty for the N/A state, and on every chrome that has no chips of its
    # own to render (docs/METER_V2.md, the mockup's chips section): only the race page's
    # Jinja and lit twins read this field today. Defaulted for the same
    # reason `MeterBlockRender.candidate_ids` is.
    chips: tuple[MeterCandidateChip, ...] = ()


def personalization_lookup_context(view_model: PublicationViewModel) -> dict[str, Any]:
    """Derived views over the personalization contract shared by every page that
    renders it (the guide and the standalone sources page): a code -> identity
    lookup distinct from source_by_id's id keying, the reverse id -> code lookup
    the markup needs to address a source the way the client payload does, and
    category labels for a multi-category source's "also in" tag."""
    return {
        "source_by_id": {source.id: source for source in view_model.sources},
        "personalization_source_by_code": {
            source.code: source for source in view_model.personalization.sources
        },
        # docs/FRONTEND.md, The data contract: one identifier space. A rendered
        # source is addressed by the same transport code the payload publishes,
        # so no client module translates between the two.
        "source_code_by_id": {
            source.id: source.code for source in view_model.personalization.sources
        },
        "category_label_by_id": {
            category.id: category.label for category in view_model.personalization.categories
        },
    }


def race_display(race: PublicationRace, race_path: str) -> RaceDisplay:
    """One race's audited presentation on the guide, published so no client
    module reads it back out of a card (docs/FRONTEND.md, The data contract)."""
    return RaceDisplay(
        race_id=race.id,
        race_label=race.race_label,
        race_path=race_path,
        candidates=[
            RaceCandidateDisplay(candidate_id=group.candidate_id, label=group.candidate_label)
            for group in candidate_endorsement_groups(race)
        ],
        audited_accessible_summary=race_detail_accessible_summary(race),
    )


def race_detail_display(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
    *,
    source_code_by_id: dict[str, str],
    category_label_by_key: dict[str, str],
) -> RaceDetailDisplay:
    """One race's whole audited presentation, as its own page renders it.

    The candidate sections are a lit region on the race page, so every value
    their markup carries is published here rather than read back off the
    server's copy of it: the row's source name, its category and that
    category's label, its cell state, the status phrase the group gives it, and
    its evidence link. A source that co-endorses two candidates renders one row
    under each, which is why the rows are grouped per candidate rather than
    listed once — the same shape `race_detail_candidate_sections` renders.
    """
    cells_by_source_id = {cell.source_id: cell for cell in tallying_source_cells(race, sources)}
    return RaceDetailDisplay(
        race_id=race.id,
        race_label=race.race_label,
        candidates=[
            RaceCandidateEndorsements(
                candidate_id=group.candidate_id,
                label=group.candidate_label,
                endorsers=[
                    _race_source_row(
                        cells_by_source_id[endorser.source_id],
                        race,
                        sources[endorser.source_id],
                        group="candidate",
                        source_code_by_id=source_code_by_id,
                        category_label_by_key=category_label_by_key,
                    )
                    for endorser in group.endorsers
                ],
            )
            for group in candidate_endorsement_groups(race)
        ],
        audited_accessible_summary=race_detail_accessible_summary(race),
    )


def race_source_group_rows(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
    *,
    source_code_by_id: dict[str, str],
    category_label_by_key: dict[str, str],
) -> dict[str, list[RaceSourceRow]]:
    """The race page's non-candidate evidence rows, grouped and in rendered order.

    The four groups a source can land in when it endorsed nobody in this race:
    no endorsement, needs verification, did not cover it, outside its district.
    Unlike the candidate sections these are not a projection of the reader's
    selection — a deselected source still did not cover the race — so the page
    renders them once and lit never touches them.
    """
    grouped: dict[str, list[RaceSourceRow]] = {
        group: [] for group in ("no_endorsement", "unverified", "not_covered", "not_applicable")
    }
    for cell in tallying_source_cells(race, sources):
        source = sources[cell.source_id]
        group = source_cell_group(cell, race, source)
        if group not in grouped:
            continue
        grouped[group].append(
            _race_source_row(
                cell,
                race,
                source,
                group=group,
                source_code_by_id=source_code_by_id,
                category_label_by_key=category_label_by_key,
            )
        )
    return grouped


def race_social_description(race: PublicationRace) -> str:
    """One race's consensus in a sentence, for its `og:description` (issue #136).

    A crawler and a share sheet get the audited result, never a personalized
    one: a lens lives in the fragment, which never reaches a crawler at all.
    Built from the same grammar the page renders, so an unfurl and the page it
    unfurls cannot state the result two ways.
    """
    share = "" if race.percentage_whole is None else f", {race.percentage_label} agreement"
    return (
        f"{race.race_label}: {race.recommendation_label}{share}. "
        f"{race_detail_support_summary(race)}."
    )


def _race_source_row(
    cell: SourceCell,
    race: PublicationRace,
    source: PublicationSource,
    *,
    group: str,
    source_code_by_id: dict[str, str],
    category_label_by_key: dict[str, str],
) -> RaceSourceRow:
    return RaceSourceRow(
        code=source_code_by_id[cell.source_id],
        name=source.name,
        category=source.category,
        category_label=category_label_by_key[source.category],
        state=cell.state,
        panel_role=source.panel_role,
        detail_label=source_cell_detail_label(cell, race, group),
        evidence_url=cell.evidence_url,
    )


def comparison_fragment(view_model: PublicationViewModel, columns: list[str]) -> str:
    """Build a static preset fragment in the canonical compare-codec order."""
    from urllib.parse import urlencode

    parameters = [
        ("cmp", "1"),
        ("cols", "".join(columns)),
        ("panel", view_model.personalization.panel_id),
        ("ph", view_model.personalization.panel_hash[:12]),
        ("data", view_model.metadata.data_version),
        ("scoring", view_model.personalization.scoring.configuration_id),
    ]
    return urlencode(parameters)


def comparison_sections(view_model: PublicationViewModel) -> tuple[ComparisonSectionView, ...]:
    personalization_races = {race.race_id: race for race in view_model.personalization.races}
    sources = {source.id: source for source in view_model.personalization.sources}
    try:
        stranger = sources["the-stranger"]
        times = sources["seattle-times-editorial-board"]
    except KeyError as error:
        raise ValueError(f"comparison default source is unavailable: {error.args[0]}") from error

    grouped: list[ComparisonSectionView] = []
    current_section_id: str | None = None
    current_section_label = ""
    rows: list[ComparisonRowView] = []
    for display in view_model.comparisons.display_index:
        if display.section_id != current_section_id:
            if current_section_id is not None:
                grouped.append(
                    ComparisonSectionView(
                        section_id=current_section_id,
                        section_label=current_section_label,
                        rows=tuple(rows),
                    )
                )
            current_section_id = display.section_id
            current_section_label = display.section_label
            rows = []

        race = personalization_races[display.race_id]
        labels = display.candidate_names or display.measure_response_labels
        baseline = ComparisonCellView(
            signal="gall",
            kind="baseline",
            choice_labels=tuple(labels[pick_id] for pick_id in display.baseline.leading_pick_ids),
            leading_pick_ids=tuple(display.baseline.leading_pick_ids),
            share=display.baseline.share,
            explicit_source_count=display.baseline.explicit_source_count,
            agreement="baseline",
        )
        stranger_cell = _comparison_direct_cell(stranger, race, labels, baseline)
        times_cell = _comparison_direct_cell(times, race, labels, baseline)
        cells = (baseline, stranger_cell, times_cell)
        rows.append(
            ComparisonRowView(
                race_id=display.race_id,
                race_label=display.race_label,
                cells=cells,
                differs=comparison_row_differs(cells),
            )
        )
    if current_section_id is not None:
        grouped.append(
            ComparisonSectionView(
                section_id=current_section_id,
                section_label=current_section_label,
                rows=tuple(rows),
            )
        )
    return tuple(grouped)


def _comparison_direct_cell(
    source: PersonalizationSource,
    race: PersonalizationRace,
    labels: dict[str, str],
    baseline: ComparisonCellView,
) -> ComparisonCellView:
    if source.code not in race.eligible_source_codes:
        return ComparisonCellView(
            signal=source.code,
            kind="outside_scope",
            choice_labels=(),
            leading_pick_ids=(),
        )

    cells = {cell.source_code: cell for cell in race.cells}
    published: PersonalizationCell = cells[source.code]
    if published.state not in {"endorsement", "multi_endorsement"}:
        return ComparisonCellView(
            signal=source.code,
            kind="blank",
            choice_labels=(),
            leading_pick_ids=(),
        )
    leading_pick_ids = tuple(
        candidate_id
        for candidate_id in race.candidate_order
        if candidate_id in published.allocation
    )
    return ComparisonCellView(
        signal=source.code,
        kind="comparison" if source.panel_role == "comparison" else "direct",
        choice_labels=tuple(labels[candidate_id] for candidate_id in leading_pick_ids),
        leading_pick_ids=leading_pick_ids,
        agreement=("agree" if set(leading_pick_ids) & set(baseline.leading_pick_ids) else "differ"),
    )


def comparison_row_differs(cells: tuple[ComparisonCellView, ...]) -> bool:
    if len(cells) < 2 or not cells[0].leading_pick_ids:
        return False
    reference = set(cells[0].leading_pick_ids)
    return any(
        bool(cell.leading_pick_ids) and reference.isdisjoint(cell.leading_pick_ids)
        for cell in cells[1:]
    )


def comparison_percentage_label(value: str | None) -> str:
    if value is None:
        return ""
    percentage = Fraction(value) * 100
    if percentage.denominator == 1:
        return f"{percentage.numerator}%"
    return f"{float(percentage):.1f}%"


def _filter_options(view_model: PublicationViewModel) -> list[str]:
    section_labels = {section.label for section in view_model.sections}
    return sorted(
        {
            token
            for section in view_model.sections
            for race in section.races
            for token in race.filter_tokens
            if token not in section_labels and (" " in token or token.endswith("wide"))
        }
    )


def filter_scope_groups(view_model: PublicationViewModel) -> list[FilterScopeGroupView]:
    """The Ballot filter's option groups, in rendered order.

    One generator for both consumers (docs/FRONTEND.md, The data contract): the
    template renders its `<optgroup>`/`<option>` markup from these, and the
    payload publishes the same options flattened, so the filter status line can
    name the selected scope without reading the select's own text back
    (issue #239). The options are `FilterScope` on both sides, so the two
    consumers cannot disagree about a key.
    """
    return [
        FilterScopeGroupView(
            label=None,
            options=(FilterScope(value="all", label="All Seattle ballot races"),),
        ),
        FilterScopeGroupView(
            label="Ballot sections",
            options=tuple(
                FilterScope(value=section.id, label=section.label)
                for section in view_model.sections
            ),
        ),
        FilterScopeGroupView(
            label="Districts and jurisdictions",
            options=tuple(
                FilterScope(value=token, label=token) for token in _filter_options(view_model)
            ),
        ),
    ]


def _footer_update_dates(view_model: PublicationViewModel) -> tuple[str, str]:
    data_updated_at = view_model.metadata.data_as_of or view_model.metadata.generated_at
    return (
        data_updated_at.date().isoformat(),
        view_model.metadata.generated_at.date().isoformat(),
    )


def footer_update_context(view_model: PublicationViewModel) -> dict[str, str]:
    """The two provenance dates the shared election footer renders.

    Everything else its audit line needs is already on `guide.metadata`, which
    the template has, so only the derived dates cross the boundary. The footer
    itself is `_shell.html.j2`'s `election_footer_band`, composed once for the
    guide, Sources, and Comparisons.
    """
    data_updated_date, site_updated_date = _footer_update_dates(view_model)
    return {
        "footer_data_updated_date": data_updated_date,
        "footer_site_updated_date": site_updated_date,
    }


def _meter_support_summary_fallback(race: PublicationRace) -> str:
    """The caption's pre-v2 wording, kept as the fallback for a tie or a race
    with no single recommended choice: there is no one candidate's count to
    lead the sentence with, so the sentence states only the denominator, as it
    always did (docs/METER_V2.md, Caption)."""
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    return f"Based on {race.explicit_endorsement_count} endorsing {noun}"


def screen_support_summary(race: PublicationRace, sources: dict[str, PublicationSource]) -> str:
    """The meter's own caption (I39), stating the recommended choice's exact
    endorsement count rather than only the denominator (docs/METER_V2.md,
    Caption — decided in #314, revised in #314's own review): "21½ of 23
    endorsements". The caption never repeats the recommended choice's name —
    every card that renders it already carries that name one row up, in the
    same `<h3 data-display-role="recommendation">` this function's own
    `leader_units` guard is keyed to, so a name here would only restate what
    the reader already read. A tie or a race with no single recommended choice
    falls back to the caption's older wording, which states only the
    denominator — the same fallback `race_detail_support_summary` uses for the
    same reason, though that function feeds a different string (the race
    page's visually-hidden description, which has no adjacent headline to
    lean on) and is not part of this decision.
    """
    leader_units = _meter_leader_units(race, sources)
    if leader_units is None:
        return _meter_support_summary_fallback(race)
    return (
        f"{endorsement_count_label(leader_units)} of {race.explicit_endorsement_count} endorsements"
    )


def screen_support_summary_compact(
    race: PublicationRace, sources: dict[str, PublicationSource]
) -> str:
    """H34: the compact-mode caption drops the name — the card's own heading
    already carries it — and the sentence, matching how the print edition's own
    full/compact captions already differ."""
    leader_units = _meter_leader_units(race, sources)
    if leader_units is None:
        return f"{race.explicit_endorsement_count} sources"
    return (
        f"{endorsement_count_label(leader_units)} of {race.explicit_endorsement_count} endorsements"
    )


def candidate_endorsement_groups(
    race: PublicationRace,
) -> list[PublicationChoiceEndorsements]:
    leaders = set(race.support_leader_candidate_ids)
    return sorted(
        race.endorsement_groups,
        key=lambda group: (
            -group.source_count,
            group.candidate_id not in leaders,
            group.candidate_label.casefold(),
            group.candidate_id,
        ),
    )


def tallying_source_cells(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
) -> list[SourceCell]:
    """The cells the guide renders as evidence.

    Issue 124 retired the guide-side comparison entirely, so a comparison
    source contributes no row, no count, and no candidate section here. It
    stays in the payload and on the Comparisons page, which is now the one
    place a reader compares it against the consensus.
    """
    return [
        cell for cell in race.source_cells if sources[cell.source_id].panel_role != "comparison"
    ]


# The cell states the segmented meter has an opinion about: the endorsements it
# draws a block for, and the explicit "no endorsement" that deliberately gets
# neither a block nor denominator weight (docs/METER_V2.md, Counting and the
# denominator). A source that did not cover the race, or whose claim is still
# unverified, is not in the meter's universe at all — the race page groups
# those separately — so `meter_endorsements` never admits them. Exported so
# `tests/mirror_parity.py`'s fixture cases are built from this same admission
# rule rather than a second copy of it (a deferred finding from #313's review).
METER_COUNTED_STATES = frozenset({"endorsement", "multi_endorsement", "no_endorsement"})


def meter_endorsements(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
) -> list[MeterEndorsement]:
    """One race's cells, as the segmented meter counts them.

    The one production home for the admission rule `METER_COUNTED_STATES`
    names: every surface that draws meter v2 from a `PublicationRace` — the
    card, the race headline, and the validator — calls this rather than
    re-deriving which cells count (docs/METER_V2.md, Implementation notes).
    `tallying_source_cells` already drops a comparison source's cells; this
    narrows further to the states the meter draws a block for or explicitly
    excludes from the denominator, and resolves each cell's `source_id` to its
    display name.
    """
    return [
        MeterEndorsement(
            source_label=sources[cell.source_id].name,
            candidate_ids=tuple(cell.candidate_ids),
            candidate_labels=tuple(cell.candidate_labels),
        )
        for cell in tallying_source_cells(race, sources)
        if cell.state in METER_COUNTED_STATES
    ]


def race_detail_support_summary(race: PublicationRace) -> str:
    if len(race.recommendation_candidate_ids) != 1:
        return _meter_support_summary_fallback(race)
    leader_id = race.recommendation_candidate_ids[0]
    leader_count = next(
        group.source_count for group in race.endorsement_groups if group.candidate_id == leader_id
    )
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    verb = "agrees" if race.explicit_endorsement_count == 1 else "agree"
    return f"{leader_count} of {race.explicit_endorsement_count} endorsing {noun} {verb}"


def race_detail_accessible_summary(race: PublicationRace) -> str:
    share = "Consensus unavailable" if race.percentage_whole is None else race.percentage_label
    qualifier = "No majority. " if has_no_majority(race) else ""
    return f"{race.recommendation_label}. {qualifier}{share}. {race_detail_support_summary(race)}."


def has_no_majority(race: PublicationRace) -> bool:
    return race.winner_share is not None and Fraction(race.winner_share) <= Fraction(1, 2)


# The single-glyph vulgar fractions Unicode offers, keyed by the reduced
# fractional part each renders. Everything else falls back below.
_VULGAR_FRACTION_GLYPHS = {
    (1, 2): "½",
    (1, 3): "⅓",
    (2, 3): "⅔",
    (1, 4): "¼",
    (3, 4): "¾",
    (1, 5): "⅕",
    (2, 5): "⅖",
    (3, 5): "⅗",
    (4, 5): "⅘",
    (1, 6): "⅙",
    (5, 6): "⅚",
    (1, 7): "⅐",
    (1, 8): "⅛",
    (3, 8): "⅜",
    (5, 8): "⅝",
    (7, 8): "⅞",
    (1, 9): "⅑",
    (1, 10): "⅒",
}


def endorsement_count_label(count: Fraction) -> str:
    """An exact endorsement tally as a mixed number: "21½", "⅓", "7".

    Meter v2's caption states the count, not the percent, and a split
    endorsement makes the tally an exact rational (docs/METER_V2.md, Counting),
    so this renders a `Fraction` — never a float — as its whole part plus a
    vulgar-fraction glyph. A fractional part with no single glyph, reachable
    the moment splits compound past the glyph table (a quarter plus a third is
    7/12), renders as numerator⁄denominator with the U+2044 fraction slash,
    joined to a nonzero whole part by a no-break space: "2 7⁄12".
    """
    whole = count.numerator // count.denominator
    part = count - whole
    if not part:
        return str(whole)
    glyph = _VULGAR_FRACTION_GLYPHS.get((part.numerator, part.denominator))
    if glyph is not None:
        return f"{whole}{glyph}" if whole else glyph
    fallback = f"{part.numerator}⁄{part.denominator}"
    return f"{whole}\u00a0{fallback}" if whole else fallback


def meter_units(endorsements: Sequence[MeterEndorsement]) -> dict[str, Fraction]:
    """Each candidate's exact endorsement tally: 1/n to each candidate a split
    names (docs/METER_V2.md, Counting and the denominator). Units, not source
    counts, and never a float — the caption's whole reason for existing is that
    this exact fraction used to be computed and then thrown away.

    Public because the meter's caption and its accessible name both need one
    candidate's exact tally without walking the block list back apart, and
    `meter_standings` needs it to rank the runs — a third computation of the
    same sum is exactly what this module's other mirrored functions exist to
    prevent.
    """
    units: dict[str, Fraction] = {}
    for endorsement in endorsements:
        if not endorsement.candidate_ids:
            continue
        share = Fraction(1, len(endorsement.candidate_ids))
        for candidate_id in endorsement.candidate_ids:
            units[candidate_id] = units.get(candidate_id, Fraction(0)) + share
    return units


def meter_candidate_labels(endorsements: Sequence[MeterEndorsement]) -> dict[str, str]:
    """Each candidate's display label, as the cells that name them spell it."""
    labels: dict[str, str] = {}
    for endorsement in endorsements:
        for candidate_id, label in zip(
            endorsement.candidate_ids, endorsement.candidate_labels, strict=True
        ):
            labels[candidate_id] = label
    return labels


def meter_standings(endorsements: Sequence[MeterEndorsement]) -> list[str]:
    """The endorsed candidates, leader first, as the meter orders their runs.

    Units, not source counts (see `meter_units`), so this is exact rational
    arithmetic rather than the whole-source ordering
    `candidate_endorsement_groups` gives the race page's candidate sections.

    Equal units are broken by display label and then by id. The comparison is
    the plain one both languages already agree on, character by character —
    deliberately not `casefold()`, whose JavaScript counterpart does not exist,
    and not a locale collation, which is a different order on every machine.
    The tie-break's whole job is to make two implementations reach one run
    order, so it has to be an order both of them spell the same way.

    Public — beyond block layout, this is also the meter's color assignment's
    and accessible name's own rank order (docs/METER_V2.md, Color; Splits: the
    tongue rule), so every consumer reads one order rather than three.
    """
    units = meter_units(endorsements)
    labels = meter_candidate_labels(endorsements)
    return sorted(
        units,
        key=lambda candidate_id: (-units[candidate_id], labels[candidate_id], candidate_id),
    )


def meter_layout_blocks(endorsements: Sequence[MeterEndorsement]) -> list[MeterBlock]:
    """The segmented meter's blocks, left to right, from the cells it counts.

    Meter v2 is one block per endorsement, grouped into runs by candidate in
    standings order, with each split placed at the boundary between its
    candidates' runs (docs/METER_V2.md, Splits: placement and the tongue rule).
    This is the whole of that layout, and both renderers read the result rather
    than recomputing it: the server iterates `race.source_cells` in active-source
    order and the lens payload delivers sorted transport codes, so nothing about
    the order below may depend on the order the cells arrive in.

    Within a run, solid blocks sort by their source's display label and the
    splits follow, farthest partner first so the nearest partner's split touches
    the next run. A split between non-adjacent candidates — a third candidate's
    run intervenes — therefore lands at the end of the higher-ranked candidate's
    run, which is where the spec puts it. Splits with the same partner fall back
    to the source label, for the same reason the solids sort by it: it is the
    one key both sides hold. Two sources can share a display label, so the
    split's own membership finishes the order — every key here is total, because
    a key that ties is a key that hands the decision back to the order the cells
    arrived in, which is the one thing this function may not do.

    Band edges are read off the run, not off the neighbouring block. Two runs'
    splits can sit side by side — a candidate whose whole support is split
    halves has no solids of their own — and the mockup's neighbour-type
    heuristic reads that pair as one band, which is why it is documented as
    sufficient only for two-run bands.

    An empty tally returns an empty list: the N/A state renders the bare track
    (docs/METER_V2.md, Edge states), and it has no blocks to decide about.
    """
    standings = meter_standings(endorsements)
    rank = {candidate_id: index for index, candidate_id in enumerate(standings)}
    counted = [item for item in endorsements if item.candidate_ids]
    solids: dict[str, list[MeterEndorsement]] = {candidate_id: [] for candidate_id in standings}
    splits: dict[str, list[tuple[tuple[str, ...], MeterEndorsement]]] = {
        candidate_id: [] for candidate_id in standings
    }
    for endorsement in counted:
        ordered = tuple(sorted(endorsement.candidate_ids, key=lambda item: rank[item]))
        if len(ordered) == 1:
            solids[ordered[0]].append(endorsement)
        else:
            splits[ordered[0]].append((ordered, endorsement))

    blocks: list[MeterBlock] = []
    for candidate_id in standings:
        for endorsement in sorted(solids[candidate_id], key=lambda item: item.source_label):
            blocks.append(
                MeterBlock(
                    type="solid",
                    width=1,
                    candidate_ids=(candidate_id,),
                    source_label=endorsement.source_label,
                    band_start=False,
                    band_end=False,
                    tongue_corner_start=False,
                    tongue_corner_end=False,
                )
            )
        band = sorted(
            splits[candidate_id],
            key=lambda item: (
                -rank[item[0][1]],
                item[1].source_label,
                tuple(rank[member] for member in item[0]),
            ),
        )
        for position, (ordered, endorsement) in enumerate(band):
            starts, ends = position == 0, position == len(band) - 1
            index = len(blocks)
            blocks.append(
                MeterBlock(
                    type="split",
                    width=1,
                    candidate_ids=ordered,
                    source_label=endorsement.source_label,
                    band_start=starts,
                    band_end=ends,
                    tongue_corner_start=starts and index > 0,
                    tongue_corner_end=ends and index < len(counted) - 1,
                )
            )
    return blocks


def _meter_leader_units(
    race: PublicationRace, sources: dict[str, PublicationSource]
) -> Fraction | None:
    """The recommended choice's exact endorsement tally, or `None` when the
    caption has no single choice to attribute it to — a tie, or a race with no
    recommendation at all (docs/METER_V2.md, Caption)."""
    if len(race.recommendation_candidate_ids) != 1:
        return None
    leader_id = race.recommendation_candidate_ids[0]
    return meter_units(meter_endorsements(race, sources)).get(leader_id, Fraction(0))


# Color (docs/METER_V2.md, Color): every value below is a CSS value string, not
# a literal color, so a block's paint is always a reference to a `base.css`
# token — the document's rule that page CSS never introduces a color literal
# applies to a block's inline style exactly as it applies to a stylesheet rule.
_METER_TIE_COLORS: tuple[str, ...] = ("var(--amber)", "var(--meter-tie-deep)")
_METER_TRAIL_COLORS: tuple[str, ...] = (
    "var(--meter-trail-slate)",
    "var(--meter-trail-taupe)",
    "var(--meter-trail-plum)",
)


def _meter_stepped_color(pool: tuple[str, ...], index: int) -> str:
    """A color from a fixed pool, or — once the pool runs out — the pool's last
    color stepped progressively toward the track, so two candidates in one
    meter never share a swatch (docs/METER_V2.md, Counting and the
    denominator's sibling rule in Color: "a fourth trailing candidate, a third
    tied leader")."""
    if index < len(pool):
        return pool[index]
    step = index - len(pool) + 1
    percent = max(30, 100 - 22 * step)
    return f"color-mix(in srgb, {pool[-1]} {percent}%, var(--meter-track))"


def meter_candidate_colors(
    standings: Sequence[str],
    leader_ids: frozenset[str],
    *,
    has_majority: bool,
) -> dict[str, str]:
    """Each standing candidate's block color (docs/METER_V2.md, Color).

    `leader_ids` is `race.support_leader_candidate_ids` — the tie-aware
    leader set the scoring engine already decided, reused rather than
    re-derived from `standings` so the meter's colors cannot disagree with the
    race's own no-majority/tie decision (I56). `has_majority` only matters when
    there is exactly one leader: the site's own teal for a majority, its own
    amber for a sole leader short of one — v1's semantic, unchanged.
    """
    colors: dict[str, str] = {}
    tie_index = 0
    trail_index = 0
    for candidate_id in standings:
        if candidate_id in leader_ids:
            if len(leader_ids) > 1:
                colors[candidate_id] = _meter_stepped_color(_METER_TIE_COLORS, tie_index)
                tie_index += 1
            else:
                colors[candidate_id] = "var(--teal)" if has_majority else "var(--amber)"
        else:
            colors[candidate_id] = _meter_stepped_color(_METER_TRAIL_COLORS, trail_index)
            trail_index += 1
    return colors


def meter_block_decision(block: MeterBlock, labels: dict[str, str]) -> str:
    """One block's tooltip decision line (docs/METER_V2.md, The discovery
    model): "Endorsed Jamie Pedersen" for a solid block, "Split: Hawk + Diaz —
    ½ each" for the common two-way split, and the literal "1/n each" ratio for
    a wider one (Decision log #21) — a vulgar-fraction glyph would overstate
    the tooltip's job, which is naming the split, not restating the caption's
    exact arithmetic."""
    names = [labels[candidate_id] for candidate_id in block.candidate_ids]
    if block.type == "solid":
        return f"Endorsed {names[0]}"
    share = "½ each" if len(names) == 2 else f"1/{len(names)} each"
    return f"Split: {' + '.join(names)} — {share}"


def _meter_seam_tint(color: str) -> str:
    """A same-candidate seam: the fill mixed 88% with the seam pole
    (docs/METER_V2.md, Seams)."""
    return f"color-mix(in srgb, {color} 88%, var(--meter-seam-pole))"


def _meter_seam_bridge(left: str, right: str) -> str:
    """A cross-candidate seam: the 50/50 blend of the two facing colors, mixed
    86% with the seam pole (docs/METER_V2.md, Seams)."""
    return (
        f"color-mix(in srgb, color-mix(in srgb, {left} 50%, {right} 50%) 86%, "
        "var(--meter-seam-pole))"
    )


def _meter_block_facing(block: MeterBlock, colors: dict[str, str]) -> tuple[str, str]:
    """The two colors a block's own left edge is made of, top half and bottom
    half: identical for a solid block, the split's own top/bottom colors for
    a split. A seam has two halves because a split's two halves can each face
    a different neighbour — a boundary between two different splits in one
    band, the case a single shared seam color got wrong until this function
    existed, since the band's shared leader makes the top halves agree while
    the two partners in the bottom halves do not (docs/METER_V2.md, Seams)."""
    if block.type == "solid":
        color = colors[block.candidate_ids[0]]
        return (color, color)
    return (colors[block.candidate_ids[0]], colors[block.candidate_ids[1]])


def _meter_seam_declarations(prefix: str, top: str, bottom: str) -> list[str]:
    """One seam's CSS declarations, as one pair of `top`/`bottom` half colors.

    A flat, transitionable `--{prefix}-color` when both halves agree — the
    common case, and the only one `border-left-color` can smoothly animate.
    Otherwise a two-stop `border-image` gradient, `--{prefix}-image`, since a
    plain border cannot show two colors on one 1px edge. The mockup's own
    mechanism (docs/METER_V2.md, Seams: "any technique producing a 1px seam
    of the specified mixes satisfies the spec" — its own border-image
    mechanism is explicitly non-normative) is what this mirrors, kept only
    where a flat color cannot express two colors at once.
    """
    if top == bottom:
        return [f"--{prefix}-color:{top}"]
    return [f"--{prefix}-image:linear-gradient(180deg, {top} 0 50%, {bottom} 50% 100%)"]


def meter_block_renders(
    blocks: Sequence[MeterBlock],
    colors: dict[str, str],
    labels: dict[str, str],
) -> list[MeterBlockRender]:
    """Every block's paint, seam, and tooltip data, in rendered order
    (docs/METER_V2.md, Splits: placement and the tongue rule; Seams).

    The tongue tip's exposed notch shows the color the tongue rests on: a
    band's first block rests on its own top (leader) color, a band's last
    rests on its own bottom (partner) color, and a single-block band — both
    flags set — is the two-stop split of both.
    """
    renders: list[MeterBlockRender] = []
    previous: MeterBlock | None = None
    for block in blocks:
        declarations = [f"--meter-w:{block.width}"]
        if block.type == "solid":
            color = colors[block.candidate_ids[0]]
            declarations.append(f"--meter-c:{color}")
        else:
            top_color = colors[block.candidate_ids[0]]
            bottom_color = colors[block.candidate_ids[1]]
            declarations.append(f"--meter-ca:{top_color}")
            declarations.append(f"--meter-cb:{bottom_color}")
            declarations.append(f"--meter-splitline-rest:{bottom_color}")
            declarations.append(
                f"--meter-splitline-hover:{_meter_seam_bridge(top_color, bottom_color)}"
            )
            if block.tongue_corner_start and block.tongue_corner_end:
                declarations.append(
                    f"--meter-tongue-bg:linear-gradient(90deg, {top_color} 0 50%, "
                    f"{bottom_color} 50% 100%)"
                )
            elif block.tongue_corner_start:
                declarations.append(f"--meter-tongue-bg:{top_color}")
            elif block.tongue_corner_end:
                declarations.append(f"--meter-tongue-bg:{bottom_color}")
            # At rest a split's own two halves paint its resting border,
            # except a band's first block, which rests flat on its own
            # leader (top) color for both halves so the straight border
            # never fragments against the rounded tongue corner
            # (docs/METER_V2.md, Seams). This reads the block's own colors
            # only — never the previous block's — which is what keeps a
            # multi-split band's interior boundaries correctly two-toned
            # instead of flattened to one half's color for the whole edge.
            rest_top, rest_bottom = (
                (top_color, top_color) if block.band_start else (top_color, bottom_color)
            )
            declarations.extend(_meter_seam_declarations("meter-seam-rest", rest_top, rest_bottom))
        if previous is not None:
            previous_top, previous_bottom = _meter_block_facing(previous, colors)
            current_top, current_bottom = _meter_block_facing(block, colors)
            hover_top = (
                _meter_seam_tint(previous_top)
                if previous_top == current_top
                else _meter_seam_bridge(previous_top, current_top)
            )
            hover_bottom = (
                _meter_seam_tint(previous_bottom)
                if previous_bottom == current_bottom
                else _meter_seam_bridge(previous_bottom, current_bottom)
            )
            declarations.extend(
                _meter_seam_declarations("meter-seam-hover", hover_top, hover_bottom)
            )
        renders.append(
            MeterBlockRender(
                type=block.type,
                width=block.width,
                style="; ".join(declarations),
                band_start=block.band_start,
                band_end=block.band_end,
                tongue_corner_start=block.tongue_corner_start,
                tongue_corner_end=block.tongue_corner_end,
                source_label=block.source_label,
                decision=meter_block_decision(block, labels),
                candidate_ids=block.candidate_ids,
            )
        )
        previous = block
    return renders


def _meter_candidate_chips(
    standings: Sequence[str],
    units: dict[str, Fraction],
    labels: dict[str, str],
    colors: dict[str, str],
) -> list[MeterCandidateChip]:
    """Every standing candidate's chip, in the meter's own order (docs/METER_V2.md,
    the mockup's chips section; #315).

    Composes four maps `meter_view` already built for the blocks themselves —
    nothing here decides a color, a label, or a count a second time, so a chip
    can never name a different candidate order, color, or tally than the
    blocks it selects among."""
    return [
        MeterCandidateChip(
            candidate_id=candidate_id,
            label=labels[candidate_id],
            color=colors[candidate_id],
            count_label=endorsement_count_label(units[candidate_id]),
        )
        for candidate_id in standings
    ]


def meter_accessible_label(
    standings: Sequence[str],
    units: dict[str, Fraction],
    labels: dict[str, str],
) -> str:
    """The meter's spoken name: the full standings, not the resting percentage
    (docs/METER_V2.md, The discovery model's accessibility model). Empty
    standings is the N/A state's own name."""
    if not standings:
        return "No endorsements recorded"
    total = sum((units[candidate_id] for candidate_id in standings), Fraction(0))
    return "; ".join(
        f"{labels[candidate_id]} {endorsement_count_label(units[candidate_id])} of "
        f"{endorsement_count_label(total)} endorsements"
        for candidate_id in standings
    )


# Minimum block width (docs/METER_V2.md, Edge states): below ~3px per block,
# per-block seams drop and the meter degrades to plain candidate runs. The
# site's four chromes span a fixed 7.5rem (print) to a fluid 100% (compact
# ballot, race headline), so no one static pixel width covers all of them —
# this uses the tightest chrome's own floor (print, 120px at 16px/rem) as a
# conservative shared threshold, which never lets *any* chrome render a
# narrower block than the spec allows. `MeterBlock.width` is always 1 (one
# endorsement per block), so the block count is the list length.
_METER_DEGRADE_MAX_BLOCKS = 120 // 3


def meter_view(race: PublicationRace, sources: dict[str, PublicationSource]) -> MeterView:
    """The one meter view every v2 chrome renders from (docs/METER_V2.md).

    Built once so the audited Jinja twin and the validator read identical
    blocks, colors, and accessible name — the client builds the same shape
    from its own mirrored functions over the cells its lens selects, which is
    why every function this composes is exported rather than kept private to
    this call.

    The N/A state (docs/METER_V2.md, Edge states) is decided by `race.
    percentage_whole` alone — the same field the resting percentage itself
    reads — and forces empty blocks and the N/A accessible name regardless of
    what the cells would otherwise lay out: the audited template's N/A branch
    renders no blocks at all, so a `MeterView` that claimed blocks anyway
    would describe a meter no renderer draws (`rendering/validation.py`'s
    block-count check is what would catch that disagreement).
    """
    if race.percentage_whole is None:
        return MeterView(
            na=True,
            no_majority=False,
            low_fill=False,
            degraded=False,
            fill_percent=None,
            percentage_label=race.percentage_label,
            accessible_label="No endorsements recorded",
            blocks=(),
        )
    endorsements = meter_endorsements(race, sources)
    standings = meter_standings(endorsements)
    units = meter_units(endorsements)
    labels = meter_candidate_labels(endorsements)
    colors = meter_candidate_colors(
        standings,
        frozenset(race.support_leader_candidate_ids),
        has_majority=not has_no_majority(race),
    )
    blocks = meter_layout_blocks(endorsements)
    return MeterView(
        na=False,
        no_majority=has_no_majority(race),
        low_fill=race.percentage_whole < 30,
        degraded=len(blocks) > _METER_DEGRADE_MAX_BLOCKS,
        fill_percent=race.percentage_whole,
        percentage_label=race.percentage_label,
        accessible_label=meter_accessible_label(standings, units, labels),
        blocks=tuple(meter_block_renders(blocks, colors, labels)),
        chips=tuple(_meter_candidate_chips(standings, units, labels, colors)),
    )


def source_cell_group(
    cell: SourceCell,
    race: PublicationRace,
    source: PublicationSource,
) -> str:
    del race
    if cell.state in {"not_covered", "not_applicable"}:
        return cell.state
    if cell.state in {"unavailable", "unverified"}:
        return "unverified"
    if cell.state == "no_endorsement":
        return "no_endorsement"
    return "candidate"


def source_cell_group_count(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
    group: str,
) -> int:
    """Count the rendered cells in one group."""
    return sum(
        source_cell_group(cell, race, sources[cell.source_id]) == group
        for cell in tallying_source_cells(race, sources)
    )


def source_cell_group_label(race: PublicationRace, group: str) -> str:
    del race
    return {
        "no_endorsement": "No endorsement",
        "unverified": "Needs verification",
        "not_covered": "Did not cover this race",
        "not_applicable": "Outside this source's district",
    }[group]


def source_cell_detail_label(
    cell: SourceCell,
    race: PublicationRace,
    group: str,
) -> str | None:
    if group == "candidate":
        return "Co-endorsed" if cell.state == "multi_endorsement" else None
    if group in {"no_endorsement", "not_covered", "not_applicable"}:
        return None
    del race
    return _source_cell_status_label(cell)


def _source_cell_status_label(cell: SourceCell) -> str:
    if cell.state == "endorsement":
        return f"Endorsed {cell.candidate_labels[0]}"
    if cell.state == "multi_endorsement":
        return f"Endorsed {' and '.join(cell.candidate_labels)}"
    return {
        "no_endorsement": "No endorsement",
        "not_covered": "Did not cover this race",
        "unavailable": "Endorsement unavailable",
        "unverified": "Could not verify an endorsement",
        "not_applicable": "Outside this source's district",
    }[cell.state]
