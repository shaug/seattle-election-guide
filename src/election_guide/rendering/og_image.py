"""The per-race social card, rasterized at build time (issue #136).

Every link the site publishes used to unfurl as the same site-wide brand card,
because a URL fragment is never sent to a crawler and so a "shared race" was
just the guide again. Race detail now has its own address, and this module
gives that address its own picture: the race, the consensus pick, the agreement
share, and how many sources are behind it.

Build time, not request time. One PNG per race is written into that race's
output directory by `hosting/pages.py`, so the published archive stays a
directory of static files with no server compute anywhere in it.

Pillow rather than a headless browser: the brand mark is four rectangles and
the card is five lines of text, so a screenshot pipeline would buy nothing and
cost a Chrome launch per race.

**The font is vendored.** Pillow's bundled face is a small ASCII bitmap, and
this site's own copy is not ASCII: race labels carry an em dash ("… — District
2") and candidate names carry diacritics ("Rebecca Saldaña"), both of which
would rasterize as replacement boxes. `fonts/DejaVuSans.ttf` and its bold
companion travel with the repository under `fonts/LICENSE-DejaVu.txt`; they are
a build input and are never served to a reader.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from election_guide.publication.models import PublicationRace
from election_guide.rendering import context
from election_guide.rendering.shell import SITE_NAME

FONT_DIR = Path(__file__).parent / "fonts"
REGULAR_FONT = FONT_DIR / "DejaVuSans.ttf"
BOLD_FONT = FONT_DIR / "DejaVuSans-Bold.ttf"

# The size every social platform crops from, and the one `summary_large_image`
# is specified against (issue #135 established the tag set this fills in).
CARD_SIZE = (1200, 630)
MARGIN = 72

# The vertical grid, stated once because two of these positions are load
# bearing: the meter row is pinned so every card puts its numbers in the same
# place, and the label's top is what leaves exactly enough room above it for the
# longest label and the longest pick.
EYEBROW_TOP = 152
LABEL_TOP = 196
METER_TOP = 498
METER_WIDTH = 420
METER_HEIGHT = 56

# The brand palette, from base.css's tokens by way of `rendering/shell.py`,
# which duplicates them for the same reason: the mark is also drawn where no
# stylesheet exists.
NAVY = (16, 42, 67)
TEAL = (8, 127, 115)
MINT = (158, 231, 223)
PAPER = (251, 250, 246)
WHITE = (255, 255, 255)
AMBER = (191, 118, 26)
SKY = (155, 184, 209)
TRACK = (28, 61, 92)


@dataclass(frozen=True)
class RaceCard:
    """Everything the card states, resolved before anything is drawn.

    A dataclass rather than five parameters so the caller cannot silently pass
    them in the wrong order, and so the rendering below reads as layout only.
    """

    election_name: str
    race_label: str
    recommendation: str
    share_label: str | None
    """The agreement share as the page prints it, or None where the page prints
    `N/A` — a race with no measurable consensus draws no meter at all rather
    than an empty one labelled with an abbreviation."""
    fill_percent: int
    no_majority: bool
    support: str


def race_card(race: PublicationRace, *, election_name: str) -> RaceCard:
    """What one race's card says, from the same values the page renders.

    Nothing here is recomputed: the recommendation, the share, and the support
    sentence are the audited view model's own, so a card and the page it
    unfurls cannot state the result two ways.
    """
    return RaceCard(
        election_name=election_name,
        race_label=race.race_label,
        recommendation=race.recommendation_label,
        share_label=None if race.percentage_whole is None else race.percentage_label,
        fill_percent=race.percentage_whole or 0,
        no_majority=context.has_no_majority(race),
        support=context.race_detail_support_summary(race),
    )


def render_race_card(card: RaceCard) -> bytes:
    """Rasterize one race's social card as PNG bytes.

    Deterministic: the same card renders the same bytes, so restaging an
    unchanged election produces an unchanged archive and a subscriber sees a
    revision only when the data actually moved.
    """
    image = Image.new("RGB", CARD_SIZE, NAVY)
    draw = ImageDraw.Draw(image)
    inner = CARD_SIZE[0] - 2 * MARGIN

    _draw_brand(draw, MARGIN, MARGIN)
    _draw_text(draw, card.election_name.upper(), MARGIN, EYEBROW_TOP, _font(BOLD_FONT, 24), MINT)

    # The label and the pick grow downward from a fixed top; the meter row is
    # pinned to a fixed baseline instead, so every card in a timeline has its
    # numbers in the same place however long the race's name runs. The two
    # cannot collide: three lines of label and two of the pick end exactly at
    # the row's top, and both are ellipsized past that.
    label_end = _draw_wrapped(
        draw, card.race_label, MARGIN, LABEL_TOP, _font(BOLD_FONT, 36), PAPER, inner, 3
    )
    _draw_wrapped(
        draw, card.recommendation, MARGIN, label_end + 24, _font(BOLD_FONT, 52), WHITE, inner, 2
    )

    support_font = _font(REGULAR_FONT, 26)
    support_x = MARGIN
    if card.share_label is not None:
        _draw_meter(draw, MARGIN, METER_TOP, card)
        support_x = MARGIN + METER_WIDTH + 28
    draw.text(
        (support_x, METER_TOP + (METER_HEIGHT - _line_height(support_font)) // 2),
        card.support,
        font=support_font,
        fill=SKY,
    )

    buffer = io.BytesIO()
    # `optimize` keeps the bytes a function of the pixels alone; Pillow writes
    # no timestamp into a PNG, so nothing else here varies between builds.
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def _draw_brand(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """The Meter mark and the wordmark, in the on-dark variant the navy needs.

    The same geometry as `shell.site_icon_svg`, scaled from its 64-unit box:
    a rounded teal tile, a navy track, and a mint fill anchored left.
    """
    size = 56
    scale = size / 64
    draw.rounded_rectangle((x, y, x + size, y + size), radius=14 * scale, fill=TEAL)
    track = (x + 10 * scale, y + 25 * scale, x + 54 * scale, y + 39 * scale)
    draw.rounded_rectangle(track, radius=7 * scale, fill=NAVY)
    fill = (x + 10 * scale, y + 25 * scale, x + 41 * scale, y + 39 * scale)
    draw.rounded_rectangle(fill, radius=7 * scale, fill=MINT)
    font = _font(BOLD_FONT, 28)
    draw.text((x + size + 20, y + 14), SITE_NAME, font=font, fill=PAPER)


def _draw_meter(draw: ImageDraw.ImageDraw, x: int, y: int, card: RaceCard) -> None:
    """The one meter, as the pages draw it: left-anchored fill, label riding it.

    The no-majority state takes the differ/amber family rather than a hue of its
    own, exactly as `guide-race.css` does — default styling never overstates
    confidence (docs/DESIGN.md, Data display).
    """
    height = METER_HEIGHT
    radius = height // 2
    draw.rounded_rectangle((x, y, x + METER_WIDTH, y + height), radius=radius, fill=TRACK)
    filled = round(METER_WIDTH * min(max(card.fill_percent, 0), 100) / 100)
    if filled >= 2 * radius:
        draw.rounded_rectangle(
            (x, y, x + filled, y + height),
            radius=radius,
            fill=AMBER if card.no_majority else TEAL,
        )
    label = card.share_label or ""
    font = _font(BOLD_FONT, 34)
    # The label rides the fill, and drops to the track's own ink below the
    # threshold where white would bleed onto the pale end (I41).
    low_fill = card.fill_percent < 30
    text_x = x + filled + 20 if low_fill else x + 26
    colour = PAPER if low_fill else (NAVY if card.no_majority else WHITE)
    draw.text((text_x, y + (height - _line_height(font)) // 2), label, font=font, fill=colour)


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def _draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    colour: tuple[int, int, int],
) -> int:
    draw.text((x, y), text, font=font, fill=colour)
    return y + _line_height(font)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    colour: tuple[int, int, int],
    max_width: int,
    max_lines: int,
) -> int:
    """Draw `text` wrapped to `max_width`, truncating past `max_lines`.

    Truncation ends in an ellipsis rather than a hard cut, because a card is a
    summary and a clipped word reads as a rendering fault rather than as
    brevity.
    """
    line_height = _line_height(font)
    lines = _wrap(text, font, max_width, max_lines)
    for index, line in enumerate(lines):
        draw.text((x, y + index * line_height), line, font=font, fill=colour)
    return y + len(lines) * line_height


def _wrap(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and _text_width(candidate, font) > max_width:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) == max_lines and current and lines[-1] != current:
        lines[-1] = _ellipsize(lines[-1], font, max_width)
    return lines


def _ellipsize(line: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    ellipsis = "…"
    while line and _text_width(f"{line}{ellipsis}", font) > max_width:
        line = line[:-1].rstrip()
    return f"{line}{ellipsis}"


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = font.getbbox(text)
    return int(right - left)
