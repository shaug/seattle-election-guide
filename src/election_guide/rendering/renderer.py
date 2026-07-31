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
from datetime import UTC, date
from fractions import Fraction
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
    PublicationChoiceEndorsements,
    PublicationComparison,
    PublicationRace,
    PublicationSource,
    PublicationViewModel,
    SourceCell,
)
from election_guide.publication.personalization import (
    PersonalizationCell,
    PersonalizationRace,
    PersonalizationSource,
)
from election_guide.rendering.models import (
    RenderCheck,
    RenderedPage,
    RenderingConfiguration,
    RenderingValidationReport,
)
from election_guide.rendering.shell import (
    close_icon_svg,
    election_names,
    page_title,
    print_footer_audit_html,
    share_icon_svg,
    site_band_html,
    site_footer_audit_html,
    site_footer_band_html,
    site_head_links_html,
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


@dataclass(frozen=True)
class ComparisonCellView:
    signal: str
    kind: str
    choice_labels: tuple[str, ...]
    leading_pick_ids: tuple[str, ...]
    share: str | None = None
    explicit_source_count: int | None = None
    agreement: str = "neutral"


@dataclass(frozen=True)
class ComparisonRowView:
    race_id: str
    race_label: str
    cells: tuple[ComparisonCellView, ...]
    differs: bool


@dataclass(frozen=True)
class ComparisonSectionView:
    section_id: str
    section_label: str
    rows: tuple[ComparisonRowView, ...]


class PrintLayoutError(ValueError):
    """The configured two-page print layout cannot contain its full content."""


def read_rendering_configuration(path: Path) -> RenderingConfiguration:
    """Read the strict Chromium rendering contract."""
    return RenderingConfiguration.model_validate(read_yaml(path))


def _template_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _personalization_lookup_context(view_model: PublicationViewModel) -> dict[str, Any]:
    """Derived views over the personalization contract shared by every page that
    renders it (the guide and the standalone sources page): a code -> identity
    lookup distinct from source_by_id's id keying, category labels for a
    multi-category source's "also in" tag, and the contract as a plain dict for
    Jinja's `tojson` filter, which only accepts JSON-native values."""
    return {
        "source_by_id": {source.id: source for source in view_model.sources},
        "personalization_source_by_code": {
            source.code: source for source in view_model.personalization.sources
        },
        "category_label_by_id": {
            category.id: category.label for category in view_model.personalization.categories
        },
        "lens_personalization": view_model.personalization.model_dump(mode="json"),
    }


def render_html_document(
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
) -> str:
    """Render the one HTML document shared by screen and print presentation."""
    environment = _template_environment()
    template = environment.get_template("guide.html.j2")
    # base.css carries the design tokens and accessibility utility classes (the
    # skip link, visually-hidden) shared with the site-wide About page in
    # hosting/pages.py, so both read the one file rather than hand-duplicating it.
    stylesheet = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8") + (
        TEMPLATE_DIR / "guide.css"
    ).read_text(encoding="utf-8")
    # The fragment codec ships from its single source; the page inlines it verbatim
    # inside a module script so the guide stays one self-contained file.
    lens_url_script = (TEMPLATE_DIR / "lens-url.mjs").read_text(encoding="utf-8")
    # The scoring engine, migration resolver, and divergence comparison are
    # only ever needed once a lens release enables the policy; the template
    # inlines each only inside that gate, so a disabled release's page is
    # unaffected.
    lens_score_script = (TEMPLATE_DIR / "lens-score.mjs").read_text(encoding="utf-8")
    lens_migrate_script = (TEMPLATE_DIR / "lens-migrate.mjs").read_text(encoding="utf-8")
    lens_divergence_script = (TEMPLATE_DIR / "lens-divergence.mjs").read_text(encoding="utf-8")
    # H31: recomputes the Times comparison tone/verb against the displayed
    # (personalized) result while a lens is active.
    lens_comparison_script = (TEMPLATE_DIR / "lens-comparison.mjs").read_text(encoding="utf-8")
    # Shared with the About page in hosting/pages.py so the native-share/
    # clipboard/execCommand fallback policy has exactly one implementation.
    share_link_script = (TEMPLATE_DIR / "share-link.mjs").read_text(encoding="utf-8")
    rendered_urls = [
        configuration.project_url,
        *(source.evidence_url for source in view_model.sources),
        *(
            cell.evidence_url
            for section in view_model.sections
            for race in section.races
            for cell in race.source_cells
            if cell.evidence_url is not None
        ),
    ]
    for url in rendered_urls:
        _require_web_url(url)
    source_category_label_by_key = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    source_cells_by_race_id = {
        race.id: {cell.source_id: cell for cell in race.source_cells}
        for section in view_model.sections
        for race in section.races
    }
    guide_path = f"/e/{view_model.metadata.election_id}/"
    sources_page_url = f"{configuration.public_site_url}{guide_path}sources/"
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(election=election_display_name)
    election_date_display = display_date(view_model.metadata.election_date)
    data_updated_date, site_updated_date = _footer_update_dates(view_model)
    print_footer_audit = print_footer_audit_html(
        data_updated_date=data_updated_date,
        site_updated_date=site_updated_date,
        git_commit=view_model.metadata.git_commit,
        project_url=configuration.project_url,
    )
    return template.render(
        **_personalization_lookup_context(view_model),
        guide=view_model,
        config=configuration,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        lens_url_script=lens_url_script,
        lens_score_script=lens_score_script,
        lens_migrate_script=lens_migrate_script,
        lens_divergence_script=lens_divergence_script,
        lens_comparison_script=lens_comparison_script,
        share_link_script=share_link_script,
        race_share_icon=share_icon_svg(),
        race_close_icon=close_icon_svg(),
        site_band=site_band_html(
            guide_href=guide_path,
            sources_href=sources_page_url,
            compare_href=(
                f"{guide_path}compare/" if view_model.comparisons.policy.enabled else None
            ),
            current="endorsements",
            sources_link_data_attribute=True,
        ),
        site_head_links=site_head_links_html(configuration.public_site_url),
        election_date_display=election_date_display,
        election_day_kicker=_election_day_kicker(view_model.metadata.election_date),
        site_footer_band=_election_footer_band(
            view_model,
            project_url=configuration.project_url,
            guide_path=guide_path,
            pdf_href=configuration.pdf_filename,
        ),
        site_footer_audit=print_footer_audit,
        filter_options=_filter_options(view_model),
        source_category_label_by_key=source_category_label_by_key,
        source_cells_by_race_id=source_cells_by_race_id,
        concise_warning_labels=_concise_warning_labels,
        has_no_majority=_has_no_majority,
        screen_share_accessible_label=_screen_share_accessible_label,
        screen_support_summary=_screen_support_summary,
        screen_support_summary_compact=_screen_support_summary_compact,
        race_detail_candidate_choices=_race_detail_candidate_choices,
        comparison_candidate_cells=_comparison_candidate_cells,
        race_detail_accessible_summary=_race_detail_accessible_summary,
        race_detail_support_summary=_race_detail_support_summary,
        source_cell_group=_source_cell_group,
        source_cell_group_count=_source_cell_group_count,
        source_cell_group_label=_source_cell_group_label,
        source_cell_detail_label=_source_cell_detail_label,
        source_cell_group_keys=("no_endorsement", "unverified"),
    )


