"""Fixed-input software history and the retained legacy changelog index."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
GENERATED_AT = datetime(2026, 10, 16, 12, tzinfo=UTC)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=repository, text=True).strip()


@pytest.fixture
def history_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "History Test")
    _git(repository, "config", "user.email", "history@example.invalid")
    shutil.copyfile(PROJECT_ROOT / "cliff.toml", repository / "cliff.toml")
    (repository / "node_modules").symlink_to(
        PROJECT_ROOT / "node_modules", target_is_directory=True
    )
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "feat: excluded boundary")
    boundary = _git(repository, "rev-parse", "HEAD")
    _git(repository, "tag", "2026-general.1")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "feat: in range feature")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "Unconventional in range work")
    source = _git(repository, "rev-parse", "HEAD")
    _git(repository, "commit", "--quiet", "--allow-empty", "-m", "fix: excluded later work")
    return repository, boundary, source


def _history(repository: Path, boundary: str, source: str) -> str:
    from election_guide.release.history import generate_software_history

    return generate_software_history(
        repository,
        previous_release_sha=boundary,
        source_sha=source,
        release_version="2026-general.2",
        generated_at=GENERATED_AT,
    )


def test_history_identical_before_and_after_candidate_tag(
    history_repository: tuple[Path, str, str],
) -> None:
    repository, boundary, source = history_repository
    before_tag = _history(repository, boundary, source)
    _git(repository, "tag", "2026-general.2", source)
    assert before_tag == _history(repository, boundary, source)
    assert "## 2026-general.2" in before_tag


def test_history_uses_fixed_range_and_commit_time(
    history_repository: tuple[Path, str, str],
) -> None:
    repository, boundary, source = history_repository
    text = _history(repository, boundary, source)
    assert "## 2026-general.2 — 2026-10-16" in text
    assert "### Added" in text
    assert "- In range feature" in text
    assert "### Other" in text
    assert "- Unconventional in range work" in text
    assert "excluded boundary" not in text.lower()
    assert "excluded later" not in text.lower()
    assert "# Changelog" not in text


def test_history_ignores_ambient_git_cliff_options(
    history_repository: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, boundary, source = history_repository
    expected = _history(repository, boundary, source)
    monkeypatch.setenv("GIT_CLIFF_WITH_COMMIT", "feat: undeclared ambient work")
    assert _history(repository, boundary, source) == expected


@pytest.mark.parametrize("invalid", ["missing", "descendant", "shorthand"])
def test_history_rejects_invalid_boundaries(
    history_repository: tuple[Path, str, str], invalid: str
) -> None:
    repository, boundary, source = history_repository
    boundary = {
        "missing": "0" * 40,
        "descendant": _git(repository, "rev-parse", "HEAD"),
        "shorthand": boundary[:8],
    }[invalid]
    with pytest.raises(ValueError):
        _history(repository, boundary, source)


def test_legacy_index_ignores_future_tags(
    history_repository: tuple[Path, str, str],
) -> None:
    from election_guide.release.history import generate_changelog_index

    repository, _, source = history_repository
    config = repository / "cliff.toml"
    config.write_text(
        config.read_text().replace("c5a5252202d0f78bcec5e54f9f6d0dfe0841d481", source)
    )
    _git(repository, "tag", "2026-general.2", source)
    before = generate_changelog_index(repository)
    _git(repository, "tag", "2026-general.3")
    assert before == generate_changelog_index(repository)
    assert "## 2026-general.2" in before
    assert "## 2026-general.3" not in before


def test_committed_index_preserves_historical_section_bytes() -> None:
    # The pre-policy historical section bytes are immutable. This literal digest
    # also works in shallow CI checkouts and after the implementation is squashed.
    text = (PROJECT_ROOT / "CHANGELOG.md").read_bytes()
    sections = text[text.index(b"## 2026-primary.4") :]
    assert hashlib.sha256(sections).hexdigest() == (
        "91e2f09864e562becc2b7b424970afea0baa1baf99e8df4e73f227363620621a"
    )
