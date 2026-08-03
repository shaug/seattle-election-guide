"""The generated changelog and the wiring that keeps it honest (issue 216)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"


def test_changelog_covers_history_back_to_the_first_release() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")

    headings = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)
    assert "2026-primary.1 — 2026-07-20" in headings
    assert "2026-primary.2 — 2026-08-02" in headings
    # Newest first, so the oldest release is the last section.
    assert headings[-1].startswith("2026-primary.1")


def test_changelog_states_the_split_from_per_release_notes() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")

    assert "RELEASE_NOTES.md" in text
    assert "Do not edit by hand" in text


def test_the_generator_is_pinned_to_an_exact_version() -> None:
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))

    pinned = package["devDependencies"]["git-cliff"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned), pinned
    assert package["scripts"]["changelog:version"] == "git-cliff --version"
    assert "--config cliff.toml" in package["scripts"]["changelog"]


def test_the_full_gate_regenerates_and_compares_the_changelog() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "$(MAKE) check-changelog" in makefile
    assert "cmp CHANGELOG.md dist/CHANGELOG.check.md" in makefile


def test_ci_checks_the_changelog_against_complete_history() -> None:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    check_steps = workflow["jobs"]["check"]["steps"]
    checkout = next(
        step for step in check_steps if step.get("uses", "").startswith("actions/check")
    )
    # git-cliff renders from every commit and release tag, so a shallow, tagless
    # checkout would regenerate a different file and the comparison would be a lie.
    assert checkout["with"]["fetch-depth"] == "0"
    changelog_step = next(
        step
        for step in check_steps
        if step.get("name") == "Verify the committed changelog matches history"
    )
    assert changelog_step["run"].strip() == "make check-changelog"
    # Reading history needs no credential; the check job must stay secret-free.
    assert "env" not in changelog_step


def test_the_changelog_records_only_tagged_releases() -> None:
    """The byte comparison is only satisfiable if untagged commits render nothing.

    An "unreleased" section would contain the very commit that carries the
    regenerated file, so committing it would change what the next regeneration
    produces. It would also differ on every pull request, because CI renders an
    ephemeral `refs/pull/N/merge` commit, and again at squash-merge, which
    appends a `(#N)` suffix the branch never saw.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "cliff.toml").read_text(encoding="utf-8")

    assert "Unreleased" not in text
    assert re.search(r"^## (?!\d{4}-[a-z]+\.\d+ )", text, flags=re.MULTILINE) is None
    # The body renders nothing at all when there is no version.
    assert "{% if version %}" in config
    assert "{% else %}" not in config


def test_the_changelog_config_pins_election_scoped_tags() -> None:
    config = (PROJECT_ROOT / "cliff.toml").read_text(encoding="utf-8")

    # Release versions are election-scoped, not semver, so the default `v1.2.3`
    # tag pattern would match nothing and collapse every release into one section.
    assert 'tag_pattern = "[0-9]{4}-[a-z]+\\\\.[0-9]+"' in config
    # Nothing may depend on the wall clock: the output is compared byte for byte.
    assert "now()" not in config
