"""An official index is traversed and known articles are independently rechecked."""

import base64
import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.http import HttpArtifact

ROOT = Path(__file__).parents[1]
runner = CliRunner()


def test_new_article_and_known_article_edit_never_become_quiet_zero_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
    policy = cast(dict[str, Any], yaml.safe_load((ROOT / "config/verification.yaml").read_text()))
    election = policy["elections"][0]
    election["sources"] = [
        source for source in election["sources"] if source["source_id"] == "seattle-gay-news"
    ]
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy))
    titles = re.findall(
        r"<p>(.*?)</p>", (ROOT / "tests/fixtures/verification/seattle-gay-news.html").read_text()
    )
    articles = {
        f"https://www.sgn.org/story/{168513 + i}/": (
            f"<h1>{title}</h1><p>Authored fixture article.</p>".encode()
        )
        for i, title in enumerate(titles)
    }
    first_links = [
        f'<a href="/story/{168513 + i}/News/Seattle/SGN%20Endorsements">Article</a>'
        for i in range(1, len(titles))
    ]
    pages = {
        "https://www.sgn.org/ch/News/Seattle": (
            "".join(first_links) + '<a href="?start=10">Next</a>'
        ).encode(),
        "https://www.sgn.org/ch/News/Seattle?start=10": (
            b'<a href="/story/168513/News/Seattle/SGN%20Endorsements">Boundary</a>'
        ),
    }
    calls: list[str] = []

    def fetch(url: str, *, timeout_seconds: float = 30) -> HttpArtifact:
        calls.append(url)
        return HttpArtifact(
            content={**pages, **articles}[url],
            status=200,
            canonical_url=url,
            redirect_chain=[],
            media_type="text/html",
        )

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)
    state = tmp_path / "state"
    first = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy_path),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            "2026-10-05T18:00:00Z",
        ],
    )
    assert first.exit_code == 0, first.output
    event = json.loads(first.output)["automatic"][0]
    assert event["status"] == "created", event
    assert len(event["diff"]) == 7
    assert "https://www.sgn.org/ch/News/Seattle?start=10" in calls
    # A changed article body with the same heading is still review work.
    articles["https://www.sgn.org/story/168514/"] += b"<p>Changed authored wording.</p>"
    second = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy_path),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            "2026-10-06T18:00:00Z",
        ],
    )
    assert second.exit_code == 0, second.output
    event = json.loads(second.output)["automatic"][0]
    assert event["content_changed"] is True and event["diff"] == []
    # A previously unknown endorsement article is discovered from the current
    # index. Fixed known mappings cannot interpret it; the changed-byte gate
    # must send it to human review even when known decisions are identical.
    articles["https://www.sgn.org/story/199999/"] = (
        b"<h1>SGN Endorsements A Newly Published Candidate</h1>"
    )
    pages["https://www.sgn.org/ch/News/Seattle"] += (
        b'<a href="/story/199999/News/Seattle/SGN%20Endorsements">New</a>'
    )
    third = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy_path),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            "2026-10-07T18:00:00Z",
        ],
    )
    assert third.exit_code == 0, third.output
    assert "https://www.sgn.org/story/199999/" in calls
    event = json.loads(third.output)["automatic"][0]
    assert event["status"] == "updated" and event["content_changed"] is True
    tasks = runner.invoke(
        app,
        [
            "verification",
            "reconcile",
            str(policy_path),
            "--state-root",
            str(state),
            "--repository",
            "example/guide",
            "--revision",
            "a" * 40,
            "--as-of",
            "2026-10-07",
            "--dry-run",
        ],
    )
    assert tasks.exit_code == 0, tasks.output
    assert "unrecognized wording" in tasks.output
    assert not any(
        b"Changed authored wording" in path.read_bytes() for path in state.rglob("*.json")
    )
    # Losing the reviewed boundary is an explicit failure rather than a
    # truncated check of the first page.
    pages["https://www.sgn.org/ch/News/Seattle?start=10"] = b"<p>Parser changed.</p>"
    fourth = runner.invoke(
        app,
        [
            "verification",
            "run",
            str(policy_path),
            "--state-root",
            str(state),
            "--live",
            "--checked-at",
            "2026-10-08T18:00:00Z",
        ],
    )
    assert fourth.exit_code == 0, fourth.output
    event = json.loads(fourth.output)["automatic"][0]
    assert event["status"] == "failed" and event["previous_snapshot_id"] is not None
