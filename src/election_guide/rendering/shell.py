"""Shared cross-page chrome: the site name, brand icon, nav band, and footer.

Every page on the site (the guide, the sources editor, About, the election
archive, and the branded 404) renders this exact band, and every page except
the 404 renders this exact footer, so the cross-page chrome has one
implementation each (UI polish round 4, item L54/L55). The icon is "The
Meter": the guide's agreement meter distilled into a mark, with a
left-anchored fill matching the on-page meters.
"""

from __future__ import annotations

import html
from datetime import date
from typing import Literal

SITE_NAME = "Seattle Elections Guide"
CONTACT_HREF = "mailto:seattle-elections@dobravoda.dev"
# King County Elections administers Seattle's ballots and is already this
# repository's cited authority for the sample ballot, candidate filings, and
# precinct maps (config/elections/*-inventory.yaml).
HOW_TO_VOTE_HREF = "https://kingcounty.gov/en/dept/elections/how-to-vote"

# Every link that leaves the site opens in a new tab, so a reader checking a
# receipt — an endorsement's evidence, the source files, how to vote — keeps
# their place in the guide. `noopener` is the security half; the referrer is
# deliberately left intact so the organizations we cite can see the traffic.
# In-site navigation never uses this.
EXTERNAL_LINK_ATTRIBUTES = ' target="_blank" rel="noopener"'
OPENS_IN_NEW_TAB = " (opens in a new tab)"


def election_names(
    election_date: str,
    election_type: str | None,
    state: str | None,
    *,
    legacy_name: str | None = None,
    election_id: str | None = None,
) -> tuple[str, str]:
    """Return canonical names, with a strict reader for immutable schema-1.8 bundles."""

    if election_type is None:
        type_tokens = {
            token.casefold()
            for token in (legacy_name or "").split()
            if token.casefold() in {"primary", "general", "special"}
        }
        if len(type_tokens) != 1:
            raise ValueError(
                "legacy election name must contain exactly one supported election type"
            )
        election_type = type_tokens.pop()
    if state is None:
        prefix = (election_id or "").split("-", 1)[0].upper()
        state = prefix if len(prefix) == 2 else None

    parsed_date = date.fromisoformat(election_date)
    if election_type not in {"primary", "general", "special"}:
        raise ValueError(f"unsupported election type: {election_type}")
    state_name = {"WA": "Washington"}.get(state) if state is not None else None
    if state_name is None:
        raise ValueError(f"unsupported election state: {state}")
    display_name = f"{parsed_date:%B %Y} {election_type.title()}"
    archive_name = (
        f"{parsed_date:%B} {parsed_date.day}, {parsed_date:%Y} {state_name} {election_type}"
    )
    return display_name, archive_name


def page_title(*, page: str | None = None, election: str | None = None) -> str:
    """Build the shared title grammar for every site surface."""

    parts = [part for part in (page, election, SITE_NAME) if part]
    return " — ".join(parts)


# Brand palette, duplicated from base.css tokens because the icon also ships
# as a standalone favicon.svg where no stylesheet exists.
_NAVY = "#102a43"
_TEAL = "#087f73"
_MINT = "#9ee7df"
_PAPER = "#fbfaf6"

# Minimal 24x24 Lucide stroke glyphs for icon action clusters. `currentColor`
# follows the surrounding link or button color, so no separate on-dark variant
# is needed the way the brand mark requires.
_SHARE_ICON_SVG = (
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img"'
    ' aria-hidden="true" focusable="false">'
    '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>'
    '<line x1="8.6" y1="10.6" x2="15.4" y2="6.4"/><line x1="8.6" y1="13.4" x2="15.4" y2="17.6"/>'
    "</svg>"
)
_INFO_ICON_SVG = (
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img"'
    ' aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>'
    "</svg>"
)
_CLOSE_ICON_SVG = (
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img"'
    ' aria-hidden="true" focusable="false">'
    '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'
    "</svg>"
)
_ENVELOPE_ICON_SVG = (
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img"'
    ' aria-hidden="true" focusable="false">'
    '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 6 10 7 10-7"/>'
    "</svg>"
)
# The standard "mark-github" glyph (as widely shipped on open-source project
# sites, e.g. the Simple Icons project's CC0-licensed path data), fully
# filled so it reads at footer icon size without stroke weight. Built from
# explicitly space-joined chunks (rather than adjacent string literals) so a
# missing separator at a chunk boundary cannot silently fuse two coordinates.
_GITHUB_MARK_PATH = " ".join(
    (
        "M12 .297c-6.63 0-12 5.373-12 12",
        "0 5.303 3.438 9.8 8.205 11.385",
        ".6.113.82-.258.82-.577",
        "0-.285-.01-1.04-.015-2.04",
        "-3.338.724-4.042-1.61-4.042-1.61",
        "-.546-1.387-1.333-1.756-1.333-1.756",
        "-1.089-.744.084-.729.084-.729",
        "1.205.084 1.838 1.236 1.838 1.236",
        "1.07 1.835 2.809 1.305 3.495.998",
        ".108-.776.417-1.305.76-1.605",
        "-2.665-.3-5.466-1.332-5.466-5.93",
        "0-1.31.465-2.38 1.235-3.22",
        "-.135-.303-.54-1.523.105-3.176",
        "0 0 1.005-.322 3.3 1.23",
        ".96-.267 1.98-.399 3-.405",
        "1.02.006 2.04.138 3 .405",
        "2.28-1.552 3.285-1.23 3.285-1.23",
        ".645 1.653.24 2.873.12 3.176",
        ".765.84 1.23 1.91 1.23 3.22",
        "0 4.61-2.805 5.625-5.475 5.92",
        ".42.36.81 1.096.81 2.22",
        "0 1.606-.015 2.896-.015 3.286",
        "0 .315.21.69.825.57",
        "C20.565 22.092 24 17.592 24 12.297",
        "c0-6.627-5.373-12-12-12",
    )
)
_GITHUB_ICON_SVG = (
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" role="img"'
    ' aria-hidden="true" focusable="false">'
    f'<path d="{_GITHUB_MARK_PATH}"/>'
    "</svg>"
)


