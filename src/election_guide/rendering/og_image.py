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
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from election_guide.publication.models import PublicationRace, PublicationSource
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

# Meter v2's frame and tongue-tip radii are spec'd as fractions of the 2rem
# frame height every other chrome uses (docs/METER_V2.md, Anatomy and
# geometry: ".4rem corner radius", "Tongue tip radius: .25rem"); this card's
# own frame is a fixed 56px rather than 2rem, so the two curves are carried
# forward as that same fraction of *this* chrome's own height rather than a
# literal rem value with no stylesheet to resolve it against.
METER_FRAME_RADIUS = round(METER_HEIGHT * 0.4 / 2)
METER_TONGUE_RADIUS = round(METER_HEIGHT * 0.25 / 2)

# The brand palette, from base.css's tokens by way of `rendering/shell.py`,
# which duplicates them for the same reason: the mark is also drawn where no
# stylesheet exists.
NAVY = (16, 42, 67)
TEAL = (8, 127, 115)
MINT = (158, 231, 223)
PAPER = (251, 250, 246)
WHITE = (255, 255, 255)
AMBER = (217, 144, 0)
SKY = (155, 184, 209)

# Meter v2's own palette (docs/METER_V2.md, Color), duplicated from base.css
# for the same reason as the brand palette above: this module draws pixels,
# not stylesheet rules, so it cannot read a custom property. Duplication is
# the whole exposure, and one drift test closes it --
# `test_og_image.py::test_the_meter_palette_mirrors_base_css` parses
# `base.css`'s own hex values and holds every constant below to them in both
# directions, so a token that moves on either side fails `make check` rather
# than a reader's eye. (Before this ticket, `AMBER` above and the v1 `TRACK`
# it replaces were never held to base.css at all -- AMBER's literal RGB above
# predates this test and did not match `--amber` until this change corrected
# it; that drift is exactly the failure mode the test now closes off.)
METER_TRACK = (237, 242, 244)  # --meter-track
LINE_STRONG = (130, 154, 177)  # --line-strong, the frame's own border
MUTED = (82, 96, 109)  # --muted, the N/A label and the low-fill guard's ink
METER_TIE_DEEP = (138, 93, 18)  # --meter-tie-deep
METER_TRAIL_SLATE = (125, 149, 173)  # --meter-trail-slate
METER_TRAIL_TAUPE = (169, 158, 138)  # --meter-trail-taupe
METER_TRAIL_PLUM = (160, 130, 150)  # --meter-trail-plum

# `meter_candidate_colors` (rendering/context.py) names a candidate's color as
# one of these CSS custom properties -- the fixed pool every chrome draws
# from before `_meter_stepped_color` starts stepping a pool-exhausted
# candidate toward the track (a fourth trailing candidate, a third tied
# leader). `_resolve_meter_color` below is the whole of this module's answer
# to "the color source of truth is a CSS custom property and this module has
# no CSS engine": it reads the same string every stylesheet declaration would,
# and resolves it to the RGB this module can paint.
_METER_TOKEN_RGB: dict[str, tuple[int, int, int]] = {
    "var(--teal)": TEAL,
    "var(--amber)": AMBER,
    "var(--meter-tie-deep)": METER_TIE_DEEP,
    "var(--meter-trail-slate)": METER_TRAIL_SLATE,
    "var(--meter-trail-taupe)": METER_TRAIL_TAUPE,
    "var(--meter-trail-plum)": METER_TRAIL_PLUM,
}

# `_meter_stepped_color`'s own pool-exhaustion shape: a `color-mix()` toward
# `--meter-track` at a percentage that steps down as the pool is overrun
# again. Matched structurally rather than evaluated as CSS -- this module
# still never runs a CSS engine -- because the shape is small and stable
# enough that mirroring its two captures (which color, what percent) is
# simpler and more legible than vendoring one.
_COLOR_MIX_RE = re.compile(
    r"^color-mix\(in srgb, (?P<base>[^ ]+) (?P<percent>\d+)%, var\(--meter-track\)\)$"
)


