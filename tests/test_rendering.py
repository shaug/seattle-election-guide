from __future__ import annotations

import sys
from pathlib import Path
from stat import S_IMODE
from typing import cast

import pytest
from PIL import Image
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter

from election_guide.publication import build_publication_bundle
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering import (
    build_rendered_guide,
    read_rendering_configuration,
    render_html_document,
    validate_rendered_guide,
)
from election_guide.rendering.models import RenderingValidationReport
from election_guide.rendering.renderer import (
    _missing_pdf_race_values,  # pyright: ignore[reportPrivateUsage]
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
        0.139,
        0.125,
        0.063,
        0.039,
        0.090,
        0.076,
        0.122,
        0.068,
        0.086,
        0.072,
        0.116,
        0.069,
        0.038,
        0.037,
        0.069,
        0.043,
    ],
    "pdf-page-2": [
        0.094,
        0.081,
        0.054,
        0.029,
        0.050,
        0.035,
        0.041,
        0.020,
        0.089,
        0.092,
        0.089,
        0.051,
        0.122,
        0.137,
        0.135,
        0.084,
    ],
    "desktop": [
        0.519,
        0.695,
        0.784,
        0.593,
        0.357,
        0.482,
        0.498,
        0.366,
        0.094,
        0.065,
        0.082,
        0.058,
        0.075,
        0.060,
        0.050,
        0.047,
    ],
    "mobile": [
        0.723,
        0.692,
        0.745,
        0.816,
        0.238,
        0.216,
        0.197,
        0.200,
        0.120,
        0.122,
        0.082,
        0.034,
        0.105,
        0.089,
        0.058,
        0.026,
    ],
}
LINUX_VISUAL_BASELINES = {
    "pdf-page-1": [
        0.133,
        0.119,
        0.058,
        0.038,
        0.082,
        0.075,
        0.114,
        0.068,
        0.078,
        0.071,
        0.110,
        0.068,
        0.034,
        0.037,
        0.065,
        0.043,
    ],
    "pdf-page-2": [
        0.090,
        0.073,
        0.052,
        0.029,
        0.047,
        0.035,
        0.038,
        0.020,
        0.088,
        0.092,
        0.086,
        0.051,
        0.122,
        0.137,
        0.135,
        0.084,
    ],
    "desktop": [
        0.525,
        0.757,
        0.837,
        0.593,
        0.478,
        0.692,
        0.712,
        0.514,
        0.073,
        0.046,
        0.056,
        0.050,
        0.072,
        0.050,
        0.054,
        0.043,
    ],
    "mobile": [
        0.740,
        0.725,
        0.784,
        0.825,
        0.234,
        0.213,
        0.197,
        0.200,
        0.116,
        0.110,
        0.072,
        0.034,
        0.101,
        0.081,
        0.047,
        0.026,
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
    assert '<option value="Legislative District 43">Legislative District 43</option>' in html
    assert "JSON.parse(card.dataset.filterTokens)" in html
    assert "View source evidence" in html
    assert "Seattle Times" in html
    assert "Coverage note:" in html
    assert 'class="methodology-panel screen-grade-legend"' in html
    assert 'class="methodology-panel screen-source-categories"' in html
    assert 'class="methodology-panel screen-audit-metadata"' in html
    assert 'class="methodology-panel screen-verification"' in html
    assert configuration.project_url in html


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
    cell = next(
        cell
        for section in view_model.sections
        for race in section.races
        for cell in race.source_cells
        if cell.evidence_url is not None
    )
    cell.evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))


def test_pdf_result_header_cannot_be_masked_by_agreeing_comparison(tmp_path: Path) -> None:
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
            race.grade,
            share,
            race.support_summary,
            "Seattle Times AGREES",
            race.recommendation_label,
            *race.warning_messages,
        )
    )

    missing = _missing_pdf_race_values([race], misleading_text, _pdf_race_display_values)

    assert f"{race.id}: ordered race result header" in missing


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
    view_model = _view_model(tmp_path / "fixture")
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
        cell.evidence_url
        for race in races
        for cell in race.source_cells
        if cell.evidence_url is not None
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
            "Not available",
            'Not available <a href="https://evil.example/phish">More evidence</a>',
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
    row_start = canonical_html.index('<tr class="source-state-')
    row_end = canonical_html.index("</tr>", row_start) + len("</tr>")
    canonical_row = canonical_html[row_start:row_end]
    malicious_duplicate = canonical_row.replace(
        "</tr>", '<td><a href="https://evil.example/phish">Wrong evidence</a></td></tr>'
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

    masked_pdf_html = tmp_path / "masked-pdf.html"
    masked_html_text = rendered.html_path.read_text(encoding="utf-8").replace(
        f"<strong>{race_with_alternative.recommendation_label}</strong>",
        "<strong>Wrong recommendation</strong>",
        1,
    )
    comparison = race_with_alternative.comparisons[0]
    assert comparison.candidate_labels
    masked_html_text = masked_html_text.replace(
        (f"<b>Times: {comparison.badge_label}</b>\n {' / '.join(comparison.candidate_labels)}"),
        f"<b>Times: AGREES</b>\n {race_with_alternative.recommendation_label}",
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
    assert rendered.validation_report.edition == "concise_plus_detailed"
    assert rendered.detailed_pdf_path is not None
    assert rendered.validation_report.detailed_page_count > 2
    assert len(rendered.detailed_page_images) == rendered.validation_report.detailed_page_count
    assert rendered.validation_report.detailed_page_count >= 10
    assert [page.page_number for page in rendered.validation_report.detailed_pages] == list(
        range(1, rendered.validation_report.detailed_page_count + 1)
    )


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
        "no_endorsement_count": example.no_endorsement_count,
        "missing_source_count": example.missing_source_count,
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
