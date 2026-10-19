"""Registered synthetic panels for the preregistered sensitivity examples."""

from pathlib import Path
from typing import Any

from election_guide.normalization.models import CanonicalDataset
from election_guide.sources.models import SourceRegistry
from tests.test_scoring import (
    COMPARISON_SOURCE_ID,
    RACE_ID,
    EndorsementSpec,
    _candidate_ids,  # pyright: ignore[reportPrivateUsage]
    _dataset,  # pyright: ignore[reportPrivateUsage]
    _source_registry,  # pyright: ignore[reportPrivateUsage]
)


def synthetic_dataset(
    root: Path,
    categories: list[tuple[int, int]],
    *,
    grouped_a_per_category: int = 0,
    no_endorsements: int = 0,
    missing_sources: int = 0,
) -> CanonicalDataset:
    registry = _source_registry().model_dump(mode="json")
    template = next(source for source in registry["sources"] if source["panel_role"] == "consensus")
    comparison = next(
        source for source in registry["sources"] if source["id"] == COMPARISON_SOURCE_ID
    )
    category_template = registry["categories"][0]
    category_count = max(1, len(categories))
    registry["categories"] = [
        {
            **category_template,
            "id": f"synthetic_{index}",
            "code": f"G{index:03d}",
            "label": f"Synthetic category {index}",
            "panel_role": "tallying",
            "selectable": True,
        }
        for index in range(category_count)
    ] + [
        {
            **category_template,
            "id": comparison["reporting_category_id"],
            "code": "GZZZ",
            "label": "Comparison",
            "panel_role": "comparison",
            "selectable": True,
        }
    ]
    sources: list[dict[str, Any]] = []
    specs: list[EndorsementSpec] = []
    group_members: list[str] = []
    candidates = _candidate_ids()

    def add_source(category: int) -> str:
        index = len(sources)
        source_id = f"synthetic-source-{index:03d}"
        sources.append(
            {
                **template,
                "id": source_id,
                "code": f"s{index:03d}",
                "name": f"Synthetic source {index}",
                "reporting_category_id": f"synthetic_{category}",
                "selection_category_ids": [f"synthetic_{category}"],
                "overlap_group_ids": [],
            }
        )
        return source_id

    for category, counts in enumerate(categories):
        for choice, count in enumerate(counts):
            for ordinal in range(count):
                source_id = add_source(category)
                specs.append((source_id, "endorsed", candidates[choice : choice + 1]))
                if choice == 0 and ordinal < grouped_a_per_category:
                    group_members.append(source_id)
    for _ in range(no_endorsements):
        specs.append((add_source(0), "no_endorsement", []))
    for _ in range(missing_sources):
        add_source(0)
    registry["overlap_groups"] = []
    if group_members:
        registry["overlap_groups"] = [
            {
                "id": "synthetic-group",
                "label": "Synthetic group",
                "description": "A disclosed relationship; independent decisions are unknown.",
                "member_ids": group_members,
            }
        ]
        for source in sources:
            if source["id"] in group_members:
                source["overlap_group_ids"] = ["synthetic-group"]
    registry["sources"] = [*sources, comparison]
    registry["retired_codes"] = []
    dataset = _dataset(root, specs, source_registry=SourceRegistry.model_validate(registry))
    payload = dataset.model_dump(mode="json")
    payload["inventory"]["races"] = [
        race for race in payload["inventory"]["races"] if race["id"] == RACE_ID
    ]
    for check in payload["inventory"]["coverage_checks"]:
        check["matched_races"] = sum(
            check["source_id"] in race["source_ids"] for race in payload["inventory"]["races"]
        )
        check["matched_choices"] = sum(
            check["source_id"] in choice["source_ids"]
            for race in payload["inventory"]["races"]
            for choice in race["choices"]
        )
    return CanonicalDataset.model_validate(payload)
