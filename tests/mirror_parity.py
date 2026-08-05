"""Golden cases for the cross-language mirrors that survived the contract work.

docs/FRONTEND.md § Cross-language mirrors: logic written in both Python and
JavaScript needs a generated parity fixture, because a comment is not a
contract. `tests/mirrors.json` is the inventory of what remains a mirror after
#236 moved the audited labels into the payload and #239 extracted the guide's
glue into modules; this module emits the golden cases for every entry that
inventory marks `parity-fixture`, and `tests/js/mirror-parity.test.mjs` asserts
them against the client modules.

**Nothing here restates a formatting rule.** Each expectation comes from the
shipped server implementation, in one of five ways:

`published race`
    Most cases come from a real publication bundle, so the expectation is a
    `rendering/context.py` function or a `publication/builder.py` field
    evaluated on a race the audited pipeline actually built. Panels beyond the
    full one are produced by `lens_parity.restricted_dataset`, exactly as the
    lens fixture produces its selections: restricting the panel *is* what
    selecting a subset means, so a narrow panel yields genuine insufficient
    races and genuine missing shares rather than states invented here.

`share`
    A percentage formatter takes a rational string, not a race, so its rounding
    boundaries are reachable directly. `comparison_percentage_label` is called
    as shipped; the whole-percentage rounding comes from `_percentage_whole`,
    the same function `publication/builder.py` uses to fill `percentage_label`;
    and `has_no_majority` is called on a copy of a published race carrying the
    boundary share, because it reads a race rather than a share. Only the
    trailing `%` is written here, and it is written identically in `builder.py`,
    in `models.py`'s validator, and in the client.

`fragment`
    `comparison_fragment` writes the Comparisons preset fragment and is called
    as shipped, on the same view model the audited page was rendered from.

`audited page`
    Two strings are the server's template text rather than any function's
    return value. Their expectation is read out of the committed audited page
    fixtures — the real rendered documents `page_parity.py` generates — so the
    client is held to the bytes the server shipped.

`layout shape`
    The segmented meter's block list takes cells rather than a race, so the
    published cases hand it the cells of the races `page_parity.py`'s own
    feature census already chose, and the rules this election's data cannot
    reach — a three-way split, two split bands side by side — are hand-built
    cell sets handed to the same shipped function.

The panels are chosen for the states they reach, not for how many they are: the
full panel is the audited page itself, and a one-source panel drives every race
below the explicit-source floor, which is the only way to reach a null share
with a real bundle. That null share is what these cases exist for. The audited
dataset has no race without a winner, so no markup-parity diff can reach the
client's null-share rendering; a fixture can.

Regenerate with::

    uv run python -m tests.mirror_parity
"""

from __future__ import annotations

import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

