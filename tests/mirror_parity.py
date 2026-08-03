"""Golden cases for the cross-language mirrors that survived the contract work.

docs/FRONTEND.md § Cross-language mirrors: logic written in both Python and
JavaScript needs a generated parity fixture, because a comment is not a
contract. `tests/mirrors.json` is the inventory of what remains a mirror after
#236 moved the audited labels into the payload and #239 extracted the guide's
glue into modules; this module emits the golden cases for every entry that
inventory marks `parity-fixture`, and `tests/js/mirror-parity.test.mjs` asserts
them against the client modules.

**Nothing here restates a formatting rule.** Each expectation comes from the
shipped server implementation, in one of four ways:

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
    PublicationViewModel,
    _percentage_whole,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.rendering import context
from election_guide.rendering.validation import (
    _html_semantic_values,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.serialization import read_json
from tests.test_personalization import DATASET_PATH, _bundle  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "mirror-parity.json"
MIRRORS_PATH = PROJECT_ROOT / "tests" / "mirrors.json"
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


def _meter_label(race: PublicationRace) -> str:
    """The meter's visible text, as the rendered-HTML validator requires it.

    `_html_semantic_values` is the audited page's own statement of what each
    display role must contain, so its `share` entry is the server's answer for
    both a race with a share and a race without one.
    """
    return _html_semantic_values(race)["share"][0]


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


def _race_cases(race: PublicationRace, panel: str) -> list[dict[str, Any]]:
    scored = _scored(race)
    share = race.winner_share
    leader_count = _leader_count(race)
    labels = _labels(race)
    cases: list[dict[str, Any]] = [
        {
            "mirror": "no-majority",
            "input": {"share": share},
            "expected": context.has_no_majority(race),
        },
        {
            "mirror": "share-accessible-label",
            "input": {"share": share},
            "expected": context.screen_share_accessible_label(race),
        },
        {
            "mirror": "support-summary",
            "input": {"scored": scored},
            "expected": context.screen_support_summary(race),
        },
        {
            "mirror": "support-summary-compact",
            "input": {"scored": scored},
            "expected": context.screen_support_summary_compact(race),
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
            "expected": _meter_label(race),
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


def _panel_cases(dataset: CanonicalDataset) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for panel, source_ids, note in PANELS:
        panel_dataset = (
            dataset if source_ids is None else restricted_dataset(dataset, set(source_ids))
        )
        seen: set[tuple[Any, ...]] = set()
        for race in _races(_bundle(panel_dataset).view_model):
            state = _state(race)
            if state in seen:
                continue
            seen.add(state)
            for case in _race_cases(race, panel):
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
    view_model = _bundle(dataset).view_model
    cases = _deduplicate(
        [
            *_panel_cases(dataset),
            *_share_cases(_races(view_model)[0]),
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


def fixtured_mirrors() -> set[str]:
    """The inventory entries this module is expected to emit cases for."""
    inventory = json.loads(MIRRORS_PATH.read_text(encoding="utf-8"))
    return {
        name for name, entry in inventory["mirrors"].items() if entry["proof"] == "parity-fixture"
    }


if __name__ == "__main__":
    FIXTURE_PATH.write_text(
        json.dumps(generate(), indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {FIXTURE_PATH.relative_to(PROJECT_ROOT)}")
