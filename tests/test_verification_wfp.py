"""WFP complete responses travel through the existing encrypted archive pipeline."""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from election_guide.collection.http import HttpArtifact
from election_guide.collection.vault import restore_store
from election_guide.collection.verification import read_policy
from election_guide.collection.verification_runtime import run_verification

ROOT = Path(__file__).parents[1]
SOURCE = "washington-working-families-party"
ENDPOINT = "https://workingfamilies.org/wp-admin/admin-ajax.php"
FORM = {"action": "more_candidates", "state": "25", "count": "0"}


@pytest.mark.parametrize(
    "visible_attributes",
    [
        b"",
        b' aria-hidden="false" class="externally-hidden" '
        b'style="display: table-row; visibility: visible; content-visibility: visible"',
    ],
    ids=["plain", "visible-attributes"],
)
def test_live_wfp_collects_complete_response_and_records_truthful_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, visible_attributes: bytes
) -> None:
    key = bytes(range(32))
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(key).decode())
    policy = read_policy(ROOT / "config/verification.yaml")
    election = policy.elections[0]
    source = next(s for s in election.sources if s.source_id == SOURCE)
    policy = policy.model_copy(
        update={"elections": [election.model_copy(update={"sources": [source]})]}
    )
    complete = (ROOT / f"tests/fixtures/verification/{SOURCE}.html").read_bytes()
    complete = complete.replace(b"<tr>", b"<tr" + visible_attributes + b">").replace(
        b"<td>", b"<td" + visible_attributes + b">"
    )
    initial = (ROOT / f"tests/fixtures/verification/{SOURCE}-initial-page.html").read_bytes()

    def fetch(url: str, *, form: dict[str, str] | None = None) -> HttpArtifact:
        body = complete if url == ENDPOINT and form == FORM else initial
        return HttpArtifact(body, 200, url, [], "text/html")

    monkeypatch.setattr("election_guide.collection.verification_runtime.fetch_http", fetch)
    state = tmp_path / "state"
    first = run_verification(
        policy, state, datetime.fromisoformat("2026-10-05T18:00:00+00:00"), live=True, fixtures=None
    )
    event = first["automatic"][0]
    assert event["status"] == "created", event
    assert len(event["diff"]) == 10
    assert event["baseline_reviewed"] is False
    root = state / "wa-2026-general"
    snapshot = json.loads((root / "extractions" / f"{event['snapshot_id']}.json").read_text())
    assert {tuple(decision["candidate_ids"]) for decision in snapshot["decisions"]} == {
        ("us-house-7--pramila-jayapal",),
        ("king-county-council-4--jorge-l-baron",),
        ("king-county-council-8--teresa-mosqueda",),
        ("seattle-city-council-5--nilu-jenks",),
        ("ld-37-state-representative-1--kelabe-tewolde",),
        ("ld-37-state-representative-2--jaelynn-scott",),
        ("ld-43-state-representative-2--shaun-scott",),
        ("ld-46-state-representative-2--darya-farivar",),
        ("ld-36-state-senator--noel-c-frame",),
        ("ld-43-state-senator--hannah-sabio-howell",),
    }
    assert all(decision["requires_review"] for decision in snapshot["decisions"])
    manifest = json.loads((root / "manifests" / f"{event['capture_id']}.json").read_text())
    assert manifest["requested_url"] == manifest["canonical_url"] == ENDPOINT
    assert manifest["http_status"] == 200
    assert "POST" in manifest["redistribution_note"]
    assert "action=more_candidates&state=25&count=0" in manifest["redistribution_note"]
    assert manifest["content_sha256"] == hashlib.sha256(complete).hexdigest()
    restored = tmp_path / "restored"
    restore_store(root / "vault", restored, key)
    assert any(p.read_bytes() == complete for p in restored.rglob("*") if p.is_file())
    assert not list(state.rglob("*.html"))
    before = {p: p.read_bytes() for p in (root / "vault").rglob("*.json")}
    second = run_verification(
        policy, state, datetime.fromisoformat("2026-10-06T18:00:00+00:00"), live=True, fixtures=None
    )
    assert second["automatic"][0]["status"] == "unchanged"
    assert second["automatic"][0]["snapshot_id"] == event["snapshot_id"]
    assert {p: p.read_bytes() for p in (root / "vault").rglob("*.json")} == before
    assert second["automatic"][0]["baseline_reviewed"] is False