def share_icon_svg() -> str:
    """Return the shared Lucide Share 2 glyph for an accessible action wrapper."""

    return _SHARE_ICON_SVG


def close_icon_svg() -> str:
    """Return the shared Lucide X glyph for an accessible action wrapper."""

    return _CLOSE_ICON_SVG


def site_icon_svg(size: int | None = 22, *, on_dark: bool = False) -> str:
    """The Meter icon. `on_dark` swaps to the teal-tile variant for navy bands."""
    tile, track, fill = (_TEAL, _NAVY, _MINT) if on_dark else (_NAVY, _PAPER, _TEAL)
    dimensions = f' width="{size}" height="{size}"' if size is not None else ""
    return (
        f'<svg{dimensions} viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"'
        ' role="img" aria-hidden="true" focusable="false">'
        f'<rect width="64" height="64" rx="14" fill="{tile}"/>'
        f'<rect x="10" y="25" width="44" height="14" rx="7" fill="{track}"/>'
        f'<rect x="10" y="25" width="31" height="14" rx="7" fill="{fill}"/>'
        "</svg>"
    )


def site_band_html(
    *,
    guide_href: str,
    sources_href: str,
    compare_href: str | None = None,
    about_href: str = "/about/",
    current: str | None = None,
    sources_link_data_attribute: bool = False,
    shareable: bool = True,
) -> str:
    """Slot 1 of the shell grammar (issue 192): brand, nav, and page actions.

    `current` names the nav entry for this page (`endorsements`, `comparisons`,
    `sources`, or `about`). The brand lockup links to `guide_href` — the current
    election's endorsements page — rather than `/`, which only redirects there;
    that link target is also what R3 keys the extended masthead off.

    The nav is one `<details>` disclosure at every width. Above the shell
    breakpoint CSS forces its panel visible and hides the summary, so it renders
    as the familiar inline row; below it, the summary becomes a control reading
    "Pages" and the panel drops beneath. This needs no JavaScript, which matters
    because the archived guides are frozen files.

    `shareable` follows the same flag that governs a page's social card (R2), so
    the 404 gets neither an og card nor a Share action from one property.
    `sources_link_data_attribute` adds the guide's `data-sources-link` hook so
    its script can carry the reader's live selection onto the Sources page.
    """

    def nav_link(label: str, href: str, key: str, extra: str = "") -> str:
        current_attribute = ' aria-current="page"' if current == key else ""
        return f'<a href="{html.escape(href, quote=True)}"{extra}{current_attribute}>{label}</a>'

    sources_extra = " data-sources-link" if sources_link_data_attribute else ""
    brand = (
        f'<a class="site-brand" href="{html.escape(guide_href, quote=True)}">'
        f"{site_icon_svg(on_dark=True)}<span>{SITE_NAME}</span></a>"
    )
    # Share is named in DESIGN.md's universal-glyph set, so it stays icon-only at
    # every width; the disclosure control beside it is text, matching the nav
    # links it stands in for.
    share_action = (
        '<button type="button" class="band-icon-action" data-shell-share'
        ' aria-label="Share this page" title="Share this page">'
        f"{_SHARE_ICON_SVG}</button>"
        if shareable
        else ""
    )
    share_status = (
        '<p class="visually-hidden" role="status" aria-live="polite" data-shell-share-status></p>'
        if shareable
        else ""
    )
    return (
        '<div class="site-band">'
        f"{brand}"
        '<div class="site-band-actions">'
        f"{share_action}"
        '<details class="site-band-menu">'
        "<summary>Pages</summary>"
        '<nav aria-label="Site">'
        # Reading order follows dependency: the guide is the destination, Sources
        # is what feeds it, Comparisons is a view derived from those sources, and
        # How this works explains all three.
        f"{nav_link('Endorsements', guide_href, 'endorsements')}"
        f"{nav_link('Sources', sources_href, 'sources', sources_extra)}"
        + (nav_link("Comparisons", compare_href, "comparisons") if compare_href is not None else "")
        + f"{nav_link('How this works', about_href, 'about')}"
        "</nav></details></div></div>" + share_status
    )


