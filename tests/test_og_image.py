"""The per-race social card (issue #136).

The claims this module makes that nothing else can see. The card is a build
artifact, so a defect in it never fails a page render and never shows up in the
archive's own hashes — it shows up in a link somebody shared.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from election_guide.rendering.bundler import TEMPLATE_DIR
from election_guide.rendering.og_image import (
    AMBER,
    BOLD_FONT,
    CARD_SIZE,
    LINE_STRONG,
    MARGIN,
    METER_HEIGHT,
    METER_TIE_DEEP,
    METER_TOP,
    METER_TRACK,
    METER_TRAIL_PLUM,
    METER_TRAIL_SLATE,
    METER_TRAIL_TAUPE,
    MUTED,
    NAVY,
    REGULAR_FONT,
    TEAL,
    WHITE,
    MeterBlockPaint,
    RaceCard,
    _blend,  # pyright: ignore[reportPrivateUsage]
    _resolve_meter_color,  # pyright: ignore[reportPrivateUsage]
    _wrap,  # pyright: ignore[reportPrivateUsage]
    race_card,
    render_race_card,
)
from election_guide.rendering.shell import election_names
from tests.page_parity import published_view_model

# A codepoint in the Private Use Area, which no real font maps: rendering it
# gives the `.notdef` glyph, which is what a *missing* character looks like.
MISSING_GLYPH = ""

# Characters the published ballot's own text carries and Pillow's bundled ASCII
# face does not: the em dash separating a race from its district, the tilde in a
# candidate's name, the middle dot the kicker joins with, and the ellipsis a
# truncated label ends in. The assertion mechanism is exercised by its own
# opposite — a CJK glyph DejaVu genuinely lacks compares *equal* to `.notdef`,
# which is what makes an equality here a real failure rather than a tautology.
NON_ASCII = ("—", "ñ", "·", "…")
UNMAPPED = "漢"


def _glyph(font: ImageFont.FreeTypeFont, character: str) -> bytes:
    """One character rasterized on its own, as comparable pixels."""
    canvas = Image.new("L", (96, 96), 0)
    ImageDraw.Draw(canvas).text((8, 8), character, font=font, fill=255)
    return canvas.tobytes()


def _colours(png: bytes) -> set[object]:
    """Every distinct colour one card draws, so a tone can be asserted present."""
    with Image.open(io.BytesIO(png)) as opened:
        counted = opened.convert("RGB").getcolors(1 << 20) or []
    return {colour for _, colour in counted}


def _solid(colour: tuple[int, int, int]) -> MeterBlockPaint:
    return MeterBlockPaint(
        type="solid",
        width=1,
        top=colour,
        bottom=colour,
        tongue_corner_start=False,
        tongue_corner_end=False,
    )


def _split(
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
    *,
    tongue_start: bool = False,
    tongue_end: bool = False,
) -> MeterBlockPaint:
    return MeterBlockPaint(
        type="split",
        width=1,
        top=top,
        bottom=bottom,
        tongue_corner_start=tongue_start,
        tongue_corner_end=tongue_end,
    )


# A representative run: a 20-block teal leader, one split block naming the
# leader and the first trailing candidate (both tongue corners, since it is
# its own one-block band), and a two-block slate trailing run — enough shapes
# to exercise every branch `_draw_meter_blocks` has without claiming to be one
# race's real tally.
_DEFAULT_BLOCKS = (
    *([_solid(TEAL)] * 20),
    _split(TEAL, METER_TRAIL_SLATE, tongue_start=True, tongue_end=True),
    *([_solid(METER_TRAIL_SLATE)] * 2),
)


def _card(**overrides: object) -> RaceCard:
    defaults = {
        "election_name": "August 2026 Primary",
        "race_label": "Metropolitan King County Council — District 2",
        "recommendation": "Rebecca Saldaña",
        "na": False,
        "low_fill": False,
        "no_majority": False,
        "fill_percent": 88,
        "percentage_label": "88%",
        "blocks": _DEFAULT_BLOCKS,
        "support": "23 of 24 endorsing sources agree",
    }
    return RaceCard(**{**defaults, **overrides})  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("path", [REGULAR_FONT, BOLD_FONT])
@pytest.mark.parametrize("character", NON_ASCII)
def test_the_vendored_font_has_a_real_glyph_for_every_character_the_ballot_uses(
    path: Path, character: str
) -> None:
    """The reason the font is vendored at all.

    Pillow's bundled face is ASCII-only, so "… — District 2" and "Rebecca
    Saldaña" would rasterize as replacement boxes — a card that looks broken in
    exactly the share it exists to improve. Asserted against the `.notdef` box
    itself rather than against "some ink was drawn", because `.notdef` *is* ink:
    swapping the vendored face for Pillow's default fails this.
    """
    font = ImageFont.truetype(path, size=48)
    missing = _glyph(font, MISSING_GLYPH)

    assert _glyph(font, character) != missing, (
        f"{character!r} rasterizes as the missing-glyph box in {path.name}"
    )
    # ...and the comparison is one a real gap fails: this face has no CJK.
    assert _glyph(font, UNMAPPED) == missing


def test_a_card_is_the_same_bytes_every_time_it_is_built() -> None:
    """Restaging unchanged data must produce an unchanged archive.

    Every staged file is hashed into the deployment manifest, so a card that
    varied between builds would make every restage look like a change.
    """
    card = _card()

    assert render_race_card(card) == render_race_card(card)


def test_a_card_is_the_size_every_platform_crops_from() -> None:
    with Image.open(io.BytesIO(render_race_card(_card()))) as image:
        assert image.size == CARD_SIZE
        assert image.format == "PNG"


def test_every_race_on_the_ballot_fits_inside_its_own_card() -> None:
    """The layout claim, measured rather than eyeballed.

    The label and the pick grow downward from a fixed top while the meter row is
    pinned to a fixed baseline, so the way this breaks is a long name running
    into the numbers or off the bottom edge. Asserted as ink inside the margins,
    over every race the published ballot actually carries.
    """
    view_model = published_view_model()
    source_by_id = {source.id: source for source in view_model.sources}
    election_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    width, height = CARD_SIZE

    for section in view_model.sections:
        for race in section.races:
            data = render_race_card(race_card(race, source_by_id, election_name=election_name))
            with Image.open(io.BytesIO(data)) as opened:
                image = opened.convert("RGB")
            background = image.getpixel((0, 0))
            # Everything that is not the navy ground, sampled on a coarse grid:
            # the claim is about margins, and a per-pixel sweep of thirty-odd
            # 1200x630 cards would cost far more than it proves.
            ink = [
                (x, y)
                for y in range(0, height, 4)
                for x in range(0, width, 4)
                if image.getpixel((x, y)) != background
            ]
            assert ink, f"{race.id} rendered a blank card"
            assert min(x for x, _ in ink) >= MARGIN - 4, f"{race.id} draws past the left margin"
            assert max(x for x, _ in ink) <= width - MARGIN + 4, (
                f"{race.id} draws past the right margin"
            )
            assert min(y for _, y in ink) >= MARGIN - 4, f"{race.id} draws above the top margin"
            assert max(y for _, y in ink) <= height - MARGIN + 4, (
                f"{race.id} draws past the bottom margin"
            )


def test_a_name_too_long_for_its_lines_ends_in_an_ellipsis() -> None:
    """A card is a summary; a clipped word reads as a fault rather than brevity."""
    font = ImageFont.truetype(BOLD_FONT, size=36)
    lines = _wrap(" ".join(["Metropolitan"] * 40), font, 1056, 3)

    assert len(lines) == 3
    assert lines[-1].endswith("…")


def test_a_race_with_no_measurable_share_draws_an_empty_track_and_an_n_a_label() -> None:
    """N/A follows the site's own edge-state rule (docs/METER_V2.md, Edge
    states): an empty track under a muted "N/A", not an absent meter row —
    what this module drew before this ticket, back when the track was its own
    private v1 color rather than `--meter-track`.
    """
    na = render_race_card(_card(na=True, blocks=(), percentage_label="N/A"))
    with_meter = render_race_card(_card())

    assert na != with_meter
    # The track color shows only where there is no meter to fill it: unlike
    # v1's partial fill, meter v2's blocks always cover the meter's whole
    # width regardless of the leader's share, so a card with real blocks never
    # exposes the track underneath them.
    assert METER_TRACK in _colours(na)
    assert METER_TRACK not in _colours(with_meter)
    assert MUTED in _colours(na)


def test_a_leader_short_of_a_majority_takes_the_differ_family() -> None:
    """docs/DESIGN.md, Data display: default styling never overstates confidence."""
    majority = render_race_card(_card())
    no_majority = render_race_card(
        _card(
            no_majority=True,
            fill_percent=50,
            percentage_label="50%",
            blocks=(_solid(AMBER),) * 20 + (_solid(METER_TRAIL_SLATE),) * 3,
        )
    )

    assert majority != no_majority
    # The amber the meter switches to, never a hue of its own.
    assert AMBER in _colours(no_majority)
    assert AMBER not in _colours(majority)


def test_a_tied_field_takes_the_tie_amber_family() -> None:
    """Two leaders neither of whom has a majority (docs/METER_V2.md, Color):
    the deeper of the two tie ambers, never a hue a solo leader would draw."""
    tied = render_race_card(
        _card(
            no_majority=True,
            fill_percent=50,
            percentage_label="50%",
            blocks=(_solid(AMBER),) * 10 + (_solid(METER_TIE_DEEP),) * 10,
        )
    )

    assert METER_TIE_DEEP in _colours(tied)


def test_a_trailing_field_draws_every_muted_hue_it_names() -> None:
    """Three trailing candidates read as three distinguishable, recessive
    hues (docs/METER_V2.md, Color) — not one undifferentiated "everyone else"
    tone."""
    card = _card(
        blocks=(_solid(TEAL),) * 10
        + (_solid(METER_TRAIL_SLATE),) * 4
        + (_solid(METER_TRAIL_TAUPE),) * 3
        + (_solid(METER_TRAIL_PLUM),) * 2
    )
    colours = _colours(render_race_card(card))

    assert {METER_TRAIL_SLATE, METER_TRAIL_TAUPE, METER_TRAIL_PLUM} <= colours


def test_a_split_blocks_tongue_tip_rounds_toward_its_partners_colour() -> None:
    """The corner rule, as pixels (docs/METER_V2.md, Splits: the tongue rule:
    "a curve appears only where two candidates' colors meet").

    A one-block band rounds both of its own interior corners, and each
    rounded-away notch shows the *other* half's color underneath — the same
    job `--meter-tongue-bg` does in CSS (`meter_block_renders`,
    rendering/context.py), asserted here on the one block a hand-built,
    single-block layout can isolate. The block spans the meter's whole width
    (`METER_WIDTH`, `METER_HEIGHT` = 420x56), so with the frame radius
    (`METER_FRAME_RADIUS` = 11) and the tongue radius (`METER_TONGUE_RADIUS` =
    7) both fixed, two hand-picked pixels settle it without depending on
    either constant's exact value: one a few pixels inside the bottom half's
    own rounded top-left corner (inside the tongue's 7px radius, so the
    rounding has carved it away and the backdrop -- the top color -- shows
    through) and one further along the same edge, still inside the frame's
    own 11px corner exclusion but outside the tongue's tighter one (so the
    bottom half's own color paints normally).
    """
    card = _card(blocks=(_split(TEAL, METER_TRAIL_SLATE, tongue_start=True, tongue_end=True),))
    with Image.open(io.BytesIO(render_race_card(card))) as opened:
        image = opened.convert("RGB")

    mid = METER_TOP + METER_HEIGHT // 2
    assert image.getpixel((MARGIN + 1, mid + 1)) == TEAL
    assert image.getpixel((MARGIN + 30, mid + 10)) == METER_TRAIL_SLATE


def test_the_meter_frame_matches_the_shared_border_token() -> None:
    """The frame's own `--line-strong` border, drawn regardless of edge state."""
    colours = _colours(render_race_card(_card()))

    assert LINE_STRONG in colours