def render_sources_document(
    view_model: PublicationViewModel,
    *,
    public_site_url: str,
    project_url: str | None = None,
    pdf_filename: str | None = None,
) -> str:
    """Render the standalone per-election sources/customization page (issue 107).

    Purely a selection editor: it reads a selection from its own incoming URL
    fragment and writes one back on Save, but never scores anything, so it
    inlines only the fragment codec, not the scoring engine the guide needs.
    `project_url` and `pdf_filename` feed the shared footer (item L55): a
    caller that omits `project_url` gets no footer band or audit line at
    all (both need it), and one that omits `pdf_filename` gets a footer
    without a Printable PDF action, exactly like the shared footer's own
    general fallback behavior. Every real caller (`hosting/pages.py`)
    supplies `project_url`, so the page always renders its footer in
    production; this only matters for a caller (e.g. a test) that renders
    the page without it.
    """
    environment = _template_environment()
    template = environment.get_template("sources.html.j2")
    stylesheet = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8") + (
        TEMPLATE_DIR / "guide.css"
    ).read_text(encoding="utf-8")
    lens_url_script = (TEMPLATE_DIR / "lens-url.mjs").read_text(encoding="utf-8")
    share_link_script = (TEMPLATE_DIR / "share-link.mjs").read_text(encoding="utf-8")
    guide_path = f"/e/{view_model.metadata.election_id}/"
    pdf_href = f"{guide_path}{pdf_filename}" if pdf_filename is not None else None
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(page="Sources", election=election_display_name)
    return template.render(
        **_personalization_lookup_context(view_model),
        guide=view_model,
        public_site_url=public_site_url,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        lens_url_script=lens_url_script,
        share_link_script=share_link_script,
        site_band=site_band_html(
            guide_href=guide_path,
            sources_href=f"{guide_path}sources/",
            compare_href=(
                f"{guide_path}compare/" if view_model.comparisons.policy.enabled else None
            ),
            current="sources",
        ),
        site_head_links=site_head_links_html(public_site_url),
        site_footer_band=_election_footer_band(
            view_model,
            project_url=project_url,
            guide_path=guide_path,
            pdf_href=pdf_href,
        ),
    )


def render_comparison_document(
    view_model: PublicationViewModel,
    *,
    public_site_url: str,
    project_url: str | None = None,
    pdf_filename: str | None = None,
) -> str:
    """Render the policy-gated, no-JavaScript comparison baseline."""
    if not view_model.comparisons.policy.enabled:
        raise ValueError("comparison page cannot render while its release policy is disabled")

    environment = _template_environment()
    template = environment.get_template("compare.html.j2")
    stylesheet = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8") + (
        TEMPLATE_DIR / "compare.css"
    ).read_text(encoding="utf-8")
    share_link_script = (TEMPLATE_DIR / "share-link.mjs").read_text(encoding="utf-8")
    compare_url_script = (TEMPLATE_DIR / "compare-url.mjs").read_text(encoding="utf-8")
    lens_score_script = (TEMPLATE_DIR / "lens-score.mjs").read_text(encoding="utf-8")
    compare_signals_script = (
        (TEMPLATE_DIR / "compare-signals.mjs")
        .read_text(encoding="utf-8")
        .replace("import { scoreRace } from './lens-score.mjs';\n", "")
    )
    compare_client_script = (TEMPLATE_DIR / "compare-client.mjs").read_text(encoding="utf-8")
    guide_path = f"/e/{view_model.metadata.election_id}/"
    pdf_href = f"{guide_path}{pdf_filename}" if pdf_filename is not None else None
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(page="Compare sources", election=election_display_name)
    source_names = {source.id: source.name for source in view_model.sources}
    source_labels = {
        source.code: source_names[source.id] for source in view_model.personalization.sources
    }
    race_by_id = {race.id: race for section in view_model.sections for race in section.races}
    comparison_payload = {
        "schema_version": "1.0",
        "data_version": view_model.metadata.data_version,
        "default_columns": ["gall", "strn", "stim"],
        "personalization": view_model.personalization.model_dump(mode="json"),
        "comparisons": view_model.comparisons.model_dump(mode="json"),
        "source_labels": source_labels,
        "contested_race_ids": [
            display.race_id
            for display in view_model.comparisons.display_index
            if race_by_id[display.race_id].is_contested
        ],
    }
    preset_fragments = [
        (
            "The Stranger and The Times",
            _comparison_fragment(view_model, ["gall", "strn", "stim"]),
        ),
        (
            "Labor and environment",
            _comparison_fragment(view_model, ["gall", "Glab", "Genv"]),
        ),
        (
            "The Urbanist",
            _comparison_fragment(view_model, ["gall", "urbn"]),
        ),
    ]
    comparison_sections = _comparison_sections(view_model)
    return template.render(
        guide=view_model,
        public_site_url=public_site_url,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        share_link_script=share_link_script,
        compare_url_script=compare_url_script,
        lens_score_script=lens_score_script,
        compare_signals_script=compare_signals_script,
        compare_client_script=compare_client_script,
        site_band=site_band_html(
            guide_href=guide_path,
            compare_href=f"{guide_path}compare/",
            sources_href=f"{guide_path}sources/",
            current="compare",
        ),
        site_head_links=site_head_links_html(public_site_url),
        site_footer_band=_election_footer_band(
            view_model,
            project_url=project_url,
            guide_path=guide_path,
            pdf_href=pdf_href,
        ),
        comparison_sections=comparison_sections,
        comparison_race_count=sum(len(section.rows) for section in comparison_sections),
        comparison_differ_count=sum(
            row.differs for section in comparison_sections for row in section.rows
        ),
        comparison_payload=comparison_payload,
        comparison_source_labels=source_labels,
        comparison_presets=preset_fragments,
        comparison_percentage_label=comparison_percentage_label,
    )


def _comparison_fragment(view_model: PublicationViewModel, columns: list[str]) -> str:
    """Build a static preset fragment in the canonical compare-codec order."""
    from urllib.parse import urlencode

    parameters = [
        ("cmp", "1"),
        ("cols", "".join(columns)),
        ("panel", view_model.personalization.panel_id),
        ("ph", view_model.personalization.panel_hash[:12]),
        ("data", view_model.metadata.data_version),
        ("scoring", view_model.personalization.scoring.configuration_id),
    ]
    return urlencode(parameters)


def _comparison_sections(view_model: PublicationViewModel) -> tuple[ComparisonSectionView, ...]:
    personalization_races = {race.race_id: race for race in view_model.personalization.races}
    sources = {source.id: source for source in view_model.personalization.sources}
    try:
        stranger = sources["the-stranger"]
        times = sources["seattle-times-editorial-board"]
    except KeyError as error:
        raise ValueError(f"comparison default source is unavailable: {error.args[0]}") from error

    grouped: list[ComparisonSectionView] = []
    current_section_id: str | None = None
    current_section_label = ""
    rows: list[ComparisonRowView] = []
    for display in view_model.comparisons.display_index:
        if display.section_id != current_section_id:
            if current_section_id is not None:
                grouped.append(
                    ComparisonSectionView(
                        section_id=current_section_id,
                        section_label=current_section_label,
                        rows=tuple(rows),
                    )
                )
            current_section_id = display.section_id
            current_section_label = display.section_label
            rows = []

        race = personalization_races[display.race_id]
        labels = display.candidate_names or display.measure_response_labels
        baseline = ComparisonCellView(
            signal="gall",
            kind="baseline",
            choice_labels=tuple(labels[pick_id] for pick_id in display.baseline.leading_pick_ids),
            leading_pick_ids=tuple(display.baseline.leading_pick_ids),
            share=display.baseline.share,
            explicit_source_count=display.baseline.explicit_source_count,
            agreement="baseline",
        )
        stranger_cell = _comparison_direct_cell(stranger, race, labels, baseline)
        times_cell = _comparison_direct_cell(times, race, labels, baseline)
        cells = (baseline, stranger_cell, times_cell)
        rows.append(
            ComparisonRowView(
                race_id=display.race_id,
                race_label=display.race_label,
                cells=cells,
                differs=_comparison_row_differs(cells),
            )
        )
    if current_section_id is not None:
        grouped.append(
            ComparisonSectionView(
                section_id=current_section_id,
                section_label=current_section_label,
                rows=tuple(rows),
            )
        )
    return tuple(grouped)


def _comparison_direct_cell(
    source: PersonalizationSource,
    race: PersonalizationRace,
    labels: dict[str, str],
    baseline: ComparisonCellView,
) -> ComparisonCellView:
    if source.code not in race.eligible_source_codes:
        return ComparisonCellView(
            signal=source.code,
            kind="outside_scope",
            choice_labels=(),
            leading_pick_ids=(),
        )

    cells = {cell.source_code: cell for cell in race.cells}
    published: PersonalizationCell = cells[source.code]
    if published.state not in {"endorsement", "multi_endorsement"}:
        return ComparisonCellView(
            signal=source.code,
            kind="blank",
            choice_labels=(),
            leading_pick_ids=(),
        )
    leading_pick_ids = tuple(
        candidate_id
        for candidate_id in race.candidate_order
        if candidate_id in published.allocation
    )
    return ComparisonCellView(
        signal=source.code,
        kind="comparison" if source.panel_role == "comparison" else "direct",
        choice_labels=tuple(labels[candidate_id] for candidate_id in leading_pick_ids),
        leading_pick_ids=leading_pick_ids,
        agreement=("agree" if set(leading_pick_ids) & set(baseline.leading_pick_ids) else "differ"),
    )


