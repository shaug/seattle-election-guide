"""Minimal wording regressions from the completed October 23 source reviews.

These authored excerpts test mappings only; they are not live source baselines.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from election_guide.collection.adapters import ExtractionError, extract_decisions, validate_adapter
from election_guide.collection.discovery import discover_publication
from election_guide.collection.http import HttpArtifact
from election_guide.collection.refresh import read_adapter_spec
from election_guide.collection.verification import read_policy
from election_guide.collection.verification_runtime import run_verification
from election_guide.inventory.importer import read_inventory
from election_guide.sources.registry import read_source_registry

ROOT = Path(__file__).parents[1]
SMITH_URL = "https://www.sgn.org/story/171425/"
SMITH_TITLE = "SGN Endorsements: Adam Smith (US House of Representatives, 9th District)"


@pytest.mark.parametrize(
    ("source_id", "wording", "expected"),
    [
        (
            "seattle-gay-news",
            SMITH_TITLE,
            {"us-house-9": ("endorsed", ["us-house-9--adam-smith"])},
        ),
        (
            "ufcw-3000",
            "Jaime Hawk, Position 3",
            {
                "supreme-court-justice-3": (
                    "endorsed",
                    ["supreme-court-justice-3--jaime-michelle-hawk"],
                )
            },
        ),
        (
            "ufcw-3000",
            "Shaun Scott, State Representative Pos 2",
            {
                "ld-43-state-representative-2": (
                    "endorsed",
                    ["ld-43-state-representative-2--shaun-scott"],
                )
            },
        ),
        (
            "ufcw-3000",
            "Vote NO on I-645 — Protect Tax Relief for Working People\n"
            "Vote NO on I-638 and I-001 — Protect Kids. Reject Hate.",
            {
                f"initiative-26-{number}": ("endorsed", [f"initiative-26-{number}--no"])
                for number in ("001", "638", "645")
            },
        ),
        (
            "ufcw-3000",
            "Kelabe Tewolde, State Representative Pos. 1 (Dual)\n"
            "Sharon Tomiko Santos, State Representative Pos. 1 (Dual)",
            {
                "ld-37-state-representative-1": (
                    "dual_endorsement",
                    [
                        "ld-37-state-representative-1--kelabe-tewolde",
                        "ld-37-state-representative-1--sharon-tomiko-santos",
                    ],
                )
            },
        ),
        (
            "seiu-775",
            "State Representative Pos. 1: Danica Noble\n"
            "State Representative Pos. 1: Sharon Tomiko Santos and Kelabe Tewolde "
            "(both candidates earned an endorsement)\n"
            "County Council Pos. 4: Jorge L. Baron",
            {
                "ld-32-state-representative-1": (
                    "endorsed",
                    ["ld-32-state-representative-1--danica-noble"],
                ),
                "ld-37-state-representative-1": (
                    "dual_endorsement",
                    [
                        "ld-37-state-representative-1--sharon-tomiko-santos",
                        "ld-37-state-representative-1--kelabe-tewolde",
                    ],
                ),
                "king-county-council-4": ("endorsed", ["king-county-council-4--jorge-l-baron"]),
            },
        ),
    ],
)
def test_reviewed_current_wording_maps_exact_ballot_choices(
    source_id: str, wording: str, expected: dict[str, tuple[str, list[str]]]
) -> None:
    spec = read_adapter_spec(ROOT / f"config/adapters/wa-2026-general/{source_id}.yaml")
    validate_adapter(
        spec,
        read_inventory(ROOT / "data/normalized/wa-2026-general-inventory.json"),
        read_source_registry(ROOT / "config/sources/wa-2026-general.yaml"),
    )
    artifact = "".join(f"<p>{line}</p>" for line in wording.splitlines()).encode()
    if source_id == "seiu-775":
        artifact = (
            b"<p>Statewide Ballot Initiatives</p>" + artifact + b"<p>Alaska</p><p>Federal:</p>"
        )
    decisions = extract_decisions(spec, artifact, media_type="text/html")
    assert {d.race_id: (d.status, d.candidate_ids) for d in decisions} == expected
    assert all(d.requires_review for d in decisions)
    # One source/race row holds each dual. A repeated source line is still invalid,
    # including the one measure line that supplies two distinct race decisions.
    with pytest.raises(ExtractionError):
        extract_decisions(spec, artifact + artifact, media_type="text/html")


@pytest.mark.parametrize("failure", ["fetch", "heading"])
def test_sgn_known_smith_article_remains_required_after_index_rotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    complete_policy = read_policy(ROOT / "config/verification.yaml")
    election = complete_policy.elections[0]
    policy = next(s for s in election.sources if s.source_id == "seattle-gay-news")
    runtime_policy = complete_policy.model_copy(
        update={"elections": [election.model_copy(update={"sources": [policy]})]}
    )
    assert policy.index_url is not None
    title = "SGN Endorsements Pramila Jayapal (US House of Representatives 7th District)"
    pages: dict[str, bytes | Exception] = {
        policy.index_url: b'<a href="/story/168513/News/Seattle/SGN%20Endorsements">Boundary</a>',
        "https://www.sgn.org/story/168513/": f"<h1>{title}</h1>".encode(),
        SMITH_URL: f"<h1>{SMITH_TITLE}</h1><p>Vote Smith.</p>".encode(),
    }
    calls: list[str] = []

    def fetch(url: str) -> HttpArtifact:
        calls.append(url)
        value = pages[url]
        if isinstance(value, Exception):
            raise value
        return HttpArtifact(value, 200, url, [], "text/html")

    monkeypatch.setattr("election_guide.collection.discovery.fetch_http", fetch)
    root = tmp_path / "state"
    root.mkdir()
    storage = tmp_path / "temporary" / "vault"
    storage.parent.mkdir()
    body = discover_publication(
        policy, root, storage, datetime(2026, 10, 23, tzinfo=UTC), retention="facts_only"
    )
    assert SMITH_URL in calls
    spec = read_adapter_spec(ROOT / "config/adapters/wa-2026-general/seattle-gay-news.yaml")
    assert {d.race_id for d in extract_decisions(spec, body, media_type="text/html")} == {
        "us-house-7",
        "us-house-9",
    }
    runtime_root = tmp_path / "runtime"
    baseline = run_verification(
        runtime_policy,
        runtime_root,
        datetime(2026, 10, 23, tzinfo=UTC),
        live=True,
        fixtures=None,
    )["automatic"][0]
    assert baseline["status"] == "created"
    assert baseline["baseline_reviewed"] is False
    history = {p: p.read_bytes() for p in runtime_root.rglob("*.json")}
    # Failure on an independent fresh state must also require the known article;
    # no successful discovery audit or currently visible index link is needed.
    independent = tmp_path / "independent"
    independent.mkdir()
    pages[SMITH_URL] = (
        OSError("authored unavailable article")
        if failure == "fetch"
        else b"<h1>Unclassified article</h1>"
    )
    calls.clear()
    with pytest.raises((OSError, ValueError)):
        discover_publication(
            policy, independent, storage, datetime(2026, 10, 24, tzinfo=UTC), retention="facts_only"
        )
    assert SMITH_URL in calls
    assert not list(independent.glob("discovery/*.json"))

    failed = run_verification(
        runtime_policy,
        runtime_root,
        datetime(2026, 10, 24, tzinfo=UTC),
        live=True,
        fixtures=None,
    )["automatic"][0]
    assert failed["status"] == "failed"
    assert failed["snapshot_id"] is None
    assert failed["previous_snapshot_id"] == baseline["snapshot_id"]
    for path, raw in history.items():
        assert path.read_bytes() == raw
