"""Render one publication view model to a responsive, printable HTML guide."""

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
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup
from PIL import Image, ImageChops
from websocket import (  # pyright: ignore[reportUnknownVariableType]
    WebSocket,
    WebSocketException,
    create_connection,  # pyright: ignore[reportUnknownVariableType]
)

from election_guide.publication.models import (
    PublicationChoiceEndorsements,
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
from election_guide.rendering.bundler import TEMPLATE_DIR, bundle_entry
from election_guide.rendering.models import (
    RenderCheck,
    RenderingConfiguration,
    RenderingValidationReport,
)
from election_guide.rendering.payload import (
    FilterScope,
    RaceCandidateDisplay,
    RaceDisplay,
    comparisons_payload,
    guide_payload,
    source_participation_label,
    sources_payload,
)
from election_guide.rendering.shell import (
    EXTERNAL_LINK_ATTRIBUTES,
    HOW_TO_VOTE_HREF,
    close_icon_svg,
    election_day_banner_html,
    election_names,
    page_title,
    share_icon_svg,
    site_band_html,
    site_footer_audit_html,
    site_footer_band_html,
    site_head_links_html,
    site_page_head_html,
)
from election_guide.serialization import canonical_json_bytes, read_json, read_yaml


@dataclass(frozen=True)
class RenderedGuide:
    html_path: Path
    validation_path: Path
    screenshots: list[Path]
    validation_report: RenderingValidationReport


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
class FilterScopeGroupView:
    """One `<optgroup>` of the guide's Ballot filter. `label` is `None` for the
    ungrouped leading option."""

    label: str | None
    options: tuple[FilterScope, ...]


@dataclass(frozen=True)
class ComparisonSectionView:
    section_id: str
    section_label: str
    rows: tuple[ComparisonRowView, ...]


def read_rendering_configuration(path: Path) -> RenderingConfiguration:
    """Read the strict Chromium rendering contract."""
    return RenderingConfiguration.model_validate(read_yaml(path))


def _template_environment() -> Environment:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # A global rather than a per-render variable: most evidence links are
    # rendered inside macros, which do not see the calling template's context,
    # so passing it per render silently covered only the handful of links
    # outside a macro.
    # Markup, not a plain string: autoescape is on, so a bare string would render
    # as `target=&#34;_blank&#34;` and do nothing.
    # `Environment.globals` is typed for Jinja's own builtins, so widen it here.
    globals_map = cast(dict[str, Any], environment.globals)
    globals_map["external_link_attributes"] = Markup(EXTERNAL_LINK_ATTRIBUTES)
    return environment


def _personalization_lookup_context(view_model: PublicationViewModel) -> dict[str, Any]:
    """Derived views over the personalization contract shared by every page that
    renders it (the guide and the standalone sources page): a code -> identity
    lookup distinct from source_by_id's id keying, the reverse id -> code lookup
    the markup needs to address a source the way the client payload does, and
    category labels for a multi-category source's "also in" tag."""
    return {
        "source_by_id": {source.id: source for source in view_model.sources},
        "personalization_source_by_code": {
            source.code: source for source in view_model.personalization.sources
        },
        # docs/FRONTEND.md, The data contract: one identifier space. A rendered
        # source is addressed by the same transport code the payload publishes,
        # so no client module translates between the two.
        "source_code_by_id": {
            source.id: source.code for source in view_model.personalization.sources
        },
        "category_label_by_id": {
            category.id: category.label for category in view_model.personalization.categories
        },
    }


def _race_display(race: PublicationRace) -> RaceDisplay:
    """One race's audited presentation, published so no client module reads it
    back out of the dialog (docs/FRONTEND.md, The data contract)."""
    return RaceDisplay(
        race_id=race.id,
        race_label=race.race_label,
        candidates=[
            RaceCandidateDisplay(candidate_id=group.candidate_id, label=group.candidate_label)
            for group in _candidate_endorsement_groups(race)
        ],
        audited_accessible_summary=_race_detail_accessible_summary(race),
    )


def render_html_document(
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
) -> str:
    """Render the guide's one HTML document, which also carries its print rules."""
    environment = _template_environment()
    template = environment.get_template("guide.html.j2")
    # base.css carries the design tokens and accessibility utility classes (the
    # skip link, visually-hidden) shared with the site-wide About page in
    # hosting/pages.py, so both read the one file rather than hand-duplicating it.
    stylesheet = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8") + (
        TEMPLATE_DIR / "guide.css"
    ).read_text(encoding="utf-8")
    # One entry module, one bundle, inlined verbatim inside a module script so
    # the guide stays one self-contained file (docs/FRONTEND.md, Modules).
    guide_entry_script = bundle_entry("guide-entry.mjs", global_name="GuidePage")
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
    # Root-relative, like every other in-site link: an absolute production URL
    # walked a reader off any other origin — a local preview, a staging deploy,
    # a PR preview — straight to seattleelections.guide. Nothing needs the
    # origin: the band link, the strip's "Edit sources" link, and the script
    # that appends the live lens fragment all work from a path.
    sources_page_url = f"{guide_path}sources/"
    filter_scope_groups = _filter_scope_groups(view_model)
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(page="Endorsements", election=election_display_name)
    return template.render(
        **_personalization_lookup_context(view_model),
        guide=view_model,
        config=configuration,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        guide_entry_script=guide_entry_script,
        client_payload=guide_payload(
            view_model,
            races=[
                _race_display(race) for section in view_model.sections for race in section.races
            ],
            filter_scopes=[option for group in filter_scope_groups for option in group.options],
            sources_page_path=sources_page_url,
        ).model_dump(mode="json"),
        race_share_icon=share_icon_svg(),
        race_close_icon=close_icon_svg(),
        site_band=site_band_html(
            guide_href=guide_path,
            sources_href=sources_page_url,
            compare_href=(
                f"{guide_path}comparisons/" if view_model.comparisons.policy.enabled else None
            ),
            current="endorsements",
            sources_link_data_attribute=True,
        ),
        site_page_head=site_page_head_html(
            eyebrow=election_display_name,
            title="Endorsements",
            tagline_html="Seattle&rsquo;s progressive voices, distilled.",
            mode="extended",
        ),
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        site_head_links=site_head_links_html(configuration.public_site_url),
        site_footer_band=_election_footer_band(
            view_model,
            project_url=configuration.project_url,
            guide_path=guide_path,
        ),
        filter_scope_groups=filter_scope_groups,
        source_category_label_by_key=source_category_label_by_key,
        source_cells_by_race_id=source_cells_by_race_id,
        has_no_majority=_has_no_majority,
        screen_share_accessible_label=_screen_share_accessible_label,
        screen_support_summary=_screen_support_summary,
        screen_support_summary_compact=_screen_support_summary_compact,
        candidate_endorsement_groups=_candidate_endorsement_groups,
        tallying_source_cells=_tallying_source_cells,
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
) -> str:
    """Render the standalone per-election sources/customization page (issue 107).

    Purely a selection editor: it reads a selection from its own incoming URL
    fragment and writes one back on Save, but never scores anything, so it
    inlines only the fragment codec, not the scoring engine the guide needs.
    `project_url` feeds the shared footer (item L55): a caller that omits it
    gets no footer band or audit line at all (both need it). Every real caller
    (`hosting/pages.py`) supplies it, so the page always renders its footer in
    production; this only matters for a caller (e.g. a test) that renders the
    page without it.
    """
    environment = _template_environment()
    template = environment.get_template("sources.html.j2")
    stylesheet = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8") + (
        TEMPLATE_DIR / "guide.css"
    ).read_text(encoding="utf-8")
    sources_entry_script = bundle_entry("sources-entry.mjs", global_name="SourcesPage")
    guide_path = f"/e/{view_model.metadata.election_id}/"
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(page="Sources", election=election_display_name)
    # Issue 124: the comparison section is documentation, not a control, and
    # points at the one page that still puts these sources side by side.
    compare_href = f"{guide_path}comparisons/" if view_model.comparisons.policy.enabled else None
    payload = sources_payload(view_model, guide_path=guide_path)
    return template.render(
        **_personalization_lookup_context(view_model),
        guide=view_model,
        public_site_url=public_site_url,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        sources_entry_script=sources_entry_script,
        client_payload=payload.model_dump(mode="json"),
        # One definition of the count grammar, shared by the audited row this
        # template renders and the payload the client re-renders it from
        # (docs/FRONTEND.md § Cross-language mirrors).
        source_participation_label=source_participation_label,
        # How many sources the audited default counts. Read off the payload's
        # own tree, deduplicated, so the audited count line and the client's
        # cannot disagree about which rows are one source.
        counted_source_count=len(
            {source.code for category in payload.tree for source in category.sources}
        ),
        compare_href=compare_href,
        site_band=site_band_html(
            guide_href=guide_path,
            sources_href=f"{guide_path}sources/",
            compare_href=compare_href,
            current="sources",
        ),
        site_page_head=site_page_head_html(
            eyebrow=election_display_name,
            title="Sources",
            tagline_html=(
                "Choose which sources count &mdash; the guide recalculates from your selection."
            ),
        ),
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        site_head_links=site_head_links_html(public_site_url),
        site_footer_band=_election_footer_band(
            view_model,
            project_url=project_url,
            guide_path=guide_path,
        ),
    )