def _comparison_row_differs(cells: tuple[ComparisonCellView, ...]) -> bool:
    data_cells = [set(cell.leading_pick_ids) for cell in cells if cell.leading_pick_ids]
    return any(
        left.isdisjoint(right)
        for index, left in enumerate(data_cells)
        for right in data_cells[index + 1 :]
    )


def comparison_percentage_label(value: str | None) -> str:
    if value is None:
        return ""
    percentage = Fraction(value) * 100
    if percentage.denominator == 1:
        return f"{percentage.numerator}%"
    return f"{float(percentage):.1f}%"


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


def display_date(iso_date: str) -> str:
    """Human display form ("August 4, 2026") for an ISO date string.

    Reader-facing surfaces use this form; data files and version identifiers
    keep ISO dates.
    """
    parsed = date.fromisoformat(iso_date)
    return f"{parsed:%B} {parsed.day}, {parsed.year}"


def _footer_update_dates(view_model: PublicationViewModel) -> tuple[str, str]:
    data_updated_at = view_model.metadata.data_as_of or view_model.metadata.generated_at
    return (
        data_updated_at.date().isoformat(),
        view_model.metadata.generated_at.date().isoformat(),
    )


def _election_footer_band(
    view_model: PublicationViewModel,
    *,
    project_url: str | None,
    guide_path: str,
    pdf_href: str | None,
) -> str | None:
    """Compose election-page provenance once for Guide, Sources, and Compare."""
    if project_url is None:
        return None
    data_updated_date, site_updated_date = _footer_update_dates(view_model)
    audit_html = site_footer_audit_html(
        data_updated_date=data_updated_date,
        site_updated_date=site_updated_date,
        data_version=view_model.metadata.data_version,
        git_commit=view_model.metadata.git_commit,
        project_url=project_url,
        data_href=f"{guide_path}release-manifest.json",
        source_panel_id=view_model.metadata.source_panel_id,
        source_panel_hash=view_model.metadata.source_panel_hash,
    )
    return site_footer_band_html(
        project_url=project_url,
        audit_html=audit_html,
        pdf_href=pdf_href,
    )


def _election_day_kicker(iso_date: str) -> str:
    """The guide hero's kicker (UI polish round 4, item L54): the exact
    election day, templated per election ("ELECTION DAY · AUGUST 4"). The
    hero h1 already states the month and year, so the kicker states only the
    day at a coarser precision, once each."""
    parsed = date.fromisoformat(iso_date)
    return f"ELECTION DAY · {parsed:%B} {parsed.day}".upper()


def _concise_warning_labels(race: PublicationRace) -> list[str]:
    return ["TOO FEW ENDORSEMENTS"] if race.grade == "Insufficient" else []


def _screen_support_summary(race: PublicationRace) -> str:
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    return f"Based on {race.explicit_endorsement_count} endorsing {noun}"


def _screen_support_summary_compact(race: PublicationRace) -> str:
    """H34: the compact-mode caption drops the sentence, matching how the
    print edition's own full/compact captions already differ."""
    return f"{race.explicit_endorsement_count} sources"


def _screen_comparison_label(comparison: PublicationComparison) -> str:
    """H37: "Times agrees" renders the verb alone — the choice is by
    definition the headline name directly above it — while every other
    status keeps the full "status · choice" compound. Shared by the screen
    macro's semantic-parity expectations and the detailed edition's PDF
    validator, both of which mirror this same screen markup."""
    return (
        comparison.print_status_label if comparison.status == "agrees" else comparison.print_label
    )


def _candidate_endorsement_groups(
    race: PublicationRace,
) -> list[PublicationChoiceEndorsements]:
    leaders = set(race.support_leader_candidate_ids)
    return sorted(
        race.endorsement_groups,
        key=lambda group: (
            -group.source_count,
            group.candidate_id not in leaders,
            group.candidate_label.casefold(),
            group.candidate_id,
        ),
    )


def _comparison_candidate_cells(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
    candidate_id: str,
) -> list[SourceCell]:
    return [
        cell
        for cell in race.source_cells
        if sources[cell.source_id].panel_role == "comparison"
        and cell.state in {"endorsement", "multi_endorsement"}
        and candidate_id in cell.candidate_ids
    ]


def _race_detail_candidate_choices(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
) -> list[tuple[str, str, PublicationChoiceEndorsements | None]]:
    endorsement_groups = _candidate_endorsement_groups(race)
    choices: list[tuple[str, str, PublicationChoiceEndorsements | None]] = [
        (group.candidate_id, group.candidate_label, group) for group in endorsement_groups
    ]
    contributing_candidate_ids = {group.candidate_id for group in endorsement_groups}
    comparison_only_labels: dict[str, str] = {}
    for cell in race.source_cells:
        if sources[cell.source_id].panel_role != "comparison" or cell.state not in {
            "endorsement",
            "multi_endorsement",
        }:
            continue
        for candidate_id, candidate_label in zip(
            cell.candidate_ids, cell.candidate_labels, strict=True
        ):
            if candidate_id not in contributing_candidate_ids:
                comparison_only_labels[candidate_id] = candidate_label
    choices.extend(
        (candidate_id, candidate_label, None)
        for candidate_id, candidate_label in sorted(
            comparison_only_labels.items(),
            key=lambda item: (item[1].casefold(), item[0]),
        )
    )
    return choices


def _race_detail_support_summary(race: PublicationRace) -> str:
    if len(race.recommendation_candidate_ids) != 1:
        return _screen_support_summary(race)
    leader_id = race.recommendation_candidate_ids[0]
    leader_count = next(
        group.source_count for group in race.endorsement_groups if group.candidate_id == leader_id
    )
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    verb = "agrees" if race.explicit_endorsement_count == 1 else "agree"
    return f"{leader_count} of {race.explicit_endorsement_count} endorsing {noun} {verb}"


def _race_detail_accessible_summary(race: PublicationRace) -> str:
    share = "Consensus unavailable" if race.percentage_whole is None else race.percentage_label
    qualifier = "No majority. " if _has_no_majority(race) else ""
    return f"{race.recommendation_label}. {qualifier}{share}. {_race_detail_support_summary(race)}."


def _has_no_majority(race: PublicationRace) -> bool:
    return race.winner_share is not None and Fraction(race.winner_share) <= Fraction(1, 2)


def _screen_share_accessible_label(race: PublicationRace) -> str:
    share = "not available" if race.percentage_whole is None else race.percentage_label
    qualifier = "No majority. " if _has_no_majority(race) else ""
    return f"{qualifier}Consensus among explicitly endorsing sources: {share}"


def _source_cell_group(
    cell: SourceCell,
    race: PublicationRace,
    source: PublicationSource,
) -> str:
    del race
    if cell.state in {"not_covered", "not_applicable"}:
        return cell.state
    if cell.state in {"unavailable", "unverified"}:
        return "unverified"
    if cell.state == "no_endorsement":
        return "no_endorsement"
    return "candidate"


def _source_cell_group_count(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
    group: str,
    *,
    include_comparison: bool = True,
) -> int:
    """Count the cells in one group, optionally excluding the comparison source.

    The responsive guide hides the comparison by default, so a heading rendered
    for that state must count only the rows it actually shows.
    """
    return sum(
        _source_cell_group(cell, race, sources[cell.source_id]) == group
        and (include_comparison or sources[cell.source_id].panel_role != "comparison")
        for cell in race.source_cells
    )


def _source_cell_group_label(race: PublicationRace, group: str) -> str:
    del race
    return {
        "no_endorsement": "No endorsement",
        "unverified": "Needs verification",
        "not_covered": "Did not cover this race",
        "not_applicable": "Outside this source's district",
    }[group]


