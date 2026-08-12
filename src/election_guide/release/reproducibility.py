"""Compare two builds of one release under the reproducibility contract.

Repeating a build with identical inputs has to produce the same release. What
"the same" means is not uniform across the bundle, and pretending it is cost the
project a gate that failed roughly one run in seven with nothing to show for it
but a byte offset -- the recurrence of issue #341 that #343 did not close
(issue #367).

Every artifact the pipeline computes -- the canonical data, the guide HTML, the
manifests, the validation report -- is a pure function of its inputs and is
compared byte for byte. The two screenshots are not computed, they are
*rasterized*, and the one way they are observed to differ is understood exactly.

The guide's vertical rhythm is built on rem-derived sizes, so most boxes on the
page have fractional CSS-pixel heights and land at fractional offsets: measured
on the real controls row, the shared brand band is 43.2188px tall and everything
under it inherits that fraction, putting the filter bar's origin at y=267.7344.
Painting
an edge that falls between two device pixels is not guaranteed to snap the same
way on every headless-Chrome renderer-process launch, which is the finding
issue #341 reached and #343 fixed for one element by pinning it to a whole
pixel. Pinning does not generalize: the fraction accumulates from the top of the
page, so a child's whole height still starts at a fractional origin (verified --
pinning the row's segmented controls and its select to 44px left the divergence
bit-for-bit unchanged, 2 of 30 same-input builds on the real runner).

So the contract for a raster is not a pixel budget, it is the shape of the
difference: two captures are the same capture when every pixel that differs is
explained by an edge snapping one device pixel vertically. Measured against the
real divergence, 3306 of 3326 differing pixels are explained that way and the
20 that are not are the antialiasing on the corners of two rounded rectangles
that moved with it.

That is narrow on purpose, and it is not a pixel-count tolerance in disguise. A
capture that reflowed a line, moved a card, lost a tile, failed to decode, or
drew a control in a different state changes *which pixels exist*, not merely
which row an edge rounds to, so none of it is explained by a snap and all of it
fails here exactly as a byte comparison would have.

What it does not catch, stated rather than left to be discovered: content moved
*vertically* by more than one device pixel, when the rows it moved through hold
the same colours it does -- a band of flat colour, or a shape sitting against a
flat ground. Every such pixel finds a matching neighbour one row away and the
move reads as a snap. Requiring each column to agree on a single snap direction
was tried and rejects the real divergence too: a glyph that moves one pixel is
not a clean translation of itself, so its columns legitimately disagree. What
remains caught is everything that changes the page rather than only its
vertical rounding -- reflow, lost tiles, changed states, resizes -- and a
vertical move is not this gate's only cover either: `rendering/validation.py`
checks each capture's exact viewport and ink on every build,
`tests/test_rendering.py` holds both captures to an approved coarse visual
signature, and docs/RENDERING.md requires a human to look at them after any
meaningful change.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops
from pydantic import Field

from election_guide.release.models import ARCHIVE_ROOT_DIR, ReleaseModel
from election_guide.serialization import parse_json_bytes

# Bundle-relative paths of the artifacts a browser rasterizes. Everything else
# in the bundle is computed, and computed artifacts are compared byte for byte.
RASTER_ARTIFACTS = frozenset(
    {
        "validation/rendering/screenshots/desktop.png",
        "validation/rendering/screenshots/mobile.png",
    }
)

MANIFEST_ARTIFACT = "release-manifest.json"

# How far an edge may snap: one device pixel, vertically. Not a tunable -- it is
# the phenomenon itself. Widening it would stop describing a snap and start
# describing a layout change.
SNAP_DEVICE_PIXELS = 1

# What a snap is allowed to leave unexplained: the antialiasing on the corners of
# whatever rounded box moved with it. Measured at 20 pixels on the real
# divergence (the four corners of two rounded rectangles); this is that with
# room, and it is a ratchet -- it may shrink in a pull request, never grow
# (AGENTS.md, Working rules).
MAX_UNEXPLAINED_PIXELS = 64

# A whole page snapping at once is a layout change wearing a snap's clothes, so
# how much of the capture may participate is bounded too. The real divergence
# moves 0.192% of the desktop capture (one control row); a change that shifted
# everything below the fold would be an order of magnitude past this. Also a
# ratchet.
MAX_SNAPPED_PIXEL_FRACTION = 0.01


class ArtifactDifference(ReleaseModel):
    """One reason two builds of the same release are not the same release."""

    artifact: str
    kind: Literal["membership", "bytes", "dimensions", "raster"]
    detail: str


class ReproducibilityReport(ReleaseModel):
    compared_artifact_count: int = Field(ge=0)
    differences: list[ArtifactDifference]

    @property
    def passed(self) -> bool:
        return not self.differences


def compare_release_archives(left: Path, right: Path) -> ReproducibilityReport:
    """Check that two archives are the same release under the contract above."""
    left_members = _read_archive(left)
    right_members = _read_archive(right)

    differences: list[ArtifactDifference] = []
    if list(left_members) != list(right_members):
        differences.append(
            ArtifactDifference(
                artifact="<archive>",
                kind="membership",
                detail=(
                    "archives do not contain the same entries in the same order: "
                    f"only in {left.name}: {sorted(set(left_members) - set(right_members))}; "
                    f"only in {right.name}: {sorted(set(right_members) - set(left_members))}"
                ),
            )
        )
        # Every later comparison is keyed by name, so a membership mismatch is
        # reported alone rather than as a cascade of per-entry noise.
        return ReproducibilityReport(compared_artifact_count=0, differences=differences)

    for artifact, left_bytes in left_members.items():
        right_bytes = right_members[artifact]
        if artifact in RASTER_ARTIFACTS:
            differences.extend(_compare_raster(artifact, left_bytes, right_bytes))
        elif artifact == MANIFEST_ARTIFACT:
            differences.extend(_compare_manifest(artifact, left_bytes, right_bytes))
        elif left_bytes != right_bytes:
            differences.append(
                ArtifactDifference(
                    artifact=artifact,
                    kind="bytes",
                    detail=(
                        f"computed artifact is not reproducible: {len(left_bytes)} bytes "
                        f"vs {len(right_bytes)} bytes, first difference at "
                        f"{_first_difference(left_bytes, right_bytes)}"
                    ),
                )
            )

    return ReproducibilityReport(compared_artifact_count=len(left_members), differences=differences)


def _read_archive(path: Path) -> dict[str, bytes]:
    """Bundle-relative entry name to content, in the archive's own order."""
    with zipfile.ZipFile(path) as archive:
        members: dict[str, bytes] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            prefix = f"{ARCHIVE_ROOT_DIR}/"
            if not name.startswith(prefix):
                raise ValueError(f"{path.name} contains an entry outside the bundle root: {name}")
            members[name[len(prefix) :]] = archive.read(info)
        return members


