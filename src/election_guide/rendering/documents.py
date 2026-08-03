"""Compose one full HTML document from the publication view model.

One autoescaped Jinja environment renders every page: the guide, the sources
editor, Comparisons, and the three site-wide documents `hosting/pages.py`
renders through the same `base.html.j2` layout (issue 241). Display values come
from `rendering/context.py`; this module only assembles them into a document.
"""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering import context
from election_guide.rendering.bundler import TEMPLATE_DIR, bundle_entry
from election_guide.rendering.models import RenderingConfiguration
from election_guide.rendering.payload import (
    comparisons_payload,
    guide_payload,
    source_participation_label,
    sources_payload,
)
from election_guide.rendering.shell import (
    CONTACT_HREF,
    EXTERNAL_LINK_ATTRIBUTES,
    OPENS_IN_NEW_TAB,
    SITE_NAME,
    close_icon_svg,
    election_day_banner_html,
    election_names,
    envelope_icon_svg,
    github_icon_svg,
    info_icon_svg,
    page_title,
    share_icon_svg,
    site_icon_svg,
)
from election_guide.rendering.stylesheets import page_stylesheet


def template_environment() -> Environment:
    """The one Jinja environment every full HTML document renders through.

    Public because `hosting/pages.py` renders the three site-wide documents —
    About, the archive, and the 404 — from the same environment and the same
    `base.html.j2` layout as the election-scoped pages (issue 241).
    """
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Globals rather than per-render variables: most of these are read inside
    # `_shell.html.j2`'s macros, which do not see the calling template's
    # context, so passing them per render silently covered only the handful of
    # uses outside a macro.
    # The link attributes are Markup, not a plain string: autoescape is on, so a
    # bare string would render as `target=&#34;_blank&#34;` and do nothing. The
    # icon builders return Markup for the same reason.
    # `Environment.globals` is typed for Jinja's own builtins, so widen it here.
    globals_map = cast(dict[str, Any], environment.globals)
    globals_map["external_link_attributes"] = Markup(EXTERNAL_LINK_ATTRIBUTES)
    globals_map["opens_in_new_tab"] = OPENS_IN_NEW_TAB
    globals_map["site_name"] = SITE_NAME
    globals_map["contact_href"] = CONTACT_HREF
    globals_map["site_icon_svg"] = site_icon_svg
    globals_map["share_icon_svg"] = share_icon_svg
    globals_map["info_icon_svg"] = info_icon_svg
    globals_map["envelope_icon_svg"] = envelope_icon_svg
    globals_map["github_icon_svg"] = github_icon_svg
    # The shell macros as a global too, so no page has to import them to render
    # the band, page head, or footer. `.module` binds them against the globals
    # set above, which is why it is built last.
    globals_map["shell"] = environment.get_template("_shell.html.j2").module
    return environment


def render_html_document(
    view_model: PublicationViewModel,
    configuration: RenderingConfiguration,
) -> str:
    """Render the guide's one HTML document, which also carries its print rules."""
    environment = template_environment()
    template = environment.get_template("guide.html.j2")
    # One CSS entry per page, so the guide ships the shell, the rules it shares
    # with the sources editor, and its own — and nothing the editor alone
    # renders (rendering/stylesheets.py).
    stylesheet = page_stylesheet("guide")
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
    filter_scope_groups = context.filter_scope_groups(view_model)
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    document_title = page_title(page="Endorsements", election=election_display_name)
    return template.render(
        **context.personalization_lookup_context(view_model),
        guide=view_model,
        config=configuration,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        guide_entry_script=guide_entry_script,
        client_payload=guide_payload(
            view_model,
            races=[
                context.race_display(race)
                for section in view_model.sections
                for race in section.races
            ],
            filter_scopes=[option for group in filter_scope_groups for option in group.options],
            sources_page_path=sources_page_url,
        ).model_dump(mode="json"),
        race_share_icon=share_icon_svg(),
        race_close_icon=close_icon_svg(),
        guide_path=guide_path,
        sources_page_url=sources_page_url,
        compare_href=(
            f"{guide_path}comparisons/" if view_model.comparisons.policy.enabled else None
        ),
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        canonical_origin=configuration.public_site_url,
        project_url=configuration.project_url,
        **context.footer_update_context(view_model),
        filter_scope_groups=filter_scope_groups,
        source_category_label_by_key=source_category_label_by_key,
        source_cells_by_race_id=source_cells_by_race_id,
        has_no_majority=context.has_no_majority,
        screen_share_accessible_label=context.screen_share_accessible_label,
        screen_support_summary=context.screen_support_summary,
        screen_support_summary_compact=context.screen_support_summary_compact,
        candidate_endorsement_groups=context.candidate_endorsement_groups,
        tallying_source_cells=context.tallying_source_cells,
        race_detail_accessible_summary=context.race_detail_accessible_summary,
        race_detail_support_summary=context.race_detail_support_summary,
        source_cell_group=context.source_cell_group,
        source_cell_group_count=context.source_cell_group_count,
        source_cell_group_label=context.source_cell_group_label,
        source_cell_detail_label=context.source_cell_detail_label,
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
    environment = template_environment()
    template = environment.get_template("sources.html.j2")
    stylesheet = page_stylesheet("sources")
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
        **context.personalization_lookup_context(view_model),
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
        guide_path=guide_path,
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        canonical_origin=public_site_url,
        project_url=project_url,
        **context.footer_update_context(view_model),
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

    environment = template_environment()
    template = environment.get_template("compare.html.j2")
    stylesheet = page_stylesheet("compare")
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
            context.comparison_fragment(view_model, ["strn", "stim"]),
        ),
        (
            "Labor and environment",
            context.comparison_fragment(view_model, ["Glab", "Genv"]),
        ),
        (
            "All sources and The Urbanist",
            context.comparison_fragment(view_model, ["gall", "urbn"]),
        ),
    ]
    comparison_sections = context.comparison_sections(view_model)
    return template.render(
        guide=view_model,
        public_site_url=public_site_url,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        compare_entry_script=compare_entry_script,
        guide_path=guide_path,
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        canonical_origin=public_site_url,
        project_url=project_url,
        **context.footer_update_context(view_model),
        comparison_sections=comparison_sections,
        comparison_race_count=sum(len(section.rows) for section in comparison_sections),
        comparison_differ_count=sum(
            row.differs for section in comparison_sections for row in section.rows
        ),
        client_payload=payload.model_dump(mode="json"),
        comparison_source_labels=payload.source_labels,
        comparison_presets=preset_fragments,
        comparison_percentage_label=context.comparison_percentage_label,
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
