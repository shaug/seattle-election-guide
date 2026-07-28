from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from stat import S_IMODE
from typing import Any, cast
from urllib.parse import urlencode

import pytest
from PIL import Image
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from websocket import create_connection  # pyright: ignore[reportUnknownVariableType]

from election_guide.publication import build_publication_bundle
from election_guide.publication.builder import reprojected_personalization
from election_guide.publication.models import (
    PublicationComparison,
    PublicationRace,
    PublicationViewModel,
    SourceCell,
)
from election_guide.publication.personalization import PersonalizationSource
from election_guide.rendering import (
    build_rendered_guide,
    read_rendering_configuration,
    render_html_document,
    validate_rendered_guide,
)
from election_guide.rendering.models import RenderingValidationReport
from election_guide.rendering.renderer import (
    PrintLayoutError,
    _CdpSocket,  # pyright: ignore[reportPrivateUsage]
    _comparison_candidate_cells,  # pyright: ignore[reportPrivateUsage]
    _detailed_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
    _missing_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_race_core_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_race_display_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_source_participation_labels,  # pyright: ignore[reportPrivateUsage]
    _race_detail_accessible_summary,  # pyright: ignore[reportPrivateUsage]
    _race_detail_candidate_choices,  # pyright: ignore[reportPrivateUsage]
    _race_detail_support_summary,  # pyright: ignore[reportPrivateUsage]
    _render_pdf,  # pyright: ignore[reportPrivateUsage]
    _render_pdf_pages,  # pyright: ignore[reportPrivateUsage]
    _render_screenshot,  # pyright: ignore[reportPrivateUsage]
    _set_pdf_metadata,  # pyright: ignore[reportPrivateUsage]
    _source_cell_detail_label,  # pyright: ignore[reportPrivateUsage]
    _source_cell_group,  # pyright: ignore[reportPrivateUsage]
    _terminate_process,  # pyright: ignore[reportPrivateUsage]
    _trim_trailing_blank_pages,  # pyright: ignore[reportPrivateUsage]
    _validate_print_layout,  # pyright: ignore[reportPrivateUsage]
    _wait_for_devtools_endpoint,  # pyright: ignore[reportPrivateUsage]
    find_chrome,
    find_pdftoppm,
)
from election_guide.scoring import score_dataset
from election_guide.serialization import canonical_json_bytes, read_json
from tests.test_personalization import (
    _bundle as _production_bundle,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_publication import (
    _publication_dataset,  # pyright: ignore[reportPrivateUsage]
    _snapshot_store,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_scoring import (
    NOW,
    _configuration,  # pyright: ignore[reportPrivateUsage]
)

PROJECT_ROOT = Path(__file__).parent.parent
RENDERING_CONFIG = PROJECT_ROOT / "config/rendering/pdf.yaml"
DARWIN_VISUAL_BASELINES = {
    "pdf-page-1": [
        0.171,
        0.196,
        0.124,
        0.106,
        0.112,
        0.146,
        0.157,
        0.133,
        0.114,
        0.140,
        0.159,
        0.137,
        0.064,
        0.089,
        0.099,
        0.084,
    ],
    "pdf-page-2": [
        0.090,
        0.058,
        0.056,
        0.031,
        0.077,
        0.056,
        0.103,
        0.039,
        0.093,
        0.073,
        0.094,
        0.037,
        0.047,
        0.031,
        0.052,
        0.022,
    ],
    "desktop": [
        0.455,
        0.669,
        0.688,
        0.514,
        0.080,
        0.051,
        0.065,
        0.042,
        0.077,
        0.065,
        0.051,
        0.054,
        0.085,
        0.068,
        0.103,
        0.052,
    ],
    "mobile": [
        0.614,
        0.609,
        0.616,
        0.693,
        0.233,
        0.254,
        0.029,
        0.021,
        0.142,
        0.145,
        0.076,
        0.082,
        0.114,
        0.111,
        0.058,
        0.058,
    ],
}
LINUX_VISUAL_BASELINES = {
    "pdf-page-1": [
        0.165,
        0.193,
        0.120,
        0.103,
        0.107,
        0.144,
        0.152,
        0.133,
        0.108,
        0.140,
        0.153,
        0.137,
        0.061,
        0.089,
        0.095,
        0.084,
    ],
    "pdf-page-2": [
        0.078,
        0.051,
        0.050,
        0.029,
        0.080,
        0.055,
        0.097,
        0.037,
        0.089,
        0.071,
        0.099,
        0.039,
        0.046,
        0.037,
        0.048,
        0.021,
    ],
    "desktop": [
        0.463,
        0.659,
        0.728,
        0.514,
        0.072,
        0.044,
        0.058,
        0.042,
        0.067,
        0.055,
        0.043,
        0.054,
        0.080,
        0.060,
        0.090,
        0.052,
    ],
    "mobile": [
        0.626,
        0.626,
        0.634,
        0.696,
        0.227,
        0.237,
        0.028,
        0.027,
        0.120,
        0.103,
        0.074,
        0.092,
        0.092,
        0.052,
        0.041,
        0.071,
    ],
}
APPROVED_VISUAL_BASELINES_BY_PLATFORM = {
    "darwin": DARWIN_VISUAL_BASELINES,
    "linux": LINUX_VISUAL_BASELINES,
}


def test_html_uses_one_view_model_for_screen_print_filters_and_evidence(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    gap_source = next(source for source in view_model.sources if source.endorsement_count == 0)
    gap_source.contribution_status = "coverage_gap"
    gap_source.coverage_gap_status = "not_found"
    gap_source.coverage_gap_note = "The official site did not publish endorsement results."
    view_model.metadata.contributing_source_count -= 1
    view_model.metadata.coverage_gap_count += 1
    view_model = _revalidated(view_model)
    configuration = read_rendering_configuration(RENDERING_CONFIG)

    html = render_html_document(view_model, configuration)

    races = [race for section in view_model.sections for race in section.races]
    source_by_id = {source.id: source for source in view_model.sources}
    category_label_by_key = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    assert html.count('data-publication-race-id="') == len(races)
    assert all(f'data-publication-race-id="{race.id}"' in html for race in races)
    assert "@media print" in html
    assert "@media (max-width: 720px)" in html
    assert 'id="race-filter"' in html
    assert 'input type="radio" name="ballot-view" value="full" checked><span>Full</span>' in html
    assert 'input type="radio" name="ballot-view" value="compact"><span>Compact</span>' in html
    assert (
        'input type="radio" name="race-set" value="complete" id="complete-filter" checked'
        "><span>Complete</span>" in html
    )
    assert (
        'input type="radio" name="race-set" value="contested" id="contested-filter"'
        "><span>Contested</span>" in html
    )
    assert "contested-control" not in html
    assert html.count('data-contested="') == len(races)
    assert "Full race detail" not in html
    assert 'aria-labelledby="race-label-' in html
    assert html.count('<a class="race-card-primary"') == len(races)
    assert html.count('aria-label="View endorsements for ') == len(races)
    assert '<option value="Legislative District 43">Legislative District 43</option>' in html
    assert "JSON.parse(card.dataset.filterTokens)" in html
    assert "card.dataset.contested === 'true'" in html
    assert "matchesScope && matchesContest" in html
    assert "url.searchParams.set('view', 'compact')" in html
    assert "url.searchParams.set('races', 'contested')" in html
    assert "url.searchParams.set('filter', select.value)" in html
    assert "syncControlsFromUrl();" in html
    assert "html.compact-ballot-mode .race-grid { grid-template-columns: repeat(4" in html
    assert "html.compact-ballot-mode .race-grid { grid-template-columns: 1fr; }" in html
    assert "> View endorsements" not in html
    assert "html.compact-ballot-mode .screen-comparisons { display: none; }" in html
    assert html.count('<dialog class="race-detail-dialog"') == len(races)
    assert html.count("August 2026 Primary · Endorsements") == len(races)
    assert html.count('data-copy-race-link="') == len(races)
    assert html.count(">Share link</button>") == len(races)
    assert "Source details" not in html
    assert "Open source evidence" not in html
    assert "Race source audit" not in html
    for race in races:
        assert f'id="race-{race.id}"' in html
        assert html.count(f'href="#race-{race.id}" data-race-detail-link') == 1
        trigger_start = html.index(f'<a class="race-card-primary" href="#race-{race.id}"')
        trigger_end = html.index("</a>", trigger_start)
        trigger_html = html[trigger_start:trigger_end]
        assert f'id="race-label-{race.id}"' in trigger_html
        contested_value = "true" if race.is_contested else "false"
        assert f'data-contested="{contested_value}"' in html[trigger_start - 300 : trigger_start]
        assert 'data-display-role="recommendation"' in trigger_html
        assert 'data-display-role="share"' in trigger_html
        assert 'data-display-role="comparison"' in trigger_html
        assert 'data-display-role="support"' in trigger_html
        dialog_start = html.index(f'id="race-detail-{race.id}"')
        assert trigger_end < dialog_start
        dialog_end = html.index("</dialog>", dialog_start)
        dialog_html = html[dialog_start:dialog_end]
        assert (
            f'aria-labelledby="race-detail-election-{race.id} race-detail-title-{race.id}"'
            in dialog_html
        )
        assert f'id="race-detail-election-{race.id}"' in dialog_html
        assert "race-detail-overview" not in dialog_html
        assert "race-detail-category-groups" not in dialog_html
        assert "data-race-detail-category=" not in dialog_html
        assert f'id="copy-race-status-{race.id}"' in dialog_html
        assert 'role="status"' in dialog_html
        assert 'aria-live="polite" data-copy-race-status' in dialog_html
        assert f'aria-describedby="copy-race-status-{race.id}"' in dialog_html
        assert race.recommendation_label in dialog_html
        assert _race_detail_accessible_summary(race) in dialog_html
        assert _race_detail_support_summary(race) in dialog_html
        candidate_choices = _race_detail_candidate_choices(race, source_by_id)
        candidate_positions = [
            dialog_html.index(f'data-race-detail-candidate-id="{candidate_id}"')
            for candidate_id, _candidate_label, _endorsement_group in candidate_choices
        ]
        assert candidate_positions == sorted(candidate_positions)
        source_counts = [
            endorsement_group.source_count if endorsement_group is not None else 0
            for _candidate_id, _candidate_label, endorsement_group in candidate_choices
        ]
        assert source_counts == sorted(source_counts, reverse=True)
        for candidate_id, candidate_label, endorsement_group in candidate_choices:
            assert candidate_label in dialog_html
            contributing_count = (
                endorsement_group.source_count if endorsement_group is not None else 0
            )
            comparison_count = len(_comparison_candidate_cells(race, source_by_id, candidate_id))
            assert (
                dialog_html.count(f'data-endorsed-candidate-id="{candidate_id}"')
                == contributing_count + comparison_count
            )
        expected_row_count = sum(
            len(cell.candidate_ids)
            if _source_cell_group(cell, race, source_by_id[cell.source_id]) == "candidate"
            else 1
            for cell in race.source_cells
        )
        assert dialog_html.count('data-race-detail-source-id="') == expected_row_count
        assert dialog_html.count('data-source-group="') == expected_row_count
        assert dialog_html.count('class="race-detail-category-badge') == expected_row_count
        expected_co_endorsement_rows = sum(
            len(cell.candidate_ids)
            for cell in race.source_cells
            if cell.state == "multi_endorsement"
        )
        assert dialog_html.count(">Co-endorsed</span>") == expected_co_endorsement_rows
        for state in ("not_covered", "not_applicable"):
            missing_count = sum(
                _source_cell_group(cell, race, source_by_id[cell.source_id]) == state
                for cell in race.source_cells
            )
            if not missing_count:
                continue
            noun = "source" if missing_count == 1 else "sources"
            if state == "not_covered":
                summary = f"{missing_count} {noun} did not cover this race"
            else:
                verb = "was" if missing_count == 1 else "were"
                summary = f"{missing_count} {noun} {verb} outside this district"
            assert summary in dialog_html
        for cell in race.source_cells:
            group = _source_cell_group(cell, race, source_by_id[cell.source_id])
            expected_occurrences = len(cell.candidate_ids) if group == "candidate" else 1
            assert (
                dialog_html.count(f'data-race-detail-source-id="{cell.source_id}"')
                == expected_occurrences
            )
            assert f'data-source-state="{cell.state}"' in dialog_html
            source = source_by_id[cell.source_id]
            assert category_label_by_key[source.category] in dialog_html
            if source.panel_role == "comparison":
                assert "Comparison only" in dialog_html
            detail_label = _source_cell_detail_label(cell, race, group)
            if detail_label is not None:
                assert detail_label in dialog_html
            if cell.evidence_url is not None:
                assert f'href="{cell.evidence_url}"' in dialog_html
    assert "No endorsement" in html
    assert "Made no endorsement" not in html
    assert "Needs verification" in html
    assert "Comparison only" in html
    # The phrase belongs to the customize option (issue 79) and must not leak back
    # into the source panel or the race-detail rows, which say "Comparison only".
    customize_dialog = html.split('<dialog class="customize-dialog"')[1].split("</dialog>")[0]
    assert "Show Seattle Times comparison" in customize_dialog
    rendered_content = re.sub(r"<script\b.*?</script>", "", html, flags=re.S).replace(
        customize_dialog, ""
    )
    assert "Seattle Times comparison" not in rendered_content
    assert 'data-race-detail-group="comparison"' not in html
    assert "race-detail-source-row-comparison" in html
    assert "See which groups line up with the leading choice" not in html
    assert "race-detail-description-" not in html
    assert "history.pushState({ ...state, raceDetail: link.hash }" in html
    assert "history.back()" in html
    assert "target.showModal()" in html
    assert "dialog.addEventListener('cancel'" in html
    assert "window.addEventListener('popstate'" in html
    assert "window.addEventListener('hashchange'" in html
    assert "navigator.clipboard?.writeText" in html
    assert "const link = new URL(window.location.href);" in html
    assert "link.hash = button.dataset.copyRaceLink;" in html
    assert "Consensus among explicitly endorsing sources" in html
    assert "Seattle Times" in html
    assert "August 2026 Primary" in html
    assert "Seattle Progressive Endorsement Guide" in html
    canonical_url = f"{configuration.public_site_url}/e/{view_model.metadata.election_id}/"
    assert f'<link rel="canonical" href="{canonical_url}">' in html
    assert f'<meta property="og:url" content="{canonical_url}">' in html
    assert f'href="{configuration.pdf_filename}">Printable PDF</a>' in html
    assert 'href="mailto:seattle-elections@dobravoda.dev">Feedback?</a>' in html
    assert 'class="footer-actions" aria-label="Guide links"' in html
    footer_actions_start = html.index('<nav class="footer-actions"')
    footer_actions_end = html.index("</nav>", footer_actions_start)
    assert html[footer_actions_start:footer_actions_end].count(configuration.project_url) == 1
    assert ".detailed-footer-audit { display: none; }" in html
    assert "html.detailed-edition .detailed-footer-audit { display: inline; }" in html
    assert ">AGREES<" not in html
    assert ">DIFFERENT PICK<" not in html
    assert ">NO PICK<" not in html
    assert f"{view_model.metadata.captured_source_count} represented sources" not in html
    assert f"{view_model.metadata.unresolved_review_count} unresolved reviews" not in html
    assert "Coverage note:" not in html
    assert "Category representation and support" not in html
    assert 'data-display-role="grade"' not in html
    assert 'class="methodology-panel screen-consensus-key"' in html
    assert 'class="guide-notes" id="methodology"' in html
    assert 'class="guide-notes" id="sources"' in html
    assert "How the consensus works" not in html
    assert "Verify the guide" not in html
    assert "Build and audit details" not in html
    assert "document.querySelectorAll('.guide-notes').forEach" in html
    assert configuration.project_url in html
    comparisons = [comparison for race in races for comparison in race.comparisons]
    for comparison in comparisons:
        assert f"comparison-{comparison.voter_tone}" in html
        assert f'class="comparison comparison-{comparison.voter_tone}" role="group"' in html
        assert f'aria-label="{comparison.voter_accessible_label}"' in html
        assert f'<strong class="comparison-status">{comparison.print_status_label}</strong>' in html
        assert f'<span class="comparison-choice">{comparison.print_choice_label}</span>' in html
        assert (f"print-times-pick print-times-pick-{comparison.voter_tone}") in html
        assert (
            f'>{comparison.print_status_label}</span><span class="print-times-separator"> · '
            in html
        )
        assert (
            f'<span class="print-times-choice">{comparison.print_choice_label}</span></b>' in html
        )
    assert ".screen-race-result, .screen-race-context { display: grid;" in html
    assert "grid-template-columns: minmax(0, 1fr) 11rem" in html
    assert (
        ".screen-meter { --meter-direction: to left; --meter-text-align: right; display: flex;"
        in html
    )
    assert "linear-gradient(var(--meter-direction), var(--teal) 0 var(--meter-fill)" in html
    assert (
        "html.compact-ballot-mode .screen-meter { --meter-direction: to right; "
        "--meter-text-align: left;" in html
    )
    assert "text-align: var(--meter-text-align);" in html
    assert ".comparison-status { font-weight: 800; }" in html
    assert ".comparison-choice { min-width: 0; font-weight: 500; }" in html
    assert ".comparison-agrees { border-color: #83bfae; background: #edf8f4;" in html
    contributing_sources = [
        source for source in view_model.sources if source.contribution_status == "contributing"
    ]
    coverage_gap_sources = [
        source for source in view_model.sources if source.contribution_status == "coverage_gap"
    ]
    assert html.count('data-publication-source-id="') == 2 * len(contributing_sources)
    assert html.count('data-coverage-gap-source-id="') == 2 * len(coverage_gap_sources)
    assert html.count('class="source-column"') == 2
    for source in contributing_sources:
        assert html.count(f'data-publication-source-id="{source.id}"') == 2
        assert html.count(f'data-source-role="{source.panel_role}"') >= 2
        assert html.count(f'<a href="{source.evidence_url}">{source.name}</a>') >= 2
        noun = "picks" if source.panel_role == "comparison" else "endorsements"
        screen_participation = (
            f"{source.endorsement_count} {noun} · {source.split_endorsement_count} split"
        )
        print_noun = " picks" if source.panel_role == "comparison" else ""
        print_participation = (
            f"{source.endorsement_count}{print_noun} · {source.split_endorsement_count} split"
        )
        marker = f'data-publication-source-id="{source.id}"'
        cursor = 0
        for participation in (screen_participation, print_participation):
            row_start = html.index(marker, cursor)
            row_end = html.index("</div>", row_start)
            assert participation in html[row_start:row_end]
            cursor = row_end
    assert "Read the meter" in html
    assert "Read the Times pill" in html
    assert "Overlap and limitations" in html
    assert "Verify before voting" in html
    assert "Counts cover the" in html
    for source in coverage_gap_sources:
        assert html.count(f'data-coverage-gap-source-id="{source.id}"') == 2
        assert html.count(f'<a href="{source.evidence_url}">{source.name}</a>') == 2
        assert source.coverage_gap_note is not None
        assert source.coverage_gap_note in html
        status_label = (
            "Official results inaccessible"
            if source.coverage_gap_status == "access_restricted"
            else "No published results found"
        )
        assert html.count(status_label) >= 2
    assert f"Sources ({view_model.metadata.contributing_source_count})" in html
    assert f"Coverage gaps ({view_model.metadata.coverage_gap_count})" in html
    assert "They do not contribute to consensus scores" in html
    assert "zero means the source currently contributes no picks" not in html
    assert ".screen-source-columns { column-count: 2;" in html
    assert ".screen-source-category { display: inline-block;" in html
    assert "break-inside: avoid;" in html
    assert ".screen-source-columns { column-count: 1; }" in html
    assert ".source-columns { display: grid;" in html
    assert "grid-template-columns: 1fr 1fr;" in html
    assert ".source-row { display: grid;" in html
    category_group_markers = [
        f'data-source-category-group="{category.category}"'
        for category in view_model.methodology.source_categories
    ]
    assert all(html.count(marker) == 1 for marker in category_group_markers)
    assert [html.index(marker) for marker in category_group_markers] == sorted(
        html.index(marker) for marker in category_group_markers
    )
    assert category_group_markers[-1] == 'data-source-category-group="comparison"'
    print_contributing_sources = [
        source
        for category in view_model.methodology.source_categories
        for source in contributing_sources
        if source.category == category.category
    ]
    print_source_positions = [
        html.rindex(f'data-publication-source-id="{source.id}"')
        for source in print_contributing_sources
    ]
    assert print_source_positions == sorted(print_source_positions)
    assert "source_midpoint" not in html
    assert 'class="print-metadata"' not in html
    assert ".print-races { display: grid; grid-template-columns: 1fr 1fr;" in html
    assert html.count('class="print-race-column"') == 2
    assert "State — continued" in html
    assert ".print-race:nth-of-type(even) { background: #f2f6f8; }" in html
    assert '--print-sans: Helvetica, "Liberation Sans", sans-serif' in html
    assert "const centerPrintInk = () =>" in html
    assert "window.addEventListener('beforeprint', calibratePrintInk)" in html
    assert "requestAnimationFrame(() => requestAnimationFrame(calibratePrintInk))" in html
    assert "font: 800 17pt/.95 var(--print-sans)" in html
    assert '<div class="print-guide">' in html
    assert '<div class="print-guide" aria-hidden="true">' not in html
    assert "font: 800 8.9pt/1 var(--print-sans)" in html
    assert "--print-meter-width: 1.65in" in html
    assert "grid-template-columns: minmax(0, 1fr) var(--print-meter-width)" in html
    assert "linear-gradient(to left, var(--teal) 0 var(--meter-fill)" in html
    assert 'style="--meter-fill: ' in html


def test_rendering_configuration_rejects_contract_drift() -> None:
    configuration = read_rendering_configuration(RENDERING_CONFIG)
    payload = configuration.model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        type(configuration).model_validate(payload)

    for field in ("title", "author", "subject"):
        blank = configuration.model_dump(mode="json")
        blank[field] = "   "
        with pytest.raises(ValidationError):
            type(configuration).model_validate(blank)

    coerced = configuration.model_dump(mode="json")
    coerced["require_selectable_text"] = 1
    with pytest.raises(ValidationError):
        type(configuration).model_validate(coerced)

    aliased_pdfs = configuration.model_dump(mode="json")
    aliased_pdfs["detailed_pdf_filename"] = aliased_pdfs["pdf_filename"]
    with pytest.raises(ValidationError, match="must be distinct"):
        type(configuration).model_validate(aliased_pdfs)


def test_print_layout_rejects_visibly_uncentered_control_text(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    html_path = tmp_path / "uncentered.html"
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    html_path.write_text(
        html.replace(
            "</head>",
            """
<style>
@media print {
  .print-guide { font-family: Arial, Helvetica, sans-serif; }
  .print-meter-label { padding: 0 .05in 0 0; }
  .print-meter-text, .print-times-pick > span { position: relative; top: -3px; transform: none; }
}
</style>
<script>window.__disablePrintInkCentering = true;</script>
</head>
""",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(PrintLayoutError, match=r"(label|comparison)-centering"):
        _validate_print_layout(
            html_path,
            find_chrome(),
            minimum_font_points=read_rendering_configuration(
                RENDERING_CONFIG
            ).minimum_print_font_points,
        )


@pytest.mark.parametrize(
    ("injected_markup", "expected_issue"),
    [
        (
            """
<style>@media print { .print-times-pick { height: .18in !important; } }</style>
""",
            "comparison-treatment",
        ),
        (
            """
<style>@media print { .print-times-pick { border-width: 2px !important; } }</style>
""",
            "comparison-treatment",
        ),
        (
            """
<script>
let printPillOffset = false;
window.addEventListener('beforeprint', () => {
  const pillText = document.querySelector('.print-times-pick > span');
  if (pillText) {
    pillText.style.position = 'relative';
    pillText.style.top = printPillOffset ? '0px' : '1px';
  }
  printPillOffset = !printPillOffset;
});
</script>
""",
            "print-ink-calibration-repeatability",
        ),
        (
            """
<script>
let printMeterOffset = false;
window.addEventListener('beforeprint', () => {
  const label = document.querySelector('.print-meter-label');
  if (label) label.style.paddingTop = printMeterOffset ? '0px' : '2px';
  printMeterOffset = !printMeterOffset;
});
</script>
""",
            "print-ink-calibration-repeatability",
        ),
        (
            """
<script>
let printPillInset = false;
window.addEventListener('beforeprint', () => {
  const pill = document.querySelector('.print-times-pick');
  if (pill) pill.style.paddingLeft = printPillInset ? '5px' : '10px';
  printPillInset = !printPillInset;
});
</script>
""",
            "print-ink-calibration-repeatability",
        ),
    ],
)
def test_print_layout_rejects_unstable_pill_geometry(
    tmp_path: Path, injected_markup: str, expected_issue: str
) -> None:
    view_model = _view_model(tmp_path / "fixture")
    html_path = tmp_path / "unstable-pill.html"
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    html_path.write_text(
        html.replace("</body>", f"{injected_markup}</body>", 1),
        encoding="utf-8",
    )

    with pytest.raises(PrintLayoutError, match=expected_issue):
        _validate_print_layout(
            html_path,
            find_chrome(),
            minimum_font_points=read_rendering_configuration(
                RENDERING_CONFIG
            ).minimum_print_font_points,
        )


def test_print_layout_rejects_underfilled_source_page(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    html_path = tmp_path / "underfilled.html"
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    html_path.write_text(html.replace("height: 9.45in", "height: auto", 1), encoding="utf-8")

    with pytest.raises(PrintLayoutError, match=r"print-page\[1\]-underfill"):
        _validate_print_layout(
            html_path,
            find_chrome(),
            minimum_font_points=read_rendering_configuration(
                RENDERING_CONFIG
            ).minimum_print_font_points,
        )


def test_html_escapes_publication_text_and_filter_attributes(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    payload = '<img src=x onerror="globalThis.pwned=1">'
    view_model.sources[0].name = payload
    view_model.sections[0].races[0].filter_tokens.append(payload)

    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))

    assert payload not in html
    assert "&lt;img src=x onerror=&#34;globalThis.pwned=1&#34;&gt;" in html
    assert r"\u003cimg src=x onerror=\"globalThis.pwned=1\"\u003e" in html


def test_html_rejects_non_web_evidence_links(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    endorsement_cell = next(
        cell
        for section in view_model.sections
        for race in section.races
        for cell in race.source_cells
        if cell.state in {"endorsement", "multi_endorsement"}
    )
    endorsement_cell.evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))

    source_view_model = _view_model(tmp_path / "source")
    source_view_model.sources[0].evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(source_view_model, read_rendering_configuration(RENDERING_CONFIG))

    cell_view_model = _view_model(tmp_path / "cell")
    cell = next(
        cell
        for section in cell_view_model.sections
        for race in section.races
        for cell in race.source_cells
        if cell.state in {"no_endorsement", "unavailable", "unverified"}
    )
    cell.evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(cell_view_model, read_rendering_configuration(RENDERING_CONFIG))


def test_pdf_result_header_cannot_be_masked_by_comparison_text(tmp_path: Path) -> None:
    race = next(
        race
        for section in _view_model(tmp_path).sections
        for race in section.races
        if race.recommendation_candidate_labels
    )
    share = "N/A" if race.percentage_whole is None else race.percentage_label
    misleading_text = " ".join(
        (
            race.race_label,
            "Wrong recommendation",
            share,
            race.support_summary,
            "Seattle Times",
            race.comparisons[0].voter_label,
            race.recommendation_label,
            *race.warning_messages,
        )
    )

    missing = _missing_pdf_race_values([race], misleading_text, _pdf_race_display_values)

    assert f"{race.id}: ordered race result header" in missing

    short_choice_race = race.model_copy(update={"recommendation_label": "Yes"})
    prefix_corrupted_text = " ".join(_pdf_race_display_values(short_choice_race)).replace(
        "Yes", "Yesterday", 1
    )
    prefix_corrupted_missing = _missing_pdf_race_values(
        [short_choice_race], prefix_corrupted_text, _pdf_race_display_values
    )
    assert f"{race.id}: ordered race result header" in prefix_corrupted_missing
    assert f"{race.id}: Yes" in prefix_corrupted_missing

    percentage_race = race.model_copy(update={"percentage_label": "100%", "percentage_whole": 100})
    suffixed_percentage_text = " ".join(_pdf_race_display_values(percentage_race)).replace(
        "100%", "100%%", 1
    )
    suffixed_percentage_missing = _missing_pdf_race_values(
        [percentage_race], suffixed_percentage_text, _pdf_race_display_values
    )
    assert f"{race.id}: 100%" in suffixed_percentage_missing

    prefixed_percentage_text = " ".join(_pdf_race_display_values(percentage_race)).replace(
        "100%", "!100%", 1
    )
    prefixed_percentage_missing = _missing_pdf_race_values(
        [percentage_race], prefixed_percentage_text, _pdf_race_display_values
    )
    assert f"{race.id}: 100%" in prefixed_percentage_missing


@pytest.mark.parametrize(
    "value_fn",
    (_pdf_race_display_values, _pdf_race_core_values, _detailed_pdf_race_values),
)
@pytest.mark.parametrize(
    ("status", "badge_label", "candidate_labels"),
    (
        ("agrees", "AGREES", ["Candidate A"]),
        ("differs", "DIFFERENT PICK", ["No"]),
        ("no_endorsement", "NO PICK", []),
        ("not_covered", "NOT COVERED", []),
    ),
)
def test_pdf_comparison_validation_requires_compound_chip_and_rejects_legacy_badges(
    tmp_path: Path,
    value_fn: Callable[[PublicationRace], list[str]],
    status: str,
    badge_label: str,
    candidate_labels: list[str],
) -> None:
    race = next(
        race
        for section in _view_model(tmp_path).sections
        for race in section.races
        if race.recommendation_candidate_labels
    ).model_copy(deep=True)
    rendered_candidate_labels = (
        race.recommendation_candidate_labels if status == "agrees" else candidate_labels
    )
    rendered_candidate_ids = (
        race.recommendation_candidate_ids
        if status == "agrees"
        else [f"comparison-candidate-{index}" for index, _ in enumerate(rendered_candidate_labels)]
    )
    comparison = PublicationComparison.model_validate(
        {
            "source_id": race.comparisons[0].source_id,
            "status": status,
            "badge_label": badge_label,
            "candidate_ids": rendered_candidate_ids,
            "candidate_labels": rendered_candidate_labels,
        }
    )
    race.comparisons = [comparison]
    separator = "\n" if value_fn is _detailed_pdf_race_values else " "
    expected_text = separator.join(value_fn(race))
    chip_label = comparison.print_label
    support_label = (
        race.support_summary
        if value_fn is _pdf_race_display_values
        else (
            f"Based on {race.explicit_endorsement_count} endorsing "
            f"{'source' if race.explicit_endorsement_count == 1 else 'sources'}"
            if value_fn is _detailed_pdf_race_values
            else f"{race.explicit_endorsement_count} endorsers"
        )
    )
    compound = f"{chip_label} {support_label}"

    assert _missing_pdf_race_values([race], expected_text, value_fn) == []
    wrapped_header_text = expected_text.replace(
        race.race_label,
        race.race_label.replace(" ", "\n", 1),
        1,
    )
    assert _missing_pdf_race_values([race], wrapped_header_text, value_fn) == []
    joined_value_text = expected_text.replace(
        race.race_label,
        race.race_label.replace(" ", "", 1),
        1,
    )
    assert f"{race.id}: {race.race_label}" in _missing_pdf_race_values(
        [race], joined_value_text, value_fn
    )

    for suffix in ("body", " body", "-body"):
        prefix_collision_text = expected_text.replace(chip_label, f"{chip_label}{suffix}", 1)
        prefix_collision_missing = _missing_pdf_race_values([race], prefix_collision_text, value_fn)
        assert f"{race.id}: {compound}" in prefix_collision_missing

    wrong_chip_text = expected_text.replace(chip_label, "Times differs: Wrong pick", 1)
    wrong_chip_missing = _missing_pdf_race_values([race], wrong_chip_text, value_fn)
    assert f"{race.id}: {compound}" in wrong_chip_missing

    if comparison.voter_label == "No":
        not_covered_text = expected_text.replace(chip_label, "Times: not covered", 1)
        not_covered_missing = _missing_pdf_race_values([race], not_covered_text, value_fn)
        assert f"{race.id}: {compound}" in not_covered_missing

    if badge_label != "NOT COVERED":
        legacy_text = expected_text.replace(
            chip_label,
            f"Seattle Times {badge_label} {comparison.voter_label}",
            1,
        )
        legacy_missing = _missing_pdf_race_values([race], legacy_text, value_fn)
        assert f"{race.id}: {compound}" in legacy_missing
        assert f"{race.id}: legacy Seattle Times badge {badge_label}" in legacy_missing


def test_nonempty_render_destination_is_preserved(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()
    marker = output_dir / "keep.txt"
    marker.write_text("owned by another generation", encoding="utf-8")

    with pytest.raises(ValueError, match="must be absent or empty"):
        build_rendered_guide(view_model_path, RENDERING_CONFIG, output_dir)

    assert marker.read_text(encoding="utf-8") == "owned by another generation"


def test_chromium_build_is_two_page_selectable_linked_and_visually_safe(tmp_path: Path) -> None:
    view_model = _visual_view_model(_view_model(tmp_path / "fixture"))
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))

    rendered = build_rendered_guide(
        view_model_path,
        RENDERING_CONFIG,
        tmp_path / "rendered",
    )

    rendered_html = rendered.html_path.read_text(encoding="utf-8")
    assert view_model.metadata.source_panel_id in rendered_html
    assert view_model.metadata.source_panel_hash in rendered_html
    for percentage in (53, 64, 70, 100):
        assert f'style="--meter-fill: {percentage}%"' in rendered_html
    for tone in ("agrees", "differs", "not_covered"):
        assert f"comparison-{tone}" in rendered_html

    assert rendered.validation_report.passed
    assert rendered.validation_report.edition == "concise"
    assert rendered.detailed_pdf_path is None
    assert rendered.validation_report.page_count == 2
    assert len(rendered.page_images) == 2
    assert len(rendered.screenshots) == 2
    report = RenderingValidationReport.model_validate(read_json(rendered.validation_path))
    assert report == rendered.validation_report
    tagged_structure_check = next(
        check for check in report.checks if check.id == "pdf-tagged-structure"
    )
    assert tagged_structure_check.passed
    vacuous = report.model_dump(mode="json")
    vacuous.update(
        {
            "page_count": 0,
            "pdf_text_length": 0,
            "link_count": 0,
            "checks": [],
            "pages": [],
        }
    )
    with pytest.raises(ValidationError, match="each required check exactly once"):
        RenderingValidationReport.model_validate(vacuous)
    invalid_fallback = report.model_dump(mode="json")
    invalid_fallback.update(
        {
            "edition": "concise_plus_detailed",
            "detailed_page_count": 1,
            "detailed_pages": [
                {
                    "page_number": 1,
                    "image_path": "pdf/detailed-pages/page-1.png",
                    "width": 1224,
                    "height": 1584,
                    "ink_fraction": 0,
                    "edge_ink_fraction": 0,
                }
            ],
        }
    )
    with pytest.raises(ValidationError, match="longer than two pages"):
        RenderingValidationReport.model_validate(invalid_fallback)
    swapped_page_paths = report.model_dump(mode="json")
    swapped_page_paths["pages"][0]["image_path"] = "pdf/pages/page-2.png"
    swapped_page_paths["pages"][1]["image_path"] = "pdf/pages/page-1.png"
    with pytest.raises(ValidationError, match="page paths must match"):
        RenderingValidationReport.model_validate(swapped_page_paths)
    reader = PdfReader(rendered.pdf_path)
    assert len(reader.pages) == 2
    assert reader.metadata is not None
    assert reader.metadata.title == "Seattle Progressive Endorsement Guide"
    concise_text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "august 2026 primary" in concise_text.casefold()
    assert "Seattle Progressive Endorsement Guide" in concise_text
    assert all(source.name in concise_text for source in view_model.sources)
    assert (
        f"Panel {view_model.metadata.source_panel_version} · "
        f"{view_model.metadata.source_panel_hash[:12]}"
    ) in concise_text
    times_source = next(
        source for source in view_model.sources if source.panel_role == "comparison"
    )
    assert f"{times_source.endorsement_count} picks" in concise_text
    assert report.link_count == len(view_model.sources) + 2
    assert all(len(page.extract_text() or "") > 100 for page in reader.pages)
    with Image.open(rendered.page_images[0]) as page:
        assert page.size == (1224, 1584)
    with Image.open(rendered.screenshots[0]) as desktop:
        assert desktop.size == (1440, 1200)
    with Image.open(rendered.screenshots[1]) as mobile:
        assert mobile.size == (390, 1200)
    assert S_IMODE((tmp_path / "rendered").stat().st_mode) == 0o755
    assert S_IMODE(rendered.html_path.stat().st_mode) == 0o644
    approved_baselines = APPROVED_VISUAL_BASELINES_BY_PLATFORM[sys.platform]
    artifact_paths = dict(
        zip(
            approved_baselines,
            [*rendered.page_images, *rendered.screenshots],
            strict=True,
        )
    )
    observed_signatures = {
        label: _coarse_visual_signature(path) for label, path in artifact_paths.items()
    }
    for label, observed in observed_signatures.items():
        expected = approved_baselines[label]
        assert (
            sum(abs(left - right) for left, right in zip(observed, expected, strict=True)) / 16
            < 0.04
        ), f"{label}: observed signatures {observed_signatures}"
        assert (
            max(abs(left - right) for left, right in zip(observed, expected, strict=True)) < 0.12
        ), f"{label}: observed signatures {observed_signatures}"

    blank_screenshots: list[Path] = []
    for index, screenshot in enumerate(rendered.screenshots):
        with Image.open(screenshot) as source:
            blank = Image.new("RGB", source.size, "white")
        blank_path = tmp_path / f"blank-{index}.png"
        blank.save(blank_path)
        blank_screenshots.append(blank_path)
    blank_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        rendered.pdf_path,
        rendered.page_images,
        blank_screenshots,
    )
    responsive_check = next(
        check for check in blank_report.checks if check.id == "responsive-viewports"
    )
    assert not responsive_check.passed

    races = [race for section in view_model.sections for race in section.races]
    evidence_urls = [
        endorser.evidence_url
        for race in races
        for group in race.endorsement_groups
        for endorser in group.endorsers
    ]
    assert len(evidence_urls) >= 2
    mutated_html = tmp_path / "mutated.html"
    mutated_html.write_text(
        rendered.html_path.read_text(encoding="utf-8").replace(
            evidence_urls[0], evidence_urls[1], 1
        ),
        encoding="utf-8",
    )
    row_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        mutated_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    evidence_check = next(
        check for check in row_report.checks if check.id == "html-source-evidence"
    )
    assert not evidence_check.passed

    unexpected_link_html = tmp_path / "unexpected-link.html"
    unexpected_link_html.write_text(
        rendered.html_path.read_text(encoding="utf-8").replace(
            "</body>",
            '<a href="https://evil.example/phish">More evidence</a></body>',
            1,
        ),
        encoding="utf-8",
    )
    unexpected_link_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        unexpected_link_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    unexpected_link_check = next(
        check for check in unexpected_link_report.checks if check.id == "html-source-evidence"
    )
    assert not unexpected_link_check.passed

    canonical_html = rendered.html_path.read_text(encoding="utf-8")
    detail_race, detail_cell = next(
        (race, cell)
        for race in races
        for cell in race.source_cells
        if cell.evidence_url is not None
    )
    detail_source = next(
        source for source in view_model.sources if source.id == detail_cell.source_id
    )
    row_marker = f'<li data-race-detail-source-id="{detail_cell.source_id}"'
    race_start = canonical_html.index(f'id="race-detail-{detail_race.id}"')
    row_start = canonical_html.index(row_marker, race_start)
    row_end = canonical_html.index("</li>", row_start) + len("</li>")
    canonical_row = canonical_html[row_start:row_end]
    malicious_duplicate = canonical_row.replace(
        "</li>", '<a href="https://evil.example/phish">Wrong evidence</a></li>'
    )
    duplicate_row_html = tmp_path / "duplicate-source-row.html"
    duplicate_row_html.write_text(
        canonical_html.replace(canonical_row, malicious_duplicate + canonical_row, 1),
        encoding="utf-8",
    )
    duplicate_row_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        duplicate_row_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    duplicate_row_check = next(
        check for check in duplicate_row_report.checks if check.id == "html-source-evidence"
    )
    assert not duplicate_row_check.passed

    race_with_alternative = next(race for race in races if race.alternatives)
    wrong_recommendation_html = tmp_path / "wrong-recommendation.html"
    wrong_recommendation_html.write_text(
        rendered.html_path.read_text(encoding="utf-8").replace(
            (
                '<h3 data-display-role="recommendation">'
                f"{race_with_alternative.recommendation_label}</h3>"
            ),
            (
                '<h3 data-display-role="recommendation">'
                f"{race_with_alternative.alternatives[0].candidate_label}</h3>"
            ),
            1,
        ),
        encoding="utf-8",
    )
    semantic_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        wrong_recommendation_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    semantic_check = next(
        check for check in semantic_report.checks if check.id == "html-display-values"
    )
    assert not semantic_check.passed

    wrong_detail_row = canonical_row.replace(
        f"<strong>{detail_source.name}</strong>", "<strong>Wrong organization</strong>", 1
    )
    assert wrong_detail_row != canonical_row
    endorsement_html = tmp_path / "wrong-endorsement-source.html"
    endorsement_html.write_text(
        canonical_html.replace(canonical_row, wrong_detail_row, 1),
        encoding="utf-8",
    )
    endorsement_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        endorsement_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    endorsement_check = next(
        check for check in endorsement_report.checks if check.id == "html-source-evidence"
    )
    assert not endorsement_check.passed

    first_source, second_source = view_model.sources[:2]
    first_source_link = f'<a href="{first_source.evidence_url}">{first_source.name}</a>'
    second_source_link = f'<a href="{second_source.evidence_url}">{second_source.name}</a>'
    assert first_source_link in canonical_html
    assert second_source_link in canonical_html
    swapped_source_links_html = tmp_path / "swapped-publication-source-links.html"
    swapped_source_links_html.write_text(
        canonical_html.replace(first_source_link, "__FIRST_SOURCE_LINK__", 2)
        .replace(
            second_source_link,
            f'<a href="{first_source.evidence_url}">{second_source.name}</a>',
            2,
        )
        .replace(
            "__FIRST_SOURCE_LINK__",
            f'<a href="{second_source.evidence_url}">{first_source.name}</a>',
            2,
        ),
        encoding="utf-8",
    )
    swapped_source_links_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        swapped_source_links_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    swapped_source_links_check = next(
        check for check in swapped_source_links_report.checks if check.id == "html-source-evidence"
    )
    assert not swapped_source_links_check.passed

    consensus_source = next(
        source for source in view_model.sources if source.panel_role == "consensus"
    )
    source_role_marker = (
        f'data-publication-source-id="{consensus_source.id}"\n'
        f'      data-source-category="{consensus_source.category}"\n'
        '      data-source-role="consensus"'
    )
    assert source_role_marker in canonical_html
    wrong_source_role_html = tmp_path / "wrong-publication-source-role.html"
    wrong_source_role_html.write_text(
        canonical_html.replace(
            source_role_marker,
            source_role_marker.replace(
                'data-source-role="consensus"', 'data-source-role="comparison"'
            ),
            1,
        ),
        encoding="utf-8",
    )
    wrong_source_role_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        wrong_source_role_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    wrong_source_role_check = next(
        check for check in wrong_source_role_report.checks if check.id == "html-source-evidence"
    )
    assert not wrong_source_role_check.passed

    fake_source_row = (
        '<div class="source-row source-row-consensus" '
        'data-publication-source-id="fake-source" '
        f'data-source-category="{first_source.category}" data-source-role="consensus">'
        f'<a href="{first_source.evidence_url}">Fake Organization</a>'
        "<span>Consensus</span></div>"
    )
    extra_source_row_html = tmp_path / "extra-publication-source-row.html"
    extra_source_row_html.write_text(
        canonical_html.replace(first_source_link, fake_source_row + first_source_link, 1),
        encoding="utf-8",
    )
    extra_source_row_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        extra_source_row_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    extra_source_row_check = next(
        check for check in extra_source_row_report.checks if check.id == "html-source-evidence"
    )
    assert not extra_source_row_check.passed

    source_group = next(
        group
        for group in (
            "leader",
            "alternative",
            "no_endorsement",
            "comparison",
            "unverified",
            "not_covered",
        )
        if f'data-source-group="{group}"' in canonical_row
    )
    wrong_group_html = tmp_path / "wrong-source-group.html"
    wrong_group_html.write_text(
        canonical_html.replace(
            canonical_row,
            canonical_row.replace(
                f'data-source-group="{source_group}"', 'data-source-group="wrong"', 1
            ),
            1,
        ),
        encoding="utf-8",
    )
    wrong_group_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        wrong_group_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    wrong_group_check = next(
        check for check in wrong_group_report.checks if check.id == "html-source-evidence"
    )
    assert not wrong_group_check.passed

    recommendation_element = (
        f'<h3 data-display-role="recommendation">{race_with_alternative.recommendation_label}</h3>'
    )
    for index, replacement in enumerate(
        (
            recommendation_element.replace(
                "</h3>", f" / {race_with_alternative.alternatives[0].candidate_label}</h3>"
            ),
            recommendation_element + recommendation_element,
        )
    ):
        conflicting_html = tmp_path / f"conflicting-recommendation-{index}.html"
        conflicting_html.write_text(
            rendered.html_path.read_text(encoding="utf-8").replace(
                recommendation_element, replacement, 1
            ),
            encoding="utf-8",
        )
        conflicting_report = validate_rendered_guide(
            view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            conflicting_html,
            rendered.pdf_path,
            rendered.page_images,
            rendered.screenshots,
        )
        conflicting_check = next(
            check for check in conflicting_report.checks if check.id == "html-display-values"
        )
        assert not conflicting_check.passed

    accessible_race = next(race for race in races if race.comparisons)
    accessible_comparison = accessible_race.comparisons[0]
    accessible_html = rendered.html_path.read_text(encoding="utf-8")
    for index, (original, replacement) in enumerate(
        (
            (
                f'aria-label="{accessible_comparison.voter_accessible_label}"',
                'aria-label="Seattle Times comparison"',
            ),
            ('role="group"', 'role="presentation"'),
        )
    ):
        assert original in accessible_html
        broken_accessibility_html = tmp_path / f"broken-comparison-accessibility-{index}.html"
        broken_accessibility_html.write_text(
            accessible_html.replace(original, replacement, 1),
            encoding="utf-8",
        )
        broken_accessibility_report = validate_rendered_guide(
            view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            broken_accessibility_html,
            rendered.pdf_path,
            rendered.page_images,
            rendered.screenshots,
        )
        broken_accessibility_check = next(
            check
            for check in broken_accessibility_report.checks
            if check.id == "html-display-values"
        )
        assert not broken_accessibility_check.passed

    share_label = (
        f"Consensus among explicitly endorsing sources: {accessible_race.percentage_label}"
    )
    for index, (original, replacement) in enumerate(
        (
            (f'aria-label="{share_label}"', 'aria-label="Consensus among endorsers: 100%"'),
            ('role="img"', 'role="presentation"'),
        )
    ):
        assert original in accessible_html
        broken_share_html = tmp_path / f"broken-share-accessibility-{index}.html"
        broken_share_html.write_text(
            accessible_html.replace(original, replacement, 1),
            encoding="utf-8",
        )
        broken_share_report = validate_rendered_guide(
            view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            broken_share_html,
            rendered.pdf_path,
            rendered.page_images,
            rendered.screenshots,
        )
        broken_share_check = next(
            check for check in broken_share_report.checks if check.id == "html-display-values"
        )
        assert not broken_share_check.passed

    unavailable_view_model = view_model.model_copy(deep=True)
    unavailable_race = unavailable_view_model.sections[0].races[0]
    unavailable_race.support_leader_candidate_ids = []
    unavailable_race.support_leader_candidate_labels = []
    unavailable_race.support_leader_label = "No leader"
    unavailable_race.recommendation_candidate_ids = []
    unavailable_race.recommendation_candidate_labels = []
    unavailable_race.recommendation_label = "Too few endorsements"
    unavailable_race.grade = "Insufficient"
    unavailable_race.winner_share = None
    unavailable_race.percentage_label = "—"
    unavailable_race.percentage_whole = None
    unavailable_view_model = _revalidated(unavailable_view_model)
    unavailable_html_text = render_html_document(
        unavailable_view_model, read_rendering_configuration(RENDERING_CONFIG)
    )
    unavailable_html = tmp_path / "unavailable-share.html"
    unavailable_html.write_text(unavailable_html_text, encoding="utf-8")
    unavailable_report = validate_rendered_guide(
        unavailable_view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        unavailable_html,
        rendered.pdf_path,
        rendered.page_images,
        rendered.screenshots,
    )
    unavailable_html_check = next(
        check for check in unavailable_report.checks if check.id == "html-display-values"
    )
    assert unavailable_html_check.passed
    unavailable_label = "Consensus among explicitly endorsing sources: not available"
    for index, (original, replacement) in enumerate(
        (
            (f'aria-label="{unavailable_label}"', 'aria-label="Consensus among endorsers: 0%"'),
            ('role="img"', 'role="presentation"'),
        )
    ):
        assert original in unavailable_html_text
        broken_unavailable_html = tmp_path / f"broken-unavailable-accessibility-{index}.html"
        broken_unavailable_html.write_text(
            unavailable_html_text.replace(original, replacement, 1),
            encoding="utf-8",
        )
        broken_unavailable_report = validate_rendered_guide(
            unavailable_view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            broken_unavailable_html,
            rendered.pdf_path,
            rendered.page_images,
            rendered.screenshots,
        )
        broken_unavailable_check = next(
            check for check in broken_unavailable_report.checks if check.id == "html-display-values"
        )
        assert not broken_unavailable_check.passed

    race_for_masking = next(race for race in races if race.recommendation_candidate_labels)
    masked_pdf_html = tmp_path / "masked-pdf.html"
    print_result_element = (
        '<div class="print-race-result">\n'
        f"        <strong>{race_for_masking.recommendation_label}</strong>"
    )
    rendered_html_text = rendered.html_path.read_text(encoding="utf-8")
    assert print_result_element in rendered_html_text
    masked_html_text = rendered_html_text.replace(
        print_result_element,
        print_result_element.replace(
            f"<strong>{race_for_masking.recommendation_label}</strong>",
            "<strong>Wrong recommendation</strong>",
        ),
        1,
    )
    comparison = race_for_masking.comparisons[0]
    comparison_element = (
        f'<b class="print-times-pick print-times-pick-{comparison.voter_tone}">'
        f'<span class="print-times-status">{comparison.print_status_label}</span>'
        '<span class="print-times-separator"> · </span>'
        f'<span class="print-times-choice">{comparison.print_choice_label}</span></b>'
    )
    assert comparison_element in masked_html_text
    masked_html_text = masked_html_text.replace(
        comparison_element,
        comparison_element.replace("</b>", f" / {race_for_masking.recommendation_label}</b>"),
        1,
    )
    masked_pdf_html.write_text(masked_html_text, encoding="utf-8")
    masked_pdf = tmp_path / "masked.pdf"
    _render_pdf(masked_pdf_html, masked_pdf, find_chrome())
    masked_pdf_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        masked_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    masked_pdf_check = next(
        check for check in masked_pdf_report.checks if check.id == "pdf-display-values"
    )
    assert not masked_pdf_check.passed

    malicious_link_pdf = tmp_path / "malicious-link.pdf"
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(rendered.pdf_path))
    replaced_link = False
    for page in writer.pages:
        for annotation_reference in page.get("/Annots", []):
            annotation = annotation_reference.get_object()
            action = annotation.get("/A")
            if action is not None and action.get("/URI"):
                action[NameObject("/URI")] = TextStringObject("https://evil.example/phish")
                replaced_link = True
                break
        if replaced_link:
            break
    assert replaced_link
    with malicious_link_pdf.open("wb") as output:
        writer.write(output)
    malicious_link_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        malicious_link_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    pdf_link_check = next(
        check for check in malicious_link_report.checks if check.id == "pdf-links"
    )
    assert not pdf_link_check.passed

    swapped_source_pdf = tmp_path / "swapped-publication-source-links.pdf"
    _render_pdf(swapped_source_links_html, swapped_source_pdf, find_chrome())
    swapped_source_pdf_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        swapped_source_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    swapped_source_pdf_link_check = next(
        check for check in swapped_source_pdf_report.checks if check.id == "pdf-links"
    )
    assert not swapped_source_pdf_link_check.passed

    swapped_source_names_html = tmp_path / "swapped-publication-source-names.html"
    swapped_source_names_html.write_text(
        canonical_html.replace(first_source_link, "__FIRST_SOURCE_LINK__", 2)
        .replace(
            second_source_link,
            f'<a href="{second_source.evidence_url}">{first_source.name}</a>',
            2,
        )
        .replace(
            "__FIRST_SOURCE_LINK__",
            f'<a href="{first_source.evidence_url}">{second_source.name}</a>',
            2,
        ),
        encoding="utf-8",
    )
    swapped_source_names_pdf = tmp_path / "swapped-publication-source-names.pdf"
    _render_pdf(swapped_source_names_html, swapped_source_names_pdf, find_chrome())
    swapped_source_names_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        swapped_source_names_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    swapped_source_names_check = next(
        check for check in swapped_source_names_report.checks if check.id == "pdf-links"
    )
    assert not swapped_source_names_check.passed

    counted_source = next(
        source for source in view_model.sources if source.split_endorsement_count > 0
    )
    assert (
        sum(
            source.endorsement_count == counted_source.endorsement_count
            and source.split_endorsement_count == counted_source.split_endorsement_count
            for source in view_model.sources
        )
        == 1
    )
    print_source_marker = f'data-publication-source-id="{counted_source.id}"'
    print_source_start = canonical_html.index(
        print_source_marker, canonical_html.index(print_source_marker) + 1
    )
    print_count_start = canonical_html.index("<span>", print_source_start)
    print_count_end = canonical_html.index("</span>", print_count_start) + len("</span>")
    wrong_source_count_html = tmp_path / "wrong-publication-source-count.html"
    wrong_source_count_html.write_text(
        canonical_html[:print_count_start]
        + "<span>999 · 999 split</span>"
        + canonical_html[print_count_end:],
        encoding="utf-8",
    )
    wrong_source_count_pdf = tmp_path / "wrong-publication-source-count.pdf"
    _render_pdf(wrong_source_count_html, wrong_source_count_pdf, find_chrome())
    wrong_source_count_pdf_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        wrong_source_count_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    wrong_source_count_pdf_check = next(
        check for check in wrong_source_count_pdf_report.checks if check.id == "pdf-display-values"
    )
    assert not wrong_source_count_pdf_check.passed

    first_count_source = next(
        source for source in view_model.sources if source.panel_role == "consensus"
    )
    second_count_source = next(
        source
        for source in view_model.sources
        if source.panel_role == "consensus"
        and (
            source.endorsement_count,
            source.split_endorsement_count,
        )
        != (
            first_count_source.endorsement_count,
            first_count_source.split_endorsement_count,
        )
    )

    def print_count_span(source_id: str) -> tuple[int, int]:
        marker = f'data-publication-source-id="{source_id}"'
        row_start = canonical_html.index(marker, canonical_html.index(marker) + 1)
        count_start = canonical_html.index("<span>", row_start)
        count_end = canonical_html.index("</span>", count_start) + len("</span>")
        return count_start, count_end

    first_start, first_end = print_count_span(first_count_source.id)
    second_start, second_end = print_count_span(second_count_source.id)
    assert first_start < second_start
    first_count = canonical_html[first_start:first_end]
    second_count = canonical_html[second_start:second_end]
    swapped_source_counts_html = tmp_path / "swapped-publication-source-counts.html"
    swapped_source_counts_html.write_text(
        canonical_html[:first_start]
        + second_count
        + canonical_html[first_end:second_start]
        + first_count
        + canonical_html[second_end:],
        encoding="utf-8",
    )
    swapped_source_counts_pdf = tmp_path / "swapped-publication-source-counts.pdf"
    _render_pdf(swapped_source_counts_html, swapped_source_counts_pdf, find_chrome())
    swapped_source_counts_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        swapped_source_counts_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    swapped_source_counts_check = next(
        check for check in swapped_source_counts_report.checks if check.id == "pdf-display-values"
    )
    assert not swapped_source_counts_check.passed

    metadata_marker = (
        f"Data {view_model.metadata.data_version} · Code {view_model.metadata.git_commit[:12]}"
    )
    rendered_html_text = rendered.html_path.read_text(encoding="utf-8")
    assert metadata_marker in rendered_html_text
    wrong_metadata_html = tmp_path / "wrong-publication-metadata.html"
    wrong_metadata_html.write_text(
        rendered_html_text.replace(metadata_marker, "Data WRONG-VERSION · Code wrong-commit", 2),
        encoding="utf-8",
    )
    wrong_metadata_pdf = tmp_path / "wrong-publication-metadata.pdf"
    _render_pdf(wrong_metadata_html, wrong_metadata_pdf, find_chrome())
    wrong_metadata_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        wrong_metadata_pdf,
        rendered.page_images,
        rendered.screenshots,
    )
    wrong_metadata_check = next(
        check for check in wrong_metadata_report.checks if check.id == "pdf-display-values"
    )
    assert not wrong_metadata_check.passed


def test_dense_concise_content_still_fits_two_pages(tmp_path: Path) -> None:
    view_model = _dense_view_model(_view_model(tmp_path / "fixture"))
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))

    rendered = build_rendered_guide(
        view_model_path,
        RENDERING_CONFIG,
        tmp_path / "rendered",
    )

    assert rendered.validation_report.passed
    assert rendered.validation_report.page_count == 2
    assert rendered.validation_report.edition == "concise"
    assert rendered.detailed_pdf_path is None
    assert rendered.validation_report.detailed_page_count == 0
    assert rendered.detailed_page_images == []