def _compare_manifest(
    artifact: str, left_bytes: bytes, right_bytes: bytes
) -> list[ArtifactDifference]:
    """Compare the manifest, holding its raster hashes to the raster contract.

    The manifest hashes every other artifact, so a raster that legitimately
    wobbled shows up here as a changed hash. Excluding those two entries is what
    keeps the manifest's own reproducibility meaningful instead of making it a
    restatement of the screenshots. Their *presence* is still required: a build
    that stopped writing a screenshot must not pass by omission.
    """
    if left_bytes == right_bytes:
        return []
    left_manifest = parse_json_bytes(left_bytes)
    right_manifest = parse_json_bytes(right_bytes)
    differences: list[ArtifactDifference] = []
    for manifest in (left_manifest, right_manifest):
        hashes = manifest.get("artifact_hashes", {})
        missing = sorted(RASTER_ARTIFACTS - set(hashes))
        if missing:
            differences.append(
                ArtifactDifference(
                    artifact=artifact,
                    kind="membership",
                    detail=f"manifest does not hash every rasterized artifact: {missing}",
                )
            )
    if differences:
        return differences

    for manifest in (left_manifest, right_manifest):
        for raster in RASTER_ARTIFACTS:
            del manifest["artifact_hashes"][raster]
    if left_manifest != right_manifest:
        return [
            ArtifactDifference(
                artifact=artifact,
                kind="bytes",
                detail=(
                    "manifest differs beyond the hashes of its rasterized artifacts, "
                    "so something computed is not reproducible"
                ),
            )
        ]
    return []