def test_a_card_states_the_races_own_audited_result() -> None:
    """Nothing here is recomputed: the card and the page cannot disagree."""
    view_model = published_view_model()
    source_by_id = {source.id: source for source in view_model.sources}
    race = next(
        race
        for section in view_model.sections
        for race in section.races
        if race.percentage_whole is not None
    )

    card = race_card(race, source_by_id, election_name="August 2026 Primary")

    assert card.race_label == race.race_label
    assert card.recommendation == race.recommendation_label
    assert card.na is False
    assert card.percentage_label == race.percentage_label
    assert card.fill_percent == race.percentage_whole
    assert len(card.blocks) > 0


def test_resolve_meter_color_reads_a_bare_token() -> None:
    assert _resolve_meter_color("var(--teal)") == TEAL
    assert _resolve_meter_color("var(--meter-trail-slate)") == METER_TRAIL_SLATE


def test_resolve_meter_color_reads_a_pool_exhaustion_step() -> None:
    """`_meter_stepped_color` (rendering/context.py) starts stepping a
    pool-exhausted candidate's color toward the track once the fixed three-hue
    trailing pool -- or the two-hue tie pool -- runs out. This is that shape,
    matched structurally rather than run through a CSS engine this module
    does not have.
    """
    resolved = _resolve_meter_color(
        "color-mix(in srgb, var(--meter-trail-plum) 78%, var(--meter-track))"
    )

    assert resolved == _blend(METER_TRAIL_PLUM, METER_TRACK, 78)


