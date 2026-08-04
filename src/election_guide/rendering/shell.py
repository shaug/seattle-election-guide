"""Shared cross-page chrome: the site name, brand icon, and brand assets.

The band, page head, and footer this module used to build are now macros in
`rendering/templates/_shell.html.j2` (issue 241), so the cross-page chrome
still has one implementation each (UI polish round 4, item L54/L55) but
autoescaping is the default rather than a per-call `html.escape` discipline.
What stays here is what a template cannot express: the naming and addressing
grammar, the election-day banner's date arithmetic, and the icon sources — the
brand mark in particular, because it also ships as a standalone `favicon.svg`
where no template is involved. The icon is "The Meter": the guide's agreement meter
distilled into a mark, with a left-anchored fill matching the on-page meters.
"""

from __future__ import annotations

import html
from datetime import date

from markupsafe import Markup

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


def race_page_path(election_id: str, race_id: str) -> str:
    """One race's own page (issue #136).

    Addressing grammar rather than chrome, so it sits beside `page_title`: the
    renderer, the staging archive, and the rendered-document validator all have
    to name the same address, and a race page's URL is as much a published
    identity as its title is. Nothing is escaped or transformed here — one
    identifier space, all the way out to the address bar (docs/FRONTEND.md, The
    data contract) — because `PublicationRace.id` is constrained to a slug by
    the model, exactly as `PublishedElection.election_id` is for the segment
    above it.
    """

    return f"/e/{election_id}/races/{race_id}/"


def race_og_image_path(election_id: str, race_id: str) -> str:
    """The per-race social card, published beside the page it belongs to."""

    return f"{race_page_path(election_id, race_id)}og-image.png"


# Brand palette, duplicated from base.css tokens because the icon also ships
# as a standalone favicon.svg where no stylesheet exists.
_NAVY = "#102a43"
_TEAL = "#087f73"
_MINT = "#9ee7df"
_PAPER = "#fbfaf6"

# Minimal 24x24 Lucide stroke glyphs for icon action clusters. `currentColor`
# follows the surrounding link or button color, so no separate on-dark variant
# is needed the way the brand mark requires.
_SHARE_ICON_SVG = Markup(
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img"'
    ' aria-hidden="true" focusable="false">'
    '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>'
    '<line x1="8.6" y1="10.6" x2="15.4" y2="6.4"/><line x1="8.6" y1="13.4" x2="15.4" y2="17.6"/>'
    "</svg>"
)
_INFO_ICON_SVG = Markup(
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img"'
    ' aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>'
    "</svg>"
)
_ENVELOPE_ICON_SVG = Markup(
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
_GITHUB_ICON_SVG = Markup(
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" role="img"'
    ' aria-hidden="true" focusable="false">'
    f'<path d="{_GITHUB_MARK_PATH}"/>'
    "</svg>"
)


# The icon builders return `Markup` rather than `str` because the shell that
# embeds them is now Jinja (issue 241), where autoescaping is on and a bare
# `str` of SVG source would render as escaped text. `Markup` is a `str`
# subclass, so `favicon_svg()` still writes a plain file.
def share_icon_svg() -> Markup:
    """Return the shared Lucide Share 2 glyph for an accessible action wrapper."""

    return _SHARE_ICON_SVG


def info_icon_svg() -> Markup:
    """Return the shared Lucide Info glyph for the footer's How-this-works link."""

    return _INFO_ICON_SVG


def envelope_icon_svg() -> Markup:
    """Return the shared Lucide Mail glyph for the footer's Contact link."""

    return _ENVELOPE_ICON_SVG


def github_icon_svg() -> Markup:
    """Return the mark-github glyph for the footer's source/audit-files link."""

    return _GITHUB_ICON_SVG


def site_icon_svg(size: int | None = 22, *, on_dark: bool = False) -> Markup:
    """The Meter icon. `on_dark` swaps to the teal-tile variant for navy bands."""
    tile, track, fill = (_TEAL, _NAVY, _MINT) if on_dark else (_NAVY, _PAPER, _TEAL)
    dimensions = f' width="{size}" height="{size}"' if size is not None else ""
    return Markup(
        f'<svg{dimensions} viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"'
        ' role="img" aria-hidden="true" focusable="false">'
        f'<rect width="64" height="64" rx="14" fill="{tile}"/>'
        f'<rect x="10" y="25" width="44" height="14" rx="7" fill="{track}"/>'
        f'<rect x="10" y="25" width="31" height="14" rx="7" fill="{fill}"/>'
        "</svg>"
    )


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


def favicon_svg() -> str:
    """The standalone SVG favicon asset (navy tile on any tab background)."""
    return site_icon_svg(None)