def site_page_head_html(
    *,
    title: str,
    tagline_html: str,
    eyebrow: str | None = None,
    mode: Literal["plain", "extended", "measured"] = "plain",
) -> str:
    """Slot 2 of the shell grammar (issue 192): one page head for every page.

    `eyebrow` is the election name on election-scoped pages and `None` on
    agnostic ones, where its absence is the only signal needed (R2). `title` is
    the page's own name, agreeing with its nav label and `<title>` (R5), and for
    election-scoped pages it is a plural noun so eyebrow and title read as one
    name — "August 2026 Primary Comparisons" (R5a).

    **`title` and `eyebrow` are escaped here; `tagline_html` is not.** The
    tagline carries inline markup on purpose — entities in the guide's copy, and
    real links on the 404 — so its caller owns escaping any value that is not a
    literal. `_about_html` shows the pattern: it passes `html.escape(...)`. The
    name says `_html` so this asymmetry is visible at the call site rather than
    only in this docstring.

    `mode` selects the head's one legal variation, as a closed set rather than
    independent flags, so a shape the grammar does not define cannot be
    expressed:

    - `plain` — the head sits below the masthead on paper.
    - `extended` — the masthead's navy runs through the head instead of stopping
      at the band. This is the single exception the brand-link target buys
      (R3/R4), and it bends no other rule: the ground-relative color rules
      already carry the eyebrow to mint and the title to white.
    - `measured` — the head takes the same ~46rem reading column its page's body
      uses, reusing the shared `.narrow-main` class. DESIGN.md § Typography
      holds that the frame is the site and the measure is the content, so a head
      whose page sets a book measure must sit on it too, or its tagline outruns
      the prose directly beneath it.
    """

    variant = {"plain": "", "extended": " extended", "measured": " narrow"}[mode]
    eyebrow_html = (
        f'<p class="page-eyebrow">{html.escape(eyebrow)}</p>' if eyebrow is not None else ""
    )
    inner = f'{eyebrow_html}<h1>{html.escape(title)}</h1><p class="page-tagline">{tagline_html}</p>'
    if mode == "measured":
        inner = f'<div class="narrow-main">{inner}</div>'
    return f'<header class="page-head{variant}">{inner}</header>'


def election_day_banner_html(
    election_date: str,
    *,
    how_to_vote_href: str = HOW_TO_VOTE_HREF,
) -> str:
    """Slot 4 of the shell grammar (issue 192): the election-day banner.

    The server renders a **tense-neutral** statement — "Election day: Tuesday,
    August 4, 2026" — because an archived guide is a frozen file that cannot know
    today's date, and a page built before an election would otherwise keep
    insisting the election is upcoming forever. A label plus a date is true in
    both eras. `election-day.mjs` then escalates it as the date nears and
    rewrites it in the past tense once the election has happened.

    The "How to vote" link is rendered unconditionally rather than added by
    script: without JavaScript, a reader before the election would otherwise lose
    the link exactly when it matters most, whereas a reader of an archived guide
    merely sees an evergreen link about how voting works. The first cost is much
    the worse of the two.

    Replaces the guide hero's old "ELECTION DAY · AUGUST 4" kicker, which stated
    the same fact in permanent chrome that could never retire it.
    """

    parsed = date.fromisoformat(election_date)
    full = f"{parsed:%A}, {parsed:%B} {parsed.day}, {parsed:%Y}"
    short = f"{parsed:%A}, {parsed:%B} {parsed.day}"
    return (
        f'<p class="election-day" data-election-day="{html.escape(election_date, quote=True)}"'
        f' data-election-day-full="{html.escape(full, quote=True)}"'
        f' data-election-day-short="{html.escape(short, quote=True)}">'
        f'<span class="election-day-when" data-election-day-when>'
        f"<b>Election day:</b> {html.escape(full)}</span>"
        '<span class="election-day-separator" aria-hidden="true"> · </span>'
        f'<a class="election-day-action" href="{html.escape(how_to_vote_href, quote=True)}"'
        f"{EXTERNAL_LINK_ATTRIBUTES}>How to vote</a>"
        "</p>"
    )


