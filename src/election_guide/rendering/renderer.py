"""Render one publication view model to responsive HTML and Chromium PDF."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from PIL import Image, ImageChops
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
from websocket import (  # pyright: ignore[reportUnknownVariableType]
    WebSocket,
    WebSocketException,
    create_connection,  # pyright: ignore[reportUnknownVariableType]
)

from election_guide.publication.models import (
    PublicationRace,
    PublicationSource,
    PublicationViewModel,
)
from election_guide.rendering.models import (
    RenderCheck,
    RenderedPage,
    RenderingConfiguration,
    RenderingValidationReport,
)
from election_guide.serialization import canonical_json_bytes, read_json, read_yaml

TEMPLATE_DIR = Path(__file__).parent / "templates"
LETTER_WIDTH_POINTS = 612.0
LETTER_HEIGHT_POINTS = 792.0


@dataclass(frozen=True)
class RenderedGuide:
    html_path: Path
    pdf_path: Path
    validation_path: Path
    page_images: list[Path]
    screenshots: list[Path]
    validation_report: RenderingValidationReport
    detailed_pdf_path: Path | None
    detailed_page_images: list[Path]


class PrintLayoutError(ValueError):
    """The configured two-page print layout cannot contain its full content."""


def read_rendering_configuration(path: Path) -> RenderingConfiguration:
    """Read the strict Chromium rendering contract."""
    return RenderingConfiguration.model_validate(read_yaml(path))


def render_html_document(
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
) -> str:
    """Render the one HTML document shared by screen and print presentation."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("guide.html.j2")
    stylesheet = (TEMPLATE_DIR / "guide.css").read_text(encoding="utf-8")
    rendered_urls = [
        configuration.project_url,
        *(source.evidence_url for source in view_model.sources),
        *(
            endorser.evidence_url
            for section in view_model.sections
            for race in section.races
            for group in race.endorsement_groups
            for endorser in group.endorsers
        ),
    ]
    for url in rendered_urls:
        _require_web_url(url)
    return template.render(
        guide=view_model,
        config=configuration,
        stylesheet=stylesheet,
        filter_options=_filter_options(view_model),
        concise_warning_labels=_concise_warning_labels,
        screen_share_accessible_label=_screen_share_accessible_label,
        screen_support_summary=_screen_support_summary,
    )


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


def _require_web_url(value: str) -> None:
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError(f"rendered link is not a safe HTTP(S) URL: {value!r}")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"rendered link is not a safe HTTP(S) URL: {value!r}") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError(f"rendered link is not a safe HTTP(S) URL: {value!r}")


def _concise_warning_labels(race: PublicationRace) -> list[str]:
    return ["TOO FEW ENDORSEMENTS"] if race.grade == "Insufficient" else []


def _screen_support_summary(race: PublicationRace) -> str:
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    return f"Based on {race.explicit_endorsement_count} endorsing {noun}"


def _screen_share_accessible_label(race: PublicationRace) -> str:
    share = "not available" if race.percentage_whole is None else race.percentage_label
    return f"Consensus among explicitly endorsing sources: {share}"


def build_rendered_guide(
    view_model_path: Path,
    configuration_path: Path,
    output_dir: Path,
    *,
    chrome_path: Path | None = None,
    pdftoppm_path: Path | None = None,
) -> RenderedGuide:
    """Build and validate a complete HTML/PDF rendering generation."""
    view_model = PublicationViewModel.model_validate(read_json(view_model_path))
    configuration = read_rendering_configuration(configuration_path)
    resolved_chrome = chrome_path or find_chrome()
    resolved_pdftoppm = pdftoppm_path or find_pdftoppm()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("render output path cannot be a symbolic link")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("render output directory must be absent or empty")
    stage: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.render-", dir=output_dir.parent)
    )
    try:
        assert stage is not None
        html_path = stage / configuration.html_filename
        pdf_dir = stage / "pdf"
        pdf_path = pdf_dir / configuration.pdf_filename
        page_dir = pdf_dir / "pages"
        detailed_pdf_path: Path | None = None
        detailed_page_images: list[Path] = []
        screenshot_dir = stage / "screenshots"
        pdf_dir.mkdir()
        page_dir.mkdir()
        screenshot_dir.mkdir()
        html_path.write_text(
            render_html_document(view_model, configuration),
            encoding="utf-8",
            newline="\n",
        )
        fallback = False
        try:
            _validate_print_layout(
                html_path,
                resolved_chrome,
                minimum_font_points=configuration.minimum_print_font_points,
            )
        except PrintLayoutError:
            fallback = True
            _validate_print_layout(
                html_path,
                resolved_chrome,
                edition="compact",
                minimum_font_points=configuration.minimum_print_font_points,
            )
            _validate_print_layout(
                html_path,
                resolved_chrome,
                edition="detailed",
                minimum_font_points=configuration.minimum_print_font_points,
            )
        _render_pdf(html_path, pdf_path, resolved_chrome, edition="compact" if fallback else None)
        _set_pdf_metadata(pdf_path, view_model, configuration)
        page_images = _render_pdf_pages(pdf_path, page_dir, resolved_pdftoppm)
        if fallback:
            detailed_pdf_path = pdf_dir / configuration.detailed_pdf_filename
            detailed_page_dir = pdf_dir / "detailed-pages"
            detailed_page_dir.mkdir()
            _render_pdf(html_path, detailed_pdf_path, resolved_chrome, edition="detailed")
            detailed_page_images = _render_pdf_pages(
                detailed_pdf_path, detailed_page_dir, resolved_pdftoppm
            )
            if _trim_trailing_blank_pages(detailed_pdf_path, detailed_page_images):
                shutil.rmtree(detailed_page_dir)
                detailed_page_dir.mkdir()
                detailed_page_images = _render_pdf_pages(
                    detailed_pdf_path, detailed_page_dir, resolved_pdftoppm
                )
            _set_pdf_metadata(
                detailed_pdf_path,
                view_model,
                configuration,
                title=f"{configuration.title} - Detailed Edition",
            )
        expected_race_count = sum(len(section.races) for section in view_model.sections)
        screenshots = [
            _render_screenshot(
                html_path,
                screenshot_dir / "desktop.png",
                resolved_chrome,
                width=configuration.desktop_width,
                height=configuration.screenshot_height,
                expected_race_count=expected_race_count,
            ),
            _render_screenshot(
                html_path,
                screenshot_dir / "mobile.png",
                resolved_chrome,
                width=configuration.mobile_width,
                height=configuration.screenshot_height,
                expected_race_count=expected_race_count,
            ),
        ]
        validation_report = validate_rendered_guide(
            view_model,
            configuration,
            html_path,
            pdf_path,
            page_images,
            screenshots,
            detailed_pdf_path=detailed_pdf_path,
            detailed_page_images=detailed_page_images,
        )
        validation_path = stage / "rendering_validation_report.json"
        validation_path.write_bytes(canonical_json_bytes(validation_report.model_dump(mode="json")))
        if not validation_report.passed:
            failed = "; ".join(
                f"{check.id}: {check.message}"
                for check in validation_report.checks
                if not check.passed
            )
            raise ValueError(f"rendered guide validation failed: {failed}")
        _set_public_modes(stage)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(stage, output_dir)
        stage = None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    final_pages = [output_dir / "pdf/pages" / path.name for path in page_images]
    final_screenshots = [output_dir / "screenshots" / path.name for path in screenshots]
    final_detailed_pages = [
        output_dir / "pdf/detailed-pages" / path.name for path in detailed_page_images
    ]
    return RenderedGuide(
        html_path=output_dir / configuration.html_filename,
        pdf_path=output_dir / "pdf" / configuration.pdf_filename,
        validation_path=output_dir / "rendering_validation_report.json",
        page_images=final_pages,
        screenshots=final_screenshots,
        validation_report=validation_report,
        detailed_pdf_path=(
            output_dir / "pdf" / configuration.detailed_pdf_filename if fallback else None
        ),
        detailed_page_images=final_detailed_pages,
    )


