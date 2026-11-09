"""Narrow, offline preparation for normal reviewed preliminary-result PRs."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from textwrap import indent
from zoneinfo import ZoneInfo

import yaml

from election_guide.corrections.models import (
    CorrectionEntry,
    CorrectionProvenanceLink,
    ElectionCorrections,
)
from election_guide.results.models import (
    PreliminaryElectionResults,
    PreliminaryRaceResults,
    ResultsDocument,
)
from election_guide.serialization import read_yaml, write_generated_bytes

EVIDENCE_PREFIXES = ("data/evidence/official/", "data/manifests/evidence/")
PUBLICATION_FILES = frozenset(
    {
        "data/results/wa-2026-general.yaml",
        "data/corrections/wa-2026-general.yaml",
        "config/hosting/site.yaml",
    }
)


def _tally(race: PreliminaryRaceResults) -> tuple[object, ...]:
    """Actual contest totals and named votes; source clocks/order are not results."""
    return (
        race.ballots_counted,
        race.votes_counted,
        race.write_in_votes,
        {outcome.choice_id: outcome.votes for outcome in race.outcomes},
    )


def build_preliminary_update(
    previous: ResultsDocument,
    current: ResultsDocument,
    *,
    checked_at: datetime,
    original_hashes: dict[str, str] | None = None,
) -> CorrectionEntry | None:
    """Announce actual tally changes, never metadata-only source refreshes (#718)."""
    if not isinstance(previous, PreliminaryElectionResults) or not isinstance(
        current, PreliminaryElectionResults
    ):
        raise ValueError("the hourly publisher accepts preliminary results only")
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("publication check time requires a timezone")
    old = {r.race_id: r for r in previous.races}
    new = {r.race_id: r for r in current.races}
    if previous.election_id != current.election_id or old.keys() != new.keys():
        raise ValueError("preliminary publication inventory membership changed")
    changed = [key for key in old if _tally(old[key]) != _tally(new[key])]
    for key in old:
        before, after = old[key].capture_evidence, new[key].capture_evidence
        if before != after and (
            original_hashes is None or before not in original_hashes or after not in original_hashes
        ):
            raise ValueError("new preliminary references require verified original hashes")
    if not changed:
        return None
    local = checked_at.astimezone(ZoneInfo("America/Los_Angeles"))
    contests = f"{len(changed)} contest" + ("s" if len(changed) != 1 else "")
    return CorrectionEntry(
        slug=f"preliminary-results-{local.strftime('%Y-%m-%d-%H%M%S')}",
        corrected_on=local.date(),
        headline=(
            f"Updated preliminary counts for {contests} at {local.strftime('%H:%M:%S')} Pacific."
        ),
        body=(
            f"Updated the unofficial counts for {contests}, using each contest's complete "
            "jurisdiction. Publisher count and export times remain separate from source "
            "verification times. No certification or outcome is inferred."
        ),
        topics=["results"],
        actions=["changed"],
        provenance=[
            CorrectionProvenanceLink(label="General election guide", url="/e/wa-2026-general/"),
            CorrectionProvenanceLink(
                label="Retained official results and refresh scope",
                url="https://github.com/shaug/seattle-election-guide/issues/696",
            ),
        ],
    )


def append_preliminary_update(path: Path, entry: CorrectionEntry) -> bool:
    """Preserve the entire authored prefix and make same-entry recovery harmless."""
    original = path.read_bytes()
    updates = ElectionCorrections.model_validate(read_yaml(path))
    if entry in updates.entries:
        return False
    ElectionCorrections.model_validate(
        {**updates.model_dump(), "entries": [*updates.entries, entry]}
    )
    if not original.endswith(b"\n"):
        raise ValueError("existing Updates text must end with a newline")
    addition = indent(
        yaml.safe_dump([entry.model_dump(mode="json")], sort_keys=False), "  "
    ).encode()
    write_generated_bytes(path, original + addition)
    return True


def validate_preliminary_publication_paths(root: Path, paths: Sequence[str]) -> tuple[str, ...]:
    """Reject unrelated files and known GitHub file-size failures before staging."""
    for name in paths:
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not (name in PUBLICATION_FILES or name.startswith(EVIDENCE_PREFIXES))
        ):
            raise ValueError(f"outside preliminary publication scope: {name}")
        p = root / name
        if p.is_symlink():
            raise ValueError(f"publication evidence cannot be a symlink: {name}")
        if not p.is_file():
            raise ValueError(f"publication file missing or deleted: {name}")
        if p.stat().st_size > 100 * 1024 * 1024:
            raise ValueError(f"publication file exceeds GitHub's 100 MiB limit: {name}")
    return tuple(paths)


def stage_preliminary_publication(root: Path) -> tuple[str, ...]:
    """Stage only validated results and append-only original evidence."""

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=root)

    tracked = [v.decode() for v in git("diff", "HEAD", "--name-only", "-z").split(b"\0") if v]
    untracked = [
        v.decode()
        for v in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        if v
    ]
    paths = validate_preliminary_publication_paths(root, sorted(set(tracked + untracked)))
    for name in paths:
        if (
            name.startswith(EVIDENCE_PREFIXES)
            and git("ls-tree", "--name-only", "HEAD", "--", name).strip()
            and name in tracked
        ):
            raise ValueError(f"retained evidence is immutable: {name}")
    updates_path = "data/corrections/wa-2026-general.yaml"
    if updates_path in paths:
        original = git("show", f"HEAD:{updates_path}")
        if not (root / updates_path).read_bytes().startswith(original):
            raise ValueError("existing Updates history is append-only")
    if paths:
        git("add", "--", *paths)
    return paths
