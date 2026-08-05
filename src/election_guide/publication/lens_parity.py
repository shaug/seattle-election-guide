"""Parity fixtures proving the client lens reproduces the audited engine.

The client engine in `rendering/templates/lens-score.mjs` recomputes consensus
for a chosen subset of the panel. Its correctness claim is only as good as its
oracle, so the oracle here is the audited engine itself: for each selection the
dataset is rescored by `score_dataset` with every unselected consensus source
excluded from the panel. Restricting the panel is exactly what selecting a
subset means, so no scoring rule is reimplemented to produce an expectation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from election_guide.normalization.models import CanonicalDataset
from election_guide.publication.models import PublicationViewModel
from election_guide.scoring import score_dataset
from election_guide.scoring.models import RaceConsensus, ScoringConfiguration

FIXTURE_SCHEMA_VERSION = "1.0"

# The fixture records only the lens contract, so neither the build commit nor the
# scoring timestamp reaches it. Both exist to satisfy required arguments: a
# placeholder commit for build_publication_bundle, and a timestamp that must not
# predate the newest scoring input or score_dataset refuses to run.
FIXTURE_COMMIT = "0" * 40
FIXTURE_COMPUTED_AT = "2026-08-05T00:20:00Z"


class ParitySelection(BaseModel):
    """One named selection expressed the way a client would express it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    category_codes: list[str] = []
    source_codes: list[str] = []
    note: str


def restricted_dataset(dataset: CanonicalDataset, source_ids: set[str]) -> CanonicalDataset:
    """Return the dataset with every consensus source outside the selection excluded."""
    sources = [
        source
        if source.panel_role != "consensus" or source.id in source_ids
        else source.model_copy(update={"panel_role": "excluded"})
        for source in dataset.source_registry.sources
    ]
    registry = dataset.source_registry.model_copy(update={"sources": sources})
    return dataset.model_copy(update={"source_registry": registry})


def _effective_source_ids(
    view_model: PublicationViewModel,
    selection: ParitySelection,
) -> set[str]:
    """Resolve the selection the way the published contract defines it."""
    contract = view_model.personalization
    selectable = {source.code: source for source in contract.sources if source.selectable}
    categories = {item.code: item for item in contract.categories if item.selectable}
    comparison = set(contract.policy.comparison_source_codes)

    codes: set[str] = set()
    for code in selection.category_codes:
        category = categories.get(code)
        if category is None:
            continue
        codes.update(category.member_source_codes)
    codes.update(selection.source_codes)
    return {selectable[code].id for code in codes if code in selectable and code not in comparison}


def _race_expectation(race: RaceConsensus) -> dict[str, object]:
    payload = race.model_dump(mode="json")
    return {
        "race_id": payload["race_id"],
        "grade": payload["grade"],
        "winner_candidate_id": payload["winner_candidate_id"],
        "winner_candidate_ids": payload["winner_candidate_ids"],
        "winner_share": payload["winner_share"],
        "is_tied": payload["is_tied"],
        "candidate_support": payload["candidate_support"],
        "eligible_source_count": payload["eligible_source_count"],
        "source_coverage_count": payload["source_coverage_count"],
        "explicit_endorsement_count": payload["explicit_endorsement_count"],
        "no_endorsement_count": payload["no_endorsement_count"],
        "missing_source_count": payload["missing_source_count"],
    }


def build_parity_fixture(
    dataset: CanonicalDataset,
    configuration: ScoringConfiguration,
    view_model: PublicationViewModel,
    selections: list[ParitySelection],
    *,
    computed_at: datetime,
) -> dict[str, object]:
    """Score every selection with the audited engine and emit a client fixture."""
    code_by_id = {source.id: source.code for source in view_model.personalization.sources}
    cases: list[dict[str, object]] = []
    for selection in selections:
        source_ids = _effective_source_ids(view_model, selection)
        report = score_dataset(
            restricted_dataset(dataset, source_ids),
            configuration,
            computed_at=computed_at,
            allow_unresolved=True,
        )
        cases.append(
            {
                "name": selection.name,
                "note": selection.note,
                "selection": {
                    "categoryCodes": selection.category_codes,
                    "sourceCodes": selection.source_codes,
                },
                "effective_source_codes": sorted(code_by_id[item] for item in source_ids),
                "races": [_race_expectation(race) for race in report.races],
            }
        )
    return {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "personalization": view_model.personalization.model_dump(mode="json"),
        "cases": cases,
    }


# One selection per behavior the acceptance criteria name. Every expectation is
# produced by the audited engine, so a case is a claim about scoring policy
# rather than about this module.
LENS_PARITY_SELECTIONS: list[ParitySelection] = [
    ParitySelection(
        name="empty",
        note="No selection scores nothing and every race is insufficient.",
    ),
    ParitySelection(
        name="single-source",
        source_codes=["strn"],
        note="One source: a lone endorsement cannot reach the explicit-source floor.",
    ),
    ParitySelection(
        name="two-sources-split",
        source_codes=["strn", "urbn"],
        note="Two sources expose split endorsements and exact tie resolution.",
    ),
    ParitySelection(
        name="category-labor",
        category_codes=["Glab"],
        note="Category selection follows current published membership.",
    ),
    ParitySelection(
        name="category-overlap-union",
        category_codes=["Glab", "Gdem"],
        note="Overlapping categories must not double-count a shared source.",
    ),
    ParitySelection(
        name="category-plus-member",
        category_codes=["Glab"],
        source_codes=["strn"],
        note="A source reached by both a category and a direct pick counts once.",
    ),
    ParitySelection(
        name="wrong-district",
        source_codes=["ld11", "ld43"],
        note="District sources stay ineligible outside their own legislative races.",
    ),
    ParitySelection(
        name="comparison-refused",
        source_codes=["stim", "strn"],
        note="The Seattle Times cannot contribute even when explicitly selected.",
    ),
    ParitySelection(
        name="excluded-refused",
        source_codes=["pvot", "strn"],
        note="An excluded source cannot be selected back into the panel.",
    ),
    ParitySelection(
        name="unknown-refused",
        category_codes=["Gzzz"],
        source_codes=["zzzz"],
        note="Unknown codes are ignored rather than scored.",
    ),
    ParitySelection(
        name="comparison-category-selected",
        category_codes=["Gcmp"],
        note="Selecting the comparison category can never enter the tally.",
    ),
    ParitySelection(
        name="full-panel",
        category_codes=["Ggen", "Gdem", "Gurb", "Genv", "Glab", "Grgt"],
        note="Every selectable category reproduces the audited published consensus.",
    ),
]
