"""The per-race social card (issue #136).

The claims this module makes that nothing else can see. The card is a build
artifact, so a defect in it never fails a page render and never shows up in the
archive's own hashes — it shows up in a link somebody shared.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from election_guide.rendering.og_image import (
    BOLD_FONT,
    CARD_SIZE,
    MARGIN,
    REGULAR_FONT,
    RaceCard,
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


# The meter track and the no-majority amber, from `og_image`'s own palette.
TRACK = (28, 61, 92)
AMBER = (191, 118, 26)


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


def _card(**overrides: object) -> RaceCard:
    defaults = {
        "election_name": "August 2026 Primary",
        "race_label": "Metropolitan King County Council — District 2",
        "recommendation": "Rebecca Saldaña",
        "share_label": "88%",
        "fill_percent": 88,
        "no_majority": False,
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
            data = render_race_card(race_card(race, election_name=election_name))
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


def test_a_race_with_no_measurable_share_draws_no_meter() -> None:
    """An empty meter labelled `N/A` would be a quantity shown with no value."""
    without = render_race_card(_card(share_label=None, fill_percent=0))
    with_meter = render_race_card(_card())

    assert without != with_meter
    # The meter's own track colour appears when there is a meter and not
    # otherwise, which is what makes this an assertion rather than a difference.
    assert TRACK in _colours(with_meter)
    assert TRACK not in _colours(without)


def test_a_leader_short_of_a_majority_takes_the_differ_family() -> None:
    """docs/DESIGN.md, Data display: default styling never overstates confidence."""
    majority = render_race_card(_card())
    no_majority = render_race_card(_card(share_label="50%", fill_percent=50, no_majority=True))

    assert majority != no_majority
    # The amber the meter switches to, never a hue of its own.
    assert AMBER in _colours(no_majority)
    assert AMBER not in _colours(majority)


def test_a_card_states_the_races_own_audited_result() -> None:
    """Nothing here is recomputed: the card and the page cannot disagree."""
    view_model = published_view_model()
    race = next(
        race
        for section in view_model.sections
        for race in section.races
        if race.percentage_whole is not None
    )

    card = race_card(race, election_name="August 2026 Primary")

    assert card.race_label == race.race_label
    assert card.recommendation == race.recommendation_label
    assert card.share_label == race.percentage_label
    assert card.fill_percent == race.percentage_whole