from election_guide.normalization.models import CanonicalDataset
from election_guide.publication.lens_parity import restricted_dataset
from election_guide.publication.models import (
    PublicationRace,
    PublicationSource,
    PublicationViewModel,
    _percentage_whole,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.rendering import context
from election_guide.rendering.validation import (
    _html_semantic_values,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.serialization import read_json
from tests.page_parity import race_parity_fixture_ids
from tests.test_personalization import DATASET_PATH, _bundle  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "mirror-parity.json"
GUIDE_PAGE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "guide-audited-page.html"
SOURCES_PAGE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "sources-audited-page.html"
COMPARE_PAGE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "compare-audited-page.html"

FIXTURE_SCHEMA_VERSION = "1.0"

# One entry per panel state the mirrors distinguish. `None` is the audited
# panel — the guide as published — and each named subset is applied by
# `restricted_dataset`, so every race it yields was built by the real pipeline.
PANELS: tuple[tuple[str, frozenset[str] | None, str], ...] = (
    (
        "audited",
        None,
        "The published panel: the shares, grades, and captions the guide ships.",
    ),
    (
        "single-source",
        frozenset({"the-stranger"}),
        "One source falls below the explicit-source floor, so every race is "
        "insufficient and the races it did not cover have no share at all.",
    ),
    (
        "two-sources",
        frozenset({"the-stranger", "the-urbanist"}),
        "Two sources split some races, which is where a half share and a tie "
        "both become reachable.",
    ),
    (
        "district-sources",
        frozenset({"11th-district-democrats", "43rd-district-democrats"}),
        "District sources cover only their own races, so most races have no "
        "endorsing source and the rest have exactly one.",
    ),
)

# Shares a panel is unlikely to produce but a category column can, chosen for
# the rounding boundaries where the two languages' arithmetic could disagree.
# Each is exact: the point is that neither side ever reaches for a float.
BOUNDARY_SHARES: tuple[tuple[str, str], ...] = (
    ("1/2", "An exact half: rounds up to 50% whole, and prints exactly in tenths."),
    ("1/8", "12.5% whole rounds half up to 13%; the tenths form is exact."),
    ("3/8", "37.5% whole rounds half up to 38%."),
    ("9/16", "56.25%: half-to-even in tenths gives 56.2%, away-from-zero 56.3%."),
    ("11/16", "68.75%: half-to-even in tenths gives 68.8%, the odd tenth rounding up."),
    ("1/3", "A repeating share, which must not print more than one decimal."),
    ("2/3", "The repeating share that rounds up."),
    ("1/1", "A unanimous share prints with no decimal at all."),
    ("1/7", "A share whose tenths are neither exact nor a half."),
)

# Endorsement tallies for the caption's count formatter, covering whole
# numbers, the glyph table's denominators, and the fallback past it. Each is
# exact, for the same reason as the shares above: neither side may reach for a
# float (docs/METER_V2.md § Counting).
COUNT_TALLIES: tuple[tuple[str, str], ...] = (
    ("0", "A zero tally is a digit, not an empty string."),
    ("23", "A whole tally is plain digits with no fractional part."),
    ("43/2", "The spec's own caption: a half renders as its glyph, 21½."),
    ("1/3", "A three-way split's single share is a bare glyph with no whole part."),
    ("2/3", "A non-unit fractional part still has a glyph."),
    ("7/4", "Quarters sit directly against the whole part: 1¾."),
    ("1/7", "A seven-way split is the n-way case with a glyph: ⅐."),
    ("4/8", "An unreduced tally reduces before the glyph lookup: ½."),
    ("25/12", "Twelfths have no glyph, so the fallback spells 2 1⁄12."),
)


def _endorsement(source_label: str, *candidates: tuple[str, str]) -> context.MeterEndorsement:
    """One cell for a hand-built layout shape, spelled `(id, label)` per candidate."""
    return context.MeterEndorsement(
        source_label=source_label,
        candidate_ids=tuple(candidate_id for candidate_id, _ in candidates),
        candidate_labels=tuple(label for _, label in candidates),
    )


# Layout shapes the published ballot does not contain. This election's data has
# no three-way split and no two split bands sitting side by side, and both are
# rules the design states outright, so they are built here and handed to the
# shipped function exactly as the comparison rows below are. The ids are ordered
# against the labels wherever the ordering rule is the point, so a case cannot
# pass by sorting on the wrong key.
LAYOUT_SHAPES: tuple[tuple[str, tuple[context.MeterEndorsement, ...], str], ...] = (
    (
        "label tie-break",
        (
            _endorsement("Ashland Assembly", ("tie--first", "Zeta Zhang")),
            _endorsement("Bellwether Board", ("tie--second", "Ada Ames")),
        ),
        "Equal units, so the display label breaks the tie and Ada Ames leads. "
        "Both the ids and the source labels run the other way, so neither can be "
        "what produced this order.",
    ),
    (
        "run-aware band edges",
        (
            _endorsement("Alpha Assembly", ("band--anchor", "Anchor Ames")),
            _endorsement("Beta Board", ("band--anchor", "Anchor Ames")),
            _endorsement(
                "Gamma Guild", ("band--anchor", "Anchor Ames"), ("band--bridge", "Bridge Brooks")
            ),
            _endorsement(
                "Delta Digest", ("band--bridge", "Bridge Brooks"), ("band--tail", "Tail Cho")
            ),
        ),
        "Bridge Brooks is supported only by split halves, so that run has no "
        "solid block and the two bands sit side by side. Each is its own band, "
        "which the mockup's neighbour-type heuristic cannot see. The last block "
        "ends at the meter's own edge, so its tongue stays square.",
    ),
    (
        "n-way split",
        (
            _endorsement("Alpha Assembly", ("nway--alpha", "Alpha Ames")),
            _endorsement("Beta Board", ("nway--alpha", "Alpha Ames")),
            _endorsement("Civic Circle", ("nway--bravo", "Bravo Brooks")),
            _endorsement(
                "Delta Digest",
                ("nway--alpha", "Alpha Ames"),
                ("nway--cho", "Cho Diaz"),
                ("nway--bravo", "Bravo Brooks"),
            ),
        ),
        "One block naming three candidates carries them in standings order, top "
        "to bottom, not in the order the cell happened to list them.",
    ),
    (
        "non-adjacent split",
        (
            _endorsement("Alpha Assembly", ("gap--alpha", "Alpha Ames")),
            _endorsement("Beta Board", ("gap--alpha", "Alpha Ames")),
            _endorsement("Civic Circle", ("gap--bravo", "Bravo Brooks")),
            _endorsement("Delta Digest", ("gap--alpha", "Alpha Ames"), ("gap--cho", "Cho Diaz")),
            _endorsement(
                "Echo Examiner", ("gap--alpha", "Alpha Ames"), ("gap--bravo", "Bravo Brooks")
            ),
        ),
        "Both splits sit at the end of the leader's run, farthest partner first, "
        "so the split whose partner's run comes next is the one touching it.",
    ),
    (
        "splits sharing a partner",
        (
            _endorsement("Alpha Assembly", ("pair--alpha", "Alpha Ames")),
            _endorsement("Beta Board", ("pair--alpha", "Alpha Ames")),
            _endorsement(
                "Zenith Ledger", ("pair--alpha", "Alpha Ames"), ("pair--bravo", "Bravo Brooks")
            ),
            _endorsement(
                "Yardley Yearbook", ("pair--alpha", "Alpha Ames"), ("pair--bravo", "Bravo Brooks")
            ),
            _endorsement("Civic Circle", ("pair--bravo", "Bravo Brooks")),
        ),
        "Two splits naming the same pair are the same distance apart, so the "
        "source label decides which comes first — without it the band would keep "
        "whichever order the cells arrived in, and the two renderers receive them "
        "in different orders.",
    ),
    (
        "splits sharing a partner and a source label",
        (
            _endorsement("Alpha Assembly", ("both--alpha", "Alpha Ames")),
            _endorsement(
                "Civic Wire",
                ("both--alpha", "Alpha Ames"),
                ("both--bravo", "Bravo Brooks"),
                ("both--cho", "Cho Diaz"),
            ),
            _endorsement(
                "Civic Wire", ("both--alpha", "Alpha Ames"), ("both--bravo", "Bravo Brooks")
            ),
        ),
        "Two sources publishing under one display name, both splitting at the "
        "same boundary: the partner ties and the source label ties, so the "
        "split's own membership is what finishes the order. Without it the band "
        "would keep whichever order the cells arrived in, and the two renderers "
        "receive them in different orders.",
    ),
    (
        "declining sources",
        (
            _endorsement("Alpha Assembly", ("solo--alpha", "Alpha Ames")),
            _endorsement("Beta Board", ("solo--alpha", "Alpha Ames")),
            _endorsement("Civic Circle"),
            _endorsement("Delta Digest"),
        ),
        "Two sources looked and declined: no block, and no denominator weight "
        "either, so the meter is two blocks wide rather than four. Every other "
        "candidate on the ballot is named by no cell and so has no run at all.",
    ),
)


def _races(view_model: PublicationViewModel) -> list[PublicationRace]:
    return [race for section in view_model.sections for race in section.races]


def _labels(race: PublicationRace) -> dict[str, str]:
    """The candidate labels the client resolves a winner id through."""
    return {group.candidate_id: group.candidate_label for group in race.endorsement_groups} | dict(
        zip(race.support_leader_candidate_ids, race.support_leader_candidate_labels, strict=True)
    )


def _leader_count(race: PublicationRace) -> int:
    """The sole recommendation candidate's contributing sources, or zero.

    `race_detail_support_summary` derives this from the endorsement groups when
    a single candidate leads; the client is passed the same number, so it is an
    input to the mirror rather than part of it.
    """
    if len(race.recommendation_candidate_ids) != 1:
        return 0
    leader_id = race.recommendation_candidate_ids[0]
    return next(
        group.source_count for group in race.endorsement_groups if group.candidate_id == leader_id
    )


def _meter_label(race: PublicationRace, sources: dict[str, PublicationSource]) -> str:
    """The meter's visible text, as the rendered-HTML validator requires it.

    `_html_semantic_values` is the audited page's own statement of what each
    display role must contain, so its `share` entry is the server's answer for
    both a race with a share and a race without one.
    """
    return _html_semantic_values(race, sources)["share"][0]


def _scored(race: PublicationRace) -> dict[str, Any]:
    """The race as the client's scorer reports it, which is what the mirrors read."""
    return {
        "grade": race.grade,
        "isTied": race.grade == "TIED",
        "winnerId": (
            race.support_leader_candidate_ids[0]
            if len(race.support_leader_candidate_ids) == 1
            else None
        ),
        "winnerIds": list(race.support_leader_candidate_ids),
        "winnerShare": race.winner_share,
        "explicitCount": race.explicit_endorsement_count,
    }


def _race_cases(
    race: PublicationRace, panel: str, sources: dict[str, PublicationSource]
) -> list[dict[str, Any]]:
    scored = _scored(race)
    share = race.winner_share
    leader_count = _leader_count(race)
    labels = _labels(race)
    # `screen_support_summary`'s own leader-units guard (docs/METER_V2.md,
    # Caption): `None` for a tie or a race with no single recommended choice,
    # otherwise the exact tally the caption's count comes from. Reached through
    # the private helper rather than restated here, for the reason
    # `_percentage_whole` already is: calling the shipped guard is not a second
    # definition of it.
    leader_units = context._meter_leader_units(race, sources)  # pyright: ignore[reportPrivateUsage]
    leader_units_json = str(leader_units) if leader_units is not None else None
    cases: list[dict[str, Any]] = [
        {
            "mirror": "no-majority",
            "input": {"share": share},
            "expected": context.has_no_majority(race),
        },
        {
            "mirror": "support-summary",
            "input": {
                "leaderUnits": leader_units_json,
                "explicitCount": race.explicit_endorsement_count,
            },
            "expected": context.screen_support_summary(race, sources),
        },
        {
            "mirror": "support-summary-compact",
            "input": {
                "leaderUnits": leader_units_json,
                "explicitCount": race.explicit_endorsement_count,
            },
            "expected": context.screen_support_summary_compact(race, sources),
        },
        {
            "mirror": "recommendation-label",
            "input": {"scored": scored, "labels": labels},
            "expected": race.recommendation_label,
        },
        {
            "mirror": "race-detail-support-summary",
            "input": {"scored": scored, "leaderCount": leader_count},
            "expected": context.race_detail_support_summary(race),
        },
        {
            "mirror": "race-detail-accessible-summary",
            "input": {"scored": scored, "labels": labels, "leaderCount": leader_count},
            "expected": context.race_detail_accessible_summary(race),
        },
    ]
    # The meter's visible text. `percentage_label` is that text only when there
    # is a share: for a race without one the template writes its own `N/A` and
    # the field's em dash is never rendered. `rendering/validation.py` already
    # spells the whole rule as one expression, because the rendered-HTML
    # validator has to know what the meter should say, so both branches read it
    # from there rather than leaving the null one to a literal nobody checks.
    cases.append(
        {
            "mirror": "share-percentage-label" if share is not None else "meter-unavailable-label",
            "input": {"share": share},
            "expected": _meter_label(race, sources),
        }
    )
    endorsements = context.meter_endorsements(race, sources)
    standings = context.meter_standings(endorsements)
    units = context.meter_units(endorsements)
    meter_labels = context.meter_candidate_labels(endorsements)
    units_json = {candidate_id: str(value) for candidate_id, value in units.items()}
    cases.append(
        {
            "mirror": "meter-standings",
            "input": {"endorsements": [_endorsement_json(item) for item in endorsements]},
            "expected": standings,
        }
    )
    cases.append(
        {
            "mirror": "meter-accessible-label",
            "input": {"standings": standings, "units": units_json, "labels": meter_labels},
            "expected": context.meter_accessible_label(standings, units, meter_labels),
        }
    )
    colors = context.meter_candidate_colors(
        standings,
        frozenset(race.support_leader_candidate_ids),
        has_majority=not context.has_no_majority(race),
    )
    cases.append(
        {
            "mirror": "meter-candidate-colors",
            "input": {
                "standings": standings,
                "leaderIds": sorted(race.support_leader_candidate_ids),
                "hasMajority": not context.has_no_majority(race),
            },
            "expected": colors,
        }
    )
    blocks = context.meter_layout_blocks(endorsements)
    cases.append(
        {
            "mirror": "meter-block-renders",
            "input": {
                "blocks": [_block_json(block) for block in blocks],
                "colors": colors,
                "labels": meter_labels,
            },
            "expected": [
                _block_render_json(item)
                for item in context.meter_block_renders(blocks, colors, meter_labels)
            ],
        }
    )
    for case in cases:
        case["source"] = f"published race {race.id} on the {panel} panel"
    return cases


def _state(race: PublicationRace) -> tuple[Any, ...]:
    """What about a race changes what the mirrors say about it.

    Thirty-two races per panel spell the same handful of outcomes over and over.
    One race per outcome keeps the fixture readable while still covering every
    state the panels reach; the key names the branches the mirrors actually
    take, so a new branch cannot hide behind a race that already matched.
    """
    return (
        race.grade,
        len(race.support_leader_candidate_ids),
        len(race.recommendation_candidate_ids),
        race.winner_share is None,
        context.has_no_majority(race),
        min(race.explicit_endorsement_count, 2),
        _leader_count(race) == race.explicit_endorsement_count,
    )


def _panel_view_models(
    dataset: CanonicalDataset,
) -> list[tuple[str, str, PublicationViewModel]]:
    """Each panel as the pipeline builds it, once, for every case family that reads it.

    Two families now read the same four panels. Restricting a panel is one
    expression and it belongs in one place, or the second copy is free to drift
    into selecting a subset the first one never scored.
    """
    return [
        (
            panel,
            note,
            _bundle(
                dataset if source_ids is None else restricted_dataset(dataset, set(source_ids))
            ).view_model,
        )
        for panel, source_ids, note in PANELS
    ]


def _panel_cases(panels: list[tuple[str, str, PublicationViewModel]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for panel, note, view_model in panels:
        sources = {source.id: source for source in view_model.sources}
        seen: set[tuple[Any, ...]] = set()
        for race in _races(view_model):
            state = _state(race)
            if state in seen:
                continue
            seen.add(state)
            for case in _race_cases(race, panel, sources):
                case["note"] = note
                cases.append(case)
    return cases


def _share_cases(base_race: PublicationRace) -> list[dict[str, Any]]:
    """Cases for the formatters that take a share rather than a race.

    `has_no_majority` reads a race, not a share, so a boundary share reaches it
    through a copy of a published race carrying that share and nothing else
    changed. The copy skips validation deliberately — the point is to call the
    shipped predicate on an input no published race happens to hold, not to
    restate its threshold here, which would make this module a second and
    competing definition of the rule.
    """
    cases: list[dict[str, Any]] = []
    for share, note in BOUNDARY_SHARES:
        cases.append(
            {
                "mirror": "comparison-percentage-label",
                "input": {"share": share},
                "expected": context.comparison_percentage_label(share),
                "note": note,
                "source": "comparison_percentage_label as shipped",
            }
        )
        cases.append(
            {
                "mirror": "share-percentage-label",
                "input": {"share": share},
                "expected": f"{_percentage_whole(Fraction(share))}%",
                "note": note,
                "source": "_percentage_whole as shipped",
            }
        )
        cases.append(
            {
                "mirror": "no-majority",
                "input": {"share": share},
                "expected": context.has_no_majority(
                    base_race.model_copy(update={"winner_share": share})
                ),
                "note": note,
                "source": "has_no_majority as shipped, on a race carrying this share",
            }
        )
    cases.append(
        {
            "mirror": "comparison-percentage-label",
            "input": {"share": None},
            "expected": context.comparison_percentage_label(None),
            "note": "A cell with no share prints nothing, not a zero.",
            "source": "comparison_percentage_label as shipped",
        }
    )
    return cases


def _count_cases() -> list[dict[str, Any]]:
    """Cases for the caption's count formatter, which takes a tally, not a race.

    No published race renders a count caption yet — #312 lands the formatter
    ahead of the meter v2 surfaces — so every case is a direct call, exactly as
    the boundary shares reach the percentage formatters."""
    return [
        {
            "mirror": "endorsement-count-label",
            "input": {"count": tally},
            "expected": context.endorsement_count_label(Fraction(tally)),
            "note": note,
            "source": "endorsement_count_label as shipped",
        }
        for tally, note in COUNT_TALLIES
    ]


def _meter_endorsements(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
) -> list[context.MeterEndorsement]:
    """One race's cells as the meter counts them, in the server's own cell order.

    The order matters to what this fixture proves: the server hands the layout
    `race.source_cells` in active-source order while the client hands it cells
    keyed by sorted transport code, so an expectation generated from the
    server's order is only reproducible on the client if the layout's own
    ordering rules are what decide the result.

    A thin alias for `context.meter_endorsements` rather than a second
    implementation of its admission rule — #314 gave that rule its one
    production home, which this fixture generator now uses too.
    """
    return context.meter_endorsements(race, sources)


def _endorsement_json(endorsement: context.MeterEndorsement) -> dict[str, Any]:
    return {
        "source_label": endorsement.source_label,
        "candidate_ids": list(endorsement.candidate_ids),
        "candidate_labels": list(endorsement.candidate_labels),
    }


def _block_json(block: context.MeterBlock) -> dict[str, Any]:
    """One block, in field order, so the two languages' goldens compare as bytes."""
    return {
        "type": block.type,
        "width": block.width,
        "candidate_ids": list(block.candidate_ids),
        "source_label": block.source_label,
        "band_start": block.band_start,
        "band_end": block.band_end,
        "tongue_corner_start": block.tongue_corner_start,
        "tongue_corner_end": block.tongue_corner_end,
    }


def _block_render_json(render: context.MeterBlockRender) -> dict[str, Any]:
    """One block's paint, in field order, so the two languages' goldens compare
    as bytes."""
    return {
        "type": render.type,
        "width": render.width,
        "style": render.style,
        "band_start": render.band_start,
        "band_end": render.band_end,
        "tongue_corner_start": render.tongue_corner_start,
        "tongue_corner_end": render.tongue_corner_end,
        "source_label": render.source_label,
        "decision": render.decision,
    }


def _synthetic_leader_ids(standings: list[str], units: dict[str, Fraction]) -> frozenset[str]:
    """The candidates tied for first, from units alone.

    Test-only: production code reads the tie-aware leader set off the race
    itself (`support_leader_candidate_ids`) rather than re-deriving it from
    block units (docs/METER_V2.md, Color), because the two must not disagree.
    A hand-built layout shape carries no race to read that set from, so this
    reconstructs it the way the reference mockup did, for exactly the
    synthetic shapes below and nowhere production code runs.
    """
    if not standings:
        return frozenset()
    top = units[standings[0]]
    return frozenset(candidate_id for candidate_id in standings if units[candidate_id] == top)


def _meter_layout_case(
    endorsements: list[context.MeterEndorsement],
    note: str,
    source: str,
) -> list[dict[str, Any]]:
    """Every mirror one endorsement set feeds, bundled so a shape reaches all
    of them at once: the block list, the standings order, the accessible
    name, the candidate colors, and each block's paint and tooltip text."""
    blocks = context.meter_layout_blocks(endorsements)
    standings = context.meter_standings(endorsements)
    units = context.meter_units(endorsements)
    labels = context.meter_candidate_labels(endorsements)
    leader_ids = _synthetic_leader_ids(standings, units)
    has_majority = len(leader_ids) == 1 and units[standings[0]] * 2 > sum(
        units.values(), Fraction(0)
    )
    colors = context.meter_candidate_colors(standings, leader_ids, has_majority=has_majority)
    endorsements_json = [_endorsement_json(item) for item in endorsements]
    return [
        {
            "mirror": "meter-layout-blocks",
            "input": {"endorsements": endorsements_json},
            "expected": [_block_json(block) for block in blocks],
            "note": note,
            "source": source,
        },
        {
            "mirror": "meter-standings",
            "input": {"endorsements": endorsements_json},
            "expected": standings,
            "note": note,
            "source": source,
        },
        {
            "mirror": "meter-accessible-label",
            "input": {
                "standings": standings,
                "units": {candidate_id: str(value) for candidate_id, value in units.items()},
                "labels": labels,
            },
            "expected": context.meter_accessible_label(standings, units, labels),
            "note": note,
            "source": source,
        },
        {
            "mirror": "meter-candidate-colors",
            "input": {
                "standings": standings,
                "leaderIds": sorted(leader_ids),
                "hasMajority": has_majority,
            },
            "expected": colors,
            "note": note,
            "source": source,
        },
        {
            "mirror": "meter-block-renders",
            "input": {
                "blocks": [_block_json(block) for block in blocks],
                "colors": colors,
                "labels": labels,
            },
            "expected": [
                _block_render_json(item)
                for item in context.meter_block_renders(blocks, colors, labels)
            ],
            "note": note,
            "source": source,
        },
    ]


def _meter_layout_cases(
    panels: list[tuple[str, str, PublicationViewModel]],
) -> list[dict[str, Any]]:
    """Cases for the segmented meter's block list (docs/METER_V2.md).

    The published races come from `page_parity.race_parity_fixture_ids`, the
    same greedy cover over the same feature census that chooses which race pages
    are committed as markup-parity fixtures: those are already the fewest races
    showing every reachable shape, and the shapes the meter cares about — a
    split, a tie, a sole leader, several candidates, a race a lens leaves with
    no endorsement at all — are named in that census. Reusing it means the
    selection stays a function of the committed dataset rather than of a
    preference expressed here, and the layout and the markup it will feed are
    read off the same races.

    What that cover cannot show, this election's data does not contain, so the
    shapes above supply it.
    """
    cases: list[dict[str, Any]] = []
    for panel, note, view_model in panels:
        sources = {source.id: source for source in view_model.sources}
        chosen = set(race_parity_fixture_ids(view_model))
        for race in _races(view_model):
            if race.id not in chosen:
                continue
            cases.extend(
                _meter_layout_case(
                    _meter_endorsements(race, sources),
                    note,
                    f"published race {race.id} on the {panel} panel",
                )
            )
    for name, endorsements, note in LAYOUT_SHAPES:
        cases.extend(
            _meter_layout_case(list(endorsements), note, f"meter_layout_blocks on the {name} shape")
        )
    return cases


# Color-pool exhaustion (docs/METER_V2.md, Color; Decision log #18) is not
# reachable by this election's published data — no race runs four trailing
# candidates or three tied leaders deep — so these hand-built standings drive
# `meter_candidate_colors` directly, the same reason `LAYOUT_SHAPES` above
# hand-builds the layout cases the ballot cannot reach.
_METER_COLOR_CASES: tuple[tuple[str, list[str], frozenset[str], bool, str], ...] = (
    (
        "sole majority leader, three trailing candidates",
        ["a", "b", "c", "d"],
        frozenset({"a"}),
        True,
        "The trailing pool — slate, taupe, plum — exactly covers three candidates; none "
        "steps toward the track.",
    ),
    (
        "sole majority leader, four trailing candidates",
        ["a", "b", "c", "d", "e"],
        frozenset({"a"}),
        True,
        "A fourth trailing candidate exhausts the muted pool: it steps toward the track "
        "rather than repeating a swatch.",
    ),
    (
        "two tied leaders",
        ["a", "b", "c"],
        frozenset({"a", "b"}),
        False,
        "Two tied leaders exactly fill the tie pool: amber, then the deep tie amber.",
    ),
    (
        "three tied leaders",
        ["a", "b", "c"],
        frozenset({"a", "b", "c"}),
        False,
        "A third tied leader exhausts the tie pool and steps toward the track, exactly as "
        "a fourth trailing candidate does.",
    ),
    (
        "sole no-majority leader",
        ["a", "b"],
        frozenset({"a"}),
        False,
        "A sole leader short of a majority keeps v1's amber, unchanged (Decision log #10).",
    ),
)


def _meter_color_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for name, standings, leader_ids, has_majority, note in _METER_COLOR_CASES:
        cases.append(
            {
                "mirror": "meter-candidate-colors",
                "input": {
                    "standings": standings,
                    "leaderIds": sorted(leader_ids),
                    "hasMajority": has_majority,
                },
                "expected": context.meter_candidate_colors(
                    standings, leader_ids, has_majority=has_majority
                ),
                "note": note,
                "source": f"meter_candidate_colors on the {name} shape",
            }
        )
    return cases


def _row_differs_cases() -> list[dict[str, Any]]:
    """Rows assembled from the cell kinds the comparison table actually renders.

    The cells are `context.ComparisonCellView`s and the expectation is
    `comparison_row_differs` itself, so a lead set that disagrees here is a
    disagreement about the published rule rather than about this module.
    """

    def cell(kind: str, *leading: str) -> context.ComparisonCellView:
        return context.ComparisonCellView(
            signal=kind,
            kind=kind,
            choice_labels=tuple(leading),
            leading_pick_ids=tuple(leading),
        )

    rows: tuple[tuple[str, tuple[context.ComparisonCellView, ...], str], ...] = (
        (
            "agreeing",
            (cell("baseline", "a"), cell("direct", "a"), cell("comparison", "a")),
            "Every column leads with the same choice.",
        ),
        (
            "one-differs",
            (cell("baseline", "a"), cell("direct", "a"), cell("comparison", "b")),
            "One disjoint lead set is enough to mark the row.",
        ),
        (
            "overlapping-leads",
            (cell("baseline", "a", "b"), cell("direct", "b", "c")),
            "Overlapping co-endorsements agree; only a disjoint set differs.",
        ),
        (
            "blank-is-neutral",
            (cell("baseline", "a"), cell("blank"), cell("direct", "b")),
            "A blank cell never creates a difference, but its neighbour can.",
        ),
        (
            "blank-only",
            (cell("baseline", "a"), cell("blank"), cell("outside_scope")),
            "Cells without data leave a row undifferentiated.",
        ),
        (
            "empty-reference",
            (cell("baseline"), cell("direct", "a")),
            "A reference with no lead set cannot be disagreed with.",
        ),
        (
            "single-cell",
            (cell("baseline", "a"),),
            "One column has nothing to compare against.",
        ),
    )
    return [
        {
            "mirror": "comparison-row-differs",
            "input": {
                "cells": [
                    {"kind": item.kind, "leadingPickIds": list(item.leading_pick_ids)}
                    for item in cells
                ]
            },
            "expected": context.comparison_row_differs(cells),
            "note": note,
            "source": f"comparison_row_differs on the {name} row",
        }
        for name, cells, note in rows
    ]


def _audited_page_text(path: Path, attribute: str) -> str:
    """The text the server rendered into one element of a committed page fixture."""
    html = path.read_text(encoding="utf-8")
    match = re.search(rf"<[^<>]*\b{attribute}\b[^<>]*>([^<]*)<", html)
    if match is None:
        raise ValueError(f"{path.name} has no element carrying {attribute}")
    return match.group(1).strip()


# Column sets to encode, within the two-to-three columns `compare-url.mjs`
# admits. The first three are the presets the Comparisons page renders as
# links; the rest reach shapes no preset uses, so the codec's ordering and its
# reserved aggregate token are covered rather than assumed.
#
# The bound is the client's alone: `MIN_COLUMNS`/`MAX_COLUMNS` guard
# `encodeCompareFragment`, and `comparison_fragment` has no matching guard. The
# two sides therefore agree on every input the server actually produces — every
# preset asks for two — and a fixture case outside that range would be
# asserting a shape only one side has an opinion about. The asymmetry is real
# but latent: a fourth column added to a preset in `rendering/documents.py`
# would render a link the client refuses to decode, and the page would open on
# its default columns instead. `tests/mirrors.json` records that rather than
# this module papering over it with a case.
FRAGMENT_COLUMNS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("strn", "stim"), "The two direct sources the page offers as a preset."),
    (("Glab", "Genv"), "Two category columns, whose tokens are capitalized."),
    (("gall", "urbn"), "The reserved all-sources aggregate beside a direct source."),
    (
        ("gall", "strn", "stim"),
        "Three columns concatenate in the order given, not in sorted order.",
    ),
    (
        ("stim", "strn"),
        "The same two sources in the other order encode to a different fragment.",
    ),
)


def _fragment_cases(view_model: PublicationViewModel) -> list[dict[str, Any]]:
    """The Comparisons preset fragment, which both sides write independently.

    `comparison_fragment` composes the fragment in Python for the links the
    audited page renders; `encodeCompareFragment` composes it in JavaScript for
    every state change after that. Both spell the same parameter names in the
    same canonical order, the same `cmp=1` schema version, and the same
    twelve-character panel-hash prefix — `panel_hash[:12]` on one side and
    `HASH_PREFIX_LENGTH = 12` on the other.

    docs/FRONTEND.md § Cross-language mirrors names encoding as a mirror
    category, and this is the only one left. It shares no display text and
    neither side names the other, so `cross_language_mirrors.py` cannot see it;
    it is on the inventory because a reader put it there. A change to the
    prefix or the order on one side alone turns every server-rendered preset
    link into a `stale_version` rejection, which is quiet: the page still loads,
    on the default columns rather than the ones the link asked for.
    """
    return [
        {
            "mirror": "compare-fragment-encoding",
            "input": {"page": COMPARE_PAGE_PATH.name, "columns": list(columns)},
            "expected": context.comparison_fragment(view_model, list(columns)),
            "note": note,
            "source": "comparison_fragment as shipped",
        }
        for columns, note in FRAGMENT_COLUMNS
    ]


def _only_count(text: str) -> int:
    """The one number a counting sentence states, or both if it states them twice.

    The count itself is an input to the mirror rather than part of it: two
    templates derive it two different ways and this module must not become a
    third. Reading it back off the sentence leaves the wording — which *is* the
    mirror — as the only thing the case asserts.
    """
    numbers = {int(item) for item in re.findall(r"\d+", text)}
    if len(numbers) != 1:
        raise ValueError(f"expected one count in {text!r}, found {sorted(numbers)}")
    return numbers.pop()


def _counting_cases() -> list[dict[str, Any]]:
    """The counting sentences, read back out of the rendered audited pages.

    Neither is a Python function: `guide.html.j2` writes the guide's banner and
    `sources.html.j2` writes the editor's count, and `countingSummary` restates
    both in the client. Holding the client to the shipped bytes is the claim, so
    the bytes are where the expectation comes from.

    The count behind those sentences is its own mirror. The guide counts
    contributing consensus sources in Jinja; `tallyingSourceCodes` counts
    non-comparison payload sources in the client. Two predicates over two
    collections that must reach one number, so the last case asserts that they
    do — against the number the audited banner actually shipped.
    """
    guide_text = _audited_page_text(GUIDE_PAGE_PATH, "data-lens-banner-status")
    sources_text = _audited_page_text(SOURCES_PAGE_PATH, "data-sources-count")
    guide_count = _only_count(guide_text)
    return [
        {
            "mirror": "counting-summary",
            "input": {
                "selectedCount": guide_count,
                "tallyingCount": guide_count,
                "personalized": False,
            },
            "expected": guide_text,
            "note": "The guide's banner before a reader touches anything.",
            "source": "guide-audited-page.html, the rendered lens banner",
        },
        {
            "mirror": "counting-summary",
            "input": {
                "selectedCount": (sources_count := _only_count(sources_text)),
                "tallyingCount": sources_count,
                "personalized": True,
            },
            "expected": sources_text,
            "note": "The sources editor's count, which spells both numbers even when they match.",
            "source": "sources-audited-page.html, the rendered page count",
        },
        {
            "mirror": "tallying-source-count",
            "input": {"page": GUIDE_PAGE_PATH.name},
            "expected": guide_count,
            "note": "A comparison source is published so a pre-removal link's "
            "token still resolves, and counts toward neither side's total.",
            "source": "guide-audited-page.html, the count its banner states",
        },
    ]


def _deduplicate(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One case per distinct claim.

    Thirty-two races times four panels repeat the same few inputs many times
    over; keeping the first of each leaves a fixture a reviewer can read while
    still covering every state the panels reach.
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for case in cases:
        key = json.dumps([case["mirror"], case["input"]], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(case)
    return sorted(
        unique, key=lambda case: (case["mirror"], json.dumps(case["input"], sort_keys=True))
    )


def build_mirror_parity_fixture(dataset: CanonicalDataset) -> dict[str, Any]:
    """Emit every golden case, computed by the server implementations."""
    panels = _panel_view_models(dataset)
    view_model = next(published for panel, _, published in panels if panel == "audited")
    cases = _deduplicate(
        [
            *_panel_cases(panels),
            *_share_cases(_races(view_model)[0]),
            *_count_cases(),
            *_meter_layout_cases(panels),
            *_meter_color_cases(),
            *_row_differs_cases(),
            *_fragment_cases(view_model),
            *_counting_cases(),
        ]
    )
    return {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "panels": [{"name": name, "note": note} for name, _, note in PANELS],
        "cases": cases,
    }


def generate() -> dict[str, Any]:
    dataset = CanonicalDataset.model_validate(read_json(DATASET_PATH))
    return build_mirror_parity_fixture(dataset)


if __name__ == "__main__":
    FIXTURE_PATH.write_text(
        json.dumps(generate(), indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {FIXTURE_PATH.relative_to(PROJECT_ROOT)}")