def _source_cell_detail_label(
    cell: SourceCell,
    race: PublicationRace,
    group: str,
) -> str | None:
    if group == "candidate":
        return "Co-endorsed" if cell.state == "multi_endorsement" else None
    if group in {"no_endorsement", "not_covered", "not_applicable"}:
        return None
    del race
    return _source_cell_status_label(cell)


def _source_cell_status_label(cell: SourceCell) -> str:
    if cell.state == "endorsement":
        return f"Endorsed {cell.candidate_labels[0]}"
    if cell.state == "multi_endorsement":
        return f"Endorsed {' and '.join(cell.candidate_labels)}"
    return {
        "no_endorsement": "No endorsement",
        "not_covered": "Did not cover this race",
        "unavailable": "Endorsement unavailable",
        "unverified": "Could not verify an endorsement",
        "not_applicable": "Outside this source's district",
    }[cell.state]


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
        expected_source_count = len(view_model.sources)
        screenshots = [
            _render_screenshot(
                html_path,
                screenshot_dir / "desktop.png",
                resolved_chrome,
                width=configuration.desktop_width,
                height=configuration.screenshot_height,
                expected_race_count=expected_race_count,
                expected_source_count=expected_source_count,
            ),
            _render_screenshot(
                html_path,
                screenshot_dir / "mobile.png",
                resolved_chrome,
                width=configuration.mobile_width,
                height=configuration.screenshot_height,
                expected_race_count=expected_race_count,
                expected_source_count=expected_source_count,
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
    source_by_id = {source.id: source for source in view_model.sources}
    category_label_by_key = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    expected_detail_keys = {
        (race.id, cell.source_id) for race in expected_races for cell in race.source_cells
    }
    if set(parser.race_detail_text) != expected_detail_keys:
        missing_evidence_rows.append("document: unexpected or missing race-detail source rows")
    for race in expected_races:
        candidate_choices = _race_detail_candidate_choices(race, source_by_id)
        for cell in race.source_cells:
            key = (race.id, cell.source_id)
            source = source_by_id[cell.source_id]
            expected_group = _source_cell_group(cell, race, source)
            expected_links: set[str] = (
                {cell.evidence_url} if cell.evidence_url is not None else set()
            )
            if expected_group == "candidate":
                expected_candidate_ids: list[str | None] = [
                    candidate_id
                    for candidate_id, _candidate_label, _endorsement_group in candidate_choices
                    if candidate_id in cell.candidate_ids
                ]
            else:
                expected_candidate_ids = [None]
            # A comparison source carries its one "Comparison only" role badge
            # instead of a category label (issue 115, item G29).
            if source.panel_role == "comparison":
                expected_parts = [source.name, "Comparison only"]
            else:
                expected_parts = [source.name, category_label_by_key[source.category]]
            detail_label = _source_cell_detail_label(cell, race, expected_group)
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
            if source.panel_role == "comparison":
                expected_row_class.add("race-detail-source-row-comparison")
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
        "/",  # the band's and footer's brand mark both link home (item L54/L55)
        f"/e/{view_model.metadata.election_id}/",
        f"{configuration.public_site_url}/e/{view_model.metadata.election_id}/sources/",
        configuration.pdf_filename,
        "mailto:seattle-elections@dobravoda.dev",
        "/about/",
        configuration.project_url,
        # The footer audit line's Code hash links to the exact commit (item L55.2).
        f"{configuration.project_url}/commit/{view_model.metadata.git_commit}",
        f"/e/{view_model.metadata.election_id}/release-manifest.json",
        *(f"#race-{race.id}" for race in expected_races),
        *(source.evidence_url for source in view_model.sources),
        *(
            cell.evidence_url
            for race in expected_races
            for cell in race.source_cells
            if cell.evidence_url is not None
        ),
    }
    canonical_url = f"{configuration.public_site_url}/e/{view_model.metadata.election_id}/"
    required_site_metadata = {
        f'<link rel="canonical" href="{canonical_url}">',
        f'<meta property="og:url" content="{canonical_url}">',
    }
    if not required_site_metadata.issubset({line.strip() for line in html.splitlines()}):
        missing_evidence_rows.append("document: missing election-scoped canonical metadata")
    if parser.links != expected_html_links:
        missing_evidence_rows.append("document: unexpected or missing links")
    source_categories = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    contributing_sources = [
        source for source in view_model.sources if source.contribution_status == "contributing"
    ]
    print_contributing_sources = [
        source
        for category in view_model.methodology.source_categories
        for source in contributing_sources
        if source.category == category.category
    ]
    coverage_gap_sources = [
        source for source in view_model.sources if source.contribution_status == "coverage_gap"
    ]
    expected_source_ids = {source.id for source in contributing_sources}
    if set(parser.publication_source_text) != expected_source_ids:
        missing_evidence_rows.append("document: unexpected or missing publication source rows")
    for source in contributing_sources:
        # Issue 97 removed the screen evidence directory's own use of this
        # macro (the merged sources tree renders its own inline checkbox
        # markup instead), so each contributing source now carries exactly
        # one `data-publication-source-id` row: print's own compact-labeled
        # source panel, unaffected by that rewrite.
        expected_rows = [
            _normalized_text(f"{source.name} {_source_participation_label(source, compact=True)}"),
        ]
        observed_rows = [
            _normalized_text(" ".join(parts))
            for parts in parser.publication_source_text.get(source.id, [])
        ]
        expected_classes = {"source-row", f"source-row-{source.panel_role}"}
        if (
            observed_rows != expected_rows
            or parser.publication_source_links.get(source.id, []) != [[source.evidence_url]]
            or parser.publication_source_categories.get(source.id, []) != [source.category]
            or parser.publication_source_heading_categories.get(source.id, []) != [source.category]
            or parser.publication_source_roles.get(source.id, []) != [source.panel_role]
            or parser.publication_source_classes.get(source.id, []) != [expected_classes]
            or source.category not in source_categories
        ):
            missing_evidence_rows.append(f"{source.id}: publication source row values")
    expected_coverage_gap_ids = {source.id for source in coverage_gap_sources}
    if set(parser.coverage_gap_text) != expected_coverage_gap_ids:
        missing_evidence_rows.append("document: unexpected or missing coverage-gap rows")
    for source in coverage_gap_sources:
        # Issue 108 removed the screen sources tree's own non-compact
        # coverage-gap listing, so print's compact-labeled row (with no note
        # paragraph) is the only one left.
        status_label = _coverage_gap_status_label(source)
        expected_rows = [
            _normalized_text(f"{source.name} {status_label}"),
        ]
        observed_rows = [
            _normalized_text(" ".join(parts))
            for parts in parser.coverage_gap_text.get(source.id, [])
        ]
        if (
            observed_rows != expected_rows
            or parser.coverage_gap_links.get(source.id, []) != [[source.evidence_url]]
            or parser.coverage_gap_statuses.get(source.id, []) != [source.coverage_gap_status]
            or parser.coverage_gap_classes.get(source.id, []) != [{"coverage-gap-row"}]
        ):
            missing_evidence_rows.append(f"{source.id}: coverage-gap row values")

    reader = PdfReader(pdf_path)
    pdf_texts = [page.extract_text() or "" for page in reader.pages]
    pdf_text = "\n".join(pdf_texts)
    comparable_pdf_text = _normalized_text(pdf_text).casefold()
    primary_value_fn = (
        _pdf_race_core_values if detailed_pdf_path is not None else _pdf_race_display_values
    )
    missing_pdf_values = _missing_pdf_race_values(expected_races, pdf_text, primary_value_fn)
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    identity_values = [election_display_name, configuration.title]
    consensus_source_count = sum(
        source.panel_role == "consensus" for source in contributing_sources
    )
    comparison_source_count = sum(
        source.panel_role == "comparison" for source in contributing_sources
    )
    data_updated_date, site_updated_date = _footer_update_dates(view_model)
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
        f"Data last updated {data_updated_date}",
        f"Site last updated {site_updated_date}",
        *(source.name for source in coverage_gap_sources),
        *(_coverage_gap_status_label(source) for source in coverage_gap_sources),
    ]
    missing_pdf_values.extend(
        value
        for value in global_pdf_values
        if _normalized_text(value).casefold() not in comparable_pdf_text
    )
    # H35 dropped the "· 0 split" suffix whenever nothing split, so a
    # non-splitting source's compact print label is a bare number with no
    # anchor a generic pattern could scan for, and source names can wrap
    # across lines in extracted text besides. Requiring each source's own
    # name immediately followed by its own expected label, after collapsing
    # all whitespace (including the line breaks a wrapped name introduces),
    # keeps this scoped to that source's own row without depending on either.
    missing_pdf_values.extend(
        f"{source.id}: print source participation row"
        for source in print_contributing_sources
        if _normalized_text(
            f"{source.name} {_source_participation_label(source, compact=True)}"
        ).casefold()
        not in comparable_pdf_text
    )
    pdf_identity_text = _pdf_text_runs(reader.pages[0]).casefold()
    missing_pdf_values.extend(
        value
        for value in identity_values
        if _normalized_text(value).casefold() not in pdf_identity_text
    )
    pages_are_letter = _pages_are_letter(reader)
    pdf_links = _pdf_links(reader)
    pdf_link_rows = _pdf_link_rows(reader)
    commit_url = f"{configuration.project_url}/commit/{view_model.metadata.git_commit}"
    expected_pdf_links = [
        configuration.project_url,
        *(source.evidence_url for source in print_contributing_sources),
        *(source.evidence_url for source in coverage_gap_sources),
        commit_url,
        commit_url,
        configuration.project_url,
    ]
    expected_source_link_rows = [
        (source.evidence_url, _normalized_text(source.name))
        for source in [*print_contributing_sources, *coverage_gap_sources]
    ]
    pdf_links_valid = (
        _web_urls_are_safe(pdf_links)
        and pdf_links == expected_pdf_links
        and pdf_link_rows[1:-3] == expected_source_link_rows
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
    # The interactive band and footer-band links are hidden in this
    # print-oriented edition (a plain, link-free text line carries the brand
    # identity instead; see .detailed-edition-brand), so only the footer's
    # audit trail (its Code hash link) and every source's evidence URL
    # remain visible.
    expected_detailed_links = {
        f"{configuration.project_url}/commit/{view_model.metadata.git_commit}",
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
                    '.comparison', '.warning'
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
                  const sourceGroups = [...document.querySelectorAll('.source-category-group')];
                  if (!sourcePanel || !methodNotes || sourceColumns.length !== 2 ||
                      sourceGroups.length < 2) {
                    issues.push('.source-directory-structure');
                  } else {
                    if (sourcePanel.getBoundingClientRect().bottom >
                        methodNotes.getBoundingClientRect().top + 1) {
                      issues.push('.source-panel-notes-overlap');
                    }
                    const columnCategories = sourceColumns.map(column =>
                      [...column.querySelectorAll('.source-category-group')].map(
                        group => group.dataset.sourceCategoryGroup
                      )
                    );
                    const categoryOrder = columnCategories.flat();
                    if (categoryOrder.some(category => !category) ||
                        new Set(categoryOrder).size !== categoryOrder.length ||
                        categoryOrder.length !== sourceGroups.length) {
                      issues.push('.source-category-containment');
                    }
                    const sourceCounts = sourceColumns.map(
                      column => column.querySelectorAll('.source-row').length
                    );
                    const categoryCounts = sourceGroups.map(
                      group => group.querySelectorAll('.source-row').length
                    );
                    const totalSourceCount = categoryCounts.reduce(
                      (total, count) => total + count, 0
                    );
                    let prefixCount = 0;
                    let optimalDifference = Number.POSITIVE_INFINITY;
                    for (let index = 0; index < categoryCounts.length - 1; index += 1) {
                      prefixCount += categoryCounts[index];
                      optimalDifference = Math.min(
                        optimalDifference,
                        Math.abs(totalSourceCount - (2 * prefixCount))
                      );
                    }
                    if (Math.abs(sourceCounts[0] - sourceCounts[1]) !== optimalDifference) {
                      issues.push('.source-column-balance');
                    }
                    if (sourcePanel.querySelector('.source-row-comparison') &&
                        categoryOrder[categoryOrder.length - 1] !== 'comparison') {
                      issues.push('.source-comparison-order');
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
                          meterStyle.justifyContent !== 'flex-start' ||
                          Number.parseFloat(meterStyle.borderTopWidth) < .4 ||
                          (!meter.classList.contains('print-meter-na') &&
                           meterStyle.backgroundImage === 'none') ||
                          (meter.classList.contains('meter-no-majority') &&
                           !meterStyle.backgroundImage.includes('rgb(217, 144, 0)'))) {
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


# The screen controls are one select and four radios. Issue 97 merged the
# personalization controls into the page-anchored sources tree, so there is
# no longer a Customize button here.
EXPECTED_SCREEN_CONTROL_COUNT = 5


def _render_screenshot(
    html_path: Path,
    output_path: Path,
    chrome_path: Path,
    *,
    width: int,
    height: int,
    expected_race_count: int,
    expected_source_count: int,
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
                    expected_source_count=expected_source_count,
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
    expected_source_count: int,
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
        # Issue 108: the guide has no interactive selection controls left, so
        # the comparison source can only ever become "checked" the way a real
        # reader reaches that state — arriving with a URL fragment naming it
        # (returned from the dedicated sources page's own Save action), not by
        # clicking a checkbox that no longer exists.
        sources_tree_probe = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(async()=>{"
                    "const pause=()=>new Promise(resolve=>setTimeout(resolve,120));"
                    "const root=document.documentElement;"
                    "const bindings=JSON.parse("
                    "document.querySelector('#lens-bindings').textContent);"
                    "const comparisonSource=bindings.sources.find("
                    "item=>item.panel_role==='comparison');"
                    # A real "check just the comparison box" interaction keeps
                    # every tallying source checked too — a fragment naming
                    # only the comparison code would also uncheck every
                    # tallying source (issue 97's own applySelection contract:
                    # every code not named is unchecked), which is not the
                    # scenario this probe means to exercise.
                    "const tallyingCodes=bindings.sources.filter("
                    "item=>item.panel_role!=='comparison').map(item=>item.code);"
                    "const selectedCodes=comparisonSource"
                    "?[...tallyingCodes,comparisonSource.code].sort():tallyingCodes;"
                    "const params=new URLSearchParams();"
                    "params.set('lens','2');params.set('mode','s');"
                    "params.set('panel',bindings.panel_id);"
                    "params.set('ph',bindings.panel_hash.slice(0,12));"
                    "params.set('data',bindings.data_version);"
                    "params.set('scoring',bindings.scoring.configuration_id);"
                    "params.set('sel',selectedCodes.join(''));"
                    "const comparisonFragment=params.toString();"
                    "const shownOnScreen=element=>{const style=getComputedStyle(element);"
                    "const rect=element.getBoundingClientRect();"
                    "return style.display!=='none'&&style.visibility==='visible'&&"
                    "rect.width>0&&rect.height>0;};"
                    "const displayed=element=>getComputedStyle(element).display!=='none';"
                    # UI polish issue 132 (H31): a lens-only twin comparison
                    # bar (no data-display-role, revealed only once a lens is
                    # actually active) now sits alongside the audited one;
                    # this probe only ever activates show-times, never a
                    # lens, so it must keep checking the audited bar alone.
                    "const pills=()=>[...document.querySelectorAll("
                    "'.comparison[data-display-role=\"comparison\"]')];"
                    "const cards=[...document.querySelectorAll('[data-publication-race-id]')];"
                    "const scored=()=>cards.map(card=>[card.querySelector('.screen-race-result')"
                    "?.textContent,card.querySelector('.screen-meter')?.textContent,"
                    "card.querySelector('.screen-race-context')?.textContent].join('|')"
                    ".replace(/\\s+/g,' ').trim()).join('||');"
                    "const before=scored();"
                    "const controlCount=document.querySelectorAll("
                    "'.screen-controls button,.screen-controls select,.screen-controls input')"
                    ".length;"
                    "const wrappers=()=>[...document.querySelectorAll("
                    "'.race-detail-source-list>li[data-source-role=\"comparison\"]')];"
                    "const supportAligned=()=>[...document.querySelectorAll("
                    "'.screen-race-context')].filter(context=>context.offsetParent).every("
                    "context=>{const support=context.querySelector('.support-line');"
                    "const meter=context.closest('[data-publication-race-id]')"
                    "?.querySelector('.screen-meter');"
                    "if(!support||!meter)return true;"
                    "return Math.abs(support.getBoundingClientRect().right-"
                    "meter.getBoundingClientRect().right)<=1;});"
                    # A closed <dialog> has no layout box, so a descendant's
                    # innerText cannot reliably resolve CSS visibility (e.g.
                    # the show-times-dependent data-times-hidden/-only pair)
                    # while its dialog stays closed; briefly opening every
                    # closed dialog (a plain property set, not showModal(),
                    # so multiple can be open at once with no modal conflict)
                    # gives each one a real layout pass before reading text.
                    "const countsAgree=()=>{"
                    "const dialogs=[...document.querySelectorAll('[data-race-detail-dialog]')];"
                    "const wasClosed=dialogs.filter(dialog=>!dialog.open);"
                    "wasClosed.forEach(dialog=>{dialog.open=true;});"
                    "const result=[...document.querySelectorAll("
                    "'.race-detail-source-list')].every(list=>{"
                    "const shown=[...list.children].filter(item=>"
                    "getComputedStyle(item).display!=='none').length;"
                    # Every source list is rendered immediately after the element that
                    # states its count (a <summary> or a heading <div>), so that single
                    # sibling is the only shape this template emits.
                    "const text=list.previousElementSibling?.innerText||'';"
                    "const claimed=Number((text.match(/(\\d+)\\s+source/)||[])[1]);"
                    "return !Number.isFinite(claimed)||claimed===shown;});"
                    "wasClosed.forEach(dialog=>{dialog.open=false;});"
                    "return result;};"
                    "const hidden={"
                    "pills:pills().length>0&&pills().every(item=>!shownOnScreen(item)),"
                    "wrappers:wrappers().length>0&&wrappers().every(item=>!displayed(item)),"
                    "supportAligned:supportAligned(),"
                    "noRootClass:!root.classList.contains('show-times'),"
                    "cleanHash:window.location.hash===''};"
                    # A real hash assignment (not history.replaceState) fires a
                    # native hashchange event, matching how a reader actually
                    # reaches this state: returning from the sources page's own
                    # Save redirect, never an in-page control.
                    "window.location.hash=comparisonFragment;await pause();"
                    "const revealed={rootClass:root.classList.contains('show-times'),"
                    "pills:pills().every(item=>displayed(item)),"
                    "lensFragment:window.location.hash.includes('lens=2')&&"
                    "window.location.hash.includes('sel=')&&"
                    "window.location.hash.includes('mode=s'),"
                    "wrappers:wrappers().every(item=>displayed(item)),"
                    "scoringUnchanged:scored()===before};"
                    "document.querySelector('.skip-link')?.click();await pause();"
                    "const afterAnchor={stillShown:root.classList.contains('show-times'),"
                    "anchorHash:window.location.hash==='#guide-races'};"
                    "return JSON.stringify({hidden,revealed,afterAnchor,"
                    "countsAgree:countsAgree(),controlCount,before});})()"
                ),
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        sources_tree_result = cast(dict[str, Any], sources_tree_probe["result"])
        if "value" not in sources_tree_result:
            raise ValueError(f"sources tree validation failed: {sources_tree_probe}")
        sources_tree_metrics = cast(
            dict[str, object], json.loads(cast(str, sources_tree_result["value"]))
        )
        expected_sources_tree = {
            "hidden": {
                "pills": True,
                "wrappers": True,
                "supportAligned": True,
                "noRootClass": True,
                "cleanHash": True,
            },
            "revealed": {
                "rootClass": True,
                "pills": True,
                "lensFragment": True,
                "wrappers": True,
                "scoringUnchanged": True,
            },
            "afterAnchor": {"stillShown": True, "anchorHash": True},
            "countsAgree": True,
            "controlCount": EXPECTED_SCREEN_CONTROL_COUNT,
            "before": sources_tree_metrics.get("before"),
        }
        if sources_tree_metrics != expected_sources_tree:
            raise ValueError(f"sources tree comparison validation failed: {sources_tree_metrics}")
        before_scores = cast(str, sources_tree_metrics["before"])

        # A fresh navigation, matching how a reader actually leaves this state
        # (Cancel/Reset on the dedicated sources page, or a plain reload) —
        # never same-page hash clearing, which the codec deliberately leaves
        # inert once a lens fragment is already applied (issue 108: the guide
        # has nothing left that clears its own selection in place).
        cdp.command("Page.navigate", {"url": url}, session_id=session_id)
        cdp.wait_event("Page.loadEventFired", session_id=session_id)
        restored_probe = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{"
                    "const cards=[...document.querySelectorAll('[data-publication-race-id]')];"
                    "const scored=()=>cards.map(card=>[card.querySelector('.screen-race-result')"
                    "?.textContent,card.querySelector('.screen-meter')?.textContent,"
                    "card.querySelector('.screen-race-context')?.textContent].join('|')"
                    ".replace(/\\s+/g,' ').trim()).join('||');"
                    "return JSON.stringify({"
                    "rootClass:!document.documentElement.classList.contains('show-times'),"
                    "cleanHash:window.location.hash==='',"
                    f"scoringUnchanged:scored()==={json.dumps(before_scores)}}});"
                    "})()"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        restored_result = cast(dict[str, Any], restored_probe["result"])
        if "value" not in restored_result:
            raise ValueError(f"sources tree restoration validation failed: {restored_probe}")
        restored_metrics = cast(dict[str, object], json.loads(cast(str, restored_result["value"])))
        expected_restored = {"rootClass": True, "cleanHash": True, "scoringUnchanged": True}
        if restored_metrics != expected_restored:
            raise ValueError(f"sources tree restoration validation failed: {restored_metrics}")

        # Leave the comparison shown so the checks below still exercise its markup.
        cdp.command(
            "Runtime.evaluate",
            {
                "expression": "document.documentElement.classList.add('show-times');true",
                "returnByValue": True,
            },
            session_id=session_id,
        )
        time.sleep(0.2)
        evaluated = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(async()=>JSON.stringify(await (async()=>{"
                    "const pause=()=>new Promise(resolve=>setTimeout(resolve,120));"
                    "const guide=document.querySelector('.screen-guide');"
                    "const filter=document.querySelector('#race-filter');"
                    "const status=document.querySelector('#filter-status');"
                    "const completeFilter=document.querySelector('#complete-filter');"
                    "const contestedFilter=document.querySelector('#contested-filter');"
                    "const viewInputs=[...document.querySelectorAll('input[name=ballot-view]')];"
                    "const binarySelectors=[...document.querySelectorAll("
                    "'.view-setting .segmented-control')];"
                    "const selectorWidths=binarySelectors.map(control=>"
                    "control.getBoundingClientRect().width);"
                    "const cards=[...document.querySelectorAll('[data-publication-race-id]')]"
                    ".filter(card=>getComputedStyle(card).display!=='none'&&"
                    "card.getBoundingClientRect().width>0&&card.getBoundingClientRect().height>0);"
                    "const cardParts=cards.flatMap(card=>[...card.querySelectorAll("
                    "'.screen-race-result,.screen-race-context,.screen-meter,.comparison')]);"
                    "const meters=[...document.querySelectorAll('.screen-meter')]"
                    ".filter(meter=>getComputedStyle(meter).display!=='none');"
                    # Every meter is left-anchored in every view (issue 115,
                    # item D14a): the label rides the fill's left edge.
                    "const meterAligned=(meter)=>{"
                    "const label=meter.querySelector('strong');const style=getComputedStyle(meter);"
                    "return style.justifyContent==='flex-start'&&"
                    "Boolean(label&&getComputedStyle(label).textAlign==='left');};"
                    "const compactInput=viewInputs.find(input=>input.value==='compact');"
                    "const fullInput=viewInputs.find(input=>input.value==='full');"
                    "const scopedOption=[...filter.options].find(option=>option.value!=='all');"
                    "if(scopedOption){filter.value=scopedOption.value;"
                    "filter.dispatchEvent(new Event('change',{bubbles:true}));}"
                    "compactInput?.click();contestedFilter?.click();await pause();"
                    "const compactCards=cards.filter(card=>!card.hidden);"
                    "const expectedCompactCards=cards.filter(card=>"
                    "(!scopedOption||JSON.parse(card.dataset.filterTokens).includes(scopedOption.value))&&"
                    "card.dataset.contested==='true');"
                    "const compactGrid=[...document.querySelectorAll('.race-grid')].find(grid=>"
                    "!grid.closest('[hidden]'));"
                    "const compactColumns=compactGrid?getComputedStyle(compactGrid)"
                    ".gridTemplateColumns.split(/\\s+/).length:0;"
                    "const expectedCompactColumns=window.innerWidth<=720?2:"
                    "window.innerWidth<=1050?3:4;"
                    "const controlQuery=new URLSearchParams(window.location.search);"
                    "const controls={"
                    "compact:document.documentElement.dataset.ballotView==='compact',"
                    "scopePreserved:Boolean(scopedOption&&filter.value===scopedOption.value),"
                    "contested:Boolean(contestedFilter?.checked),"
                    "pairedSelectors:binarySelectors.length===2&&"
                    "Math.abs(selectorWidths[0]-selectorWidths[1])<=1&&"
                    "binarySelectors.every(control=>{"
                    "const inputs=[...control.querySelectorAll('input[type=radio]')];"
                    "return inputs.length===2&&inputs.filter(input=>input.checked).length===1;}),"
                    "countMatches:compactCards.length===expectedCompactCards.length,"
                    "urlView:controlQuery.get('view')==='compact',"
                    "urlRaces:controlQuery.get('races')==='contested',"
                    "urlFilter:controlQuery.get('filter')===scopedOption?.value,"
                    "denseColumns:compactColumns===expectedCompactColumns,"
                    "noOverflow:document.documentElement.scrollWidth<=window.innerWidth+1,"
                    "compactMetersLeftAligned:compactCards.every(card=>{"
                    "const meter=card.querySelector('.screen-meter');"
                    "return Boolean(meter&&meterAligned(meter));}),"
                    "comparisonsHidden:compactCards.every(card=>{"
                    "const comparisons=card.querySelector('.screen-comparisons');"
                    "return Boolean(comparisons&&"
                    "getComputedStyle(comparisons).display==='none');})};"
                    "fullInput?.click();completeFilter?.click();"
                    "filter.value='all';filter.dispatchEvent(new Event('change',{bubbles:true}));"
                    "await pause();controls.reset="
                    "document.documentElement.dataset.ballotView==='full'&&"
                    "filter.value==='all'&&!contestedFilter?.checked&&window.location.search==='';"
                    "controls.fullMetersLeftAligned=meters.every(meter=>"
                    "meterAligned(meter));"
                    "controls.statusAllGrouped=status?.children.length===3&&"
                    "status.lastElementChild?.textContent===' · All Seattle ballot races'&&"
                    "getComputedStyle(status.lastElementChild).whiteSpace==='nowrap';"
                    # Issue 108: the guide has no page-anchored <details>
                    # disclosures left (both the methodology and sources
                    # accordions are gone), so there is nothing left to toggle
                    # or measure here.
                    "const disclosures=[];"
                    "const dialogs=[...document.querySelectorAll('[data-race-detail-dialog]')];"
                    "const firstCard=cards[0];"
                    "const firstLink=firstCard?.querySelector('[data-race-detail-link]');"
                    "const coreRecommendationsLinked=cards.every(card=>{"
                    "const link=card.querySelector("
                    "':scope > .race-card-primary[data-race-detail-link]');"
                    "return Boolean(link&&['.race-office','.screen-race-result',"
                    "'.screen-race-context'].every(selector=>link.querySelector(selector))&&"
                    "!link.textContent?.includes('View endorsements'));});"
                    "const copyButton=firstCard?.querySelector('[data-copy-race-link]');"
                    "const firstDialog=firstCard?.querySelector('[data-race-detail-dialog]');"
                    "const closeButton=firstDialog?.querySelector('[data-close-race-detail]');"
                    "let copiedValue='';"
                    "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{"
                    "writeText:async value=>{copiedValue=value;}}});"
                    "const firstHash=firstLink?.hash||'';"
                    "firstCard.hidden=true;"
                    "history.replaceState(null,'',firstHash);"
                    "window.dispatchEvent(new PopStateEvent('popstate',{state:null}));"
                    "await pause();"
                    "const directRect=firstDialog?.getBoundingClientRect();"
                    "const comparisonRow=firstDialog?.querySelector("
                    "'.race-detail-source-row-comparison');"
                    "const comparisonBadge=comparisonRow?.querySelector("
                    "'.race-detail-comparison-badge');"
                    "const comparisonStyle=comparisonRow?getComputedStyle(comparisonRow):null;"
                    "const comparisonBadgeRect=comparisonBadge?.getBoundingClientRect();"
                    "const comparisonBadgeStyle=comparisonBadge?"
                    "getComputedStyle(comparisonBadge):null;"
                    "const direct={open:Boolean(firstDialog?.open),"
                    "hash:window.location.hash===firstHash,"
                    "focused:document.activeElement===closeButton,"
                    "filterReset:filter?.value==='all'&&firstCard.hidden===false,"
                    "labelled:Boolean(firstDialog?.getAttribute('aria-labelledby')&&"
                    "firstDialog.getAttribute('aria-labelledby').split(/\\s+/).every("
                    "id=>document.getElementById(id))),"
                    "described:Boolean(firstDialog?.getAttribute('aria-describedby')&&"
                    "document.getElementById(firstDialog.getAttribute('aria-describedby'))),"
                    "sourceRows:new Set(Array.from(firstDialog?.querySelectorAll("
                    "'[data-race-detail-source-id]')||[],row=>row.dataset.raceDetailSourceId)).size,"
                    "comparisonStyled:Boolean(comparisonRow&&comparisonStyle&&"
                    "comparisonStyle.backgroundColor!=='rgba(0, 0, 0, 0)'&&"
                    "comparisonStyle.boxShadow!=='none'),"
                    "comparisonBadgeVisible:Boolean(comparisonBadge&&comparisonBadgeStyle&&"
                    "comparisonBadge.textContent?.trim()==='Comparison only'&&"
                    "comparisonBadgeStyle.display!=='none'&&"
                    "comparisonBadgeStyle.visibility==='visible'&&"
                    "Number(comparisonBadgeStyle.opacity)>0&&comparisonBadgeRect&&"
                    "comparisonBadgeRect.width>0&&comparisonBadgeRect.height>0),"
                    "inViewport:Boolean(directRect&&directRect.left>=0&&directRect.top>=0&&"
                    "directRect.right<=window.innerWidth&&directRect.bottom<=window.innerHeight),"
                    "noOverflow:Boolean(firstDialog&&firstDialog.scrollWidth<=firstDialog.clientWidth+1)};"
                    "copyButton?.click();"
                    "await pause();"
                    "const copyStatus=firstDialog?.querySelector('[data-copy-race-status]');"
                    "const copyFeedback=copyStatus?.textContent||'';"
                    "const copyDescription=copyButton?.getAttribute('aria-describedby')||'';"
                    "const copiedLink=copiedValue?new URL(copiedValue):null;"
                    "const copy={copied:copiedValue.endsWith(firstHash),"
                    "pathPreserved:copiedLink?.pathname===window.location.pathname,"
                    "queryPreserved:copiedLink?.search===window.location.search,"
                    "announced:copyFeedback.startsWith('Link copied'),"
                    "inDialog:Boolean(copyStatus&&firstDialog?.contains(copyStatus)),"
                    "described:copyDescription===copyStatus?.id};"
                    "closeButton?.click();"
                    "await pause();"
                    "const directClosed={closed:firstDialog?.open===false,"
                    "hashCleared:window.location.hash==='',focused:document.activeElement===firstLink};"
                    "firstLink?.querySelector('[data-display-role=recommendation]')?.click();"
                    "await pause();"
                    "const ownedOpened=Boolean(firstDialog?.open&&"
                    "window.location.hash===firstHash&&"
                    "document.activeElement===closeButton);"
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
                    "coreRecommendationsLinked,controls,"
                    "disclosures,dialogCount:dialogs.length,"
                    "copy,"
                    "direct,directClosed,ownedOpened};})()))()"
                ),
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        result = cast(dict[str, Any], evaluated["result"])
        if "value" not in result:
            raise ValueError(f"responsive interaction validation failed: {evaluated}")
        metrics = cast(dict[str, object], json.loads(cast(str, result["value"])))
        cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "setTimeout(()=>document.querySelector("
                    "'[data-race-detail-dialog][open] [data-close-race-detail]')?.click(),0);"
                    "true"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        time.sleep(0.25)
        traversed_back = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "JSON.stringify((()=>{"
                    "const dialog=document.querySelector('[data-race-detail-dialog]');"
                    "const card=dialog?.closest('[data-publication-race-id]');"
                    "const link=card?.querySelector('[data-race-detail-link]');"
                    "return {ownedClosed:Boolean(dialog?.open===false&&"
                    "window.location.hash===''&&document.activeElement===link)};})())"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        back_result = cast(dict[str, Any], traversed_back["result"])
        if "value" not in back_result:
            raise ValueError(f"back navigation validation failed: {traversed_back}")
        metrics.update(cast(dict[str, object], json.loads(cast(str, back_result["value"]))))
        cdp.command(
            "Runtime.evaluate",
            {"expression": "setTimeout(()=>history.forward(),0);true", "returnByValue": True},
            session_id=session_id,
        )
        time.sleep(0.25)
        traversed_forward = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(async()=>{"
                    "const pause=()=>new Promise(resolve=>setTimeout(resolve,120));"
                    "const dialog=document.querySelector('[data-race-detail-dialog]');"
                    "const card=dialog?.closest('[data-publication-race-id]');"
                    "const link=card?.querySelector('[data-race-detail-link]');"
                    "const close=dialog?.querySelector('[data-close-race-detail]');"
                    "const firstHash=link?.hash||'';"
                    "const forwardOpened=Boolean(dialog?.open&&"
                    "window.location.hash===firstHash&&document.activeElement===close);"
                    "history.replaceState(null,'',firstHash);"
                    "dialog?.dispatchEvent(new Event('cancel',{cancelable:true}));"
                    "await pause();"
                    "return JSON.stringify({forwardOpened,escapeClosed:Boolean("
                    "dialog?.open===false&&window.location.hash===''&&"
                    "document.activeElement===link)});})()"
                ),
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        forward_result = cast(dict[str, Any], traversed_forward["result"])
        if "value" not in forward_result:
            raise ValueError(f"forward navigation validation failed: {traversed_forward}")
        metrics.update(cast(dict[str, object], json.loads(cast(str, forward_result["value"]))))
        expected_metrics: dict[str, object] = {
            "innerWidth": width,
            "innerHeight": height,
            "scrollWidth": width,
            "guideVisible": True,
            "filterVisible": True,
            "visibleRaceCount": expected_race_count,
            "cardOverflow": [],
            "metersRightAligned": True,
            "coreRecommendationsLinked": True,
            "controls": {
                "compact": True,
                "scopePreserved": True,
                "contested": True,
                "pairedSelectors": True,
                "countMatches": True,
                "urlView": True,
                "urlRaces": True,
                "urlFilter": True,
                "denseColumns": True,
                "noOverflow": True,
                "compactMetersLeftAligned": True,
                "comparisonsHidden": True,
                "reset": True,
                "statusAllGrouped": True,
                "fullMetersLeftAligned": True,
            },
            "disclosures": [],
            "dialogCount": expected_race_count,
            "copy": {
                "copied": True,
                "pathPreserved": True,
                "queryPreserved": True,
                "announced": True,
                "inDialog": True,
                "described": True,
            },
            "direct": {
                "open": True,
                "hash": True,
                "focused": True,
                "filterReset": True,
                "labelled": True,
                "described": True,
                "sourceRows": expected_source_count,
                "comparisonStyled": True,
                "comparisonBadgeVisible": True,
                "inViewport": True,
                "noOverflow": True,
            },
            "directClosed": {"closed": True, "hashCleared": True, "focused": True},
            "ownedOpened": True,
            "ownedClosed": True,
            "forwardOpened": True,
            "escapeClosed": True,
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
    noun = "pick" if source.panel_role == "comparison" else "endorsement"
    if source.endorsement_count != 1:
        noun += "s"
    # H35: a real split becomes more visible once the "· 0 split" that
    # accompanied every non-splitting source disappears.
    split_suffix = (
        f" · {source.split_endorsement_count} split" if source.split_endorsement_count else ""
    )
    if compact:
        if source.panel_role == "comparison":
            return f"{source.endorsement_count} {noun}{split_suffix}"
        return f"{source.endorsement_count}{split_suffix}"
    return f"{source.endorsement_count} {noun}{split_suffix}"


def _coverage_gap_status_label(source: PublicationSource) -> str:
    if source.coverage_gap_status == "access_restricted":
        return "Official results inaccessible"
    if source.coverage_gap_status == "not_found":
        return "No published results found"
    raise ValueError(f"source {source.id!r} is missing a coverage-gap status")


def _html_semantic_values(race: PublicationRace) -> dict[str, list[str]]:
    return {
        "race-label": [race.race_label],
        "recommendation": [race.recommendation_label],
        "share": ["N/A" if race.percentage_whole is None else race.percentage_label],
        # H34: the default caption now renders as two sibling elements (full
        # sentence, then the compact-mode short form), both always present in
        # the static markup and both carrying data-display-role="support" —
        # the same "one role, ordered list of occurrences" shape the
        # "comparison" role below already uses for its own 0-or-1 occurrences.
        "support": [_screen_support_summary(race), _screen_support_summary_compact(race)],
        "comparison": [_screen_comparison_label(comparison) for comparison in race.comparisons],
        "insufficient-warning": (
            ["Too few endorsements to measure agreement."] if race.grade == "Insufficient" else []
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
    # I39: the support caption now renders directly under the meter row, with
    # the reference block (comparisons) moved to the card foot, after it —
    # the reverse of the prior anchoring, where the comparison preceded the
    # caption. The detailed edition renders the same screen DOM, so H37's
    # verb-alone "Times agrees" rendering (the differing/covered choice
    # dropped for every other status) applies here too.
    screen_support = _screen_support_summary(race)
    return [
        race.race_label,
        race.recommendation_label,
        "N/A" if race.percentage_whole is None else race.percentage_label,
        screen_support,
        *(
            f"{screen_support} {_screen_comparison_label(comparison)}"
            for comparison in race.comparisons
        ),
        *(["Too few endorsements to measure agreement."] if race.grade == "Insufficient" else []),
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
        self._current_publication_source: tuple[str, int] | None = None
        self._current_coverage_gap: tuple[str, int] | None = None
        self._current_source_category: str | None = None
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
        detail_source_id = attributes.get("data-race-detail-source-id")
        if detail_source_id is not None and self._current_race_id is not None:
            detail_key = (self._current_race_id, detail_source_id)
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
            if self._current_publication_source is not None:
                source_key, source_index = self._current_publication_source
                self.publication_source_text[source_key][source_index].append(data)
            if self._current_coverage_gap is not None:
                source_key, source_index = self._current_coverage_gap
                self.coverage_gap_text[source_key][source_index].append(data)
            if self._current_race_detail is not None:
                detail_key, detail_index = self._current_race_detail
                self.race_detail_text[detail_key][detail_index].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current_race_detail is not None:
            self._race_detail_depth -= 1
            if self._race_detail_depth == 0:
                self._current_race_detail = None
        if tag == "div" and self._current_publication_source is not None:
            self._current_publication_source = None
        if tag == "section" and self._current_coverage_gap is not None:
            self._current_coverage_gap = None
        if tag == self._display_role_tag:
            self._current_display_role = None
            self._display_role_tag = None
        if tag == "article":
            self._current_race_id = None