def site_footer_band_html(
    *,
    project_url: str,
    audit_html: str,
    about_href: str = "/about/",
) -> str:
    """The navy footer band shared by every page except the 404 (item L55).

    Mirrors `site_band_html`: the same icon+wordmark lockup, linking home,
    on the left; a centered icon action cluster on the right — Contact,
    source/audit files on GitHub, and How this works.

    Share moved to the masthead in issue 192, under the rule promoted to
    DESIGN.md § Site shell: *masthead = actions on the page; footer = meta about
    the site.* Issue 193 retired the generated PDF edition, taking the Printable
    PDF action with it — the browser's own print output is the printable one now.
    """

    def icon_link(label: str, href: str, svg: str, *, external: bool = False) -> str:
        escaped_href = html.escape(href, quote=True)
        # An icon-only control has no visible text to carry the new-tab hint, so
        # it goes in the accessible name instead.
        escaped_label = html.escape(label + (OPENS_IN_NEW_TAB if external else ""), quote=True)
        return (
            f'<a class="footer-icon-action" href="{escaped_href}" aria-label="{escaped_label}"'
            f' title="{escaped_label}"{EXTERNAL_LINK_ATTRIBUTES if external else ""}>{svg}</a>'
        )

    contact_action = icon_link("Contact", CONTACT_HREF, _ENVELOPE_ICON_SVG)
    github_action = icon_link(
        "Source and audit files on GitHub", project_url, _GITHUB_ICON_SVG, external=True
    )
    about_action = icon_link("How this works", about_href, _INFO_ICON_SVG)
    brand = (
        f'<a class="site-footer-brand" href="/" aria-label="{SITE_NAME}">'
        f"{site_icon_svg(on_dark=True)}"
        f"<span>{SITE_NAME}</span></a>"
    )
    return (
        '<div class="site-footer-band">'
        f"{brand}"
        f'<div class="site-footer-audit">{audit_html}</div>'
        '<div class="site-footer-actions">'
        f"{contact_action}{github_action}{about_action}"
        "</div></div>"
    )


def site_footer_audit_html(
    *,
    data_updated_date: str,
    site_updated_date: str,
    data_version: str,
    git_commit: str,
    project_url: str,
    data_href: str,
    source_panel_id: str | None = None,
    source_panel_hash: str | None = None,
) -> str:
    """Render the shared two-line data/site provenance grammar."""
    commit_url = html.escape(f"{project_url}/commit/{git_commit}", quote=True)
    escaped_data_href = html.escape(data_href, quote=True)
    escaped_data_date = html.escape(data_updated_date)
    escaped_site_date = html.escape(site_updated_date)
    escaped_data_version = html.escape(data_version[:12])
    panel = ""
    if source_panel_id is not None and source_panel_hash is not None:
        panel = f" · Panel {html.escape(source_panel_id)} ({html.escape(source_panel_hash[:12])})"
    return (
        '<span class="audit-data">'
        f"Data updated {escaped_data_date} "
        f'(<a href="{escaped_data_href}">{escaped_data_version}</a>){panel}'
        '</span><span class="audit-join" aria-hidden="true"> · </span>'
        '<span class="audit-site">'
        f"Site updated {escaped_site_date} "
        f'(<a href="{commit_url}"{EXTERNAL_LINK_ATTRIBUTES}>{html.escape(git_commit[:12])}</a>)'
        "</span>"
    )


def site_head_links_html(origin: str, *, shareable: bool = True) -> str:
    """The brand-asset head block shared by every page: icons and og:image.

    `origin` is the canonical https origin used for the absolute og:image URL;
    the icon links stay root-relative so any origin serves its own copies.
    `shareable` controls the accompanying twitter:card tag: every page meant
    to be shared pairs og:image with summary_large_image (the default); the
    404 page passes shareable=False to keep the wide image without implying
    the page itself is a shareable card.
    """
    escaped_origin = html.escape(origin, quote=True)
    twitter_card = (
        '<meta name="twitter:card" content="summary_large_image">\n  ' if shareable else ""
    )
    return (
        f"{twitter_card}"
        f'<meta property="og:image" content="{escaped_origin}/og-image.png">\n'
        '  <link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
        '  <link rel="icon" href="/favicon-32.png" type="image/png" sizes="32x32">\n'
        '  <link rel="apple-touch-icon" href="/apple-touch-icon.png">'
    )


def favicon_svg() -> str:
    """The standalone SVG favicon asset (navy tile on any tab background)."""
    return site_icon_svg(None)