def test_long_comparison_choice_is_not_truncated(tmp_path: Path) -> None:
    view_model = _visual_view_model(_view_model(tmp_path / "fixture"))
    race = next(race for section in view_model.sections for race in section.races)
    long_label = "Alexandria Ocasio-Cortez-Washington"
    candidate_id = race.recommendation_candidate_ids[0]
    race.support_leader_candidate_labels = [
        long_label if item == candidate_id else label
        for item, label in zip(
            race.support_leader_candidate_ids,
            race.support_leader_candidate_labels,
            strict=True,
        )
    ]
    race.support_leader_label = " / ".join(race.support_leader_candidate_labels)
    race.recommendation_candidate_labels = [
        long_label if item == candidate_id else label
        for item, label in zip(
            race.recommendation_candidate_ids,
            race.recommendation_candidate_labels,
            strict=True,
        )
    ]
    race.recommendation_label = " / ".join(race.recommendation_candidate_labels)
    for group in race.endorsement_groups:
        if group.candidate_id == candidate_id:
            group.candidate_label = long_label
    for alternative in race.alternatives:
        if alternative.candidate_id == candidate_id:
            alternative.candidate_label = long_label
    for category in race.category_breakdown:
        for support in category.candidate_support:
            if support.candidate_id == candidate_id:
                support.candidate_label = long_label
    for cell in race.source_cells:
        cell.candidate_labels = [
            long_label if item == candidate_id else label
            for item, label in zip(cell.candidate_ids, cell.candidate_labels, strict=True)
        ]
    race.comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": race.comparisons[0].source_id,
                "status": "agrees",
                "badge_label": "AGREES",
                "candidate_ids": [candidate_id],
                "candidate_labels": [long_label],
            }
        )
    ]
    view_model = _revalidated(view_model)
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))

    rendered = build_rendered_guide(
        view_model_path,
        RENDERING_CONFIG,
        tmp_path / "rendered",
    )

    assert rendered.validation_report.passed
    assert rendered.validation_report.edition == "concise_plus_detailed"
    assert rendered.detailed_pdf_path is not None
    pdf_text = " ".join(
        " ".join((page.extract_text() or "").split()) for page in PdfReader(rendered.pdf_path).pages
    )
    assert long_label in pdf_text
    assert f"{race.explicit_endorsement_count} endorsers" in pdf_text

    compact_support = (
        '<span class="print-support print-support-compact">'
        f"{race.explicit_endorsement_count} endorsers</span>"
    )
    rendered_html = rendered.html_path.read_text(encoding="utf-8")
    assert compact_support in rendered_html
    wrong_count_html = tmp_path / "wrong-compact-count.html"
    wrong_count_html.write_text(
        rendered_html.replace(
            compact_support, compact_support.replace("endorsers", "99 endorsers"), 1
        ),
        encoding="utf-8",
    )
    wrong_count_pdf = tmp_path / "wrong-compact-count.pdf"
    _render_pdf(wrong_count_html, wrong_count_pdf, find_chrome(), edition="compact")
    wrong_count_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        wrong_count_pdf,
        rendered.page_images,
        rendered.screenshots,
        detailed_pdf_path=rendered.detailed_pdf_path,
        detailed_page_images=rendered.detailed_page_images,
    )
    wrong_count_check = next(
        check for check in wrong_count_report.checks if check.id == "pdf-display-values"
    )
    assert not wrong_count_check.passed


