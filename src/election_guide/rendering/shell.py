"""Shared cross-page chrome: the site name, brand icon, and slim nav band.

Every page on the site (the guide, the sources editor, About, and the
election archive) renders this exact band so the cross-page chrome has one
implementation. The icon is "The Meter": the guide's agreement meter distilled
into a mark, with a left-anchored fill matching the on-page meters.
"""

from __future__ import annotations

import html

SITE_NAME = "Seattle Elections Guide"

# Brand palette, duplicated from base.css tokens because the icon also ships
# as a standalone favicon.svg where no stylesheet exists.
_NAVY = "#102a43"
_TEAL = "#087f73"
_MINT = "#9ee7df"
_PAPER = "#fbfaf6"


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
    about_href: str = "/about/",
    current: str | None = None,
    show_brand: bool = True,
    sources_link_data_attribute: bool = False,
) -> str:
    """The slim navy nav band shared by every page.

    `current` names the nav entry for this page (`endorsements`, `sources`, or
    `about`). The guide page passes `show_brand=False` because its hero h1 is
    the brand; every other page carries the icon-plus-name lockup linking home.
    `sources_link_data_attribute` adds the guide's `data-sources-link` hook so
    its script can carry the reader's live selection onto the Sources page.
    """

    def nav_link(label: str, href: str, key: str, extra: str = "") -> str:
        current_attribute = ' aria-current="page"' if current == key else ""
        return f'<a href="{html.escape(href, quote=True)}"{extra}{current_attribute}>{label}</a>'

    sources_extra = " data-sources-link" if sources_link_data_attribute else ""
    brand = (
        f'<a class="site-brand" href="/">{site_icon_svg(on_dark=True)}<span>{SITE_NAME}</span></a>'
        if show_brand
        else ""
    )
    return (
        '<div class="site-band">'
        f"{brand}"
        '<nav aria-label="Site">'
        f"{nav_link('Endorsements', guide_href, 'endorsements')}"
        f"{nav_link('Sources', sources_href, 'sources', sources_extra)}"
        f"{nav_link('About', about_href, 'about')}"
        "</nav></div>"
    )


def site_head_links_html(origin: str) -> str:
    """The brand-asset head block shared by every page: icons and og:image.

    `origin` is the canonical https origin used for the absolute og:image URL;
    the icon links stay root-relative so any origin serves its own copies.
    """
    escaped_origin = html.escape(origin, quote=True)
    return (
        f'<meta property="og:image" content="{escaped_origin}/og-image.png">\n'
        '  <link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
        '  <link rel="icon" href="/favicon-32.png" type="image/png" sizes="32x32">\n'
        '  <link rel="apple-touch-icon" href="/apple-touch-icon.png">'
    )


def favicon_svg() -> str:
    """The standalone SVG favicon asset (navy tile on any tab background)."""
    return site_icon_svg(None)