def _resolve_meter_color(css_value: str) -> tuple[int, int, int]:
    """One `meter_candidate_colors` value, resolved to the RGB this module
    paints (docs/METER_V2.md, Color).

    Deliberately thin: *which* color a candidate gets -- the leader/tie/trail
    ranking, and when a pool is exhausted -- stays `meter_candidate_colors`'s
    own decision, read here rather than re-derived, so the "one meter" rule
    covers ranking as much as it covers hue. Only the two shapes that function
    can ever emit are handled: a bare token naming one of #312's tokens, or
    the stepped `color-mix()` toward the track once a pool runs out.
    """
    match = _COLOR_MIX_RE.match(css_value)
    if match is None:
        return _METER_TOKEN_RGB[css_value]
    base = _METER_TOKEN_RGB[match.group("base")]
    percent = int(match.group("percent"))
    return _blend(base, METER_TRACK, percent)


def _blend(
    base: tuple[int, int, int], toward: tuple[int, int, int], percent: int
) -> tuple[int, int, int]:
    """`percent`% `base`, the rest `toward` -- `color-mix(in srgb, base
    percent%, toward)`'s own arithmetic, read on two RGB triples instead of
    evaluated by a CSS engine this module does not have."""
    return (
        round(base[0] * percent / 100 + toward[0] * (100 - percent) / 100),
        round(base[1] * percent / 100 + toward[1] * (100 - percent) / 100),
        round(base[2] * percent / 100 + toward[2] * (100 - percent) / 100),
    )


@dataclass(frozen=True)
class MeterBlockPaint:
    """One `MeterBlock` (rendering/context.py), colored for this module's own
    drawing (docs/METER_V2.md).

    Mirrors `MeterBlockRender` field for field except `style`, which names its
    colors as CSS custom properties this module has no engine to read;
    `top`/`bottom` are the same colors `_resolve_meter_color` resolves to RGB
    instead — identical for a solid block, the split's own two halves for a
    split, the same shorthand `_meter_block_facing` uses on the CSS side.
    Carries no seam data: the resting state's seams are invisible by
    construction on every chrome (docs/METER_V2.md, Seams), so nothing here
    ever draws one (Decision log #23).
    """

    type: str
    width: int
    top: tuple[int, int, int]
    bottom: tuple[int, int, int]
    tongue_corner_start: bool
    tongue_corner_end: bool


@dataclass(frozen=True)
class RaceCard:
    """Everything the card states, resolved before anything is drawn.

    A dataclass rather than eight parameters so the caller cannot silently pass
    them in the wrong order, and so the rendering below reads as layout only.
    """

    election_name: str
    race_label: str
    recommendation: str
    na: bool
    """True where the race has no measurable consensus (docs/METER_V2.md, Edge
    states) — the meter still draws, as an empty track under a muted "N/A",
    exactly as every other v2 chrome renders the same state; `blocks` is empty
    and `fill_percent`/`low_fill`/`no_majority` carry no meaning."""
    low_fill: bool
    no_majority: bool
    fill_percent: int
    percentage_label: str
    """The meter's own resting text: the literal "N/A" for `na` (the
    `meter-unavailable-label` mirror's own literal, `tests/mirrors.json`) or
    the leader's share exactly as the page prints it otherwise."""
    blocks: tuple[MeterBlockPaint, ...]
    support: str