def test_blend_is_the_color_mix_percentage_split() -> None:
    assert _blend((0, 0, 0), (100, 100, 100), 100) == (0, 0, 0)
    assert _blend((0, 0, 0), (100, 100, 100), 0) == (100, 100, 100)
    assert _blend((0, 100, 0), (100, 0, 100), 50) == (50, 50, 50)


# Every meter v2 token this module draws with, held to `base.css`'s own hex
# values in both directions -- the "one source of truth" this ticket's own
# color decision requires (docs/METER_V2.md, Color; #312's tokens). A mirrors
# module was not the right shape for a CSS custom property (`tests/mirrors.json`
# derives cross-language *function* mirrors from Python, JS, and Jinja source;
# a `:root` declaration is none of those), so this is a small, purpose-built
# drift check instead of either a hand-copied literal with no proof or a
# codegen step disproportionate to nine constants.
_TOKEN_RE = re.compile(r"--([\w-]+):\s*#([0-9a-fA-F]{6});")


def _base_css_tokens() -> dict[str, tuple[int, int, int]]:
    source = (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8")
    return {
        name: (int(hexcode[0:2], 16), int(hexcode[2:4], 16), int(hexcode[4:6], 16))
        for name, hexcode in _TOKEN_RE.findall(source)
    }


@pytest.mark.parametrize(
    ("token", "constant"),
    [
        ("teal", TEAL),
        ("amber", AMBER),
        ("navy", NAVY),
        ("white", WHITE),
        ("muted", MUTED),
        ("line-strong", LINE_STRONG),
        ("meter-track", METER_TRACK),
        ("meter-tie-deep", METER_TIE_DEEP),
        ("meter-trail-slate", METER_TRAIL_SLATE),
        ("meter-trail-taupe", METER_TRAIL_TAUPE),
        ("meter-trail-plum", METER_TRAIL_PLUM),
    ],
)
def test_the_meter_palette_mirrors_base_css(token: str, constant: tuple[int, int, int]) -> None:
    assert _base_css_tokens()[token] == constant, (
        f"og_image.py's own copy of --{token} has drifted from base.css; a Python image "
        "renderer has no CSS engine to read the token from directly, so this hand-kept "
        "mirror is the one source of truth docs/METER_V2.md's Color section requires -- "
        "update the constant in rendering/og_image.py to match."
    )
