"""Autonomous acquisition uses offline transports; it never admits partial results."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

import election_guide.results as results
from election_guide.collection.http import HttpArtifact, HttpFetchFailure
from election_guide.evidence.models import CapturedManifest, UnavailableManifest
from election_guide.evidence.storage import read_capture_manifest, verify_capture

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 11, 6, 19, tzinfo=UTC)


def repository(tmp_path: Path) -> Path:
    target = tmp_path / "config/authorities/default.yaml"
    target.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "config/authorities/default.yaml", target)
    return tmp_path


def test_acquire_preserves_direct_json_bytes_http_clock_and_authority(tmp_path: Path) -> None:
    acquire = results.acquire_preliminary
    body = (ROOT / "tests/fixtures/results/wa-2026-general-historical-county.json").read_bytes()
    calls: list[str] = []

    def fetch(url: str) -> HttpArtifact:
        calls.append(url)
        return HttpArtifact(body, 200, url, [], "application/json; charset=utf-8")

    manifest_path = acquire(
        "county", repository_root=repository(tmp_path), fetcher=fetch, clock=lambda: NOW
    )
    manifest = read_capture_manifest(manifest_path)
    assert isinstance(manifest, CapturedManifest)
    assert manifest.source_id == "king-county-elections"
    assert manifest.capture_method == "json"
    assert manifest.http_status == 200 and manifest.retrieved_at == NOW
    assert manifest.storage_scope == "repository"
    assert len(calls) == 1 and calls[0].endswith("/king-county-wa/20261103/data")
    verify_capture(
        manifest,
        tmp_path / "data/evidence/official",
        repository_storage_root=tmp_path / "data/evidence/official",
    )
    assert not (tmp_path / "data/results").exists(), "acquisition is not results admission"


def test_failed_acquisition_retains_a_real_failure_without_retry_or_count_mutation(
    tmp_path: Path,
) -> None:
    acquire = results.acquire_preliminary
    root = repository(tmp_path)
    previous = root / "data/results/wa-2026-general.yaml"
    previous.parent.mkdir(parents=True)
    previous.write_text("previous counts stay literal\n")
    calls: list[str] = []

    def denied(url: str) -> HttpArtifact:
        calls.append(url)
        raise HttpFetchFailure(
            "live collection returned HTTP 403",
            response_status=403,
            followed_redirects=0,
            redirect_class="SAME_ORIGIN",
        )

    with pytest.raises(ValueError, match="403"):
        acquire("statewide", repository_root=root, fetcher=denied, clock=lambda: NOW)
    manifests = list((root / "data/manifests/evidence").glob("*.json"))
    assert len(calls) == len(manifests) == 1
    failure = read_capture_manifest(manifests[0])
    assert isinstance(failure, UnavailableManifest)
    assert failure.source_id == "wa-secretary-of-state" and failure.http_status == 403
    assert failure.retrieved_at == NOW
    assert previous.read_text() == "previous counts stay literal\n"


@pytest.mark.parametrize("source", ["https://example.com", "unknown", "county/../statewide"])
def test_unknown_source_is_rejected_before_fetch_or_write(tmp_path: Path, source: str) -> None:
    acquire = results.acquire_preliminary

    def unexpected(url: str) -> HttpArtifact:
        pytest.fail(f"unreviewed source requested: {url}")

    with pytest.raises(ValueError, match="source"):
        acquire(source, repository_root=tmp_path, fetcher=unexpected, clock=lambda: NOW)
    assert not list(tmp_path.iterdir())


def test_wrong_election_is_retained_as_failure_not_admitted(tmp_path: Path) -> None:
    acquire = results.acquire_preliminary
    raw = json.loads(
        (ROOT / "tests/fixtures/results/wa-2026-general-historical-state.json").read_bytes()
    )
    raw["electionDate"] = "2026-08-04"

    def fetch(url: str) -> HttpArtifact:
        return HttpArtifact(json.dumps(raw).encode(), 200, url, [], "application/octet-stream")

    with pytest.raises(ValueError, match="election"):
        acquire("statewide", repository_root=repository(tmp_path), fetcher=fetch, clock=lambda: NOW)
    assert not (tmp_path / "data/results").exists()


def test_cli_requires_live_opt_in_before_any_network_or_write(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from election_guide.cli import app

    result = CliRunner().invoke(
        app, ["results", "acquire-preliminary", "county", "--repository-root", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "--live" in result.output
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("status", [301, 401, 403])
def test_subsequent_tick_does_not_repeat_a_held_denial_or_redirect(
    tmp_path: Path, status: int
) -> None:
    calls: list[str] = []
    root = repository(tmp_path)

    def fail(url: str) -> HttpArtifact:
        calls.append(url)
        raise HttpFetchFailure(
            f"live response HTTP {status}",
            response_status=status,
            followed_redirects=0,
            redirect_class="REFUSED" if status == 301 else "SAME_ORIGIN",
        )

    with pytest.raises(ValueError, match=str(status)):
        results.acquire_preliminary("county", repository_root=root, fetcher=fail, clock=lambda: NOW)
    with pytest.raises(ValueError, match="held"):
        results.acquire_preliminary("county", repository_root=root, fetcher=fail, clock=lambda: NOW)
    assert len(calls) == 1, "an autonomous next tick cannot repeat the denied operation"
    assert len(list((root / "data/manifests/evidence").glob("*.json"))) == 1