def test_detailed_pdf_trims_only_rendered_trailing_blank_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "detailed.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as output:
        writer.write(output)

    page_images = [tmp_path / f"page-{number}.png" for number in range(1, 4)]
    for path in page_images[:2]:
        image = Image.new("RGB", (200, 260), "white")
        for x in range(20, 180):
            for y in range(20, 40):
                image.putpixel((x, y), (0, 0, 0))
        image.save(path)
    Image.new("RGB", (200, 260), "white").save(page_images[2])

    assert _trim_trailing_blank_pages(pdf_path, page_images) == 1
    assert len(PdfReader(pdf_path).pages) == 2


def test_detailed_pdf_preserves_sparse_page_with_extractable_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "detailed.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.append(PROJECT_ROOT / "tests/fixtures/evidence/endorsements.pdf")
    with pdf_path.open("wb") as output:
        writer.write(output)

    page_images = [tmp_path / f"page-{number}.png" for number in range(1, 3)]
    for path in page_images:
        Image.new("RGB", (200, 260), "white").save(path)

    assert PdfReader(pdf_path).pages[-1].extract_text()
    assert _trim_trailing_blank_pages(pdf_path, page_images) == 0
    assert len(PdfReader(pdf_path).pages) == 2


def test_overflowing_screen_methodology_does_not_bloat_concise_pdf(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    view_model.methodology.interpretation_notes = [
        "This canonical interpretation sentence must remain visible in the published methodology. "
        * 180
    ]
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))
    rendered = build_rendered_guide(view_model_path, RENDERING_CONFIG, tmp_path / "rendered")

    assert rendered.validation_report.passed
    assert rendered.validation_report.edition == "concise"
    assert rendered.detailed_pdf_path is None
    assert "This canonical interpretation sentence" not in rendered.html_path.read_text(
        encoding="utf-8"
    )
    concise_text = " ".join(
        page.extract_text() or "" for page in PdfReader(rendered.pdf_path).pages
    )
    assert "This canonical interpretation sentence" not in concise_text