def render_comparison_document(
    view_model: PublicationViewModel,
    *,
    public_site_url: str,
    project_url: str | None = None,
) -> str:
    """Render the policy-gated, no-JavaScript comparison baseline."""
    if not view_model.comparisons.policy.enabled:
        raise ValueError("comparison page cannot render while its release policy is disabled")

    environment = _template_environment()
    template = environment.get_template("compare.html.j2")
    stylesheet = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8") + (
        TEMPLATE_DIR / "compare.css"
    ).read_text(encoding="utf-8")
    compare_entry_script = bundle_entry("compare-entry.mjs", global_name="ComparePage")
    guide_path = f"/e/{view_model.metadata.election_id}/"
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(page="Comparisons", election=election_display_name)
    payload = comparisons_payload(view_model, default_columns=["gall", "strn", "stim"])
    preset_fragments = [
        (
            "The Stranger and The Times",
            _comparison_fragment(view_model, ["strn", "stim"]),
        ),
        (
            "Labor and environment",
            _comparison_fragment(view_model, ["Glab", "Genv"]),
        ),
        (
            "All sources and The Urbanist",
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
        compare_entry_script=compare_entry_script,
        site_band=site_band_html(
            guide_href=guide_path,
            compare_href=f"{guide_path}comparisons/",
            sources_href=f"{guide_path}sources/",
            current="comparisons",
        ),
        site_head_links=site_head_links_html(public_site_url),
        site_page_head=site_page_head_html(
            eyebrow=election_display_name,
            title="Comparisons",
            tagline_html="Endorsements side by side, surfacing tension.",
        ),
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        site_footer_band=_election_footer_band(
            view_model,
            project_url=project_url,
            guide_path=guide_path,
        ),
        comparison_sections=comparison_sections,
        comparison_race_count=sum(len(section.rows) for section in comparison_sections),
        comparison_differ_count=sum(
            row.differs for section in comparison_sections for row in section.rows
        ),
        client_payload=payload.model_dump(mode="json"),
        comparison_source_labels=payload.source_labels,
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
    if len(cells) < 2 or not cells[0].leading_pick_ids:
        return False
    reference = set(cells[0].leading_pick_ids)
    return any(
        bool(cell.leading_pick_ids) and reference.isdisjoint(cell.leading_pick_ids)
        for cell in cells[1:]
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


def _filter_scope_groups(view_model: PublicationViewModel) -> list[FilterScopeGroupView]:
    """The Ballot filter's option groups, in rendered order.

    One generator for both consumers (docs/FRONTEND.md, The data contract): the
    template renders its `<optgroup>`/`<option>` markup from these, and the
    payload publishes the same options flattened, so the filter status line can
    name the selected scope without reading the select's own text back
    (issue #239). The options are `FilterScope` on both sides, so the two
    consumers cannot disagree about a key.
    """
    return [
        FilterScopeGroupView(
            label=None,
            options=(FilterScope(value="all", label="All Seattle ballot races"),),
        ),
        FilterScopeGroupView(
            label="Ballot sections",
            options=tuple(
                FilterScope(value=section.id, label=section.label)
                for section in view_model.sections
            ),
        ),
        FilterScopeGroupView(
            label="Districts and jurisdictions",
            options=tuple(
                FilterScope(value=token, label=token) for token in _filter_options(view_model)
            ),
        ),
    ]


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
    )


def _screen_support_summary(race: PublicationRace) -> str:
    noun = "source" if race.explicit_endorsement_count == 1 else "sources"
    return f"Based on {race.explicit_endorsement_count} endorsing {noun}"


def _screen_support_summary_compact(race: PublicationRace) -> str:
    """H34: the compact-mode caption drops the sentence, matching how the
    print edition's own full/compact captions already differ."""
    return f"{race.explicit_endorsement_count} sources"


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


def _tallying_source_cells(
    race: PublicationRace,
    sources: dict[str, PublicationSource],
) -> list[SourceCell]:
    """The cells the guide renders as evidence.

    Issue 124 retired the guide-side comparison entirely, so a comparison
    source contributes no row, no count, and no candidate section here. It
    stays in the payload and on the Comparisons page, which is now the one
    place a reader compares it against the consensus.
    """
    return [
        cell for cell in race.source_cells if sources[cell.source_id].panel_role != "comparison"
    ]


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
) -> int:
    """Count the rendered cells in one group."""
    return sum(
        _source_cell_group(cell, race, sources[cell.source_id]) == group
        for cell in _tallying_source_cells(race, sources)
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
) -> RenderedGuide:
    """Build and validate a complete HTML rendering generation."""
    view_model = PublicationViewModel.model_validate(read_json(view_model_path))
    configuration = read_rendering_configuration(configuration_path)
    resolved_chrome = chrome_path or find_chrome()
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
        screenshot_dir = stage / "screenshots"
        screenshot_dir.mkdir()
        html_path.write_text(
            render_html_document(view_model, configuration),
            encoding="utf-8",
            newline="\n",
        )
        expected_race_count = sum(len(section.races) for section in view_model.sections)
        # Issue 124: a comparison source renders no race-detail row, so the
        # dialog's expected row count is the tallying panel alone.
        expected_source_count = sum(
            source.panel_role != "comparison" for source in view_model.sources
        )
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
            screenshots,
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
    final_screenshots = [output_dir / "screenshots" / path.name for path in screenshots]
    return RenderedGuide(
        html_path=output_dir / configuration.html_filename,
        validation_path=output_dir / "rendering_validation_report.json",
        screenshots=final_screenshots,
        validation_report=validation_report,
    )


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
    # A rendered source row is addressed by its transport code, the one
    # identifier the client payload publishes (docs/FRONTEND.md, The data
    # contract), so the observed keys are in code space too.
    source_code_by_id = {source.id: source.code for source in view_model.personalization.sources}
    # Issue 124: a comparison source renders no race-detail row at all.
    expected_detail_keys = {
        (race.id, source_code_by_id[cell.source_id])
        for race in expected_races
        for cell in _tallying_source_cells(race, source_by_id)
    }
    if set(parser.race_detail_text) != expected_detail_keys:
        missing_evidence_rows.append("document: unexpected or missing race-detail source rows")
    for race in expected_races:
        endorsement_groups = _candidate_endorsement_groups(race)
        for cell in _tallying_source_cells(race, source_by_id):
            key = (race.id, source_code_by_id[cell.source_id])
            source = source_by_id[cell.source_id]
            expected_group = _source_cell_group(cell, race, source)
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
            for cell in _tallying_source_cells(race, source_by_id)
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
            id="responsive-viewports",
            passed=responsive_sizes,
            message="HTML renders nonblank content at the configured desktop and mobile viewports.",
        ),
    ]
    return RenderingValidationReport(
        passed=all(check.passed for check in checks),
        checks=checks,
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
        # Issue 124 retired the guide-side Times comparison: nothing
        # comparison-shaped may render on a real page. The companion contract —
        # that a link shared before the removal still replays with its token
        # ignored — is a property of the codec, not of a viewport, so it is
        # owned by the lens-url Node tests and by the browser replay test in
        # tests/test_rendering.py rather than repeated per screenshot here.
        residue_probe = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{"
                    "const bindings=JSON.parse("
                    "document.querySelector('[data-client-payload]').textContent);"
                    "const comparison=bindings.sources.find("
                    "item=>item.panel_role==='comparison');"
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
                    "const supportAligned=()=>[...document.querySelectorAll("
                    "'.screen-race-context')].filter(context=>context.offsetParent).every("
                    "context=>{const support=context.querySelector('.support-line');"
                    "const meter=context.closest('[data-publication-race-id]')"
                    "?.querySelector('.screen-meter');"
                    "if(!support||!meter)return true;"
                    "return Math.abs(support.getBoundingClientRect().right-"
                    "meter.getBoundingClientRect().right)<=1;});"
                    "const controlCount=document.querySelectorAll("
                    "'.screen-controls button,.screen-controls select,.screen-controls input')"
                    ".length;"
                    "return JSON.stringify({"
                    "comparisonPublished:Boolean(comparison),"
                    "noComparisonBars:document.querySelectorAll("
                    "'.comparison,.screen-comparisons,[data-display-role=\"comparison\"]')"
                    ".length===0,"
                    # The evidence panel still lists the Times as a source
                    # (a stated non-goal); what must be gone is every
                    # comparison row inside a race's own detail dialog.
                    "noComparisonRows:document.querySelectorAll("
                    '\'.race-detail-source-list [data-source-role="comparison"],'
                    ".race-detail-comparison-badge').length===0,"
                    "noTimesText:!document.querySelector('.screen-guide')"
                    ".innerHTML.includes('Times comparison'),"
                    "countsAgree:countsAgree(),supportAligned:supportAligned(),"
                    "controlCount});"
                    "})()"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        residue_result = cast(dict[str, Any], residue_probe["result"])
        if "value" not in residue_result:
            raise ValueError(f"comparison removal validation failed: {residue_probe}")
        residue_metrics = cast(dict[str, object], json.loads(cast(str, residue_result["value"])))
        expected_residue = {
            "comparisonPublished": True,
            "noComparisonBars": True,
            "noComparisonRows": True,
            "noTimesText": True,
            "countsAgree": True,
            "supportAligned": True,
            "controlCount": EXPECTED_SCREEN_CONTROL_COUNT,
        }
        if residue_metrics != expected_residue:
            raise ValueError(f"comparison removal validation failed: {residue_metrics}")

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
                    "'.screen-race-result,.screen-race-context,.screen-meter')]);"
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
                    "};"
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
                    "'[data-race-detail-source-code]')||[],row=>row.dataset.raceDetailSourceCode)).size,"
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


def _image_ink_fraction(path: Path) -> float:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        histogram = ImageChops.difference(image, background).convert("L").histogram()
        return sum(histogram[8:]) / (image.width * image.height)


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
        "support": [_screen_support_summary(race), _screen_support_summary_compact(race)],
        "insufficient-warning": (
            ["Too few endorsements to measure agreement."] if race.grade == "Insufficient" else []
        ),
    }


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
