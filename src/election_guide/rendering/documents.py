"""Compose one full HTML document from the publication view model.

One autoescaped Jinja environment renders every page: the guide, the sources
editor, Comparisons, and the three site-wide documents `hosting/pages.py`
renders through the same `base.html.j2` layout (issue 241). Display values come
from `rendering/context.py`; this module only assembles them into a document.
"""

from __future__ import annotations

from functools import partial
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
    race_payload,
    source_participation_label,
    sources_payload,
)
from election_guide.rendering.shell import (
    CONTACT_HREF,
    EXTERNAL_LINK_ATTRIBUTES,
    OPENS_IN_NEW_TAB,
    SITE_NAME,
    election_day_banner_html,
    election_names,
    envelope_icon_svg,
    github_icon_svg,
    info_icon_svg,
    page_title,
    race_og_image_path,
    race_page_path,
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
    # The guide renders one off-site link of its own now that the evidence rows
    # moved to the race pages (issue #136), and each of those pages checks its
    # own race's receipts in `render_race_document`.
    _require_web_url(configuration.project_url)
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
        guide=view_model,
        config=configuration,
        document_title=document_title,
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        guide_entry_script=guide_entry_script,
        client_payload=guide_payload(
            view_model,
            races=[
                context.race_display(race, race_page_path(view_model.metadata.election_id, race.id))
                for section in view_model.sections
                for race in section.races
            ],
            filter_scopes=[option for group in filter_scope_groups for option in group.options],
            sources_page_path=sources_page_url,
        ).model_dump(mode="json"),
        # Each card links its race's own page (issue #136). Bound to this
        # election here rather than passed as a two-argument helper, so the
        # template cannot address a race in another election.
        race_page_path=partial(race_page_path, view_model.metadata.election_id),
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
        has_no_majority=context.has_no_majority,
        screen_share_accessible_label=context.screen_share_accessible_label,
        screen_support_summary=context.screen_support_summary,
        screen_support_summary_compact=context.screen_support_summary_compact,
    )


def render_race_document(
    view_model: PublicationViewModel,
    race_id: str,
    *,
    public_site_url: str,
    project_url: str | None = None,
) -> str:
    """Render one race's own page (issue #136).

    Race detail lives at its own address, so it can be landed on, shared, and
    unfurled with the race's own title, description, and card — none of which a
    URL fragment over the guide could ever carry, because a fragment is never
    sent to the crawler that builds the preview. `docs/DESIGN.md`'s
    page-vs-modal test asks for exactly that re-evaluation when the
    requirements change, and this is the page it now calls for.

    Pure in the same sense the other documents are: same view model and race,
    same bytes. That is what lets `hosting/pages.py` publish the page and
    `rendering/validation.py` audit the very same rendering without the two
    having to share a file.
    """
    race = next(
        (
            candidate
            for section in view_model.sections
            for candidate in section.races
            if candidate.id == race_id
        ),
        None,
    )
    if race is None:
        raise ValueError(f"election {view_model.metadata.election_id!r} has no race {race_id!r}")

    # Every receipt this page links, checked before it is written into markup.
    for cell in race.source_cells:
        if cell.evidence_url is not None:
            _require_web_url(cell.evidence_url)

    environment = template_environment()
    template = environment.get_template("race.html.j2")
    stylesheet = page_stylesheet("race")
    race_entry_script = bundle_entry("race-entry.mjs", global_name="RacePage")
    election_id = view_model.metadata.election_id
    guide_path = f"/e/{election_id}/"
    sources_page_url = f"{guide_path}sources/"
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=election_id,
    )
    lookups = context.personalization_lookup_context(view_model)
    source_by_id = cast(dict[str, Any], lookups["source_by_id"])
    source_code_by_id = cast(dict[str, str], lookups["source_code_by_id"])
    category_label_by_key = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    race_detail = context.race_detail_display(
        race,
        source_by_id,
        source_code_by_id=source_code_by_id,
        category_label_by_key=category_label_by_key,
    )
    contributing_sources = [
        source for source in view_model.sources if source.contribution_status == "contributing"
    ]
    return template.render(
        **lookups,
        guide=view_model,
        race=race,
        race_detail=race_detail,
        public_site_url=public_site_url,
        # DESIGN.md's title grammar for an election-scoped page, with the race
        # itself as the page's own name: `<page> — <election> — <site>`.
        document_title=page_title(page=race.race_label, election=election_display_name),
        page_description=context.race_social_description(race),
        election_display_name=election_display_name,
        stylesheet=stylesheet,
        race_entry_script=race_entry_script,
        client_payload=race_payload(
            view_model,
            race=race_detail,
            sources_page_path=sources_page_url,
        ).model_dump(mode="json"),
        race_path=race_page_path(election_id, race.id),
        social_image_path=race_og_image_path(election_id, race.id),
        guide_path=guide_path,
        sources_page_url=sources_page_url,
        compare_href=(
            f"{guide_path}comparisons/" if view_model.comparisons.policy.enabled else None
        ),
        consensus_source_count=sum(
            source.panel_role == "consensus" for source in contributing_sources
        ),
        election_day_banner=election_day_banner_html(view_model.metadata.election_date),
        canonical_origin=public_site_url,
        project_url=project_url,
        **context.footer_update_context(view_model),
        group_rows=context.race_source_group_rows(
            race,
            source_by_id,
            source_code_by_id=source_code_by_id,
            category_label_by_key=category_label_by_key,
        ),
        has_no_majority=context.has_no_majority,
        screen_share_accessible_label=context.screen_share_accessible_label,
        screen_support_summary=context.screen_support_summary,
        screen_support_summary_compact=context.screen_support_summary_compact,
        race_detail_accessible_summary=context.race_detail_accessible_summary,
        source_cell_group_label=context.source_cell_group_label,
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
    # Every source's receipt, checked before it is written into markup. This
    # page is where those links are rendered — the tree's rows and the
    # coverage-gap rows — so it is where they are checked, the same way the
    # guide checks its one off-site link and a race page checks its own cells.
    for source in view_model.sources:
        _require_web_url(source.evidence_url)

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