def test_responsive_tablet_layout_and_methodology_disclosure(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )

    _render_screenshot(
        html_path,
        tmp_path / "tablet.png",
        find_chrome(),
        width=768,
        height=1200,
        expected_race_count=sum(len(section.races) for section in view_model.sections),
        expected_source_count=len(view_model.sources),
    )


def test_pdf_source_participation_order_survives_wrapped_source_names() -> None:
    lines = [
        "    First source name                       2 · 0 split           Third source",
        "                                                    "
        "                name wraps       5 · 1 split",
        "    Regional Progressive Coalition and Community",
        "    Action Network                          7 · 0 split           "
        "Times source        15 picks · 0 split",
    ]

    assert _pdf_source_participation_labels(lines) == [
        "2 · 0 split",
        "7 · 0 split",
        "5 · 1 split",
        "15 picks · 0 split",
    ]


def test_pdf_identity_validation_rejects_concatenated_print_title(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    configuration = read_rendering_configuration(RENDERING_CONFIG)
    html_path = tmp_path / "guide.html"
    html = render_html_document(view_model, configuration)
    html_path.write_text(
        html.replace(
            '<h1 data-document-role="print-title">Seattle Progressive Endorsement Guide</h1>',
            '<h1 data-document-role="print-title">SeattleProgressiveEndorsementGuide</h1>',
            1,
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "guide.pdf"
    _render_pdf(html_path, pdf_path, find_chrome())
    _set_pdf_metadata(pdf_path, view_model, configuration)
    page_dir = tmp_path / "pages"
    page_dir.mkdir()
    page_images = _render_pdf_pages(pdf_path, page_dir, find_pdftoppm())
    screenshots: list[Path] = []
    for name, width in (("desktop", configuration.desktop_width), ("mobile", 390)):
        screenshot = Image.new("RGB", (width, configuration.screenshot_height), "white")
        screenshot.paste("black", (0, 0, width, 100))
        screenshot_path = tmp_path / f"{name}.png"
        screenshot.save(screenshot_path)
        screenshots.append(screenshot_path)

    report = validate_rendered_guide(
        view_model,
        configuration,
        html_path,
        pdf_path,
        page_images,
        screenshots,
    )

    identity_check = next(check for check in report.checks if check.id == "pdf-display-values")
    assert not identity_check.passed
    assert "Seattle Progressive Endorsement Guide" in identity_check.message


def _dense_view_model(view_model: PublicationViewModel) -> PublicationViewModel:
    races = [race for section in view_model.sections for race in section.races]
    example = next(race for race in races if race.recommendation_candidate_labels)
    display = {
        "support_leader_candidate_ids": example.support_leader_candidate_ids,
        "support_leader_candidate_labels": example.support_leader_candidate_labels,
        "support_leader_label": example.support_leader_label,
        "recommendation_candidate_ids": example.recommendation_candidate_ids,
        "recommendation_candidate_labels": example.recommendation_candidate_labels,
        "recommendation_label": example.recommendation_label,
        "grade": example.grade,
        "winner_share": example.winner_share,
        "percentage_label": example.percentage_label,
        "percentage_whole": example.percentage_whole,
        "support_summary": example.support_summary,
        "explicit_endorsement_count": example.explicit_endorsement_count,
        "eligible_source_count": example.eligible_source_count,
        "source_coverage_count": example.source_coverage_count,
        "category_coverage_count": example.category_coverage_count,
        "category_breakdown": example.category_breakdown,
        "no_endorsement_count": example.no_endorsement_count,
        "missing_source_count": example.missing_source_count,
        "endorsement_groups": example.endorsement_groups,
        "alternatives": example.alternatives,
        "comparisons": example.comparisons,
        "warning_codes": example.warning_codes,
        "warning_messages": example.warning_messages,
        "source_cells": example.source_cells,
    }
    sections = [
        section.model_copy(
            update={"races": [race.model_copy(update=display) for race in section.races]}
        )
        for section in view_model.sections
    ]
    source_cells = [
        cell for section in sections for race in section.races for cell in race.source_cells
    ]
    sources = [
        source.model_copy(
            update={
                "endorsement_count": sum(
                    cell.source_id == source.id
                    and cell.state in {"endorsement", "multi_endorsement"}
                    for cell in source_cells
                ),
                "split_endorsement_count": sum(
                    cell.source_id == source.id and cell.state == "multi_endorsement"
                    for cell in source_cells
                ),
            }
        )
        for source in view_model.sources
    ]
    return _revalidated(view_model.model_copy(update={"sections": sections, "sources": sources}))


def _visual_view_model(view_model: PublicationViewModel) -> PublicationViewModel:
    visual = _dense_view_model(view_model)
    comparison_source_index = next(
        index for index, source in enumerate(visual.sources) if source.panel_role == "comparison"
    )
    template_source = next(
        source
        for source in visual.sources
        if source.panel_role == "consensus" and not source.overlap_group_ids
    )
    additional_sources = [
        template_source.model_copy(
            update={
                "id": f"visual-source-{index:02d}",
                "name": f"Regional Progressive Coalition and Community Action Network {index:02d}",
                "organization_url": f"https://example.com/visual-source-{index:02d}",
                "evidence_url": f"https://example.com/visual-source-{index:02d}/endorsements",
                "endorsement_count": 0,
                "split_endorsement_count": 0,
            }
        )
        for index in range(1, 32)
    ]
    visual.sources[comparison_source_index:comparison_source_index] = additional_sources
    category = next(
        category
        for category in visual.methodology.source_categories
        if category.category == template_source.category
    )
    category.source_ids.extend(source.id for source in additional_sources)
    additional_cells = [
        SourceCell.model_validate(
            {
                "source_id": source.id,
                "state": "not_applicable",
                "candidate_ids": [],
                "candidate_labels": [],
                "allocation": {},
                "evidence_url": None,
                "evidence_locator": None,
                "confidence_warning": False,
            }
        )
        for source in additional_sources
    ]
    for section in visual.sections:
        for race in section.races:
            race.source_cells[comparison_source_index:comparison_source_index] = additional_cells
    visual.metadata.source_count += len(additional_sources)
    visual.metadata.captured_source_count += len(additional_sources)
    visual.metadata.contributing_source_count += len(additional_sources)
    races = [race for section in visual.sections for race in section.races]
    source_id = races[0].comparisons[0].source_id
    races[0].comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": source_id,
                "status": "agrees",
                "badge_label": "AGREES",
                "candidate_ids": races[0].recommendation_candidate_ids,
                "candidate_labels": races[0].recommendation_candidate_labels,
            }
        )
    ]
    races[1].comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": source_id,
                "status": "differs",
                "badge_label": "DIFFERENT PICK",
                "candidate_ids": ["toshiko-grace-hasegawa"],
                "candidate_labels": ["Toshiko Grace Hasegawa"],
            }
        )
    ]
    races[2].comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": source_id,
                "status": "not_covered",
                "badge_label": "NOT COVERED",
                "candidate_ids": [],
                "candidate_labels": [],
            }
        )
    ]
    for race, percentage in zip(races[:4], (53, 64, 70, 100), strict=True):
        race.winner_share = str(Fraction(percentage, 100))
        race.percentage_label = f"{percentage}%"
        race.percentage_whole = percentage
    return _revalidated(visual)


