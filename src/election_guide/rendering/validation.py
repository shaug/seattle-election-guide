"""Check that a rendered guide says exactly what the view model says.

The document is reparsed rather than trusted: every race, semantic field,
source-evidence row, and link the HTML exposes is compared against the same
`rendering/context.py` values the templates rendered from, and the captured
screenshots are checked for the configured viewport size and nonblank ink.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image

from election_guide.publication.models import PublicationRace, PublicationViewModel
from election_guide.rendering import context
from election_guide.rendering.browser import image_ink_fraction
from election_guide.rendering.models import (
    RenderCheck,
    RenderingConfiguration,
    RenderingValidationReport,
)
from election_guide.rendering.shell import HOW_TO_VOTE_HREF


def validate_rendered_guide(
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
    html_path: Path,
    screenshots: list[Path],
) -> RenderingValidationReport:
    """Validate semantic parity and rendered responsive-capture safety."""
    html = html_path.read_text(encoding="utf-8")
    parser = _GuideHTMLParser()
    parser.feed(html)
    expected_races = [race for section in view_model.sections for race in section.races]
    expected_race_ids = [race.id for race in expected_races]
    mismatched_html_roles: list[str] = []
    for race in expected_races:
        for role, expected_values in _html_semantic_values(race).items():
            observed_values = [
                _normalized_text(" ".join(parts))
                for parts in parser.display_text.get((race.id, role), [])
            ]
            normalized_expected = [_normalized_text(value) for value in expected_values]
            if observed_values != normalized_expected:
                mismatched_html_roles.append(f"{race.id}/{role}")
        share_key = (race.id, "share")
        if parser.display_accessible_names.get(share_key, []) != [
            context.screen_share_accessible_label(race)
        ]:
            mismatched_html_roles.append(f"{race.id}/share-accessible-name")
        if parser.display_element_roles.get(share_key, []) != ["img"]:
            mismatched_html_roles.append(f"{race.id}/share-accessible-role")
    missing_evidence_rows: list[str] = []
    source_by_id = {source.id: source for source in view_model.sources}
    category_label_by_key = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    # A rendered source row is addressed by its transport code, the one
    # identifier the client payload publishes (docs/FRONTEND.md, The data
    # contract), so the observed keys are in code space too.
    source_code_by_id = {source.id: source.code for source in view_model.personalization.sources}
    # Issue 124: a comparison source renders no race-detail row at all.
    expected_detail_keys = {
        (race.id, source_code_by_id[cell.source_id])
        for race in expected_races
        for cell in context.tallying_source_cells(race, source_by_id)
    }
    if set(parser.race_detail_text) != expected_detail_keys:
        missing_evidence_rows.append("document: unexpected or missing race-detail source rows")
    for race in expected_races:
        endorsement_groups = context.candidate_endorsement_groups(race)
        for cell in context.tallying_source_cells(race, source_by_id):
            key = (race.id, source_code_by_id[cell.source_id])
            source = source_by_id[cell.source_id]
            expected_group = context.source_cell_group(cell, race, source)
            expected_links: set[str] = (
                {cell.evidence_url} if cell.evidence_url is not None else set()
            )
            if expected_group == "candidate":
                expected_candidate_ids: list[str | None] = [
                    group.candidate_id
                    for group in endorsement_groups
                    if group.candidate_id in cell.candidate_ids
                ]
            else:
                expected_candidate_ids = [None]
            expected_parts = [source.name, category_label_by_key[source.category]]
            detail_label = context.source_cell_detail_label(cell, race, expected_group)
            if detail_label is not None:
                expected_parts.append(detail_label)
            expected_rows = [
                _normalized_text(" ".join(expected_parts)) for _ in expected_candidate_ids
            ]
            expected_links_list = [expected_links for _ in expected_candidate_ids]
            expected_states = [cell.state for _ in expected_candidate_ids]
            expected_categories = [source.category for _ in expected_candidate_ids]
            expected_groups = [expected_group for _ in expected_candidate_ids]
            expected_row_class = {"race-detail-source-row"}
            expected_row_classes = [expected_row_class for _ in expected_candidate_ids]
            observed_rows = [
                _normalized_text(" ".join(parts)) for parts in parser.race_detail_text.get(key, [])
            ]
            if (
                observed_rows != expected_rows
                or parser.race_detail_links.get(key, []) != expected_links_list
                or parser.race_detail_states.get(key, []) != expected_states
                or parser.race_detail_categories.get(key, []) != expected_categories
                or parser.race_detail_groups.get(key, []) != expected_groups
                or parser.race_detail_candidate_ids.get(key, []) != expected_candidate_ids
                or parser.race_detail_row_classes.get(key, []) != expected_row_classes
            ):
                missing_evidence_rows.append(
                    f"{race.id}/{cell.source_id}: race-detail group, state, candidate, "
                    "class, or evidence"
                )
    expected_html_links = {
        "#guide-races",
        "/",  # the footer's brand mark links home (item L55)
        # The band's brand mark links straight to the current election's guide
        # rather than to `/`, which only redirects there (issue 192); that link
        # target is also what the extended-masthead dial keys off.
        f"/e/{view_model.metadata.election_id}/",
        # Slot 4's "How to vote" (issue 192). King County Elections administers
        # Seattle's ballots and is already this repository's cited authority.
        HOW_TO_VOTE_HREF,
        f"/e/{view_model.metadata.election_id}/sources/",
        "mailto:seattle-elections@dobravoda.dev",
        "/about/",
        configuration.project_url,
        # The footer audit line's Code hash links to the exact commit (item L55.2).
        f"{configuration.project_url}/commit/{view_model.metadata.git_commit}",
        f"/e/{view_model.metadata.election_id}/release-manifest.json",
        *(f"#race-{race.id}" for race in expected_races),
        *(
            cell.evidence_url
            for race in expected_races
            for cell in context.tallying_source_cells(race, source_by_id)
            if cell.evidence_url is not None
        ),
    }
    if view_model.comparisons.policy.enabled:
        expected_html_links.add(f"/e/{view_model.metadata.election_id}/comparisons/")
    canonical_url = f"{configuration.public_site_url}/e/{view_model.metadata.election_id}/"
    required_site_metadata = {
        f'<link rel="canonical" href="{canonical_url}">',
        f'<meta property="og:url" content="{canonical_url}">',
    }
    if not required_site_metadata.issubset({line.strip() for line in html.splitlines()}):
        missing_evidence_rows.append("document: missing election-scoped canonical metadata")
    if parser.links != expected_html_links:
        missing_evidence_rows.append("document: unexpected or missing links")
    screenshot_sizes: list[tuple[int, int]] = []
    screenshot_ink: list[float] = []
    for path in screenshots:
        with Image.open(path) as image:
            screenshot_sizes.append(image.size)
        screenshot_ink.append(image_ink_fraction(path))
    responsive_sizes = screenshot_sizes == [
        (configuration.desktop_width, configuration.screenshot_height),
        (configuration.mobile_width, configuration.screenshot_height),
    ] and all(fraction > 0.005 for fraction in screenshot_ink)
    checks = [
        RenderCheck(
            id="html-race-topology",
            passed=parser.race_ids == expected_race_ids,
            message="Responsive HTML contains every expected race exactly once in canonical order.",
        ),
        RenderCheck(
            id="html-display-values",
            passed=not mismatched_html_roles,
            message=(
                "Responsive HTML exposes exactly one canonical value in every semantic field."
                if not mismatched_html_roles
                else f"HTML semantic fields differ: {', '.join(mismatched_html_roles[:5])}"
            ),
        ),
        RenderCheck(
            id="html-source-evidence",
            passed=not missing_evidence_rows,
            message=(
                "Every race-detail source cell appears exactly once with canonical state "
                "and evidence."
                if not missing_evidence_rows
                else (
                    "HTML source-detail rows are incomplete: "
                    f"{', '.join(missing_evidence_rows[:5])}"
                )
            ),
        ),
        RenderCheck(
            id="responsive-viewports",
            passed=responsive_sizes,
            message="HTML renders nonblank content at the configured desktop and mobile viewports.",
        ),
    ]
    return RenderingValidationReport(
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _html_semantic_values(race: PublicationRace) -> dict[str, list[str]]:
    return {
        "race-label": [race.race_label],
        "recommendation": [race.recommendation_label],
        "share": ["N/A" if race.percentage_whole is None else race.percentage_label],
        # H34: the default caption renders as two sibling elements (full
        # sentence, then the compact-mode short form), both always present in
        # the static markup and both carrying data-display-role="support".
        "support": [
            context.screen_support_summary(race),
            context.screen_support_summary_compact(race),
        ],
        "insufficient-warning": (
            ["Too few endorsements to measure agreement."] if race.grade == "Insufficient" else []
        ),
    }


class _GuideHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.race_ids: list[str] = []
        self.race_text: dict[str, list[str]] = {}
        self.links: set[str] = set()
        self.display_text: dict[tuple[str, str], list[list[str]]] = {}
        self.display_accessible_names: dict[tuple[str, str], list[str | None]] = {}
        self.display_element_roles: dict[tuple[str, str], list[str | None]] = {}
        self.race_detail_text: dict[tuple[str, str], list[list[str]]] = {}
        self.race_detail_links: dict[tuple[str, str], list[set[str]]] = {}
        self.race_detail_states: dict[tuple[str, str], list[str | None]] = {}
        self.race_detail_categories: dict[tuple[str, str], list[str | None]] = {}
        self.race_detail_groups: dict[tuple[str, str], list[str | None]] = {}
        self.race_detail_candidate_ids: dict[tuple[str, str], list[str | None]] = {}
        self.race_detail_row_classes: dict[tuple[str, str], list[set[str]]] = {}
        self._text_parts: list[str] = []
        self._current_race_id: str | None = None
        self._current_display_role: tuple[tuple[str, str], int] | None = None
        self._display_role_tag: str | None = None
        self._current_race_detail: tuple[tuple[str, str], int] | None = None
        self._race_detail_depth = 0

    @property
    def text(self) -> str:
        return " ".join(self._text_parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self._current_race_detail is not None:
            self._race_detail_depth += 1
        race_id = attributes.get("data-publication-race-id")
        if race_id is not None:
            self.race_ids.append(race_id)
            self.race_text[race_id] = []
            self._current_race_id = race_id
        detail_source_code = attributes.get("data-race-detail-source-code")
        if detail_source_code is not None and self._current_race_id is not None:
            detail_key = (self._current_race_id, detail_source_code)
            detail_rows = self.race_detail_text.setdefault(detail_key, [])
            detail_links = self.race_detail_links.setdefault(detail_key, [])
            detail_rows.append([])
            detail_links.append(set())
            self.race_detail_row_classes.setdefault(detail_key, []).append(set())
            self.race_detail_states.setdefault(detail_key, []).append(
                attributes.get("data-source-state")
            )
            self.race_detail_categories.setdefault(detail_key, []).append(
                attributes.get("data-source-category")
            )
            self.race_detail_groups.setdefault(detail_key, []).append(
                attributes.get("data-source-group")
            )
            self.race_detail_candidate_ids.setdefault(detail_key, []).append(
                attributes.get("data-endorsed-candidate-id")
            )
            self._current_race_detail = (detail_key, len(detail_rows) - 1)
            self._race_detail_depth = 1
        classes = set((attributes.get("class") or "").split())
        if "race-detail-source-row" in classes and self._current_race_detail is not None:
            detail_key, row_index = self._current_race_detail
            self.race_detail_row_classes[detail_key][row_index] = classes
        display_role = attributes.get("data-display-role")
        if display_role is not None and self._current_race_id is not None:
            key = (self._current_race_id, display_role)
            occurrences = self.display_text.setdefault(key, [])
            occurrences.append([])
            self.display_accessible_names.setdefault(key, []).append(attributes.get("aria-label"))
            self.display_element_roles.setdefault(key, []).append(attributes.get("role"))
            self._current_display_role = (key, len(occurrences) - 1)
            self._display_role_tag = tag
        href = attributes.get("href")
        if tag == "a" and href is not None:
            self.links.add(href)
            if self._current_race_detail is not None:
                detail_key, detail_index = self._current_race_detail
                self.race_detail_links[detail_key][detail_index].add(href)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._text_parts.append(data)
            if self._current_race_id is not None:
                self.race_text[self._current_race_id].append(data)
            if self._current_display_role is not None:
                key, index = self._current_display_role
                self.display_text[key][index].append(data)
            if self._current_race_detail is not None:
                detail_key, detail_index = self._current_race_detail
                self.race_detail_text[detail_key][detail_index].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current_race_detail is not None:
            self._race_detail_depth -= 1
            if self._race_detail_depth == 0:
                self._current_race_detail = None
        if tag == self._display_role_tag:
            self._current_display_role = None
            self._display_role_tag = None
        if tag == "article":
            self._current_race_id = None