def _meter_block_paints(
    race: PublicationRace, sources: dict[str, PublicationSource]
) -> tuple[MeterBlockPaint, ...]:
    """This race's blocks, laid out and colored for Python's own drawing.

    `meter_layout_blocks` is meter v2's one layout algorithm (docs/METER_V2.md,
    Implementation notes: "It cannot be split into add-then-retire") and
    `meter_candidate_colors` is its one color-ranking rule; both are read
    verbatim rather than re-derived, so this module's whole job is resolving
    the colors they hand back to RGB (`_resolve_meter_color`), not deciding
    which candidate gets which one.
    """
    endorsements = context.meter_endorsements(race, sources)
    standings = context.meter_standings(endorsements)
    colors = {
        candidate_id: _resolve_meter_color(value)
        for candidate_id, value in context.meter_candidate_colors(
            standings,
            frozenset(race.support_leader_candidate_ids),
            has_majority=not context.has_no_majority(race),
        ).items()
    }
    return tuple(
        MeterBlockPaint(
            type=block.type,
            width=block.width,
            top=colors[block.candidate_ids[0]],
            bottom=colors[block.candidate_ids[-1]],
            tongue_corner_start=block.tongue_corner_start,
            tongue_corner_end=block.tongue_corner_end,
        )
        for block in context.meter_layout_blocks(endorsements)
    )