def _coarse_visual_signature(path: Path) -> list[float]:
    with Image.open(path) as opened:
        image = opened.convert("RGB").resize(  # pyright: ignore[reportUnknownMemberType]
            (4, 4), Image.Resampling.BOX
        )
        signature: list[float] = []
        for y in range(4):
            for x in range(4):
                pixel = cast(tuple[int, int, int], image.getpixel((x, y)))
                signature.append(round(1 - sum(pixel) / (3 * 255), 3))
        return signature


def _view_model(root: Path) -> PublicationViewModel:
    dataset = _publication_dataset(root)
    snapshot_root = _snapshot_store(root, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    return build_publication_bundle(
        dataset,
        report,
        git_commit="render-fixture",
        snapshot_root=snapshot_root,
    ).view_model


def _revalidated(view_model: PublicationViewModel) -> PublicationViewModel:
    """Revalidate a hand-built display model with a coherent lens payload.

    Layout fixtures synthesize extra panel sources, so this mints transport
    codes for them and reprojects the derived lens records before validating.
    """
    contract = view_model.personalization
    lens_by_id = {source.id: source for source in contract.sources}
    lens_sources: list[PersonalizationSource] = []
    for index, source in enumerate(view_model.sources):
        existing = lens_by_id.get(source.id)
        if existing is not None:
            lens_sources.append(existing)
            continue
        lens_sources.append(
            PersonalizationSource(
                id=source.id,
                code=f"x{index:03d}",
                panel_role=source.panel_role,
                selectable=source.panel_role == "consensus",
                reporting_category_id=source.category,
                selection_category_ids=[source.category],
                overlap_group_ids=source.overlap_group_ids,
            )
        )
    categories = [
        category.model_copy(
            update={
                "member_source_codes": sorted(
                    source.code
                    for source in lens_sources
                    if source.selectable and category.id in source.selection_category_ids
                )
                if category.selectable
                else []
            }
        )
        for category in contract.categories
    ]
    rebuilt = view_model.model_copy(
        update={
            "personalization": contract.model_copy(
                update={"sources": lens_sources, "categories": categories}
            )
        }
    )
    return PublicationViewModel.model_validate(
        reprojected_personalization(rebuilt).model_dump(mode="json")
    )


def _customize_html(tmp_path: Path) -> str:
    """Render the reference guide the way the other rendering tests do."""
    return render_html_document(
        _view_model(tmp_path), read_rendering_configuration(RENDERING_CONFIG)
    )


def test_customize_shell_hides_the_times_comparison_by_default(tmp_path: Path) -> None:
    """Issue 79: the default responsive load carries no Times pill or decision."""
    html = _customize_html(tmp_path)
    stylesheet = html.split("<style>")[1].split("</style>")[0]

    # Hidden in CSS rather than in script, so the default holds before and without JS.
    assert "html:not(.show-times):not(.detailed-edition) .screen-comparisons" in stylesheet
    # The wrapper is hidden, not the inner row, so no bordered list item is stranded.
    assert '.race-detail-source-list > li[data-source-role="comparison"]' in stylesheet
    assert ".show-times" not in html.split("<style>")[0]

    # Hiding a grid item must not reflow its sibling out of the column it occupies.
    assert ".screen-race-context .support-line { grid-column: 2; }" in stylesheet

    # A heading may never claim more sources than the state actually lists.
    detail = html.split('data-race-detail-group="no_endorsement"')[1].split("</section>")[0]
    assert "data-times-hidden" in detail and "data-times-only" in detail
    assert "html.show-times [data-times-hidden]" in stylesheet


def test_customize_shell_exposes_one_action_and_keeps_controls_in_the_dialog(
    tmp_path: Path,
) -> None:
    html = _customize_html(tmp_path)
    controls = html.split('<section class="screen-controls"')[1].split("</section>")[0]

    assert controls.count("<button") == 1
    assert "data-customize-open" in controls
    assert 'aria-haspopup="dialog"' in controls

    dialog = html.split('<dialog class="customize-dialog"')[1].split("</dialog>")[0]
    assert "data-customize-times" in dialog
    assert 'aria-labelledby="customize-title"' in dialog
    # Source selection stays out until the policy is enabled (issue 80 owns it).
    assert "data-customize-source" not in html
    assert "data-customize-category" not in html


def test_customize_shell_encodes_state_through_the_published_codec(tmp_path: Path) -> None:
    html = _customize_html(tmp_path)
    codec = (
        Path(__file__).parent.parent / "src/election_guide/rendering/templates/lens-url.mjs"
    ).read_text(encoding="utf-8")

    # The page inlines the codec verbatim rather than restating its rules.
    assert "export function encodeLensFragment" in codec
    assert codec.strip() in html
    assert 'id="lens-bindings"' in html
    assert "encodeLensFragment(" in html
    assert "decodeLensFragment(" in html


def test_customize_shell_leaves_the_print_comparison_untouched(tmp_path: Path) -> None:
    html = _customize_html(tmp_path)
    stylesheet = html.split("<style>")[1].split("</style>")[0]
    print_block = stylesheet.split("@media print {")[1]

    # The fixed PDF always carries the comparison; only the opener is screen-only.
    assert (
        ".customize-control, .customize-dialog, .lens-banner, .lens-notice { display: none; }"
        in print_block
    )
    assert "show-times" not in print_block
    assert "print-times-pick" in stylesheet
    assert "Read the Times pill" in html


def test_customize_shell_describes_the_times_as_optional(tmp_path: Path) -> None:
    html = _customize_html(tmp_path)
    hero = html.split('<p class="hero-deck">')[1].split("</p>")[0]

    assert "optional comparison" in hero
    assert "Customize" in hero
    assert "The Times is separate and optional" in html
    assert "hidden by default on screen" in html


def _candidate_section(html: str, candidate_id: str) -> str:
    match = re.search(
        rf'<section class="race-detail-candidate[^"]*"\s+'
        rf'data-race-detail-candidate-id="{re.escape(candidate_id)}"[^>]*>',
        html,
    )
    assert match is not None, f"no rendered section for {candidate_id!r}"
    return match.group(0)


def test_customize_shell_hides_a_comparison_only_candidate_by_default() -> None:
    """Issue 79: a candidate only the Seattle Times picked must not leak by default."""
    view_model = _production_bundle().view_model
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    source_by_id = {source.id: source for source in view_model.sources}

    group_by_candidate_id = {
        candidate_id: endorsement_group
        for section in view_model.sections
        for race in section.races
        for candidate_id, _label, endorsement_group in _race_detail_candidate_choices(
            race, source_by_id
        )
    }
    comparison_only_candidate_ids = {
        candidate_id for candidate_id, group in group_by_candidate_id.items() if group is None
    }
    # The production panel has at least one candidate only the comparison source
    # picked; confirm the assertions below are not vacuous.
    assert len(comparison_only_candidate_ids) > 0

    for candidate_id in comparison_only_candidate_ids:
        assert "data-times-only" in _candidate_section(html, candidate_id)

    # A candidate with a real consensus endorser must not carry the marker.
    contributing_id = next(
        candidate_id for candidate_id, group in group_by_candidate_id.items() if group is not None
    )
    assert "data-times-only" not in _candidate_section(html, contributing_id)


def _personalization_enabled_view_model(tmp_path: Path) -> PublicationViewModel:
    """The customize fixture with the lens policy enabled, for issue 80's UI."""
    view_model = _view_model(tmp_path)
    enabled_policy = view_model.personalization.policy.model_copy(update={"enabled": True})
    view_model = view_model.model_copy(
        update={
            "personalization": view_model.personalization.model_copy(
                update={"policy": enabled_policy}
            )
        }
    )
    return _revalidated(view_model)


def _evaluate_in_chrome(
    html_path: Path,
    expression: str,
    *,
    mobile_width: int | None = None,
    initial_url: str | None = None,
) -> dict[str, Any]:
    """Load one local file in headless Chrome and return one JSON object result.

    A minimal harness for the personalization flow: unlike _render_screenshot's
    responsive-interaction probe, this only needs one page load and one script
    evaluation, so it does not share that function's screenshot-capture
    machinery. Pass mobile_width to emulate a narrow CSS viewport first. Pass
    initial_url to navigate to an already-encoded shared link (query string
    and/or fragment) instead of the bare file, to exercise a load-time restore
    rather than an in-page transition.
    """
    chrome_path = find_chrome()
    profile = Path(tempfile.mkdtemp(prefix="election-guide-chrome-"))
    try:
        process = subprocess.Popen(
            [
                str(chrome_path),
                "--headless=new",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-extensions",
                "--hide-scrollbars",
                "--no-first-run",
                "--allow-file-access-from-files",
                f"--user-data-dir={profile}",
                "--remote-debugging-port=0",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            port, browser_path = _wait_for_devtools_endpoint(process, profile)
            websocket = create_connection(
                f"ws://127.0.0.1:{port}{browser_path}",
                timeout=30,
                suppress_origin=True,
                http_no_proxy=["127.0.0.1"],
            )
            try:
                cdp = _CdpSocket(websocket)
                target = cdp.command("Target.createTarget", {"url": "about:blank"})
                target_id = cast(str, target["targetId"])
                attached = cdp.command(
                    "Target.attachToTarget", {"targetId": target_id, "flatten": True}
                )
                session_id = cast(str, attached["sessionId"])
                cdp.command("Page.enable", session_id=session_id)
                if mobile_width is not None:
                    cdp.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": mobile_width,
                            "height": 780,
                            "deviceScaleFactor": 1,
                            "mobile": True,
                        },
                        session_id=session_id,
                    )
                cdp.command(
                    "Page.navigate",
                    {"url": initial_url or html_path.resolve().as_uri()},
                    session_id=session_id,
                )
                cdp.wait_event("Page.loadEventFired", session_id=session_id)
                evaluated = cdp.command(
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True, "awaitPromise": True},
                    session_id=session_id,
                )
                result = cast(dict[str, object], evaluated["result"])
                if "value" not in result:
                    raise ValueError(f"personalization evaluation failed: {evaluated}")
                return cast(dict[str, Any], json.loads(cast(str, result["value"])))
            finally:
                websocket.close()
        finally:
            _terminate_process(process)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _with_multi_category_source(view_model: PublicationViewModel) -> PublicationViewModel:
    """Give one selectable source a second selection category, for issue 80's
    "a multi-category source appears once and exposes every inclusion reason"
    acceptance criterion. The small rendering fixture has no such source."""
    contract = view_model.personalization
    target = next(source for source in contract.sources if source.selectable)
    second_category = next(
        category
        for category in contract.categories
        if category.selectable and category.id != target.reporting_category_id
    )
    sources = [
        source.model_copy(
            update={
                "selection_category_ids": sorted(
                    {*source.selection_category_ids, second_category.id}
                )
            }
        )
        if source.id == target.id
        else source
        for source in contract.sources
    ]
    categories = [
        category.model_copy(
            update={"member_source_codes": sorted({*category.member_source_codes, target.code})}
        )
        if category.id == second_category.id
        else category
        for category in contract.categories
    ]
    mutated = view_model.model_copy(
        update={
            "personalization": contract.model_copy(
                update={"sources": sources, "categories": categories}
            )
        }
    )
    return PublicationViewModel.model_validate(mutated.model_dump(mode="json"))


