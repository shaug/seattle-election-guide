"""An official index is traversed and known articles are independently rechecked."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.collection.http import HttpArtifact
from election_guide.collection.verification_review import approve_baseline

ROOT = Path(__file__).parents[1]
runner = CliRunner()


@pytest.mark.parametrize(
    "headline",
    [
        "<h1>{}</h1>",
        '<h2 class="mb-3 font-weight-bold">{}</h2><h2>Newsletter signup</h2>',
    ],
)
@pytest.mark.parametrize(
    ("new_link", "expect_fetch"),
    [
        ('<a href="/story/199999/News/Seattle/SGN%20Endorsements">New</a>', True),
        ('<a href="/story/199999/"><span>SGN Endorsements A New Article</span></a>', True),
        ('<a href="/story/199999/unrecognized-link-shape">New publication</a>', False),
    ],
)
def test_new_article_and_known_article_edit_never_become_quiet_zero_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    new_link: str,
    expect_fetch: bool,
    headline: str,
) -> None:
    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
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
            (headline.format(title) + "<p>Authored fixture article.</p>").encode()
        )
        for i, title in enumerate(titles)
    }
    articles["https://www.sgn.org/story/171425/"] = headline.format(
        "SGN Endorsements: Adam Smith (US House of Representatives, 9th District)"
    ).encode()
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
    assert len(event["diff"]) == 8
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
    approve_baseline(
        state / "wa-2026-general",
        event["snapshot_id"],
        "Fixture reviewer",
        datetime.fromisoformat("2026-10-06T19:00:00+00:00"),
        "Authored fixture publication with mocked HTTP; no real baseline approval.",
    )
    # A previously unknown endorsement article is discovered from the current
    # index. Fixed known mappings cannot interpret it; the changed-byte gate
    # must send it to human review even when known decisions are identical.
    articles["https://www.sgn.org/story/199999/"] = headline.format(
        "SGN Endorsements A Newly Published Candidate"
    ).encode()
    pages["https://www.sgn.org/ch/News/Seattle"] += new_link.encode()
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
    assert ("https://www.sgn.org/story/199999/" in calls) is expect_fetch
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
    assert event["id"] in tasks.output
    if expect_fetch:
        assert "unrecognized wording" in tasks.output
    assert not any(
        b"Changed authored wording" in path.read_bytes() for path in state.rglob("*.json")
    )
    assert not list(state.rglob("vault/**/*.json"))
    assert all(
        json.loads(p.read_text())["availability"] == "observed"
        for p in state.rglob("manifests/*.json")
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


@pytest.mark.parametrize("failure", ["fetch", "heading", "decode", "pagination"])
def test_sgn_failed_learning_survives_rotation_on_fresh_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import shutil

    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_runtime import run_verification
    from election_guide.collection.verification_state import validate_state

    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
    policy = read_policy(ROOT / "config/verification.yaml")
    election = policy.elections[0]
    policy = policy.model_copy(
        update={
            "elections": [
                election.model_copy(
                    update={
                        "sources": [
                            s for s in election.sources if s.source_id == "seattle-gay-news"
                        ]
                    }
                )
            ]
        }
    )
    index = "https://www.sgn.org/ch/News/Seattle"
    new = "https://www.sgn.org/story/199999/"
    titles = re.findall(
        r"<p>(.*?)</p>", (ROOT / "tests/fixtures/verification/seattle-gay-news.html").read_text()
    )
    pages: dict[str, bytes | Exception] = {
        f"https://www.sgn.org/story/{168513 + i}/": f"<h1>{title}</h1>".encode()
        for i, title in enumerate(titles)
    }
    pages["https://www.sgn.org/story/171425/"] = (
        b"<h1>SGN Endorsements: Adam Smith (US House of Representatives, 9th District)</h1>"
    )
    original_index = "".join(
        f'<a href="/story/{168513 + i}/News/Seattle/SGN%20Endorsements">Story</a>'
        for i in range(len(titles))
    ).encode()
    pages[index] = original_index
    calls: list[str] = []

    def fetch(url: str) -> HttpArtifact:
        calls.append(url)
        value = pages[url]
        if isinstance(value, Exception):
            raise value
        return HttpArtifact(value, 200, url, [], "text/html")

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)
    state = tmp_path / "state"

    def run(root: Path, day: int) -> dict[str, Any]:
        report = run_verification(
            policy,
            root,
            datetime.fromisoformat(f"2026-10-{day:02d}T18:00:00+00:00"),
            live=True,
            fixtures=None,
        )
        validate_state(policy, root)
        return report["automatic"][0]

    baseline = run(state, 19)
    assert baseline["status"] == "created"
    broken = {
        "fetch": OSError("authored unavailable fixture"),
        "heading": b"<h1>Unclassified article</h1>",
        "decode": b"\xff",
        "pagination": OSError("still unavailable after pagination recovers"),
    }[failure]
    pages[new] = broken
    learned_index = original_index + b'<a href="/story/199999/">SGN Endorsements New</a>'
    if failure == "pagination":
        learned_index = learned_index.replace(
            b"/story/168513/News/Seattle/SGN%20Endorsements", b"/unrelated/"
        )
    pages[index] = learned_index
    first_failure = run(state, 20)
    assert first_failure["status"] == "failed"
    assert first_failure["previous_snapshot_id"] == baseline["snapshot_id"]
    assert any(
        new in json.loads(p.read_text())["articles"]
        for p in state.rglob("discovery-obligations/*.json")
    )
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    independent = tmp_path / "independent"
    shutil.copytree(state, independent)
    pages[index] = original_index
    calls.clear()
    second_failure = run(independent, 21)
    assert new in calls
    assert second_failure["status"] == "failed"
    assert second_failure["previous_snapshot_id"] == baseline["snapshot_id"]
    pages[new] = b"<h1>SGN Endorsements New</h1><p>Recovered authored article.</p>"
    recovered = run(independent, 22)
    assert recovered["status"] == "updated" and recovered["baseline_reviewed"] is False
    assert run(independent, 23)["status"] == "unchanged"
    for relative, raw in history.items():
        assert (independent / relative).read_bytes() == raw
    assert not list(independent.rglob("vault/**/*.json"))
    assert not any(
        b"Recovered authored article" in p.read_bytes() for p in independent.rglob("*.json")
    )


@pytest.mark.parametrize("derived_size", [25 * 1024 * 1024, 25 * 1024 * 1024 + 1])
def test_sgn_escaped_heading_size_preserves_recoverable_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, derived_size: int
) -> None:
    from election_guide.collection.verification import read_policy
    from election_guide.collection.verification_runtime import run_verification
    from election_guide.collection.verification_state import validate_state

    monkeypatch.delenv("ENDORSEMENT_EVIDENCE_KEY", raising=False)
    policy = read_policy(ROOT / "config/verification.yaml")
    election = policy.elections[0]
    policy = policy.model_copy(
        update={
            "elections": [
                election.model_copy(
                    update={
                        "sources": [
                            s for s in election.sources if s.source_id == "seattle-gay-news"
                        ]
                    }
                )
            ]
        }
    )
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy.model_dump(mode="json")))
    index = "https://www.sgn.org/ch/News/Seattle"
    known = "https://www.sgn.org/story/168513/"
    new = "https://www.sgn.org/story/199999/"
    original_article = (
        b"<h1>SGN Endorsements Pramila Jayapal (US House of Representatives 7th District)</h1>"
    )
    original_index = b'<a href="/story/168513/News/Seattle/SGN%20Endorsements">Boundary</a>'
    pages: dict[str, bytes | Exception] = {index: original_index, known: original_article}

    def fetch(url: str) -> HttpArtifact:
        value = pages[url]
        if isinstance(value, Exception):
            raise value
        return HttpArtifact(value, 200, url, [], "text/html")

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)

    def run(root: Path, day: int) -> dict[str, Any]:
        report = run_verification(
            policy,
            root,
            datetime.fromisoformat(f"2026-10-{day:02d}T18:00:00+00:00"),
            live=True,
            fixtures=None,
        )
        validate_state(policy, root)
        return report["automatic"][0]

    state = tmp_path / "state"
    baseline = run(state, 19)
    assert baseline["status"] == "created"
    approve_baseline(
        state / "wa-2026-general",
        baseline["snapshot_id"],
        "Fixture reviewer",
        datetime.fromisoformat("2026-10-19T19:00:00+00:00"),
        "Authored fixture publication only; no actual source approval or live adoption.",
    )
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    # Each literal quote becomes six ASCII bytes (&quot;). Account independently
    # for both paragraph wrappers, the 71-byte digest comment and the HTML shell.
    fixed = (
        b"<html><body><p>SGN Endorsements </p><p>SGN Endorsements New</p><!--"
        + b"0" * 64
        + b"--></body></html>"
    )
    quotes, remainder = divmod(derived_size - len(fixed), 6)
    expanded_article = b"<h1>SGN Endorsements " + b'"' * quotes + b"x" * remainder + b"</h1>"
    assert len(expanded_article) < 25 * 1024 * 1024
    pages[known] = expanded_article
    pages[index] = original_index + b'<a href="/story/199999/">SGN Endorsements New</a>'
    pages[new] = b"<h1>SGN Endorsements New</h1>"
    failed = run(state, 20)
    assert failed["status"] == "failed" and failed["snapshot_id"] is None
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    assert failed["consecutive_failures"] == 1
    assert len(list(state.rglob("extractions/*.json"))) == 1
    manifests = [json.loads(p.read_text()) for p in state.rglob("manifests/*.json")]
    originals = [m for m in manifests if m["retrieved_at"].startswith("2026-10-20")]
    assert {m["requested_url"] for m in originals if m["capture_method"] == "static_html"} == {
        index,
        known,
        new,
    }
    if derived_size == 25 * 1024 * 1024:
        comparison = next(m for m in manifests if m["id"] == failed["capture_id"])
        assert comparison["byte_length"] == derived_size
        assert failed["error"] == "complete adapter detected no decision lines"
        assert len(list(state.rglob("discovery/*.json"))) == 2
    else:
        assert failed["capture_id"] is None
        assert len(list(state.rglob("discovery/*.json"))) == 1
        assert all(m["capture_method"] == "static_html" for m in originals)
    assert any(
        new in json.loads(p.read_text())["articles"]
        for p in state.rglob("discovery-obligations/*.json")
    )
    for relative, raw in history.items():
        assert (state / relative).read_bytes() == raw
    # Public records alone must preserve this failure and learned membership.
    history = {p.relative_to(state): p.read_bytes() for p in state.rglob("*.json")}
    independent = tmp_path / "independent"
    assert all(p.suffix == ".json" for p in state.rglob("*") if p.is_file())
    assert not list(state.rglob("vault/**/*.json"))
    for relative, raw in history.items():
        target = independent / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    pages[index] = original_index
    pages[known] = original_article
    pages[new] = OSError("learned article unavailable after link rotation")
    retry = run(independent, 21)
    assert retry["status"] == "failed" and retry["consecutive_failures"] == 2
    assert retry["previous_snapshot_id"] == baseline["snapshot_id"]
    pages[new] = b"<h1>SGN Endorsements New</h1><p>Recovered authored article.</p>"
    recovered = run(independent, 22)
    assert recovered["status"] == "updated" and recovered["baseline_reviewed"] is False
    assert recovered["previous_snapshot_id"] == baseline["snapshot_id"]
    assert recovered["consecutive_failures"] == 0 and recovered["escalated"] is False
    assert run(independent, 23)["status"] == "unchanged"
    for relative, raw in history.items():
        assert (independent / relative).read_bytes() == raw
    tasks = runner.invoke(
        app,
        [
            "verification",
            "reconcile",
            str(policy_path),
            "--state-root",
            str(independent),
            "--repository",
            "example/guide",
            "--revision",
            "a" * 40,
            "--as-of",
            "2026-10-23",
            "--dry-run",
        ],
    )
    assert tasks.exit_code == 0, tasks.output
    assert failed["id"] in tasks.output and retry["id"] in tasks.output
    assert recovered["id"] in tasks.output and "**failed**" in tasks.output


@pytest.mark.parametrize(
    "corruption",
    ["url", "duplicate", "bound", "capture", "source", "time", "method", "index", "identity"],
)
def test_sgn_obligation_reader_rejects_invalid_public_evidence(
    tmp_path: Path, corruption: str
) -> None:
    from election_guide.collection.discovery import (
        SgnDiscoveryObligation,
        read_sgn_discovery_obligation,
    )
    from election_guide.evidence.models import CaptureRequest, evidence_fingerprint
    from election_guide.evidence.storage import record_observation

    checked_at = datetime.fromisoformat("2026-10-20T18:00:00+00:00")
    body = tmp_path / "input.html"
    body.write_bytes(b'<a href="/story/199999/">SGN Endorsements New</a>')
    manifest = record_observation(
        CaptureRequest(
            source_id="sage-leaders" if corruption == "source" else "seattle-gay-news",
            requested_url="https://www.sgn.org/story/199999/"
            if corruption == "index"
            else "https://www.sgn.org/ch/News/Seattle",
            canonical_url="https://www.sgn.org/story/199999/"
            if corruption == "index"
            else "https://www.sgn.org/ch/News/Seattle",
            title="Authored fixture index",
            retrieved_at=checked_at,
            media_type="text/html",
            capture_method="manual_upload" if corruption == "method" else "static_html",
            http_status=None if corruption == "method" else 200,
            redistribution="restricted",
            redistribution_note="Public fixture metadata only.",
        ),
        body,
        tmp_path / "manifests",
    )
    record = SgnDiscoveryObligation(
        checked_at=checked_at,
        articles=["https://www.sgn.org/story/199999/"],
        capture_id=manifest.stem,
    ).model_dump(mode="json")
    if corruption == "url":
        record["articles"] = ["https://evil.example/story/199999/"]
    elif corruption == "duplicate":
        record["articles"] *= 2
    elif corruption == "bound":
        record["articles"] = [f"https://www.sgn.org/story/{i}/" for i in range(101)]
    elif corruption == "capture":
        record["capture_id"] = "capture-seattle-gay-news-20261020T180000Z-000000000000"
    elif corruption == "time":
        record["checked_at"] = "2026-10-21T18:00:00Z"
    directory = tmp_path / "discovery-obligations"
    directory.mkdir()
    identity = "0" * 64 if corruption == "identity" else evidence_fingerprint(record)
    path = directory / f"{identity}.json"
    path.write_text(json.dumps(record))
    with pytest.raises((ValueError, OSError)):
        read_sgn_discovery_obligation(path)
