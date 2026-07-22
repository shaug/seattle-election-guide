from __future__ import annotations

import sys
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from stat import S_IMODE
from typing import cast

import pytest
from PIL import Image
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

from election_guide.publication import build_publication_bundle
from election_guide.publication.models import (
    PublicationComparison,
    PublicationRace,
    PublicationViewModel,
    SourceCell,
)
from election_guide.rendering import (
    build_rendered_guide,
    read_rendering_configuration,
    render_html_document,
    validate_rendered_guide,
)
from election_guide.rendering.models import RenderingValidationReport
from election_guide.rendering.renderer import (
    PrintLayoutError,
    _detailed_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
    _missing_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_race_core_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_race_display_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_source_participation_labels,  # pyright: ignore[reportPrivateUsage]
    _render_pdf,  # pyright: ignore[reportPrivateUsage]
    _render_pdf_pages,  # pyright: ignore[reportPrivateUsage]
    _render_screenshot,  # pyright: ignore[reportPrivateUsage]
    _set_pdf_metadata,  # pyright: ignore[reportPrivateUsage]
    _trim_trailing_blank_pages,  # pyright: ignore[reportPrivateUsage]
    _validate_print_layout,  # pyright: ignore[reportPrivateUsage]
    find_chrome,
    find_pdftoppm,
)
from election_guide.scoring import score_dataset
from election_guide.serialization import canonical_json_bytes, read_json
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
        0.621,
        0.609,
        0.613,
        0.692,
        0.095,
        0.086,
        0.042,
        0.042,
        0.127,
        0.149,
        0.065,
        0.078,
        0.106,
        0.135,
        0.076,
        0.050,
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
        0.720,
        0.731,
        0.732,
        0.804,
        0.077,
        0.048,
        0.030,
        0.025,
        0.081,
        0.082,
        0.088,
        0.041,
        0.072,
        0.067,
        0.072,
        0.033,
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
    view_model = PublicationViewModel.model_validate(view_model.model_dump(mode="json"))
    configuration = read_rendering_configuration(RENDERING_CONFIG)

    html = render_html_document(view_model, configuration)

    races = [race for section in view_model.sections for race in section.races]
    assert html.count('data-publication-race-id="') == len(races)
    assert all(f'data-publication-race-id="{race.id}"' in html for race in races)
    assert "@media print" in html
    assert "@media (max-width: 720px)" in html
    assert 'id="race-filter"' in html
    assert 'aria-labelledby="race-label-' in html
    assert 'aria-label="View endorsements for ' in html
    assert '<option value="Legislative District 43">Legislative District 43</option>' in html
    assert "JSON.parse(card.dataset.filterTokens)" in html
    assert "View endorsements" in html
    assert "Consensus among explicitly endorsing sources" in html
    assert "Seattle Times" in html
    assert "August 2026 Primary" in html
    assert "Seattle Progressive Endorsement Guide" in html
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
    assert ".screen-meter { display: flex;" in html
    assert "linear-gradient(to left, var(--teal) 0 var(--meter-fill)" in html
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
    assert ".screen-source-columns { display: grid;" in html
    assert ".source-columns { display: grid;" in html
    assert "grid-template-columns: 1fr 1fr;" in html
    assert ".source-row { display: grid;" in html
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
    endorser = next(
        endorser
        for section in view_model.sections
        for race in section.races
        for group in race.endorsement_groups
        for endorser in group.endorsers
    )
    endorser.evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))

    source_view_model = _view_model(tmp_path / "source")
    source_view_model.sources[0].evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(source_view_model, read_rendering_configuration(RENDERING_CONFIG))


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
    row_start = canonical_html.index("<li data-candidate-id=")
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

    group = race_with_alternative.endorsement_groups[0]
    endorser = group.endorsers[0]
    endorser_marker = f'<a href="{endorser.evidence_url}">{endorser.source_name}</a>'
    endorsement_html = tmp_path / "wrong-endorsement-source.html"
    canonical_html = rendered.html_path.read_text(encoding="utf-8")
    assert endorser_marker in canonical_html
    endorsement_html.write_text(
        canonical_html.replace(
            endorser_marker,
            f'<a href="{endorser.evidence_url}">Wrong organization</a>',
            1,
        ),
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

    group_heading = (
        f"<h4>{group.candidate_label}\n"
        f"                    <span>{group.source_count} endorsing "
        f"source{'s' if group.source_count != 1 else ''}</span>"
    )
    assert group_heading in canonical_html
    for index, wrong_heading in enumerate(
        (
            group_heading.replace(group.candidate_label, "Wrong candidate", 1),
            group_heading.replace(str(group.source_count), "999", 1),
        )
    ):
        wrong_group_html = tmp_path / f"wrong-endorsement-group-{index}.html"
        wrong_group_html.write_text(
            canonical_html.replace(group_heading, wrong_heading, 1), encoding="utf-8"
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
    unavailable_view_model = PublicationViewModel.model_validate(
        unavailable_view_model.model_dump(mode="json")
    )
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
    view_model = PublicationViewModel.model_validate(view_model.model_dump(mode="json"))
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
    return PublicationViewModel.model_validate(
        view_model.model_copy(update={"sections": sections, "sources": sources}).model_dump(
            mode="json"
        )
    )


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
    return PublicationViewModel.model_validate(visual.model_dump(mode="json"))


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
