from __future__ import annotations

import sys
from collections.abc import Callable
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
)
from election_guide.rendering import (
    build_rendered_guide,
    read_rendering_configuration,
    render_html_document,
    validate_rendered_guide,
)
from election_guide.rendering.models import RenderingValidationReport
from election_guide.rendering.renderer import (
    _detailed_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
    _missing_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_race_core_values,  # pyright: ignore[reportPrivateUsage]
    _pdf_race_display_values,  # pyright: ignore[reportPrivateUsage]
    _render_pdf,  # pyright: ignore[reportPrivateUsage]
    _trim_trailing_blank_pages,  # pyright: ignore[reportPrivateUsage]
    find_chrome,
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
        0.190,
        0.190,
        0.140,
        0.105,
        0.154,
        0.153,
        0.193,
        0.136,
        0.149,
        0.144,
        0.190,
        0.137,
        0.089,
        0.094,
        0.122,
        0.085,
    ],
    "pdf-page-2": [
        0.085,
        0.060,
        0.058,
        0.029,
        0.073,
        0.061,
        0.090,
        0.034,
        0.000,
        0.000,
        0.000,
        0.000,
        0.246,
        0.288,
        0.289,
        0.174,
    ],
    "desktop": [
        0.519,
        0.695,
        0.784,
        0.593,
        0.357,
        0.482,
        0.497,
        0.366,
        0.085,
        0.059,
        0.072,
        0.052,
        0.084,
        0.068,
        0.069,
        0.046,
    ],
    "mobile": [
        0.723,
        0.692,
        0.752,
        0.818,
        0.293,
        0.277,
        0.269,
        0.276,
        0.106,
        0.088,
        0.097,
        0.047,
        0.086,
        0.088,
        0.093,
        0.044,
    ],
}
LINUX_VISUAL_BASELINES = {
    "pdf-page-1": [
        0.188,
        0.190,
        0.137,
        0.103,
        0.150,
        0.152,
        0.189,
        0.136,
        0.145,
        0.141,
        0.187,
        0.137,
        0.086,
        0.093,
        0.122,
        0.085,
    ],
    "pdf-page-2": [
        0.081,
        0.059,
        0.056,
        0.029,
        0.073,
        0.059,
        0.086,
        0.034,
        0.000,
        0.000,
        0.000,
        0.000,
        0.246,
        0.289,
        0.289,
        0.174,
    ],
    "desktop": [
        0.525,
        0.757,
        0.837,
        0.593,
        0.478,
        0.692,
        0.710,
        0.514,
        0.071,
        0.046,
        0.059,
        0.043,
        0.071,
        0.052,
        0.046,
        0.050,
    ],
    "mobile": [
        0.740,
        0.725,
        0.788,
        0.827,
        0.292,
        0.281,
        0.269,
        0.276,
        0.099,
        0.077,
        0.090,
        0.042,
        0.081,
        0.081,
        0.086,
        0.041,
    ],
}
APPROVED_VISUAL_BASELINES_BY_PLATFORM = {
    "darwin": DARWIN_VISUAL_BASELINES,
    "linux": LINUX_VISUAL_BASELINES,
}