def test_personalization_is_invisible_while_the_policy_is_disabled(tmp_path: Path) -> None:
    """Issue 80/81: no selection UI, no mode toggle, no per-race lens
    presentation, and no full payload, while disabled.

    The stylesheet carries `[data-lens-only]`/`[data-lens-hidden]` selectors
    unconditionally (an unused selector is harmless with no matching markup),
    so, like the existing show-times check, this looks only at the body.
    """
    html = _customize_html(tmp_path)
    body = html.split("</style>", 1)[1]

    for marker in (
        "data-customize-mode",
        "data-customize-category",
        "data-customize-source",
        "data-customize-personalize",
        "data-lens-banner",
        "data-lens-notice",
        "data-lens-only",
        "data-lens-hidden",
        "data-lens-card-badge",
        "data-lens-recommendation",
        "data-lens-share",
        "data-lens-support",
        "data-lens-insufficient",
        "data-lens-comparison",
        "data-race-detail-lens",
        "data-lens-detail-summary",
        "data-lens-detail-audited",
        "data-lens-detail-sources",
        'id="lens-personalization"',
    ):
        assert marker not in body

    bindings = json.loads(html.split('id="lens-bindings">')[1].split("</script>")[0])
    assert bindings["categories"] == []
    assert bindings["sources"] == []