def _compare_raster(
    artifact: str, left_bytes: bytes, right_bytes: bytes
) -> list[ArtifactDifference]:
    if left_bytes == right_bytes:
        return []
    try:
        with (
            Image.open(BytesIO(left_bytes)) as opened_left,
            Image.open(BytesIO(right_bytes)) as opened_right,
        ):
            left = opened_left.convert("RGB")
            right = opened_right.convert("RGB")
    except (OSError, ValueError) as error:
        # A capture that will not decode is the worst outcome this gate can
        # find, so it is reported as a difference rather than raised as a tool
        # failure: the run should say which artifact is unreadable.
        return [
            ArtifactDifference(
                artifact=artifact,
                kind="raster",
                detail=f"capture is not a readable image: {error}",
            )
        ]
    if left.size != right.size:
        return [
            ArtifactDifference(
                artifact=artifact,
                kind="dimensions",
                detail=f"capture size changed: {left.size} vs {right.size}",
            )
        ]

    pixel_count = left.width * left.height
    changed = _changed_mask(left, right)
    changed_count = _nonzero(changed)
    changed_fraction = changed_count / pixel_count

    # A pixel is explained when it matches the other capture one row away, in
    # either direction and either image: that is what an edge snapping by one
    # device pixel looks like from the outside. This is what catches content
    # that did not merely move -- a lost tile, a reflowed line, a control drawn
    # in another state have no counterpart one row away at all.
    explained = changed
    for offset in (SNAP_DEVICE_PIXELS, -SNAP_DEVICE_PIXELS):
        explained = ImageChops.darker(
            explained, _changed_mask(left, ImageChops.offset(right, 0, offset))
        )
        explained = ImageChops.darker(
            explained, _changed_mask(ImageChops.offset(left, 0, offset), right)
        )
    unexplained = _nonzero(explained)

    if unexplained <= MAX_UNEXPLAINED_PIXELS and changed_fraction <= MAX_SNAPPED_PIXEL_FRACTION:
        return []
    if unexplained > MAX_UNEXPLAINED_PIXELS:
        reason = (
            f"{unexplained} pixels are not explained by a one-device-pixel snap "
            f"(ceiling {MAX_UNEXPLAINED_PIXELS})"
        )
    else:
        reason = (
            f"too much of the capture moved at once: {changed_fraction:.4%} "
            f"(ceiling {MAX_SNAPPED_PIXEL_FRACTION:.4%})"
        )
    return [
        ArtifactDifference(
            artifact=artifact,
            kind="raster",
            detail=(
                f"capture is not the same capture: {reason}; {changed_count} of "
                f"{pixel_count} pixels differ in region "
                f"{ImageChops.difference(left, right).getbbox()}"
            ),
        )
    ]


def _changed_mask(left: Image.Image, right: Image.Image) -> Image.Image:
    """Per-pixel maximum channel difference, as a single band.

    Deliberately not `convert("L")` on the difference: that weights the channels
    for human luminance and can round a real single-channel difference to zero.
    """
    red, green, blue = ImageChops.difference(left, right).split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue)


def _nonzero(band: Image.Image) -> int:
    return sum(band.histogram()[1:])


def _first_difference(left: bytes, right: bytes) -> int:
    for index, (one, other) in enumerate(zip(left, right, strict=False)):
        if one != other:
            return index
    return min(len(left), len(right))