@pytest.mark.parametrize(
    "replacement",
    [
        b"<tr><td>Unknown Candidate</td><td>Washington State Senate, District 43</td></tr>",
        b"<tr><td>Hannah Sabio-Howell</td></tr>",
        b"<tr><td>Hannah Sabio-Howell</td><td></td></tr>",
        b"<tr><td>Hannah Sabio-Howell</td><td>Washington State Senate, District 43",
        b"",
        *[
            pytest.param(template.format(attributes=attributes).encode(), id=f"{element}-{style}")
            for element, template in [
                (
                    "row",
                    "<tr {attributes}><td>Hannah Sabio-Howell</td>"
                    "<td>Washington State Senate, District 43</td></tr>",
                ),
                (
                    "name-cell",
                    "<tr><td {attributes}>Hannah Sabio-Howell</td>"
                    "<td>Washington State Senate, District 43</td></tr>",
                ),
                (
                    "office-cell",
                    "<tr><td>Hannah Sabio-Howell</td>"
                    "<td {attributes}>Washington State Senate, District 43</td></tr>",
                ),
            ]
            for style, attributes in [
                ("hidden", "hidden"),
                ("aria-hidden", 'aria-hidden="true"'),
                ("display", 'style="display: none"'),
                ("visibility", 'style="visibility: hidden"'),
                ("content-visibility", 'style="content-visibility: hidden"'),
            ]
        ],
    ],
)
def test_complete_fixture_reuses_baseline_and_expanded_only_break_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement: bytes
) -> None:
    monkeypatch.setenv("ENDORSEMENT_EVIDENCE_KEY", base64.b64encode(bytes(range(32))).decode())
    policy = read_policy(ROOT / "config/verification.yaml")
    election = policy.elections[0]
    source = next(s for s in election.sources if s.source_id == SOURCE)
    policy = policy.model_copy(
        update={"elections": [election.model_copy(update={"sources": [source]})]}
    )
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    original = (ROOT / f"tests/fixtures/verification/{SOURCE}.html").read_bytes()
    target = fixtures / f"{SOURCE}.html"
    target.write_bytes(original)
    state = tmp_path / "state"

    def run(day: str) -> dict[str, Any]:
        return run_verification(
            policy,
            state,
            datetime.fromisoformat(f"2026-10-{day}T18:00:00+00:00"),
            live=False,
            fixtures=fixtures,
        )

    first = run("05")["automatic"][0]
    assert first["status"] == "created"
    assert len(first["diff"]) == 10
    root = state / "wa-2026-general"
    extractions = {p: p.read_bytes() for p in (root / "extractions").glob("*.json")}
    preserved = {p: p.read_bytes() for p in (root / "vault").rglob("*.json")}
    second = run("06")["automatic"][0]
    assert second["status"] == "unchanged"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert {p: p.read_bytes() for p in (root / "vault").rglob("*.json")} == preserved
    # All preceding rows stay identical; only the final mapped row changes.
    prefix, _, _ = original.rpartition(b"<tr>")
    target.write_bytes(prefix + replacement if replacement else b"")
    failed = run("07")["automatic"][0]
    assert failed["status"] == "failed", failed
    assert failed["previous_snapshot_id"] == first["snapshot_id"]
    assert failed["snapshot_id"] is None
    assert failed["diff"] == []
    assert failed["error"]
    assert {p: p.read_bytes() for p in (root / "extractions").glob("*.json")} == extractions
    assert not (root / "approvals").exists()
    assert not list(state.rglob("*.html"))


@pytest.mark.parametrize(
    "change",
    [
        {"source_id": "seiu-775"},
        {"adapter": None},
        {"request": {"url": "https://example.com/form", "method": "POST", "form": FORM}},
        {"request": {"url": ENDPOINT, "method": "GET", "form": FORM}},
        {"request": {"url": ENDPOINT, "method": "POST", "form": {**FORM, "count": "10"}}},
        {"request": {"url": ENDPOINT, "method": "POST", "form": {**FORM, "token": "anything"}}},
    ],
)
def test_request_policy_rejects_other_sources_endpoints_and_forms(change: dict[str, Any]) -> None:
    from pydantic import ValidationError

    from election_guide.collection.verification import SourcePolicy

    valid = {
        "source_id": SOURCE,
        "adapter": "config/adapters/wa-2026-general/washington-working-families-party.yaml",
        "request": {"url": ENDPOINT, "method": "POST", "form": FORM},
    }
    with pytest.raises(ValidationError):
        SourcePolicy.model_validate({**valid, **change})
