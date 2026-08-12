"""Compare two builds of one release, entry by entry.

Repeating a build with identical inputs produces the same release, and every
artifact in the bundle is held to its exact bytes -- the property the previous
`cmp` of the two archives had. What changes is what a failure can say: `cmp`
reported one offset into a compressed archive, which named nothing, because the
first byte to differ is whichever entry's header the deflate stream reached
first. Comparing entry by entry names the artifact instead (issue #367).

Nothing here is tolerant, and the two browser-rendered screenshots are held to
the same exact bytes as everything else. The gate this replaced failed roughly
one run in seven on same-input builds, and the cause was in the capture rather
than in the comparison: `rendering/browser.py` waited a fixed interval and then
photographed whatever frame existed. It now waits on a readiness signal and runs
Chrome with the compositor and rasterization controls that keep a half-drawn
frame from being captured, after which 30 consecutive same-input builds on the
CI runner produced byte-identical artifacts, both screenshots included. A
comparison that tolerated a difference would only have hidden that.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Literal

from pydantic import Field

from election_guide.release.models import ARCHIVE_ROOT_DIR, ReleaseModel


class ArtifactDifference(ReleaseModel):
    """One reason two builds of the same release are not the same release."""

    artifact: str
    kind: Literal["membership", "bytes"]
    detail: str


class ReproducibilityReport(ReleaseModel):
    compared_artifact_count: int = Field(ge=0)
    differences: list[ArtifactDifference]

    @property
    def passed(self) -> bool:
        return not self.differences


def compare_release_archives(left: Path, right: Path) -> ReproducibilityReport:
    """Check that two archives are the same release, artifact by artifact."""
    left_members = _read_archive(left)
    right_members = _read_archive(right)

    if list(left_members) != list(right_members):
        # Reported alone rather than as a cascade of per-entry noise: every
        # later comparison is keyed by name, so a membership mismatch would
        # otherwise restate itself once per entry that moved.
        return ReproducibilityReport(
            compared_artifact_count=0,
            differences=[
                ArtifactDifference(
                    artifact="<archive>",
                    kind="membership",
                    detail=(
                        "archives do not contain the same entries in the same order: "
                        f"only in {left.name}: {sorted(set(left_members) - set(right_members))}; "
                        f"only in {right.name}: {sorted(set(right_members) - set(left_members))}"
                    ),
                )
            ],
        )

    differences = [
        ArtifactDifference(
            artifact=artifact,
            kind="bytes",
            detail=(
                f"artifact is not reproducible: {len(left_bytes)} bytes vs "
                f"{len(right_members[artifact])} bytes, first difference at byte "
                f"{_first_difference(left_bytes, right_members[artifact])}"
            ),
        )
        for artifact, left_bytes in left_members.items()
        if left_bytes != right_members[artifact]
    ]
    return ReproducibilityReport(compared_artifact_count=len(left_members), differences=differences)


def _read_archive(path: Path) -> dict[str, bytes]:
    """Bundle-relative entry name to content, in the archive's own order."""
    with zipfile.ZipFile(path) as archive:
        members: dict[str, bytes] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            prefix = f"{ARCHIVE_ROOT_DIR}/"
            if not info.filename.startswith(prefix):
                raise ValueError(
                    f"{path.name} contains an entry outside the bundle root: {info.filename}"
                )
            members[info.filename[len(prefix) :]] = archive.read(info)
        return members


def _first_difference(left: bytes, right: bytes) -> int:
    for index, (one, other) in enumerate(zip(left, right, strict=False)):
        if one != other:
            return index
    return min(len(left), len(right))
