"""What "the same release, built twice" is allowed to mean.

The gate these cover replaced a `cmp` of two archives that failed roughly one CI
run in seven and reported nothing but a byte offset (issue #367, the recurrence
of #341 that #343 did not close). Every test here
is about the seam that replaced it: computed artifacts stay byte-exact, and the
two browser-rasterized screenshots are the same capture when every pixel that
differs is explained by an edge snapping one device pixel vertically.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from election_guide.release import compare_release_archives
from election_guide.release.builder import (
    _write_deterministic_zip,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.release.reproducibility import (
    MAX_SNAPPED_PIXEL_FRACTION,
    MAX_UNEXPLAINED_PIXELS,
    RASTER_ARTIFACTS,
)
from election_guide.serialization import canonical_json_bytes

GENERATED_AT = datetime(2026, 8, 12, tzinfo=UTC)
CAPTURE_SIZE = (720, 600)
CAPTURE_PIXELS = CAPTURE_SIZE[0] * CAPTURE_SIZE[1]


def _encoded(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _painted(*, band_top: int = 40) -> Image.Image:
    """A stand-in screenshot: one filled band on a light field.

    A horizontal edge is the whole subject here -- the real divergence is an
    edge that snapped a device pixel -- so the fixture is the smallest thing
    that has one. Sized in the real capture's proportions, because one of the
    ceilings is a share of the capture: a full-width edge is 0.33% of this
    fixture and 0.19% of the 1440x1200 desktop capture, so a fixture small
    enough to make one edge look like a wholesale change would test arithmetic
    the real gate never performs.
    """
    image = Image.new("RGB", CAPTURE_SIZE, (251, 250, 246))
    image.paste(Image.new("RGB", (CAPTURE_SIZE[0], 30), (16, 42, 67)), (0, band_top))
    return image


def _striped() -> Image.Image:
    """A capture with an edge on every other row: shifting it moves everything.

    The band fixture cannot express a wholesale shift -- most of it is flat
    field, which shifts onto itself -- so the one test about moving the whole
    page brings its own texture.
    """
    image = Image.new("RGB", CAPTURE_SIZE, (251, 250, 246))
    for row in range(0, CAPTURE_SIZE[1], 2):
        image.paste(Image.new("RGB", (CAPTURE_SIZE[0], 1), (16, 42, 67)), (0, row))
    return image


def _capture(*, band_top: int = 40) -> bytes:
    return _encoded(_painted(band_top=band_top))


def _bundle(**overrides: bytes) -> dict[str, bytes]:
    """The artifact set a release archive carries, as bundle-relative bytes."""
    artifacts: dict[str, bytes] = {
        "RELEASE_NOTES.md": b"# Release notes\n",
        "data/canonical-dataset.json": b'{"races": []}\n',
        "data/consensus.json": b'{"consensus": []}\n',
        "guide/seattle-2026-primary-guide.html": b"<!doctype html><title>Guide</title>",
        "release-status.json": b'{"passed": true}\n',
        "validation/rendering/rendering_validation_report.json": b'{"passed": true}\n',
        "validation/rendering/screenshots/desktop.png": _capture(),
        "validation/rendering/screenshots/mobile.png": _capture(),
    }
    artifacts.update(overrides)
    return artifacts


def _archive(root: Path, name: str, artifacts: dict[str, bytes]) -> Path:
    """Write `artifacts` as a release archive the way `build_release` does."""
    bundle = root / name
    for relative, content in artifacts.items():
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "schema_version": "1.1",
        "release_version": "2026-primary.2",
        "source_panel_id": "seattle-2026",
        "source_panel_hash": "0" * 64,
        "generated_at": "2026-08-12T00:00:00Z",
        "artifact_hashes": {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in sorted(artifacts.items())
        },
    }
    (bundle / "release-manifest.json").write_bytes(canonical_json_bytes(manifest))
    archive = root / f"{name}.zip"
    _write_deterministic_zip(bundle, archive, GENERATED_AT)
    return archive


def test_two_identical_builds_are_the_same_release(tmp_path: Path) -> None:
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(tmp_path, "b", _bundle())

    report = compare_release_archives(left, right)

    assert report.passed
    assert report.differences == []
    # Nine artifacts, not eight: the manifest is compared too, not skipped.
    assert report.compared_artifact_count == 9


@pytest.mark.parametrize(
    "artifact",
    [
        "data/consensus.json",
        "guide/seattle-2026-primary-guide.html",
        "release-status.json",
        "validation/rendering/rendering_validation_report.json",
        "RELEASE_NOTES.md",
    ],
)
def test_a_computed_artifact_is_still_held_to_its_exact_bytes(
    tmp_path: Path, artifact: str
) -> None:
    """The tolerance is for rasters alone. Nothing the pipeline computes may
    drift by so much as a byte, which is the property the old `cmp` had and the
    one this gate must not lose."""
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(tmp_path, "b", _bundle(**{artifact: b"drifted\n"}))

    report = compare_release_archives(left, right)

    assert not report.passed
    # Both the artifact and the manifest that hashes it: the manifest entry is
    # corroboration, and the named artifact is the answer the old byte offset
    # never gave.
    assert sorted((item.artifact, item.kind) for item in report.differences) == sorted(
        [(artifact, "bytes"), ("release-manifest.json", "bytes")]
    )


def test_an_edge_that_snapped_one_device_pixel_is_the_same_capture(tmp_path: Path) -> None:
    """The whole point of the seam. This is the real divergence in miniature:
    the band's painted edges land one row lower, nothing else about the capture
    changed, and its changed manifest hash does not make it a different
    release."""
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(
        tmp_path,
        "b",
        _bundle(**{"validation/rendering/screenshots/desktop.png": _capture(band_top=41)}),
    )

    report = compare_release_archives(left, right)

    assert report.passed, report.differences


def test_a_region_that_failed_to_rasterize_is_never_a_snap(tmp_path: Path) -> None:
    """A lost tile moves few enough pixels that a pixel budget would wave it
    through. It is not a snap: those pixels do not appear one row away, they
    stopped existing."""
    lost = _painted()
    lost.paste(Image.new("RGB", (40, 20), (255, 255, 255)), (30, 45))
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(
        tmp_path,
        "b",
        _bundle(**{"validation/rendering/screenshots/desktop.png": _encoded(lost)}),
    )

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "raster"
    assert "not explained by a one-device-pixel snap" in report.differences[0].detail


def test_a_capture_that_snapped_everywhere_at_once_is_a_layout_change(tmp_path: Path) -> None:
    """Every pixel of a wholesale shift is individually "explained" by a snap,
    so the share of the capture allowed to participate is bounded separately --
    otherwise a real regression that moved the whole page could hide behind the
    same rule that lets one edge move."""
    shifted = Image.new("RGB", CAPTURE_SIZE, (251, 250, 246))
    shifted.paste(_striped(), (0, 1))
    left = _archive(
        tmp_path,
        "a",
        _bundle(**{"validation/rendering/screenshots/desktop.png": _encoded(_striped())}),
    )
    right = _archive(
        tmp_path,
        "b",
        _bundle(**{"validation/rendering/screenshots/desktop.png": _encoded(shifted)}),
    )

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "raster"
    assert "too much of the capture moved at once" in report.differences[0].detail
    assert f"ceiling {MAX_SNAPPED_PIXEL_FRACTION:.4%}" in report.differences[0].detail


def test_the_unexplained_ceiling_is_the_ratchet_it_claims_to_be() -> None:
    """Both raster ceilings are ratchets (AGENTS.md, Working rules), so their
    values are asserted here: loosening either is a deliberate act that has to
    change this test too."""
    assert MAX_UNEXPLAINED_PIXELS == 64
    assert MAX_SNAPPED_PIXEL_FRACTION == 0.01


def test_a_resized_capture_is_never_within_tolerance(tmp_path: Path) -> None:
    """Dimensions are the one raster property with no tolerance at all: a
    capture at a different viewport is a different check, not a drifted one."""
    resized = Image.new("RGB", (CAPTURE_SIZE[0], CAPTURE_SIZE[1] + 1), (255, 255, 255))
    buffer = BytesIO()
    resized.save(buffer, format="PNG")
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(
        tmp_path,
        "b",
        _bundle(**{"validation/rendering/screenshots/desktop.png": buffer.getvalue()}),
    )

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "dimensions"


def test_an_unreadable_capture_is_reported_rather_than_raised(tmp_path: Path) -> None:
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(
        tmp_path,
        "b",
        _bundle(**{"validation/rendering/screenshots/desktop.png": b"\x89PNG\r\n\x1a\nrubbish"}),
    )

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "raster"
    assert "not a readable image" in report.differences[0].detail


def test_dropping_an_artifact_is_a_membership_failure(tmp_path: Path) -> None:
    complete = _bundle()
    reduced = {key: value for key, value in complete.items() if key != "data/consensus.json"}
    left = _archive(tmp_path, "a", complete)
    right = _archive(tmp_path, "b", reduced)

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "membership"
    assert "data/consensus.json" in report.differences[0].detail


def test_a_manifest_that_stops_hashing_a_screenshot_cannot_pass_by_omission(
    tmp_path: Path,
) -> None:
    """Excluding the raster hashes from the manifest comparison must not become
    a way to publish a release that no longer hashes its captures at all."""
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(tmp_path, "b", _bundle())
    manifest_path = tmp_path / "b/release-manifest.json"
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["artifact_hashes"]["validation/rendering/screenshots/mobile.png"]
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    right = tmp_path / "b-tampered.zip"
    _write_deterministic_zip(tmp_path / "b", right, GENERATED_AT)

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "membership"
    assert "does not hash every rasterized artifact" in report.differences[0].detail


def test_a_manifest_that_drifts_beyond_its_raster_hashes_fails(tmp_path: Path) -> None:
    left = _archive(tmp_path, "a", _bundle())
    _archive(tmp_path, "b", _bundle())
    manifest_path = tmp_path / "b/release-manifest.json"
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generated_at"] = "2026-08-13T00:00:00Z"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    right = tmp_path / "b-drifted.zip"
    _write_deterministic_zip(tmp_path / "b", right, GENERATED_AT)

    report = compare_release_archives(left, right)

    assert not report.passed
    assert [(item.artifact, item.kind) for item in report.differences] == [
        ("release-manifest.json", "bytes")
    ]


def test_the_tolerated_artifacts_are_exactly_the_two_browser_captures() -> None:
    """A ratchet guard: this set is what the byte-for-byte rule is relaxed for,
    so growing it is a deliberate act that has to change this test too
    (AGENTS.md, Working rules)."""
    assert {
        "validation/rendering/screenshots/desktop.png",
        "validation/rendering/screenshots/mobile.png",
    } == RASTER_ARTIFACTS
