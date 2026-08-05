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

    The fields are `SourceCell`'s own, so a surface hands a cell straight
    through rather than translating it (docs/FRONTEND.md, The data contract:
    one identifier space). A cell naming nobody — a source that looked and
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


def screen_support_summary(race: PublicationRace) -> str:
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    return f"Based on {race.explicit_endorsement_count} endorsing {noun}"


def screen_support_summary_compact(race: PublicationRace) -> str:
    """H34: the compact-mode caption drops the sentence, matching how the
    print edition's own full/compact captions already differ."""
    return f"{race.explicit_endorsement_count} sources"


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


def race_detail_support_summary(race: PublicationRace) -> str:
    if len(race.recommendation_candidate_ids) != 1:
        return screen_support_summary(race)
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


def _meter_standings(endorsements: Sequence[MeterEndorsement]) -> list[str]:
    """The endorsed candidates, leader first, as the meter orders their runs.

    Units, not source counts: a split allocates 1/n to each candidate it names
    (docs/METER_V2.md, Counting and the denominator), so this is exact rational
    arithmetic rather than the whole-source ordering
    `candidate_endorsement_groups` gives the race page's candidate sections.

    Equal units are broken by display label and then by id. The comparison is
    the plain one both languages already agree on, character by character —
    deliberately not `casefold()`, whose JavaScript counterpart does not exist,
    and not a locale collation, which is a different order on every machine.
    The tie-break's whole job is to make two implementations reach one run
    order, so it has to be an order both of them spell the same way.
    """
    units: dict[str, Fraction] = {}
    labels: dict[str, str] = {}
    for endorsement in endorsements:
        if not endorsement.candidate_ids:
            continue
        share = Fraction(1, len(endorsement.candidate_ids))
        for candidate_id, label in zip(
            endorsement.candidate_ids, endorsement.candidate_labels, strict=True
        ):
            units[candidate_id] = units.get(candidate_id, Fraction(0)) + share
            labels[candidate_id] = label
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
    standings = _meter_standings(endorsements)
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


def screen_share_accessible_label(race: PublicationRace) -> str:
    share = "not available" if race.percentage_whole is None else race.percentage_label
    qualifier = "No majority. " if has_no_majority(race) else ""
    return f"{qualifier}Consensus among explicitly endorsing sources: {share}"


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