def race_card(
    race: PublicationRace, sources: dict[str, PublicationSource], *, election_name: str
) -> RaceCard:
    """What one race's card says, from the same values the page renders.

    Nothing here is recomputed: the recommendation, the meter's blocks and
    colors, and the support sentence are the audited view model's own (built
    from the same `rendering/context.py` functions `meter_view` composes), so
    a card and the page it unfurls cannot state the result two ways.
    """
    percentage_whole = race.percentage_whole
    na = percentage_whole is None
    return RaceCard(
        election_name=election_name,
        race_label=race.race_label,
        recommendation=race.recommendation_label,
        na=na,
        # I41: below 30% fill the label rides past the leader's own blocks and
        # loses contrast against them; the guard moves it to ride after the
        # fill instead. `meter_view`'s own field mirrors this exact threshold
        # for every other chrome.
        low_fill=percentage_whole is not None and percentage_whole < 30,
        no_majority=context.has_no_majority(race),
        fill_percent=percentage_whole or 0,
        percentage_label="N/A" if na else race.percentage_label,
        blocks=() if na else _meter_block_paints(race, sources),
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

    # The meter always draws, N/A included (docs/METER_V2.md, Edge states: an
    # empty track under a muted label, not an absent row) — every card's
    # support text sits at the same fixed offset past it.
    _draw_meter(image, MARGIN, METER_TOP, card)
    support_font = _font(REGULAR_FONT, 26)
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


def _draw_meter(image: Image.Image, x: int, y: int, card: RaceCard) -> None:
    """The segmented meter, resting-state only (docs/METER_V2.md).

    Only the pointer-devices row of The discovery model applies: candidate
    runs as stacked solid fills, split bands as divided blocks, the resting
    percentage riding the leader's fill — a social card can never be hovered,
    focused, or tapped, so there is no reveal to port and no seam to draw
    (Decision log #23; `MeterBlockPaint` carries no seam data at all). Tongue-
    tip rounding stays: it is the resting block's own shape, not a reveal.

    The blocks paint onto their own layer at the meter's own origin, then
    paste onto the card through a rounded-rectangle mask — this module's
    equivalent of `.screen-meter { overflow: hidden; border-radius: .4rem }`,
    which is what keeps a square block corner from poking past the frame's own
    soft corner the way an un-clipped rectangle would.
    """
    width, height = METER_WIDTH, METER_HEIGHT
    layer = Image.new("RGB", (width, height), METER_TRACK)
    if not card.na:
        _draw_meter_blocks(ImageDraw.Draw(layer), card.blocks, width, height)
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width, height), radius=METER_FRAME_RADIUS, fill=255
    )
    image.paste(layer, (x, y), mask)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (x, y, x + width, y + height), radius=METER_FRAME_RADIUS, outline=LINE_STRONG, width=1
    )

    font = _font(BOLD_FONT, 34)
    if card.na:
        text_x, colour = x + 26, MUTED
    else:
        # The label rides the leader's own fill, and drops to the track's own
        # muted ink past the point where white would bleed onto it (I41) —
        # `--meter-track` is pale, exactly as it is on every other chrome, so
        # the guard's ink is the site's own `--muted`, not an on-dark choice.
        filled = round(width * card.fill_percent / 100)
        text_x = x + filled + 20 if card.low_fill else x + 26
        colour = MUTED if card.low_fill else (NAVY if card.no_majority else WHITE)
    draw.text(
        (text_x, y + (height - _line_height(font)) // 2),
        card.percentage_label,
        font=font,
        fill=colour,
    )


def _draw_meter_blocks(
    draw: ImageDraw.ImageDraw, blocks: tuple[MeterBlockPaint, ...], width: int, height: int
) -> None:
    """Every block, left to right, at the widths `meter_layout_blocks` gave
    them (docs/METER_V2.md, Anatomy and geometry: "Block width = track ÷
    endorsement count").

    Edges are cumulative rounded positions, not `width * block_width`
    rounded per block: rounding each block's own width independently would
    drift the total away from the track's own pixel width by the count of
    blocks: rounding each boundary's *running* position instead keeps every
    seam pixel-exact and still lands the last block's right edge on `width`.
    """
    total = sum(block.width for block in blocks)
    mid = height // 2
    left = 0
    cumulative = 0
    for block in blocks:
        cumulative += block.width
        right = round(width * cumulative / total)
        if block.type == "solid":
            draw.rectangle((left, 0, right, height), fill=block.top)
        else:
            _draw_split_block(draw, left, right, mid, height, block)
        left = right


def _draw_split_block(
    draw: ImageDraw.ImageDraw,
    left: int,
    right: int,
    mid: int,
    height: int,
    block: MeterBlockPaint,
) -> None:
    """One split block: two halves, each rounding its own single interior
    corner where the block is a band's first or last (docs/METER_V2.md,
    Splits: the tongue rule — "a curve appears only where two candidates'
    colors meet")."""
    if block.tongue_corner_start or block.tongue_corner_end:
        _draw_tongue_backdrop(draw, left, right, height, block)
    # The top half rounds its own bottom-right corner exactly where a band's
    # last block reaches into the next run (`.meter-tongue-end .meter-half-top`,
    # guide-race.css); `corners` is (top-left, top-right, bottom-right,
    # bottom-left).
    draw.rounded_rectangle(
        (left, 0, right, mid),
        radius=METER_TONGUE_RADIUS,
        fill=block.top,
        corners=(False, False, block.tongue_corner_end, False),
    )
    # The bottom half rounds its own top-left corner exactly where a band's
    # first block reaches back into the run before it
    # (`.meter-tongue-start .meter-half-bottom`).
    draw.rounded_rectangle(
        (left, mid, right, height),
        radius=METER_TONGUE_RADIUS,
        fill=block.bottom,
        corners=(block.tongue_corner_start, False, False, False),
    )


def _draw_tongue_backdrop(
    draw: ImageDraw.ImageDraw, left: int, right: int, height: int, block: MeterBlockPaint
) -> None:
    """The color a rounded tongue tip's own notch exposes: the block's own
    backdrop, painted before its two halves, so the corner a half rounds away
    reveals the *other* half's color rather than whatever sits underneath —
    the same job `--meter-tongue-bg` does as a CSS background layer
    (`meter_block_renders`, rendering/context.py), done here as paint order
    instead. A single-block band rounds both corners, so its backdrop is the
    two colors' own 90-degree split, matching `--meter-tongue-bg`'s two-stop
    gradient for that case.
    """
    if block.tongue_corner_start and block.tongue_corner_end:
        centre = (left + right) // 2
        draw.rectangle((left, 0, centre, height), fill=block.top)
        draw.rectangle((centre, 0, right, height), fill=block.bottom)
    elif block.tongue_corner_start:
        draw.rectangle((left, 0, right, height), fill=block.top)
    else:
        draw.rectangle((left, 0, right, height), fill=block.bottom)


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
