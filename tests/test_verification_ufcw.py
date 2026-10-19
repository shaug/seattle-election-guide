"""Full UFCW publications remain observable through durable scheduled checks."""

import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.http import HttpArtifact

ROOT = Path(__file__).parents[1]
INDEX = "https://ufcw3000.org/endorsements"
KNOWN = (
    "https://ufcw3000.org/news/2026/10/15/ufcw-3000-executive-board-unanimously-rejects-i-638-and-i-001-endorses-no-hate-campaign",
    "https://ufcw3000.org/news/2026/10/15/ufcw-3000-executive-board-unanimously-rejects-i-645-endorses-no-vote",
)
NEW = "https://ufcw3000.org/news/2026/10/20/new-endorsements"


def article(body: str = "Authored fixture position.") -> bytes:
    return (
        '<h1 class="page-title">News</h1><article class="hentry category-endorsement">'
        '<h1 class="entry-title">UFCW endorsement publication</h1>'
        f'<div class="sqs-html-content"><p>{body}</p></div></article>'
    ).encode()


@pytest.fixture
def publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
    policy = cast(dict[str, Any], yaml.safe_load((ROOT / "config/verification.yaml").read_text()))
    policy["elections"][0]["sources"] = [
        item for item in policy["elections"][0]["sources"] if item["source_id"] == "ufcw-3000"
    ]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy))
    pages: dict[str, Any] = {
        INDEX: (ROOT / "tests/fixtures/verification/ufcw-3000.html").read_bytes(),
        **dict.fromkeys(KNOWN, article()),
    }

    def fetch(url: str, *, timeout_seconds: float = 30) -> HttpArtifact:
        value = pages[url]  # Unexpected or unrelated fetches fail this fixture.
        if isinstance(value, Exception):
            raise value
        if isinstance(value, HttpArtifact):
            return value
        return HttpArtifact(
            content=value, status=200, canonical_url=url, redirect_chain=[], media_type="text/html"
        )

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)
    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    return path, pages


def run(policy: Path, state: Path, day: int) -> dict[str, Any]:
    # Each invocation constructs a new runner and rereads policy and persisted state.
    result = CliRunner().invoke(
        app,
        [
            "verification",
            "run",
            str(policy),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            f"2026-10-{day:02d}T18:00:00Z",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["automatic"][0]


def test_ufcw_body_edit_and_independent_persisted_reuse_reach_review_tasks(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]]
) -> None:
    policy, pages = publication
    first_state = tmp_path / "first-state"
    first = run(policy, first_state, 19)
    assert first["status"] == "created"
    state = tmp_path / "independent-state"
    shutil.copytree(first_state, state)
    second = run(policy, state, 20)
    assert second["status"] == "unchanged"
    assert second["snapshot_id"] == first["snapshot_id"]
    pages[KNOWN[0]] = article("Changed or withdrawn authored fixture position.")
    changed = run(policy, state, 21)
    assert changed["status"] == "updated" and changed["content_changed"] is True
    assert changed["diff"] == []
    result = CliRunner().invoke(
        app,
        [
            "verification",
            "reconcile",
            str(policy),
            "--state-root",
            str(state),
            "--repository",
            "example/guide",
            "--revision",
            "a" * 40,
            "--as-of",
            "2026-10-21",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert changed["id"] in result.output and "unrecognized wording" in result.output
    manifests = [json.loads(path.read_text()) for path in state.rglob("manifests/*.json")]
    original = next(item for item in manifests if item["requested_url"] == KNOWN[0])
    assert original["capture_method"] == "static_html" and original["http_status"] == 200
    assert any(
        item["content_sha256"] == hashlib.sha256(pages[KNOWN[0]]).hexdigest() for item in manifests
    )
    comparison = next(item for item in manifests if item["id"] == changed["capture_id"])
    assert comparison["capture_method"] == "manual_upload" and comparison["http_status"] is None
    assert not any(b"Changed or withdrawn" in path.read_bytes() for path in state.rglob("*.*"))
    validation = CliRunner().invoke(
        app, ["verification", "validate", str(policy), "--state-root", str(state)]
    )
    assert validation.exit_code == 0, validation.output


def test_ufcw_new_article_is_retained_after_landing_link_rotates_away(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]]
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    run(policy, state, 19)
    original_landing = pages[INDEX]
    pages[INDEX] += (
        f'<a href="{NEW}">New endorsements</a>'
        '<a href="/news/2026/10/20/unrelated">Office hours</a>'
        '<a href="/news/2025/10/20/past-endorsements">Past endorsements</a>'
    ).encode()
    pages[NEW] = article()
    run(policy, state, 20)
    pages[INDEX] = original_landing
    before_rotation = run(policy, state, 21)
    pages[NEW] = article("Correction after link rotated away.")
    changed = run(policy, state, 22)
    assert changed["status"] == "updated" and changed["content_changed"] is True
    assert changed["previous_snapshot_id"] == before_rotation["snapshot_id"]
    assert any(
        NEW in json.loads(path.read_text())["articles"] for path in state.rglob("discovery/*.json")
    )


@pytest.mark.parametrize(
    "failure", [OSError("fixture unavailable"), b"<html>Parser changed</html>", b"\xff"]
)
def test_ufcw_required_article_failure_preserves_baseline(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], failure: Any
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[KNOWN[1]] = failure
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    assert len(list(state.rglob("extractions/*.json"))) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://ufcw3000.org/news/2026/10/20/new-endorsements",
        "https://evil.example/news/2026/10/20/new-endorsements",
        NEW + "?unsafe=yes",
        NEW + "#fragment",
        "https://ufcw3000.org/news/2026/99/20/new-endorsements",
        "https://ufcw3000.org/news/2026/10/20/%2e%2e-endorsements",
    ],
)
def test_ufcw_invalid_relevant_links_fail_without_replacing_baseline(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], url: str
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[INDEX] += f'<a href="{url}">New endorsements</a>'.encode()
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]


@pytest.mark.parametrize("canonical", [KNOWN[0] + "?unsafe=yes", INDEX])
def test_ufcw_article_redirect_requires_an_official_article_identity(
    tmp_path: Path, publication: tuple[Path, dict[str, Any]], canonical: str
) -> None:
    policy, pages = publication
    state = tmp_path / "state"
    baseline = run(policy, state, 19)
    pages[KNOWN[0]] = HttpArtifact(
        content=article(),
        status=200,
        canonical_url=canonical,
        redirect_chain=[KNOWN[0], canonical],
        media_type="text/html",
    )
    failed = run(policy, state, 20)
    assert failed["status"] == "failed"
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