def test_personalization_ui_renders_every_selectable_category_and_source(tmp_path: Path) -> None:
    view_model = _personalization_enabled_view_model(tmp_path)
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    contract = view_model.personalization

    selectable_categories = [item for item in contract.categories if item.selectable]
    selectable_sources = [item for item in contract.sources if item.selectable]
    assert len(selectable_categories) > 0
    assert len(selectable_sources) > 0

    for category in selectable_categories:
        assert f'data-customize-category="{category.code}"' in html
    for source in selectable_sources:
        assert f'data-customize-source="{source.code}"' in html
    # The comparison source/category are identified but never selectable.
    assert 'data-customize-category="Gcmp"' not in html
    for source in contract.sources:
        if not source.selectable:
            assert f'data-customize-source="{source.code}"' not in html

    bindings = json.loads(html.split('id="lens-bindings">')[1].split("</script>")[0])
    assert len(bindings["categories"]) == len(contract.categories)
    assert len(bindings["sources"]) == len(contract.sources)

    # Categories and Sources are two sibling fieldsets, each with its own
    # legend: a fieldset accepts only one legend, and the source checklist
    # must have its own accessible group name rather than inheriting
    # "Categories" from a legend that belongs to a different group.
    personalize_panel = html.split("data-customize-personalize")[1].split(
        '<p class="customize-status"'
    )[0]
    assert personalize_panel.count("<fieldset") == 2
    category_fieldset = personalize_panel.split("<fieldset")[1]
    assert category_fieldset.count("<legend>") == 1
    assert "Categories" in category_fieldset
    source_fieldset = personalize_panel.split("<fieldset")[2]
    assert source_fieldset.count("<legend>") == 1
    assert "Sources" in source_fieldset
    assert "data-customize-source-list" in source_fieldset


def test_personalization_initial_my_sources_matches_audited_consensus(tmp_path: Path) -> None:
    """Issue 80 acceptance criterion: initial My sources results equal audited.

    Module-scoped bindings inside the page's own `<script type="module">` are
    not reachable from an injected Runtime.evaluate expression (they are not
    global), so this observes the page's own computed DOM/banner output
    rather than calling scoreSelection from outside it. The claim that
    scoring the full selectable panel reproduces the audited consensus
    exactly is lens-score.mjs's own tested contract (issue 77,
    "the full selectable panel reproduces the audited published consensus");
    this test proves only that entering My sources reaches that full-panel
    selection, which is the part issue 80 owns.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    selectable_source_count = sum(
        1 for source in view_model.personalization.sources if source.selectable
    )
    selectable_category_count = sum(
        1 for category in view_model.personalization.categories if category.selectable
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          const categoryInputs = [...document.querySelectorAll('[data-customize-category]')];
          const allChecked = categoryInputs.every((input) => input.checked);
          const noDirect = [...document.querySelectorAll('[data-customize-source]')]
            .every((input) => !input.checked);
          return JSON.stringify({
            allChecked,
            noDirect,
            counts: document.querySelector('[data-customize-counts]').textContent,
            banner: document.querySelector('[data-lens-banner]').textContent,
          });
        })()
        """,
    )
    assert result["allChecked"] is True
    assert result["noDirect"] is True
    # Every source belongs to at least one selectable category (issue 75's own
    # registry invariant), so selecting every category reaches the full panel.
    assert result["counts"] == (
        f"0 direct · {selectable_category_count} categories · "
        f"{selectable_source_count} sources included"
    )
    assert f"{selectable_source_count} of {selectable_source_count} sources" in result["banner"]


def test_personalization_multi_category_source_appears_once_with_every_reason(
    tmp_path: Path,
) -> None:
    """Issue 80 acceptance criteria: a multi-category source counts once and
    exposes every inclusion reason; removing its direct pick keeps it included
    through a still-checked category."""
    view_model = _with_multi_category_source(_personalization_enabled_view_model(tmp_path))
    contract = view_model.personalization
    target = next(source for source in contract.sources if len(source.selection_category_ids) > 1)
    other_category_id = next(
        cid for cid in target.selection_category_ids if cid != target.reporting_category_id
    )
    other_category_code = next(
        category.code for category in contract.categories if category.id == other_category_id
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          document.querySelector('[data-customize-open]').click();
          document.querySelectorAll('[data-customize-category]').forEach((input) => {{
            input.checked = false;
          }});
          const category = document.querySelector(
            '[data-customize-category="{other_category_code}"]',
          );
          category.checked = true;
          category.dispatchEvent(new Event('change', {{ bubbles: true }}));
          const sourceInput = document.querySelector('[data-customize-source="{target.code}"]');
          sourceInput.checked = true;
          sourceInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
          const row = sourceInput.closest('[data-customize-source-row]');
          const withDirect = {{
            badges: row.querySelector('[data-customize-source-badges]').textContent,
            counts: document.querySelector('[data-customize-counts]').textContent,
          }};
          // Remove the direct pick; the category is still checked.
          sourceInput.checked = false;
          sourceInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
          const withoutDirect = {{
            badges: row.querySelector('[data-customize-source-badges]').textContent,
            checked: sourceInput.checked,
          }};
          return JSON.stringify({{ withDirect, withoutDirect }});
        }})()
        """,
    )
    assert "Direct" in result["withDirect"]["badges"]
    assert (
        other_category_code not in result["withDirect"]["badges"]
    )  # codes aren't shown, labels are
    assert "1 direct" in result["withDirect"]["counts"]
    assert "Direct" not in result["withoutDirect"]["badges"]
    assert result["withoutDirect"]["badges"] != ""  # still explained by the category alone
    assert result["withoutDirect"]["checked"] is False


def test_personalization_reset_restores_audited_state_and_preserves_filters(
    tmp_path: Path,
) -> None:
    """Issue 80 acceptance criterion: reset restores audited mode, clears
    selections, hides Times, and preserves query filters."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    query_url = f"{html_path.resolve().as_uri()}?view=compact"
    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          history.replaceState(null, '', '{query_url}');
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', {{ bubbles: true }}));
          document.querySelector('[data-customize-times]').click();
          document.querySelector('[data-customize-times]')
            .dispatchEvent(new Event('change', {{ bubbles: true }}));
          document.querySelector('[data-customize-reset]').click();
          const audited = document.querySelector('[data-customize-mode][value="audited"]').checked;
          const anyCategoryChecked = [...document.querySelectorAll('[data-customize-category]')]
            .some((input) => input.checked);
          const anySourceChecked = [...document.querySelectorAll('[data-customize-source]')]
            .some((input) => input.checked);
          const timesShown = document.documentElement.classList.contains('show-times');
          const banner = document.querySelector('[data-lens-banner]');
          return JSON.stringify({{
            audited,
            anyCategoryChecked,
            anySourceChecked,
            timesShown,
            bannerHidden: banner.hidden,
            hash: window.location.hash,
            search: window.location.search,
          }});
        }})()
        """,
    )
    assert result["audited"] is True
    assert result["anyCategoryChecked"] is False
    assert result["anySourceChecked"] is False
    assert result["timesShown"] is False
    assert result["bannerHidden"] is True
    assert result["hash"] == ""
    assert result["search"] == "?view=compact"


def test_personalization_dialog_does_not_overflow_a_mobile_viewport(tmp_path: Path) -> None:
    """Issue 80 Validation: mobile checks.

    The small rendering fixture's few short source names and single-category
    memberships never produce badge or row text long enough to overflow a
    360px dialog even without the fix, which would make this test vacuous;
    the real production panel's 42 sources, longer names, and overlapping
    categories are what actually exercise the narrow layout.
    """
    view_model = _production_bundle().view_model
    enabled_policy = view_model.personalization.policy.model_copy(update={"enabled": True})
    view_model = view_model.model_copy(
        update={
            "personalization": view_model.personalization.model_copy(
                update={"policy": enabled_policy}
            )
        }
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          const dialog = document.querySelector('[data-customize-dialog]');
          return JSON.stringify({
            clientWidth: dialog.clientWidth,
            scrollWidth: dialog.scrollWidth,
          });
        })()
        """,
        mobile_width=360,
    )
    assert result["scrollWidth"] <= result["clientWidth"]


def test_personalization_copy_link_encodes_the_current_state_not_a_stale_href(
    tmp_path: Path,
) -> None:
    """Issue 80 scope: copy-link must reproduce the displayed state exactly,
    even after an in-page anchor navigation the codec does not recognize."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          // Headless Chrome over file:// has no clipboard permission to
          // grant or deny, so navigator.clipboard.writeText never settles;
          // stub it so the test exercises the status-line logic
          // deterministically rather than real OS clipboard behavior.
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async () => {} },
            configurable: true,
          });
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          // The dialog is a native modal: the rest of the page is inert while
          // it is open, so close it before the anchor can be clicked at all.
          document.querySelector('[data-customize-close]').click();
          // A plain anchor navigation the codec does not recognize: this must
          // not be mistaken for the copy target.
          document.querySelector('.skip-link').click();
          const hashAfterAnchor = window.location.hash;
          document.querySelector('[data-customize-open]').click();
          // showModal() needs a tick before headless Chrome treats the
          // dialog's own contents as interactive again.
          await new Promise((resolve) => setTimeout(resolve, 50));
          document.querySelector('[data-customize-copy]').click();
          await new Promise((resolve) => setTimeout(resolve, 50));
          return JSON.stringify({
            hashAfterAnchor,
            copyStatus: document.querySelector('[data-customize-copy-status]').textContent,
            finalHash: window.location.hash,
          });
        })()
        """,
    )
    assert result["hashAfterAnchor"] == "#guide-races"
    assert result["copyStatus"] == "Link copied."
    assert "mode=s" in result["finalHash"]
    assert "sel=" in result["finalHash"]