def validate_rendered_guide(
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
    html_path: Path,
    pdf_path: Path,
    page_images: list[Path],
    screenshots: list[Path],
    *,
    detailed_pdf_path: Path | None = None,
    detailed_page_images: list[Path] | None = None,
) -> RenderingValidationReport:
    """Validate semantic parity, PDF structure, and rendered image safety."""
    detailed_page_images = detailed_page_images or []
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
        comparison_key = (race.id, "comparison")
        expected_accessible_names = [
            comparison.voter_accessible_label for comparison in race.comparisons
        ]
        if parser.display_accessible_names.get(comparison_key, []) != expected_accessible_names:
            mismatched_html_roles.append(f"{race.id}/comparison-accessible-name")
        if parser.display_element_roles.get(comparison_key, []) != [
            "group" for _ in race.comparisons
        ]:
            mismatched_html_roles.append(f"{race.id}/comparison-accessible-role")
        share_key = (race.id, "share")
        if parser.display_accessible_names.get(share_key, []) != [
            _screen_share_accessible_label(race)
        ]:
            mismatched_html_roles.append(f"{race.id}/share-accessible-name")
        if parser.display_element_roles.get(share_key, []) != ["img"]:
            mismatched_html_roles.append(f"{race.id}/share-accessible-role")
    missing_evidence_rows: list[str] = []
    for race in expected_races:
        for group in race.endorsement_groups:
            group_key = (race.id, group.candidate_id)
            expected_group = _normalized_text(
                " ".join(
                    [
                        group.candidate_label,
                        (
                            f"{group.source_count} endorsing source"
                            f"{'s' if group.source_count != 1 else ''}"
                        ),
                        *(
                            " ".join(
                                [
                                    endorser.source_name,
                                    "Co-endorsement" if endorser.co_endorsement else "",
                                ]
                            )
                            for endorser in group.endorsers
                        ),
                    ]
                )
            )
            observed_groups = [
                _normalized_text(" ".join(parts))
                for parts in parser.endorsement_group_text.get(group_key, [])
            ]
            if observed_groups != [expected_group]:
                missing_evidence_rows.append(
                    f"{race.id}/{group.candidate_id}: group heading or rows"
                )
            for endorser in group.endorsers:
                key = (race.id, group.candidate_id, endorser.source_id)
                expected_row = _normalized_text(
                    " ".join(
                        [
                            endorser.source_name,
                            "Co-endorsement" if endorser.co_endorsement else "",
                        ]
                    )
                )
                observed_rows = [
                    _normalized_text(" ".join(parts))
                    for parts in parser.endorsement_text.get(key, [])
                ]
                if observed_rows != [expected_row]:
                    missing_evidence_rows.append(
                        f"{race.id}/{group.candidate_id}/{endorser.source_id}: row values"
                    )
                if parser.endorsement_links.get(key, []) != [{endorser.evidence_url}]:
                    missing_evidence_rows.append(
                        f"{race.id}/{group.candidate_id}/{endorser.source_id}: evidence links"
                    )
    expected_html_links = {
        "#guide-races",
        configuration.project_url,
        *(source.evidence_url for source in view_model.sources),
        *(
            endorser.evidence_url
            for race in expected_races
            for group in race.endorsement_groups
            for endorser in group.endorsers
        ),
    }
    if parser.links != expected_html_links:
        missing_evidence_rows.append("document: unexpected or missing links")
    source_categories = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    contributing_sources = [
        source for source in view_model.sources if source.contribution_status == "contributing"
    ]
    coverage_gap_sources = [
        source for source in view_model.sources if source.contribution_status == "coverage_gap"
    ]
    expected_source_ids = {source.id for source in contributing_sources}
    if set(parser.publication_source_text) != expected_source_ids:
        missing_evidence_rows.append("document: unexpected or missing publication source rows")
    for source in contributing_sources:
        expected_rows = [
            _normalized_text(f"{source.name} {_source_participation_label(source)}"),
            _normalized_text(f"{source.name} {_source_participation_label(source, compact=True)}"),
        ]
        observed_rows = [
            _normalized_text(" ".join(parts))
            for parts in parser.publication_source_text.get(source.id, [])
        ]
        expected_classes = {"source-row", f"source-row-{source.panel_role}"}
        if (
            observed_rows != expected_rows
            or parser.publication_source_links.get(source.id, [])
            != [[source.evidence_url], [source.evidence_url]]
            or parser.publication_source_categories.get(source.id, [])
            != [source.category, source.category]
            or parser.publication_source_heading_categories.get(source.id, [])
            != [source.category, source.category]
            or parser.publication_source_roles.get(source.id, [])
            != [source.panel_role, source.panel_role]
            or parser.publication_source_classes.get(source.id, [])
            != [expected_classes, expected_classes]
            or source.category not in source_categories
        ):
            missing_evidence_rows.append(f"{source.id}: publication source row values")
    expected_coverage_gap_ids = {source.id for source in coverage_gap_sources}
    if set(parser.coverage_gap_text) != expected_coverage_gap_ids:
        missing_evidence_rows.append("document: unexpected or missing coverage-gap rows")
    for source in coverage_gap_sources:
        status_label = _coverage_gap_status_label(source)
        expected_rows = [
            _normalized_text(f"{source.name} {status_label} {source.coverage_gap_note}"),
            _normalized_text(f"{source.name} {status_label}"),
        ]
        observed_rows = [
            _normalized_text(" ".join(parts))
            for parts in parser.coverage_gap_text.get(source.id, [])
        ]
        if (
            observed_rows != expected_rows
            or parser.coverage_gap_links.get(source.id, [])
            != [[source.evidence_url], [source.evidence_url]]
            or parser.coverage_gap_statuses.get(source.id, [])
            != [source.coverage_gap_status, source.coverage_gap_status]
            or parser.coverage_gap_classes.get(source.id, [])
            != [{"coverage-gap-row"}, {"coverage-gap-row"}]
        ):
            missing_evidence_rows.append(f"{source.id}: coverage-gap row values")

    reader = PdfReader(pdf_path)
    pdf_texts = [page.extract_text() or "" for page in reader.pages]
    pdf_text = "\n".join(pdf_texts)
    comparable_pdf_text = _normalized_text(pdf_text).casefold()
    source_page_lines = (
        (reader.pages[1].extract_text(extraction_mode="layout") or "").splitlines()
        if len(reader.pages) > 1
        else []
    )
    primary_value_fn = (
        _pdf_race_core_values if detailed_pdf_path is not None else _pdf_race_display_values
    )
    missing_pdf_values = _missing_pdf_race_values(expected_races, pdf_text, primary_value_fn)
    identity_values = ["August 2026 Primary", configuration.title]
    consensus_source_count = sum(
        source.panel_role == "consensus" for source in contributing_sources
    )
    comparison_source_count = sum(
        source.panel_role == "comparison" for source in contributing_sources
    )
    global_pdf_values = [
        *(section.label for section in view_model.sections),
        f"{view_model.metadata.published_race_count} races",
        f"{view_model.metadata.contributing_source_count} contributing sources",
        f"{view_model.metadata.coverage_gap_count} coverage gaps",
        f"{consensus_source_count} consensus",
        f"{comparison_source_count} Times comparison",
        *(category.label for category in view_model.methodology.source_categories),
        "Overlap and limitations",
        "Verify before voting",
        view_model.methodology.verification_instructions,
        f"Election {view_model.metadata.election_date}",
        f"Built {view_model.metadata.generated_at.date().isoformat()}",
        f"Data {view_model.metadata.data_version}",
        f"Code {view_model.metadata.git_commit[:12]}",
        *(source.name for source in coverage_gap_sources),
        *(_coverage_gap_status_label(source) for source in coverage_gap_sources),
    ]
    missing_pdf_values.extend(
        value
        for value in global_pdf_values
        if _normalized_text(value).casefold() not in comparable_pdf_text
    )
    expected_source_participation = [
        _source_participation_label(source, compact=True) for source in contributing_sources
    ]
    if _pdf_source_participation_labels(source_page_lines) != expected_source_participation:
        missing_pdf_values.append("ordered source participation rows")
    pdf_identity_text = _pdf_text_runs(reader.pages[0]).casefold()
    missing_pdf_values.extend(
        value
        for value in identity_values
        if _normalized_text(value).casefold() not in pdf_identity_text
    )
    pages_are_letter = _pages_are_letter(reader)
    pdf_links = _pdf_links(reader)
    pdf_link_rows = _pdf_link_rows(reader)
    expected_pdf_links = [
        configuration.project_url,
        *(source.evidence_url for source in contributing_sources),
        *(source.evidence_url for source in coverage_gap_sources),
        configuration.project_url,
    ]
    expected_source_link_rows = [
        (source.evidence_url, _normalized_text(source.name))
        for source in [*contributing_sources, *coverage_gap_sources]
    ]
    pdf_links_valid = (
        _web_urls_are_safe(pdf_links)
        and pdf_links == expected_pdf_links
        and pdf_link_rows[1:-1] == expected_source_link_rows
    )
    link_count = len(pdf_links)
    metadata = reader.metadata
    metadata_present = bool(
        metadata
        and metadata.title == configuration.title
        and metadata.author == configuration.author
        and metadata.subject == configuration.subject
    )
    structure_types = _pdf_structure_types(reader)
    tagged_structure_present = {
        "/Document",
        "/H1",
        "/H2",
        "/Art",
        "/P",
    }.issubset(structure_types)
    page_records = [
        _inspect_page_image(index, path).model_copy(
            update={"image_path": Path("pdf/pages") / path.name}
        )
        for index, path in enumerate(page_images, 1)
    ]
    images_nonblank = all(page.ink_fraction > 0.005 for page in page_records)
    safe_edges = all(page.edge_ink_fraction < 0.002 for page in page_records)
    detailed_reader = PdfReader(detailed_pdf_path) if detailed_pdf_path is not None else None
    detailed_texts = (
        [page.extract_text() or "" for page in detailed_reader.pages]
        if detailed_reader is not None
        else []
    )
    detailed_text = "\n".join(detailed_texts)
    missing_detailed_values: list[str] = []
    if detailed_reader is not None:
        missing_detailed_values = _missing_pdf_race_values(
            expected_races, detailed_text, _detailed_pdf_race_values
        )
        detailed_identity_text = _pdf_text_runs(detailed_reader.pages[0]).casefold()
        missing_detailed_values.extend(
            value
            for value in identity_values
            if _normalized_text(value).casefold() not in detailed_identity_text
        )
    detailed_records = [
        _inspect_page_image(index, path).model_copy(
            update={"image_path": Path("pdf/detailed-pages") / path.name}
        )
        for index, path in enumerate(detailed_page_images, 1)
    ]
    detailed_metadata = detailed_reader.metadata if detailed_reader is not None else None
    detailed_links = _pdf_links(detailed_reader) if detailed_reader is not None else []
    expected_detailed_links = {
        configuration.project_url,
        *(source.evidence_url for source in view_model.sources),
    }
    detailed_links_valid = detailed_reader is None or (
        _web_urls_are_safe(detailed_links) and set(detailed_links) == expected_detailed_links
    )
    detailed_valid = detailed_reader is None or (
        len(detailed_reader.pages) > configuration.concise_page_count
        and _pages_are_letter(detailed_reader)
        and all(len(_normalized_text(text)) > 100 for text in detailed_texts)
        and not missing_detailed_values
        and bool(
            detailed_metadata
            and detailed_metadata.title == f"{configuration.title} - Detailed Edition"
            and detailed_metadata.author == configuration.author
            and detailed_metadata.subject == configuration.subject
        )
        and len(detailed_records) == len(detailed_reader.pages)
        and all(record.ink_fraction > 0.005 for record in detailed_records)
        and all(record.edge_ink_fraction < 0.002 for record in detailed_records)
        and detailed_links_valid
    )
    detail_pair_valid = (detailed_reader is None and not detailed_records) or (
        detailed_reader is not None and bool(detailed_records)
    )
    screenshot_sizes: list[tuple[int, int]] = []
    screenshot_ink: list[float] = []
    for path in screenshots:
        with Image.open(path) as image:
            screenshot_sizes.append(image.size)
        screenshot_ink.append(_image_ink_fraction(path))
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
                "Every affirmative endorser appears under its choice with its evidence link."
                if not missing_evidence_rows
                else f"HTML endorsement rows are incomplete: {', '.join(missing_evidence_rows[:5])}"
            ),
        ),
        RenderCheck(
            id="pdf-page-count",
            passed=len(reader.pages) == configuration.concise_page_count,
            message="Concise PDF has exactly two pages.",
        ),
        RenderCheck(
            id="pdf-letter-size",
            passed=pages_are_letter,
            message="Every PDF page uses US Letter portrait dimensions.",
        ),
        RenderCheck(
            id="pdf-selectable-text",
            passed=all(len(_normalized_text(text)) > 100 for text in pdf_texts),
            message="Every PDF page contains substantial selectable text.",
        ),
        RenderCheck(
            id="pdf-display-values",
            passed=not missing_pdf_values,
            message=(
                "PDF text contains every canonical race, recommendation, "
                "consensus share, and count."
                if not missing_pdf_values
                else f"PDF text is missing canonical values: {', '.join(missing_pdf_values[:5])}"
            ),
        ),
        RenderCheck(
            id="pdf-metadata",
            passed=metadata_present,
            message="PDF includes the configured title, author, and subject metadata.",
        ),
        RenderCheck(
            id="pdf-tagged-structure",
            passed=tagged_structure_present,
            message="PDF preserves document, heading, article, and paragraph structure tags.",
        ),
        RenderCheck(
            id="pdf-links",
            passed=pdf_links_valid,
            message="PDF contains exactly the expected safe project links.",
        ),
        RenderCheck(
            id="rendered-pages",
            passed=len(page_records) == configuration.concise_page_count and images_nonblank,
            message="Every expected PDF page renders to a nonblank PNG.",
        ),
        RenderCheck(
            id="safe-print-edges",
            passed=safe_edges,
            message="Rendered content does not touch the outer page safety edge.",
        ),
        RenderCheck(
            id="detailed-fallback",
            passed=detail_pair_valid and detailed_valid,
            message=(
                (
                    "Overflow content is preserved in a selectable, visually safe detailed edition."
                    if detailed_valid
                    else "Detailed edition validation failed; missing values: "
                    + ", ".join(missing_detailed_values[:5])
                )
                if detailed_reader is not None
                else "The complete guide fits the normal concise edition without a fallback."
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
        page_count=len(reader.pages),
        pdf_text_length=len(pdf_text) + len(detailed_text),
        link_count=link_count + len(detailed_links),
        edition="concise_plus_detailed" if detailed_reader else "concise",
        detailed_page_count=len(detailed_reader.pages) if detailed_reader else 0,
        checks=checks,
        pages=page_records,
        detailed_pages=detailed_records,
    )


def find_chrome() -> Path:
    """Resolve a supported local Chrome or Chromium executable."""
    environment_path = os.environ.get("CHROME_PATH")
    candidates = [
        Path(environment_path) if environment_path else None,
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for command in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    raise ValueError("Chrome or Chromium is required; set CHROME_PATH to its executable")


def find_pdftoppm() -> Path:
    """Resolve Poppler PDF rendering for visual inspection."""
    environment_path = os.environ.get("PDFTOPPM_PATH")
    if environment_path:
        candidate = Path(environment_path)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    resolved = shutil.which("pdftoppm")
    if resolved:
        return Path(resolved)
    raise ValueError("pdftoppm is required for rendered-page inspection")


def _render_pdf(
    html_path: Path,
    pdf_path: Path,
    chrome_path: Path,
    *,
    edition: str | None = None,
) -> None:
    profile = Path(tempfile.mkdtemp(prefix="election-guide-chrome-"))
    try:
        _run_chrome(
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
                "--no-pdf-header-footer",
                f"--user-data-dir={profile}",
                f"--print-to-pdf={pdf_path}",
                _edition_url(html_path, edition),
            ],
            pdf_path,
            "PDF rendering",
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _edition_url(html_path: Path, edition: str | None) -> str:
    url = html_path.resolve().as_uri()
    return f"{url}?edition={edition}" if edition is not None else url


def _validate_print_layout(
    html_path: Path,
    chrome_path: Path,
    *,
    minimum_font_points: float,
    edition: str | None = None,
) -> None:
    profile = Path(tempfile.mkdtemp(prefix="election-guide-chrome-"))
    try:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as errors:
            process = subprocess.Popen(
                [
                    str(chrome_path),
                    "--headless=new",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-extensions",
                    "--no-first-run",
                    "--allow-file-access-from-files",
                    f"--user-data-dir={profile}",
                    "--remote-debugging-port=0",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=errors,
            )
            try:
                issues = _inspect_print_layout(
                    process,
                    profile,
                    _edition_url(html_path, edition),
                    minimum_font_points=minimum_font_points,
                    detailed=edition == "detailed",
                )
                if issues:
                    raise PrintLayoutError(
                        f"print layout clips or overlaps content: {', '.join(issues)}"
                    )
            except PrintLayoutError:
                raise
            except (OSError, ValueError, TimeoutError, WebSocketException) as error:
                errors.seek(0)
                detail = errors.read().strip()
                suffix = f": {detail}" if detail else ""
                raise ValueError(
                    f"Chromium print layout validation failed: {error}{suffix}"
                ) from error
            finally:
                _terminate_process(process)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _inspect_print_layout(
    process: subprocess.Popen[bytes],
    profile: Path,
    url: str,
    *,
    minimum_font_points: float,
    detailed: bool,
) -> list[str]:
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
        attached = cdp.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = cast(str, attached["sessionId"])
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 816,
                "height": 1056,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
            session_id=session_id,
        )
        cdp.command("Page.enable", session_id=session_id)
        cdp.command("Page.navigate", {"url": url}, session_id=session_id)
        cdp.wait_event("Page.loadEventFired", session_id=session_id)
        cdp.command(
            "Runtime.evaluate",
            {"expression": "document.fonts.ready", "awaitPromise": True},
            session_id=session_id,
        )
        cdp.command("Emulation.setEmulatedMedia", {"media": "print"}, session_id=session_id)
        cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "new Promise(resolve => requestAnimationFrame("
                    "() => requestAnimationFrame(() => {"
                    "const signature = () => JSON.stringify("
                    "[...document.querySelectorAll('.print-meter, .print-times-pick')]"
                    ".map(element => {"
                    "const rect = element.getBoundingClientRect();"
                    "const style = getComputedStyle(element);"
                    "const paddingTarget = element.querySelector('.print-meter-label') || element;"
                    "const paddingStyle = getComputedStyle(paddingTarget);"
                    "const children = element.classList.contains('print-meter') ? "
                    "[element.querySelector('.print-meter-text')].filter(Boolean) : "
                    "[...element.querySelectorAll(':scope > span')];"
                    "return [rect.left.toFixed(3), rect.top.toFixed(3),"
                    "rect.right.toFixed(3), rect.bottom.toFixed(3),"
                    "rect.width.toFixed(3), rect.height.toFixed(3),"
                    "style.borderTopWidth, style.borderRightWidth,"
                    "style.borderBottomWidth, style.borderLeftWidth,"
                    "paddingStyle.paddingTop, paddingStyle.paddingRight,"
                    "paddingStyle.paddingBottom, paddingStyle.paddingLeft,"
                    "...children.flatMap(child => {"
                    "const childRect = child.getBoundingClientRect();"
                    "return [childRect.left.toFixed(3), childRect.top.toFixed(3),"
                    "childRect.right.toFixed(3), childRect.bottom.toFixed(3),"
                    "childRect.width.toFixed(3), childRect.height.toFixed(3)]; })];"
                    "}));"
                    "window.dispatchEvent(new Event('beforeprint'));"
                    "requestAnimationFrame(() => { const first = signature();"
                    "window.dispatchEvent(new Event('beforeprint'));"
                    "requestAnimationFrame(() => {"
                    "document.documentElement.dataset.printTransitionStable = "
                    "String(first === signature()); resolve(); });"
                    "});"
                    "})))"
                ),
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        inspected = cdp.command(
            "Runtime.evaluate",
            {
                "expression": """
                JSON.stringify((() => {
                  const issues = [];
                  const detailed = __DETAILED__;
                  if (!detailed &&
                      document.documentElement.dataset.printInkCentered !== 'true') {
                    issues.push('print-ink-calibration');
                  }
                  if (!detailed &&
                      document.documentElement.dataset.printTransitionStable !== 'true') {
                    issues.push('print-ink-calibration-repeatability');
                  }
                  const measurementCanvas = document.createElement('canvas');
                  const measurementContext = measurementCanvas.getContext('2d');
                  const inkBounds = element => {
                    if (!measurementContext) return null;
                    const style = getComputedStyle(element);
                    measurementContext.font = [
                      style.fontStyle,
                      style.fontWeight,
                      style.fontSize,
                      style.fontFamily
                    ].join(' ');
                    const text = [...element.childNodes]
                      .filter(node => node.nodeType === Node.TEXT_NODE)
                      .map(node => node.textContent).join('');
                    const metrics = measurementContext.measureText(text);
                    const marker = document.createElement('i');
                    marker.style.cssText = [
                      'display:inline-block', 'width:0', 'height:0', 'overflow:hidden',
                      'margin:0', 'padding:0', 'border:0', 'vertical-align:baseline'
                    ].join(';');
                    element.append(marker);
                    const baseline = marker.getBoundingClientRect().top;
                    marker.remove();
                    if (!Number.isFinite(metrics.actualBoundingBoxAscent) ||
                        !Number.isFinite(metrics.actualBoundingBoxDescent)) return null;
                    return {
                      top: baseline - metrics.actualBoundingBoxAscent,
                      bottom: baseline + metrics.actualBoundingBoxDescent
                    };
                  };
                  const inkImbalance = (container, elements) => {
                    const bounds = elements.map(inkBounds);
                    if (bounds.some(bound => bound === null)) return null;
                    const containerRect = container.getBoundingClientRect();
                    const inkTop = Math.min(...bounds.map(bound => bound.top));
                    const inkBottom = Math.max(...bounds.map(bound => bound.bottom));
                    const topGap = inkTop - containerRect.top;
                    const bottomGap = containerRect.bottom - inkBottom;
                    return topGap - bottomGap;
                  };
                  const selectors = detailed ? [
                    '.screen-guide', '.race-card h3', '.support-line', '.alternative',
                    '.comparison', '.warning', '.methodology-panel'
                  ] : [
                    '.print-races', '.method-summary article', '.source-panel', '.source-row',
                    '.coverage-gap-row',
                    '.method-notes article', '.page-two-footer span', '.print-race-title',
                    '.print-race-result > strong', '.print-race-context > span',
                    '.print-times-pick', '.print-race-notes span'
                  ];
                  for (const selector of selectors) {
                    const elements = [...document.querySelectorAll(selector)];
                    for (const [index, element] of elements.entries()) {
                      if (element.scrollWidth > element.clientWidth + 1 ||
                          element.scrollHeight > element.clientHeight + 1) {
                        issues.push(`${selector}[${index}]`);
                      }
                    }
                  }
                  const visibleRoot = document.querySelector(
                    detailed ? '.screen-guide' : '.print-guide'
                  );
                  if (!visibleRoot || getComputedStyle(visibleRoot).display === 'none' ||
                      visibleRoot.getBoundingClientRect().height < 1) {
                    issues.push('visible-print-root');
                  }
                  const minimumPixels = __MINIMUM_POINTS__ * 96 / 72;
                  if (visibleRoot) {
                    const visibleElements = [...visibleRoot.querySelectorAll('*')];
                    for (const [index, element] of visibleElements.entries()) {
                      const ownText = [...element.childNodes]
                        .filter(node => node.nodeType === Node.TEXT_NODE)
                        .map(node => node.textContent.trim()).join(' ');
                      const style = getComputedStyle(element);
                      if (ownText && style.display !== 'none' && style.visibility !== 'hidden' &&
                          Number.parseFloat(style.fontSize) + .05 < minimumPixels) {
                        issues.push(`font-below-minimum[${index}]`);
                      }
                    }
                  }
                  if (detailed) return issues;
                  const sourcePanel = document.querySelector('.source-panel');
                  const methodNotes = document.querySelector('.method-notes');
                  const sourceColumns = [...document.querySelectorAll('.source-column')];
                  if (!sourcePanel || !methodNotes || sourceColumns.length !== 2) {
                    issues.push('.source-directory-structure');
                  } else {
                    if (sourcePanel.getBoundingClientRect().bottom >
                        methodNotes.getBoundingClientRect().top + 1) {
                      issues.push('.source-panel-notes-overlap');
                    }
                    const sourceCounts = sourceColumns.map(
                      column => column.querySelectorAll('.source-row').length
                    );
                    if (Math.abs(sourceCounts[0] - sourceCounts[1]) > 1) {
                      issues.push('.source-column-balance');
                    }
                  }
                  const raceColumns = [...document.querySelectorAll('.print-race-column')];
                  if (raceColumns.length !== 2) {
                    issues.push('.print-race-columns');
                  } else {
                    const columnBottoms = raceColumns.map((column, index) => {
                      const columnRect = column.getBoundingClientRect();
                      const lastItem = column.lastElementChild;
                      if (!lastItem ||
                          Math.abs(
                            lastItem.getBoundingClientRect().bottom - columnRect.bottom
                          ) > 2) {
                        issues.push(`.print-race-column[${index}]-underfill`);
                      }
                      return columnRect.bottom;
                    });
                    if (Math.abs(columnBottoms[0] - columnBottoms[1]) > 2) {
                      issues.push('.print-race-column-balance');
                    }
                  }
                  const meters = [...document.querySelectorAll('.print-meter')];
                  if (meters.length) {
                    const expectedWidth = meters[0].getBoundingClientRect().width;
                    for (const [index, meter] of meters.entries()) {
                      const meterRect = meter.getBoundingClientRect();
                      const meterStyle = getComputedStyle(meter);
                      const meterLabel = meter.querySelector('.print-meter-label');
                      const result = meter.closest('.print-race-result');
                      const context = result?.nextElementSibling?.classList.contains(
                        'print-race-context'
                      ) ? result.nextElementSibling : null;
                      const support = context?.querySelector('.print-support');
                      if (Math.abs(meterRect.width - expectedWidth) > 1) {
                        issues.push(`.print-meter[${index}]-width`);
                      }
                      if (meterStyle.display !== 'flex' ||
                          meterStyle.alignItems !== 'center' ||
                          meterStyle.justifyContent !== 'flex-end' ||
                          Number.parseFloat(meterStyle.borderTopWidth) < .4 ||
                          (!meter.classList.contains('print-meter-na') &&
                           meterStyle.backgroundImage === 'none')) {
                        issues.push(`.print-meter[${index}]-treatment`);
                      }
                      if (meterLabel) {
                        const meterText = meterLabel.querySelector('.print-meter-text');
                        const imbalance = meterText ? inkImbalance(meter, [meterText]) : null;
                        if (imbalance === null || Math.abs(imbalance) > 1) {
                          const detail = imbalance === null ? 'unmeasurable' :
                            `${imbalance.toFixed(2)}px`;
                          issues.push(`.print-meter[${index}]-label-centering(${detail})`);
                        }
                      }
                      if (support && getComputedStyle(support).display !== 'none' && Math.abs(
                        support.getBoundingClientRect().right - meterRect.right
                      ) > 1) {
                        issues.push(`.print-meter[${index}]-support-alignment`);
                      }
                    }
                  }
                  for (const [index, race] of
                       [...document.querySelectorAll('.print-race')].entries()) {
                    const comparison = race.querySelector('.print-times-pick');
                    if (comparison) {
                      const comparisonStyle = getComputedStyle(comparison);
                      const borderWidths = [
                        comparisonStyle.borderTopWidth,
                        comparisonStyle.borderRightWidth,
                        comparisonStyle.borderBottomWidth,
                        comparisonStyle.borderLeftWidth,
                      ].map(Number.parseFloat);
                      const status = comparison.querySelector('.print-times-status');
                      const choice = comparison.querySelector('.print-times-choice');
                      if (comparisonStyle.display !== 'inline-flex' ||
                          comparisonStyle.alignItems !== 'center' ||
                          Math.abs(Number.parseFloat(comparisonStyle.paddingRight) - 4.8) > .15 ||
                          Math.abs(Number.parseFloat(comparisonStyle.paddingLeft) - 4.8) > .15 ||
                          Math.abs(comparison.getBoundingClientRect().height - 14.4) > .5 ||
                          borderWidths.some(width => Math.abs(width - 1) > .1)) {
                        issues.push(`.print-race[${index}]-comparison-treatment`);
                      }
                      if (status && choice &&
                          Number.parseInt(getComputedStyle(status).fontWeight) <=
                          Number.parseInt(getComputedStyle(choice).fontWeight)) {
                        issues.push(`.print-race[${index}]-comparison-hierarchy`);
                      }
                      const separator = comparison.querySelector('.print-times-separator');
                      const comparisonText = [status, separator, choice].filter(Boolean);
                      const imbalance = inkImbalance(comparison, comparisonText);
                      if (imbalance === null || Math.abs(imbalance) > 1.2) {
                        const detail = imbalance === null ? 'unmeasurable' :
                          `${imbalance.toFixed(2)}px`;
                        issues.push(`.print-race[${index}]-comparison-centering(${detail})`);
                      }
                    }
                    for (const [selector, element] of [
                      ['result', race.querySelector('.print-race-result > strong')],
                      ['comparison', comparison]
                    ]) {
                      if (!element) continue;
                      const style = getComputedStyle(element);
                      const lineHeight = Number.parseFloat(style.lineHeight);
                      const range = document.createRange();
                      range.selectNodeContents(element);
                      if (range.getBoundingClientRect().height > lineHeight * 1.5) {
                        issues.push(`.print-race[${index}]-${selector}-wrap`);
                      }
                    }
                    for (const [selector, element] of [
                      ['result', race.querySelector('.print-race-result > strong')],
                      ['comparison', race.querySelector('.print-times-pick')],
                      ['support', [...race.querySelectorAll('.print-support')].find(
                        item => getComputedStyle(item).display !== 'none'
                      )]
                    ]) {
                      if (!element || getComputedStyle(element).display === 'none') continue;
                      const range = document.createRange();
                      range.selectNodeContents(element);
                      const textRect = range.getBoundingClientRect();
                      const elementRect = element.getBoundingClientRect();
                      if (textRect.left < elementRect.left - 1 ||
                          textRect.right > elementRect.right + 1) {
                        issues.push(`.print-race[${index}]-${selector}-bounds`);
                      }
                      if (selector === 'comparison' &&
                          (textRect.top < elementRect.top - 1 ||
                           textRect.bottom > elementRect.bottom + 1)) {
                        issues.push(`.print-race[${index}]-comparison-vertical-bounds`);
                      }
                    }
                  }
                  const pages = [...document.querySelectorAll('.print-page')];
                  for (const [index, page] of pages.entries()) {
                    const footer = page.querySelector('footer');
                    const selector = index === 0 ? '.print-races' : '.page-two-content';
                    const content = page.querySelector(selector);
                    if (footer && content && content.getBoundingClientRect().bottom >
                        footer.getBoundingClientRect().top + 1) {
                      issues.push(`.print-page[${index}]-footer-overlap`);
                    }
                    if (index === 1 && footer && content &&
                        footer.getBoundingClientRect().top -
                        content.getBoundingClientRect().bottom > 24) {
                      issues.push('.print-page[1]-underfill');
                    }
                  }
                  return issues;
                })())
                """.replace("__DETAILED__", str(detailed).lower()).replace(
                    "__MINIMUM_POINTS__", str(minimum_font_points)
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        result = cast(dict[str, Any], inspected["result"])
        value = cast(object, json.loads(cast(str, result["value"])))
        if not isinstance(value, list):
            raise ValueError("Chrome returned invalid print layout measurements")
        items = cast(list[object], value)
        if not all(isinstance(item, str) for item in items):
            raise ValueError("Chrome returned invalid print layout measurements")
        return cast(list[str], items)
    finally:
        websocket.close()


def _render_screenshot(
    html_path: Path,
    output_path: Path,
    chrome_path: Path,
    *,
    width: int,
    height: int,
    expected_race_count: int,
) -> Path:
    profile = Path(tempfile.mkdtemp(prefix="election-guide-chrome-"))
    try:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as errors:
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
                stderr=errors,
            )
            try:
                _capture_emulated_viewport(
                    process,
                    profile,
                    html_path.resolve().as_uri(),
                    output_path,
                    width=width,
                    height=height,
                    expected_race_count=expected_race_count,
                )
            except (OSError, ValueError, TimeoutError, WebSocketException) as error:
                errors.seek(0)
                detail = errors.read().strip()
                suffix = f": {detail}" if detail else ""
                raise ValueError(f"Chromium screenshot failed: {error}{suffix}") from error
            finally:
                _terminate_process(process)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return output_path


def _capture_emulated_viewport(
    process: subprocess.Popen[bytes],
    profile: Path,
    url: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    expected_race_count: int,
) -> None:
    """Capture an exact CSS viewport through Chrome DevTools Protocol.

    Chrome enforces a 500-pixel minimum window width on macOS. Device emulation
    avoids silently cropping a wider layout when a narrower mobile screenshot is
    requested and uses the same path on Linux CI.
    """
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
        attached = cdp.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = cast(str, attached["sessionId"])
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
                "screenWidth": width,
                "screenHeight": height,
            },
            session_id=session_id,
        )
        cdp.command("Page.enable", session_id=session_id)
        cdp.command("Page.navigate", {"url": url}, session_id=session_id)
        cdp.wait_event("Page.loadEventFired", session_id=session_id)
        evaluated = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "JSON.stringify((() => {"
                    "const guide=document.querySelector('.screen-guide');"
                    "const filter=document.querySelector('#race-filter');"
                    "const cards=[...document.querySelectorAll('[data-publication-race-id]')]"
                    ".filter(card=>getComputedStyle(card).display!=='none'&&"
                    "card.getBoundingClientRect().width>0&&card.getBoundingClientRect().height>0);"
                    "const cardParts=cards.flatMap(card=>[...card.querySelectorAll("
                    "'.screen-race-result,.screen-race-context,.screen-meter,.comparison')]);"
                    "const meters=[...document.querySelectorAll('.screen-meter')];"
                    "return {innerWidth:window.innerWidth,innerHeight:window.innerHeight,"
                    "scrollWidth:document.documentElement.scrollWidth,"
                    "guideVisible:Boolean(guide&&getComputedStyle(guide).display!=='none'&&"
                    "guide.getBoundingClientRect().width>0&&guide.getBoundingClientRect().height>0),"
                    "filterVisible:Boolean(filter&&getComputedStyle(filter).display!=='none'&&"
                    "filter.getBoundingClientRect().width>0&&filter.getBoundingClientRect().height>0),"
                    "visibleRaceCount:cards.length,"
                    "cardOverflow:cardParts.filter(part=>part.scrollWidth>part.clientWidth+1||"
                    "(!part.matches('.screen-race-result,.screen-race-context')&&"
                    "part.scrollHeight>part.clientHeight+1)).map(part=>({"
                    "race:part.closest('[data-publication-race-id]')?.dataset.publicationRaceId,"
                    "className:part.className,width:[part.clientWidth,part.scrollWidth],"
                    "height:[part.clientHeight,part.scrollHeight]})),"
                    "metersRightAligned:meters.every(meter=>Math.abs(meter.getBoundingClientRect().right-"
                    "meter.parentElement.getBoundingClientRect().right)<1),"
                    "disclosures:[...document.querySelectorAll('.guide-notes')].map(details=>{"
                    "const summary=details.querySelector('summary');"
                    "const panel=details.querySelector("
                    "'.methodology-screen,.screen-source-directory');"
                    "const visible=()=>Boolean(details.open&&panel&&"
                    "getComputedStyle(panel).display!=='none'&&"
                    "panel.getBoundingClientRect().height>0);"
                    "const initialOpen=details.open;"
                    "const initialVisible=visible();"
                    "summary?.click();"
                    "const toggledOpen=details.open;"
                    "const toggledVisible=visible();"
                    "const panelOverflow=Boolean(panel&&(panel.scrollWidth>panel.clientWidth+1||"
                    "document.documentElement.scrollWidth>window.innerWidth+1));"
                    "summary?.click();"
                    "return {id:details.id,initialOpen,initialVisible,toggledOpen,toggledVisible,"
                    "panelOverflow,restoredClosed:details.open===false};})};})())"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        result = cast(dict[str, Any], evaluated["result"])
        metrics = cast(dict[str, object], json.loads(cast(str, result["value"])))
        expected_metrics: dict[str, object] = {
            "innerWidth": width,
            "innerHeight": height,
            "scrollWidth": width,
            "guideVisible": True,
            "filterVisible": True,
            "visibleRaceCount": expected_race_count,
            "cardOverflow": [],
            "metersRightAligned": True,
            "disclosures": [
                {
                    "id": disclosure_id,
                    "initialOpen": False,
                    "initialVisible": False,
                    "toggledOpen": True,
                    "toggledVisible": True,
                    "panelOverflow": False,
                    "restoredClosed": True,
                }
                for disclosure_id in ("methodology", "sources")
            ],
        }
        if metrics != expected_metrics:
            raise ValueError(f"responsive layout overflowed its viewport: {metrics}")
        captured = cdp.command(
            "Page.captureScreenshot",
            {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
            session_id=session_id,
        )
        encoded = cast(str, captured["data"])
        output_path.write_bytes(base64.b64decode(encoded, validate=True))
        if _image_ink_fraction(output_path) <= 0.005:
            raise ValueError("responsive screenshot is blank")
    finally:
        websocket.close()


def _wait_for_devtools_endpoint(process: subprocess.Popen[bytes], profile: Path) -> tuple[int, str]:
    endpoint = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError("Chrome exited before exposing its DevTools endpoint")
        if endpoint.is_file():
            parts = endpoint.read_text(encoding="utf-8").splitlines()
            if len(parts) >= 2:
                return int(parts[0]), parts[1]
        time.sleep(0.05)
    raise TimeoutError("Chrome did not expose its DevTools endpoint")


class _CdpSocket:
    """Minimal request/response client for Chrome's DevTools WebSocket."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._pending: list[dict[str, Any]] = []
        self._next_id = 1

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        request: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        if session_id is not None:
            request["sessionId"] = session_id
        self._websocket.send(json.dumps(request, separators=(",", ":")))
        response = self._next_matching(lambda message: message.get("id") == request_id)
        if "error" in response:
            raise ValueError(f"CDP {method} failed: {response['error']}")
        return cast(dict[str, Any], response.get("result", {}))

    def wait_event(self, method: str, *, session_id: str) -> None:
        self._next_matching(
            lambda message: (
                message.get("method") == method and message.get("sessionId") == session_id
            )
        )

    def _next_matching(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        for index, message in enumerate(self._pending):
            if predicate(message):
                return self._pending.pop(index)
        while True:
            message = self._read_message()
            if predicate(message):
                return message
            self._pending.append(message)

    def _read_message(self) -> dict[str, Any]:
        raw = self._websocket.recv()
        if not isinstance(raw, str):
            raise ValueError("Chrome returned a non-text DevTools message")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Chrome returned a non-object DevTools message")
        return cast(dict[str, Any], value)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_chrome(command: list[str], expected_output: Path, label: str) -> None:
    """Wait for a stable browser artifact even when a platform Chrome process lingers."""
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as errors:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            text=True,
        )
        deadline = time.monotonic() + 60
        stable_since: float | None = None
        previous_size = -1
        complete = False
        while time.monotonic() < deadline:
            returncode = process.poll()
            if expected_output.is_file():
                size = expected_output.stat().st_size
                if size > 0 and size == previous_size:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 0.5:
                        complete = True
                        break
                else:
                    previous_size = size
                    stable_since = None
            if returncode is not None:
                complete = expected_output.is_file() and expected_output.stat().st_size > 0
                break
            time.sleep(0.1)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if not complete:
            errors.seek(0)
            detail = errors.read().strip()
            raise ValueError(f"Chromium {label} failed: {detail or 'no artifact was produced'}")


def _set_pdf_metadata(
    pdf_path: Path,
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
    *,
    title: str | None = None,
) -> None:
    reader = PdfReader(pdf_path)
    writer = PdfWriter(clone_from=reader)
    generated = view_model.metadata.generated_at.astimezone(UTC)
    pdf_date = generated.strftime("D:%Y%m%d%H%M%S+00'00'")
    writer.add_metadata(
        {
            "/Title": title or configuration.title,
            "/Author": configuration.author,
            "/Subject": configuration.subject,
            "/Keywords": "Seattle election endorsements voter guide",
            "/CreationDate": pdf_date,
            "/ModDate": pdf_date,
        }
    )
    temporary = pdf_path.with_suffix(".metadata.pdf")
    try:
        with temporary.open("wb") as output:
            writer.write(output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, pdf_path)
    finally:
        temporary.unlink(missing_ok=True)


def _render_pdf_pages(pdf_path: Path, output_dir: Path, pdftoppm_path: Path) -> list[Path]:
    prefix = output_dir / "page"
    result = subprocess.run(
        [str(pdftoppm_path), "-png", "-r", "144", str(pdf_path), str(prefix)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise ValueError(f"PDF page rendering failed: {result.stderr.strip()}")
    pages = sorted(output_dir.glob("page-*.png"), key=_rendered_page_number)
    if not pages:
        raise ValueError("PDF page rendering produced no images")
    return pages


def _rendered_page_number(path: Path) -> int:
    match = re.fullmatch(r"page-(\d+)\.png", path.name)
    if match is None:
        raise ValueError(f"PDF page rendering produced an unexpected filename: {path.name}")
    return int(match.group(1))


def _trim_trailing_blank_pages(pdf_path: Path, page_images: list[Path]) -> int:
    """Remove Chromium-only trailing pages only when pixels and PDF semantics are blank."""
    reader = PdfReader(pdf_path)
    if len(page_images) != len(reader.pages):
        raise ValueError("detailed PDF page images do not match its page count")
    trailing_blank_count = 0
    for page_image, page in zip(reversed(page_images), reversed(reader.pages), strict=True):
        if _image_ink_fraction(page_image) > 0.005:
            break
        if (page.extract_text() or "").strip() or page.get("/Annots"):
            break
        trailing_blank_count += 1
    if not trailing_blank_count:
        return 0
    retained_count = len(reader.pages) - trailing_blank_count
    if retained_count <= 0:
        raise ValueError("detailed PDF contains no nonblank pages")
    writer = PdfWriter()
    for page in reader.pages[:retained_count]:
        writer.add_page(page)
    temporary = pdf_path.with_suffix(".trimmed.pdf")
    try:
        with temporary.open("wb") as output:
            writer.write(output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, pdf_path)
    finally:
        temporary.unlink(missing_ok=True)
    return trailing_blank_count


def _inspect_page_image(page_number: int, path: Path) -> RenderedPage:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        width, height = image.size
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        difference = ImageChops.difference(image, background).convert("L")
        histogram = difference.histogram()
        changed = sum(histogram[8:])
        ink_fraction = changed / (width * height)
        edge_width = max(2, round(min(width, height) * 0.006))
        gray = image.convert("L")
        edge_strips = [
            gray.crop((0, 0, width, edge_width)),
            gray.crop((0, height - edge_width, width, height)),
            gray.crop((0, edge_width, edge_width, height - edge_width)),
            gray.crop((width - edge_width, edge_width, width, height - edge_width)),
        ]
        edge_ink = sum(sum(strip.histogram()[:220]) for strip in edge_strips)
        edge_pixel_count = sum(strip.width * strip.height for strip in edge_strips)
        edge_fraction = edge_ink / edge_pixel_count
    return RenderedPage(
        page_number=page_number,
        image_path=path,
        width=width,
        height=height,
        ink_fraction=ink_fraction,
        edge_ink_fraction=edge_fraction,
    )


def _image_ink_fraction(path: Path) -> float:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        histogram = ImageChops.difference(image, background).convert("L").histogram()
        return sum(histogram[8:]) / (image.width * image.height)


def _pdf_links(reader: PdfReader) -> list[str]:
    links: list[str] = []
    for page in reader.pages:
        annotations = page.get("/Annots", [])
        for annotation_reference in annotations:
            annotation = annotation_reference.get_object()
            action = annotation.get("/A")
            uri = action.get("/URI") if action is not None else None
            if uri is not None:
                links.append(str(uri))
    return links


def _pdf_link_rows(reader: PdfReader) -> list[tuple[str, str]]:
    """Return each linked URI with the visible text inside its annotation rectangle."""
    link_rows: list[tuple[str, str]] = []
    for page in reader.pages:
        annotations: list[tuple[str, tuple[float, float, float, float]]] = []
        for annotation_reference in page.get("/Annots", []):
            annotation = annotation_reference.get_object()
            action = annotation.get("/A")
            uri = action.get("/URI") if action is not None else None
            rectangle = annotation.get("/Rect")
            if uri is not None and rectangle is not None:
                annotations.append(
                    (
                        str(uri),
                        (
                            float(rectangle[0]),
                            float(rectangle[1]),
                            float(rectangle[2]),
                            float(rectangle[3]),
                        ),
                    )
                )

        text_runs = _pdf_positioned_text_runs(page)
        for uri, (left, bottom, right, top) in annotations:
            visible_text = " ".join(
                text
                for x, y, text in text_runs
                if left - 1 <= x <= right + 1 and bottom - 2 <= y <= top + 2
            )
            link_rows.append((uri, _normalized_text(visible_text)))
    return link_rows


def _pdf_positioned_text_runs(page: PageObject) -> list[tuple[float, float, str]]:
    text_runs: list[tuple[float, float, str]] = []

    def collect(
        text: str,
        current_transform: list[float],
        text_transform: list[float],
        *_: object,
    ) -> None:
        if not text.strip():
            return
        x = (
            text_transform[4] * current_transform[0]
            + text_transform[5] * current_transform[2]
            + current_transform[4]
        )
        y = (
            text_transform[4] * current_transform[1]
            + text_transform[5] * current_transform[3]
            + current_transform[5]
        )
        text_runs.append((x, y, text))

    page.extract_text(visitor_text=collect)
    return text_runs


def _pdf_structure_types(reader: PdfReader) -> set[str]:
    root = reader.trailer.get("/Root")
    if isinstance(root, IndirectObject):
        root = root.get_object()
    if not isinstance(root, DictionaryObject):
        return set()
    structure_root = root.get("/StructTreeRoot")
    if structure_root is None:
        return set()

    structure_types: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, IndirectObject):
            item = item.get_object()
        if isinstance(item, ArrayObject):
            for child in item:
                visit(child)
            return
        if not isinstance(item, DictionaryObject):
            return
        role = item.get("/S")
        if role is not None:
            structure_types.add(str(role))
        children = item.get("/K")
        if children is not None:
            visit(children)

    visit(structure_root)
    return structure_types


def _web_urls_are_safe(urls: list[str]) -> bool:
    try:
        for url in urls:
            _require_web_url(url)
    except ValueError:
        return False
    return True


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _pdf_text_runs(page: PageObject) -> str:
    runs: list[str] = []

    def collect(text: str, *_: object) -> None:
        if text.strip():
            runs.append(text)

    page.extract_text(visitor_text=collect)
    return _normalized_text(" ".join(runs))


def _pdf_value_is_present(value: str, segment: str) -> bool:
    normalized = _normalized_text(value).casefold()
    comparable_segment = _normalized_text(segment).casefold()
    if normalized.startswith(("seattle times ", "times ", "times:")):
        compact_times_label = normalized.startswith(("times ", "times:"))
        normalized = normalized.replace("·", " ")
        comparable_segment = comparable_segment.replace("·", " ")
        pattern = r"\s*".join(re.escape(word) for word in normalized.split())
        prefix = r"(?<!seattle\s)(?<!\S)" if compact_times_label else r"(?<!\S)"
        return re.search(prefix + pattern + r"(?=\s|$)", comparable_segment) is not None
    return (
        re.search(r"(?<!\S)" + re.escape(normalized) + r"(?=\s|$)", comparable_segment) is not None
    )


def _source_participation_label(source: PublicationSource, *, compact: bool = False) -> str:
    if compact:
        if source.panel_role == "comparison":
            return f"{source.endorsement_count} picks · {source.split_endorsement_count} split"
        return f"{source.endorsement_count} · {source.split_endorsement_count} split"
    noun = "picks" if source.panel_role == "comparison" else "endorsements"
    return f"{source.endorsement_count} {noun} · {source.split_endorsement_count} split"


def _coverage_gap_status_label(source: PublicationSource) -> str:
    if source.coverage_gap_status == "access_restricted":
        return "Official results inaccessible"
    if source.coverage_gap_status == "not_found":
        return "No published results found"
    raise ValueError(f"source {source.id!r} is missing a coverage-gap status")


def _pdf_source_participation_labels(lines: list[str]) -> list[str]:
    """Read participation labels in PDF DOM order: left column, then right column."""
    if not lines:
        return []
    midpoint = max(len(line) for line in lines) // 2
    pattern = re.compile(r"\d+(?:\s+picks)?\s*·\s*\d+\s+split")
    columns: tuple[list[tuple[int, str]], list[tuple[int, str]]] = ([], [])
    for line_number, line in enumerate(lines):
        for match in pattern.finditer(line):
            column = 0 if match.start() < midpoint else 1
            columns[column].append((line_number, _normalized_text(match.group())))
    return [label for column in columns for _, label in sorted(column)]


def _html_semantic_values(race: PublicationRace) -> dict[str, list[str]]:
    return {
        "race-label": [race.race_label],
        "recommendation": [race.recommendation_label],
        "share": ["N/A" if race.percentage_whole is None else race.percentage_label],
        "support": [_screen_support_summary(race)],
        "comparison": [comparison.print_label for comparison in race.comparisons],
        "insufficient-warning": (
            ["Too few explicit endorsements to assess consensus reliably."]
            if race.grade == "Insufficient"
            else []
        ),
    }


def _pdf_race_display_values(race: PublicationRace) -> list[str]:
    return [
        race.race_label,
        race.recommendation_label,
        "N/A" if race.percentage_whole is None else race.percentage_label,
        race.support_summary,
        *(f"{comparison.print_label} {race.support_summary}" for comparison in race.comparisons),
        *_concise_warning_labels(race),
    ]


def _pdf_race_core_values(race: PublicationRace) -> list[str]:
    compact_support = f"{race.explicit_endorsement_count} endorsers"
    return [
        race.race_label,
        race.recommendation_label,
        "N/A" if race.percentage_whole is None else race.percentage_label,
        compact_support,
        *(f"{comparison.print_label} {compact_support}" for comparison in race.comparisons),
        *(_concise_warning_labels(race)[:1]),
    ]


def _detailed_pdf_race_values(race: PublicationRace) -> list[str]:
    screen_support = _screen_support_summary(race)
    return [
        race.race_label,
        race.recommendation_label,
        "N/A" if race.percentage_whole is None else race.percentage_label,
        screen_support,
        *(f"{comparison.print_label} {screen_support}" for comparison in race.comparisons),
        *(
            ["Too few explicit endorsements to assess consensus reliably."]
            if race.grade == "Insufficient"
            else []
        ),
    ]


def _missing_pdf_race_values(
    races: list[PublicationRace],
    pdf_text: str,
    value_fn: Callable[[PublicationRace], list[str]],
) -> list[str]:
    comparable = pdf_text.casefold()
    positions: list[int | None] = []
    cursor = 0
    for race in races:
        label_pattern = r"\s*".join(
            re.escape(word) for word in _normalized_text(race.race_label).casefold().split()
        )
        match = re.search(label_pattern, comparable[cursor:])
        position = None if match is None else cursor + match.start()
        positions.append(position)
        if match is not None:
            cursor += match.end()
    missing: list[str] = []
    for index, race in enumerate(races):
        position = positions[index]
        if position is None:
            missing.append(f"{race.id}: {race.race_label}")
            continue
        later = [item for item in positions[index + 1 :] if item is not None]
        segment = comparable[position : later[0] if later else len(comparable)]
        header_pattern = r"\s+".join(
            r"\s*".join(re.escape(word) for word in _normalized_text(value).casefold().split())
            for value in (race.race_label, race.recommendation_label)
        )
        if re.match(header_pattern + r"(?=\s|$)", segment) is None:
            missing.append(f"{race.id}: ordered race result header")
        for value in value_fn(race):
            if not _pdf_value_is_present(value, segment):
                missing.append(f"{race.id}: {value}")
        legacy_badges = {
            comparison.badge_label
            for comparison in race.comparisons
            if comparison.badge_label != "NOT COVERED"
        }
        missing.extend(
            f"{race.id}: legacy Seattle Times badge {badge}"
            for badge in sorted(legacy_badges)
            if re.search(
                r"seattle\s*times\s*"
                + r"\s*".join(re.escape(word) for word in badge.casefold().split()),
                segment,
            )
            is not None
        )
    return missing


def _pages_are_letter(reader: PdfReader) -> bool:
    return all(
        abs(float(page.mediabox.width) - LETTER_WIDTH_POINTS) < 1
        and abs(float(page.mediabox.height) - LETTER_HEIGHT_POINTS) < 1
        for page in reader.pages
    )


def _set_public_modes(root: Path) -> None:
    root.chmod(0o755)
    for path in root.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)


class _GuideHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.race_ids: list[str] = []
        self.race_text: dict[str, list[str]] = {}
        self.links: set[str] = set()
        self.endorsement_text: dict[tuple[str, str, str], list[list[str]]] = {}
        self.endorsement_links: dict[tuple[str, str, str], list[set[str]]] = {}
        self.endorsement_group_text: dict[tuple[str, str], list[list[str]]] = {}
        self.display_text: dict[tuple[str, str], list[list[str]]] = {}
        self.display_accessible_names: dict[tuple[str, str], list[str | None]] = {}
        self.display_element_roles: dict[tuple[str, str], list[str | None]] = {}
        self.publication_source_text: dict[str, list[list[str]]] = {}
        self.publication_source_links: dict[str, list[list[str]]] = {}
        self.publication_source_categories: dict[str, list[str | None]] = {}
        self.publication_source_heading_categories: dict[str, list[str | None]] = {}
        self.publication_source_roles: dict[str, list[str | None]] = {}
        self.publication_source_classes: dict[str, list[set[str]]] = {}
        self.coverage_gap_text: dict[str, list[list[str]]] = {}
        self.coverage_gap_links: dict[str, list[list[str]]] = {}
        self.coverage_gap_statuses: dict[str, list[str | None]] = {}
        self.coverage_gap_classes: dict[str, list[set[str]]] = {}
        self._text_parts: list[str] = []
        self._current_race_id: str | None = None
        self._current_endorsement_key: tuple[tuple[str, str, str], int] | None = None
        self._current_endorsement_group_key: tuple[tuple[str, str], int] | None = None
        self._current_display_role: tuple[tuple[str, str], int] | None = None
        self._display_role_tag: str | None = None
        self._current_publication_source: tuple[str, int] | None = None
        self._current_coverage_gap: tuple[str, int] | None = None
        self._current_source_category: str | None = None

    @property
    def text(self) -> str:
        return " ".join(self._text_parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        race_id = attributes.get("data-publication-race-id")
        if race_id is not None:
            self.race_ids.append(race_id)
            self.race_text[race_id] = []
            self._current_race_id = race_id
        source_id = attributes.get("data-source-id")
        candidate_id = attributes.get("data-candidate-id")
        classes = set((attributes.get("class") or "").split())
        heading_category = attributes.get("data-source-category")
        if tag == "h3" and heading_category is not None:
            self._current_source_category = heading_category
        publication_source_id = attributes.get("data-publication-source-id")
        if publication_source_id is not None:
            rows = self.publication_source_text.setdefault(publication_source_id, [])
            links = self.publication_source_links.setdefault(publication_source_id, [])
            rows.append([])
            links.append([])
            self.publication_source_categories.setdefault(publication_source_id, []).append(
                attributes.get("data-source-category")
            )
            self.publication_source_heading_categories.setdefault(publication_source_id, []).append(
                self._current_source_category
            )
            self.publication_source_roles.setdefault(publication_source_id, []).append(
                attributes.get("data-source-role")
            )
            self.publication_source_classes.setdefault(publication_source_id, []).append(classes)
            self._current_publication_source = (publication_source_id, len(rows) - 1)
        coverage_gap_source_id = attributes.get("data-coverage-gap-source-id")
        if coverage_gap_source_id is not None:
            rows = self.coverage_gap_text.setdefault(coverage_gap_source_id, [])
            links = self.coverage_gap_links.setdefault(coverage_gap_source_id, [])
            rows.append([])
            links.append([])
            self.coverage_gap_statuses.setdefault(coverage_gap_source_id, []).append(
                attributes.get("data-coverage-gap-status")
            )
            self.coverage_gap_classes.setdefault(coverage_gap_source_id, []).append(classes)
            self._current_coverage_gap = (coverage_gap_source_id, len(rows) - 1)
        if (
            tag == "section"
            and "endorsement-group" in classes
            and candidate_id is not None
            and self._current_race_id is not None
        ):
            key = (self._current_race_id, candidate_id)
            groups = self.endorsement_group_text.setdefault(key, [])
            groups.append([])
            self._current_endorsement_group_key = (key, len(groups) - 1)
        if (
            tag == "li"
            and source_id is not None
            and candidate_id is not None
            and self._current_race_id is not None
        ):
            key = (self._current_race_id, candidate_id, source_id)
            rows = self.endorsement_text.setdefault(key, [])
            links = self.endorsement_links.setdefault(key, [])
            rows.append([])
            links.append(set())
            self._current_endorsement_key = (key, len(rows) - 1)
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
            if self._current_publication_source is not None:
                source_key, source_index = self._current_publication_source
                self.publication_source_links[source_key][source_index].append(href)
            if self._current_coverage_gap is not None:
                source_key, source_index = self._current_coverage_gap
                self.coverage_gap_links[source_key][source_index].append(href)
            if self._current_endorsement_key is not None:
                key, index = self._current_endorsement_key
                self.endorsement_links[key][index].add(href)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._text_parts.append(data)
            if self._current_race_id is not None:
                self.race_text[self._current_race_id].append(data)
            if self._current_endorsement_key is not None:
                key, index = self._current_endorsement_key
                self.endorsement_text[key][index].append(data)
            if self._current_endorsement_group_key is not None:
                key, index = self._current_endorsement_group_key
                self.endorsement_group_text[key][index].append(data)
            if self._current_display_role is not None:
                key, index = self._current_display_role
                self.display_text[key][index].append(data)
            if self._current_publication_source is not None:
                source_key, source_index = self._current_publication_source
                self.publication_source_text[source_key][source_index].append(data)
            if self._current_coverage_gap is not None:
                source_key, source_index = self._current_coverage_gap
                self.coverage_gap_text[source_key][source_index].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "li":
            self._current_endorsement_key = None
        if tag == "div" and self._current_publication_source is not None:
            self._current_publication_source = None
        if tag == "section" and self._current_endorsement_group_key is not None:
            self._current_endorsement_group_key = None
        if tag == "section" and self._current_coverage_gap is not None:
            self._current_coverage_gap = None
        if tag == self._display_role_tag:
            self._current_display_role = None
            self._display_role_tag = None
        if tag == "article":
            self._current_race_id = None