def test_html_uses_one_view_model_for_screen_print_filters_and_evidence(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
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
    assert "Consensus among endorsers" in html
    assert "Seattle Times" in html
    assert ">AGREES<" not in html
    assert ">DIFFERENT PICK<" not in html
    assert ">NO PICK<" not in html
    assert f"{view_model.metadata.captured_source_count} represented sources" in html
    assert f"{view_model.metadata.unavailable_source_count} unavailable" in html
    assert "Coverage note:" not in html
    assert "Category representation and support" not in html
    assert 'data-display-role="grade"' not in html
    assert 'class="methodology-panel screen-consensus-key"' in html
    assert 'class="methodology-panel screen-source-categories"' in html
    assert 'class="methodology-panel screen-audit-metadata"' in html
    assert 'class="methodology-panel screen-verification"' in html
    assert configuration.project_url in html
    comparisons = [comparison for race in races for comparison in race.comparisons]
    for comparison in comparisons:
        assert f"comparison-{comparison.voter_tone}" in html
        assert f'class="comparison comparison-{comparison.voter_tone}" role="group"' in html
        assert f'aria-label="{comparison.voter_accessible_label}"' in html
        assert f"<strong>{comparison.voter_label}</strong>" in html
        assert (f"print-times-pick print-times-pick-{comparison.voter_tone}") in html
        assert f">{comparison.print_label}</b>" in html
    assert ".comparison strong { max-width: 72%; margin-left: auto;" in html
    assert html.count('class="method-column"') == 2
    assert ".print-races { display: grid; grid-template-columns: 1fr 1fr;" in html
    assert html.count('class="print-race-column"') == 2
    assert "State Legislature — continued" in html
    assert ".print-race:nth-of-type(even) { background: #f2f6f8; }" in html
    assert "font: 800 20pt/.95 Arial, Helvetica, sans-serif" in html
    assert '<div class="print-guide">' in html
    assert '<div class="print-guide" aria-hidden="true">' not in html
    assert "font: 800 8.9pt/1 Arial, Helvetica, sans-serif" in html
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
    expected_text = " ".join(value_fn(race))
    compound = (
        f"Seattle Times {comparison.voter_label}"
        if value_fn is _detailed_pdf_race_values
        else comparison.print_label
    )

    assert _missing_pdf_race_values([race], expected_text, value_fn) == []

    prefix_collision_text = expected_text.replace(compound, f"{compound}body", 1)
    prefix_collision_missing = _missing_pdf_race_values([race], prefix_collision_text, value_fn)
    assert f"{race.id}: {compound}" in prefix_collision_missing

    wrong_chip_text = expected_text.replace(compound, "Times differs: Wrong pick", 1)
    wrong_chip_missing = _missing_pdf_race_values([race], wrong_chip_text, value_fn)
    assert f"{race.id}: {compound}" in wrong_chip_missing

    if comparison.voter_label == "No":
        not_covered_text = expected_text.replace(compound, "Times: not covered", 1)
        not_covered_missing = _missing_pdf_race_values([race], not_covered_text, value_fn)
        assert f"{race.id}: {compound}" in not_covered_missing

    if badge_label != "NOT COVERED":
        legacy_text = expected_text.replace(
            compound,
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
    assert reader.metadata.title == "Seattle 2026 Primary Endorsement Consensus Guide"
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
        f"{comparison.print_label}</b>"
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
    pdf_text = " ".join(
        " ".join((page.extract_text() or "").split()) for page in PdfReader(rendered.pdf_path).pages
    )
    assert long_label in pdf_text
    assert f"{race.explicit_endorsement_count} endorsers" in pdf_text


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


def test_overflowing_methodology_uses_detailed_fallback(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    view_model.methodology.interpretation_notes = [
        "This canonical interpretation sentence must remain visible in the published methodology. "
        * 180
    ]
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))
    rendered = build_rendered_guide(view_model_path, RENDERING_CONFIG, tmp_path / "rendered")

    assert rendered.validation_report.passed
    assert rendered.validation_report.edition == "concise_plus_detailed"
    assert rendered.detailed_pdf_path is not None
    assert rendered.validation_report.detailed_page_count > 2
    detailed_text = " ".join(
        page.extract_text() or "" for page in PdfReader(rendered.detailed_pdf_path).pages
    )
    assert "This canonical interpretation sentence" in detailed_text


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
    return PublicationViewModel.model_validate(
        view_model.model_copy(update={"sections": sections}).model_dump(mode="json")
    )


def _visual_view_model(view_model: PublicationViewModel) -> PublicationViewModel:
    visual = _dense_view_model(view_model)
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
