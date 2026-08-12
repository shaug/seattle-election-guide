"""What "the same release, built twice" means.

The gate these cover replaced a `cmp` of two archives that failed roughly one CI
run in seven and reported nothing but a byte offset (issue #367). Every artifact
is still held to its exact bytes, screenshots included; what the replacement adds
is the ability to say which artifact moved.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from PIL import Image

from election_guide.release import compare_release_archives
from election_guide.release.builder import (
    _write_deterministic_zip,  # pyright: ignore[reportPrivateUsage]
)
from election_guide.serialization import canonical_json_bytes

GENERATED_AT = datetime(2026, 8, 12, tzinfo=UTC)
CAPTURE_SIZE = (200, 150)


def _capture(*, band_top: int = 40) -> bytes:
    """A stand-in screenshot: a real PNG, which the comparison reads as bytes."""
    image = Image.new("RGB", CAPTURE_SIZE, (251, 250, 246))
    image.paste(Image.new("RGB", (CAPTURE_SIZE[0], 30), (16, 42, 67)), (0, band_top))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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
        "validation/rendering/screenshots/desktop.png",
        "validation/rendering/screenshots/mobile.png",
    ],
)
def test_a_drifted_artifact_is_named_rather_than_located_by_byte_offset(
    tmp_path: Path, artifact: str
) -> None:
    """The reason this replaced `cmp`, and the property it kept.

    Every artifact is held to its exact bytes -- the screenshots on this list
    exactly as strictly as the JSON. What is new is the answer: `cmp` printed
    one offset into the compressed archive, which named nothing, because the
    first byte to differ belongs to whichever entry's header the deflate stream
    reached first. Each artifact that moved is named here, alongside the
    manifest that hashes it.
    """
    drifted = _capture(band_top=41) if artifact.endswith(".png") else b"drifted\n"
    left = _archive(tmp_path, "a", _bundle())
    right = _archive(tmp_path, "b", _bundle(**{artifact: drifted}))

    report = compare_release_archives(left, right)

    assert not report.passed
    assert sorted((item.artifact, item.kind) for item in report.differences) == sorted(
        [(artifact, "bytes"), ("release-manifest.json", "bytes")]
    )


def test_dropping_an_artifact_is_a_membership_failure(tmp_path: Path) -> None:
    complete = _bundle()
    reduced = {key: value for key, value in complete.items() if key != "data/consensus.json"}
    left = _archive(tmp_path, "a", complete)
    right = _archive(tmp_path, "b", reduced)

    report = compare_release_archives(left, right)

    assert not report.passed
    assert [item.kind for item in report.differences] == ["membership"]
    assert "data/consensus.json" in report.differences[0].detail


def test_an_order_only_mismatch_says_what_actually_differs(tmp_path: Path) -> None:
    """Same entries, different order. The set differences are both empty, so
    reporting them would print two empty lists and tell the reader nothing."""
    artifacts = _bundle()
    left = _archive(tmp_path, "a", artifacts)
    reordered = tmp_path / "b"
    for relative, content in artifacts.items():
        path = reordered / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (reordered / "release-manifest.json").write_bytes(
        (tmp_path / "a/release-manifest.json").read_bytes()
    )
    right = tmp_path / "b.zip"
    with ZipFile(right, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(reordered.rglob("*"), reverse=True):
            if path.is_file():
                info = ZipInfo(
                    f"seattle-election-guide/{path.relative_to(reordered).as_posix()}",
                    date_time=GENERATED_AT.timetuple()[:6],
                )
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED)

    report = compare_release_archives(left, right)

    assert not report.passed
    assert report.differences[0].kind == "membership"
    assert "different order" in report.differences[0].detail
    assert "[]" not in report.differences[0].detail


def test_a_corrupt_member_is_rejected_rather_than_raised_as_a_traceback(
    tmp_path: Path,
) -> None:
    """A corrupt deflated member raises `zlib.error`, which is not an `OSError`
    or a `ValueError`, so it would otherwise escape the command as a traceback
    (the policy `hosting/releases.py` already applies to a downloaded bundle)."""
    left = _archive(tmp_path, "a", _bundle())
    corrupt = tmp_path / "corrupt.zip"
    raw = bytearray(left.read_bytes())
    # Well past the first local header, inside a deflated member body.
    raw[len(raw) // 2] ^= 0xFF
    corrupt.write_bytes(bytes(raw))

    with pytest.raises(ValueError, match="not a readable ZIP archive"):
        compare_release_archives(left, corrupt)


def test_a_membership_failure_is_reported_once_rather_than_per_entry(tmp_path: Path) -> None:
    """A renamed directory moves every entry under it. One membership difference
    names the set; it does not restate itself once per file."""
    complete = _bundle()
    moved = {
        key.replace("validation/rendering/", "validation/render/"): value
        for key, value in complete.items()
    }
    left = _archive(tmp_path, "a", complete)
    right = _archive(tmp_path, "b", moved)

    report = compare_release_archives(left, right)

    assert not report.passed
    assert len(report.differences) == 1
    assert report.differences[0].kind == "membership"