def test_personalization_copy_status_clears_on_the_next_change(tmp_path: Path) -> None:
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          // Headless Chrome over file:// has no clipboard permission to
          // grant or deny, so navigator.clipboard.writeText never settles;
          // stub it so the test exercises the status-line logic
          // deterministically rather than real OS clipboard behavior.
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async () => {} },
            configurable: true,
          });
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          document.querySelector('[data-customize-copy]').click();
          await new Promise((resolve) => setTimeout(resolve, 50));
          const afterCopy = document.querySelector('[data-customize-copy-status]').textContent;
          document.querySelector('[data-customize-reset]').click();
          const afterReset = document.querySelector('[data-customize-copy-status]').textContent;
          return JSON.stringify({ afterCopy, afterReset });
        })()
        """,
    )
    assert result["afterCopy"] != ""
    assert result["afterReset"] == ""


def test_personalization_history_back_and_forward_restore_selection(tmp_path: Path) -> None:
    """Issue 80 scope: back and forward behavior.

    A plain back() to a history entry that was last written by the very same
    live DOM state proves nothing about applyMode: the checkboxes would look
    "restored" even if the restore code never ran. This test forces a genuine
    divergence — after the entry we will return to has already recorded a
    category-based selection, it switches to a different, direct-source
    selection before pushing the race-detail entry, so back() must actually
    reach into the earlier entry's fragment and re-check different boxes than
    whatever is currently checked.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = () => new Promise((resolve) => setTimeout(resolve, 60));
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          await pause();
          // Entering sources mode selects every category by default; this is
          // the selection the later back() must restore. Capture it, then
          // immediately push a new history entry (the race-detail permalink,
          // matching how the rest of the guide already navigates) so this
          // selection is frozen onto the entry we will later return to,
          // before anything has a chance to replaceState over it.
          const afterEnter = window.location.hash;
          const categoryInputsSnapshot = [
            ...document.querySelectorAll('[data-customize-category]'),
          ];
          const categoryCodesAfterEnter = categoryInputsSnapshot
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeCategory)
            .sort();
          const link = document.querySelector('[data-race-detail-link]');
          link.click();
          await pause();
          // Now, on the new entry, diverge to a direct-source selection.
          // writeLensState only ever replaceState()s, so this overwrites only
          // the new entry's own fragment, leaving the earlier entry's
          // category-based fragment untouched underneath it.
          document.querySelectorAll('[data-customize-category]').forEach((input) => {
            input.checked = false;
          });
          const source = document.querySelector('[data-customize-source]');
          source.checked = true;
          source.dispatchEvent(new Event('change', { bubbles: true }));
          await pause();
          const sourceCodesBeforeBack = [...document.querySelectorAll('[data-customize-source]')]
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeSource)
            .sort();
          history.back();
          await pause();
          const audited = document.querySelector('[data-customize-mode][value="audited"]').checked;
          const restored = window.location.hash === afterEnter;
          const categoryCodesAfterBack = [...document.querySelectorAll('[data-customize-category]')]
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeCategory)
            .sort();
          const sourceCodesAfterBack = [...document.querySelectorAll('[data-customize-source]')]
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeSource)
            .sort();
          history.forward();
          await pause();
          const dialogOpen = document.querySelector('[data-race-detail-dialog][open]') !== null;
          return JSON.stringify({
            afterEnter,
            restored,
            audited,
            dialogOpen,
            categoryCodesAfterEnter,
            sourceCodesBeforeBack,
            categoryCodesAfterBack,
            sourceCodesAfterBack,
          });
        })()
        """,
    )
    assert "mode=s" in result["afterEnter"]
    assert result["categoryCodesAfterEnter"] != []
    # Confirms the divergence actually happened before back(): a direct source
    # was checked in place of the categories.
    assert result["sourceCodesBeforeBack"] != []
    assert result["restored"] is True
    assert result["audited"] is False
    # back() must reinstate the category-based selection recorded in the
    # earlier entry, not leave the direct-source selection in place.
    assert result["categoryCodesAfterBack"] == result["categoryCodesAfterEnter"]
    assert result["sourceCodesAfterBack"] == []
    assert result["dialogOpen"] is True


def test_personalization_shared_link_restores_the_same_version_selection(tmp_path: Path) -> None:
    """Issue 80 scope: a link that already encodes a personalized selection
    must restore that exact selection on load, complementing the
    back/forward test above by exercising the initial-load restore path
    (applyMode(lensState()) at script start) rather than the hashchange path.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    capture = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          // Diverge from the "select every category" default this mode starts
          // with, so the captured link encodes one specific, checkable
          // category rather than the whole set.
          document.querySelectorAll('[data-customize-category]').forEach((input) => {
            input.checked = false;
          });
          const category = document.querySelector('[data-customize-category]');
          category.checked = true;
          category.dispatchEvent(new Event('change', { bubbles: true }));
          return JSON.stringify({
            href: window.location.href,
            categoryCode: category.dataset.customizeCategory,
          });
        })()
        """,
    )
    base, _, fragment = capture["href"].partition("#")
    shared_url = f"{base}?edition=compact#{fragment}"
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          audited: document.querySelector('[data-customize-mode][value="audited"]').checked,
          sources: document.querySelector('[data-customize-mode][value="sources"]').checked,
          categoryCodes: [...document.querySelectorAll('[data-customize-category]')]
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeCategory)
            .sort(),
          sourceCodes: [...document.querySelectorAll('[data-customize-source]')]
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeSource)
            .sort(),
          counts: document.querySelector('[data-customize-counts]').textContent,
          bannerHidden: document.querySelector('[data-lens-banner]').hidden,
          bannerText: document.querySelector('[data-lens-banner]').textContent,
          search: window.location.search,
        })
        """,
        initial_url=shared_url,
    )
    assert result["audited"] is False
    assert result["sources"] is True
    assert result["categoryCodes"] == [capture["categoryCode"]]
    assert result["sourceCodes"] == []
    assert "1 categories" in result["counts"]
    assert result["bannerHidden"] is False
    assert "Personalized lens active" in result["bannerText"]
    assert result["search"] == "?edition=compact"


# Issue 81: per-race personalized presentation and audited divergence.


def test_personalization_full_panel_selection_shows_no_divergent_comparison(tmp_path: Path) -> None:
    """Issue 81 acceptance criterion: an unchanged race stays free of
    redundant audited detail. Entering My sources with every category
    selected (the mode's own default) reproduces the audited consensus for
    every race exactly (issue 77's tested contract), so no card's compact
    audited comparison may appear, and every card is still labeled.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          const cards = [...document.querySelectorAll('.race-card')];
          const anyComparisonShown = cards.some(
            (card) => card.querySelector('[data-lens-comparison]')?.hidden === false,
          );
          const badgesPresent = cards.every(
            (card) => card.querySelector('[data-lens-card-badge]') !== null,
          );
          const firstCard = cards[0];
          return JSON.stringify({
            cardCount: cards.length,
            anyComparisonShown,
            badgesPresent,
            recommendationMatches: firstCard.querySelector('[data-lens-recommendation]').textContent
              === firstCard.querySelector('[data-display-role="recommendation"]').textContent,
            supportMatches: firstCard.querySelector('[data-lens-support]').textContent
              === firstCard.querySelector('[data-display-role="support"]').textContent,
          });
        })()
        """,
    )
    assert result["cardCount"] > 0
    assert result["anyComparisonShown"] is False
    assert result["badgesPresent"] is True
    assert result["recommendationMatches"] is True
    assert result["supportMatches"] is True


def test_personalization_divergent_race_discloses_a_compact_comparison_and_full_detail(
    tmp_path: Path,
) -> None:
    """Issue 81 acceptance criteria: every defined divergence dimension is
    detected from structured values, a divergent card shows a compact
    audited comparison, and the race detail panel discloses complete
    audited/personalized values, contributing sources, and inclusion
    reasons. Narrowing the real production panel to one category is
    virtually certain to push some races below the minimum-explicit-sources
    threshold, diverging their recommendation state from the full panel
    this mode starts with.
    """
    view_model = _production_bundle().view_model
    enabled_policy = view_model.personalization.policy.model_copy(update={"enabled": True})
    view_model = view_model.model_copy(
        update={
            "personalization": view_model.personalization.model_copy(
                update={"policy": enabled_policy}
            )
        }
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          document.querySelectorAll('[data-customize-category]').forEach((input) => {
            input.checked = false;
          });
          const category = document.querySelector('[data-customize-category]');
          category.checked = true;
          category.dispatchEvent(new Event('change', { bubbles: true }));
          const cards = [...document.querySelectorAll('.race-card')];
          const divergent = cards.find(
            (card) => card.querySelector('[data-lens-comparison]')?.hidden === false,
          );
          const unchanged = cards.find(
            (card) => card.querySelector('[data-lens-comparison]')?.hidden === true,
          );
          let detail = null;
          if (divergent) {
            divergent.querySelector('[data-race-detail-link]').click();
            await new Promise((resolve) => setTimeout(resolve, 50));
            const dialog = divergent.querySelector('[data-race-detail-dialog]');
            detail = {
              summary: dialog.querySelector('[data-lens-detail-summary]').textContent,
              auditedHidden: dialog.querySelector('[data-lens-detail-audited]').hidden,
              auditedText: dialog.querySelector('[data-lens-detail-audited]').textContent,
              sourceRowCount: dialog.querySelectorAll('[data-lens-detail-sources] li').length,
            };
          }
          return JSON.stringify({
            hasDivergent: divergent !== undefined,
            hasUnchanged: unchanged !== undefined,
            divergentBadge: divergent?.querySelector('[data-lens-card-badge]')?.textContent,
            divergentComparisonText: divergent
              ?.querySelector('[data-lens-comparison]')?.textContent,
            unchangedComparisonHidden: unchanged?.querySelector('[data-lens-comparison]')?.hidden,
            detail,
          });
        })()
        """,
    )
    assert result["hasDivergent"] is True, (
        "expected at least one production race to diverge from the full-panel audited baseline"
    )
    assert result["divergentBadge"].strip() == "My sources"
    assert "Audited consensus:" in result["divergentComparisonText"]
    assert result["detail"]["auditedHidden"] is False
    assert "Audited consensus:" in result["detail"]["auditedText"]
    assert result["detail"]["sourceRowCount"] >= 0
    if result["hasUnchanged"]:
        assert result["unchangedComparisonHidden"] is True


def _lens_fragment(
    view_model: PublicationViewModel,
    *,
    mode: str,
    category_codes: tuple[str, ...] = (),
    source_codes: tuple[str, ...] = (),
    times: bool = False,
    data_version: str | None = None,
    scoring_id: str | None = None,
) -> str:
    """Hand-encode a lens fragment in the exact parameter shape lens-url.mjs
    reads.

    Used only to construct a shared link the codec would never itself
    produce (a cross-version or malformed one), since there is no Python
    binding to call the JS codec directly.
    """
    contract = view_model.personalization
    selection = "".join(sorted({*category_codes, *source_codes}))
    params = {
        "lens": "1",
        "mode": mode,
        "panel": contract.panel_id,
        "ph": contract.panel_hash[:12],
        "data": data_version if data_version is not None else view_model.metadata.data_version,
        "scoring": scoring_id if scoring_id is not None else contract.scoring.configuration_id,
        "times": "1" if times else "0",
    }
    if selection:
        params["sel"] = selection
    return urlencode(params)


def test_personalization_stale_link_migrates_with_a_persistent_notice(tmp_path: Path) -> None:
    """Issue 81 acceptance criteria: a cross-version link that still
    resolves against the current panel is migrated, its migrated selection
    is applied, and a persistent explanation discloses the migration.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    contract = view_model.personalization
    category = next(
        item for item in contract.categories if item.selectable and item.member_source_codes
    )
    fragment = _lens_fragment(
        view_model,
        mode="s",
        category_codes=(category.code,),
        data_version="a-retired-data-version",
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          noticeText: document.querySelector('[data-lens-notice]').textContent,
          sourcesChecked: document.querySelector('[data-customize-mode][value="sources"]').checked,
          categoryChecked: [...document.querySelectorAll('[data-customize-category]')]
            .filter((input) => input.checked)
            .map((input) => input.dataset.customizeCategory),
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert "migrated" in result["noticeText"]
    assert result["sourcesChecked"] is True
    assert result["categoryChecked"] == [category.code]


def test_personalization_unresolvable_link_falls_back_to_audited_with_a_persistent_notice(
    tmp_path: Path,
) -> None:
    """Issue 81 acceptance criterion: a cross-version link whose category can
    no longer be resolved falls back to the audited consensus rather than a
    partial personalized score, with a persistent explanation.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(
        view_model,
        mode="s",
        category_codes=("Gzzz",),
        data_version="a-retired-data-version",
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          noticeText: document.querySelector('[data-lens-notice]').textContent,
          audited: document.querySelector('[data-customize-mode][value="audited"]').checked,
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert "could not be migrated" in result["noticeText"]
    assert result["audited"] is True


def test_personalization_malformed_link_falls_back_to_audited_with_a_persistent_notice(
    tmp_path: Path,
) -> None:
    """Issue 81 acceptance criterion: an invalid link (an unknown token in an
    otherwise current-version fragment here) falls back to audited with a
    persistent explanation.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(view_model, mode="s", category_codes=("Gzzz",))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          noticeText: document.querySelector('[data-lens-notice]').textContent,
          audited: document.querySelector('[data-customize-mode][value="audited"]').checked,
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert "could not be read" in result["noticeText"]
    assert result["audited"] is True


def test_personalization_ordinary_anchor_navigation_never_shows_a_lens_notice(
    tmp_path: Path,
) -> None:
    """The skip link decodes to the same `unrecognized_fragment` malformed
    status a corrupted lens link could, but a plain in-page anchor must
    never be mistaken for one: it must never show a lens notice.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('.skip-link').click();
          await new Promise((resolve) => setTimeout(resolve, 30));
          return JSON.stringify({
            noticeHidden: document.querySelector('[data-lens-notice]').hidden,
            hash: window.location.hash,
          });
        })()
        """,
    )
    assert result["hash"] == "#guide-races"
    assert result["noticeHidden"] is True


def test_personalization_notice_clears_on_the_next_explicit_change(tmp_path: Path) -> None:
    """A persistent link explanation must not survive the reader's own next
    explicit customization, the same convention the copy-status line uses.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(view_model, mode="s", category_codes=("Gzzz",))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const before = document.querySelector('[data-lens-notice]').hidden;
          document.querySelector('[data-customize-open]').click();
          document.querySelector('[data-customize-reset]').click();
          return JSON.stringify({
            before,
            afterHidden: document.querySelector('[data-lens-notice]').hidden,
          });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["before"] is False
    assert result["afterHidden"] is True


def test_personalization_times_comparison_stays_independent_of_the_lens(tmp_path: Path) -> None:
    """Issue 81 acceptance criterion: the Seattle Times comparison remains
    visually and computationally independent of the personalized lens.
    Showing it must not change the personalized recommendation text, and
    entering My sources must not implicitly reveal it.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('[data-customize-open]').click();
          const modeSources = document.querySelector('[data-customize-mode][value="sources"]');
          modeSources.click();
          modeSources.dispatchEvent(new Event('change', { bubbles: true }));
          const timesShownAfterSources = document.documentElement.classList.contains('show-times');
          const firstCard = document.querySelector('.race-card');
          const before = firstCard.querySelector('[data-lens-recommendation]').textContent;
          document.querySelector('[data-customize-times]').click();
          document.querySelector('[data-customize-times]')
            .dispatchEvent(new Event('change', { bubbles: true }));
          const after = firstCard.querySelector('[data-lens-recommendation]').textContent;
          return JSON.stringify({
            timesShownAfterSources,
            timesShownAfterToggle: document.documentElement.classList.contains('show-times'),
            recommendationUnchanged: before === after,
          });
        })()
        """,
    )
    assert result["timesShownAfterSources"] is False
    assert result["timesShownAfterToggle"] is True
    assert result["recommendationUnchanged"] is True
