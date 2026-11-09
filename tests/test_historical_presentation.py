"""Current presentation must preserve the archive's verified election facts (#721)."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest

from election_guide.hosting.models import PublishedElection
from election_guide.hosting.pages import (
    _verify_bundle,  # pyright: ignore[reportPrivateUsage]
    bundle_hash,
    read_site_manifest,
    stage_pages_site,
    verify_staged_pages_site,
)
from election_guide.hosting.production_probe import run_production_check
from election_guide.hosting.updates import build_updates_snapshot, check_updates
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import render_html_document
from election_guide.serialization import canonical_json_bytes
from tests.test_hosting import (  # pyright: ignore[reportPrivateUsage]
    COMMIT,
    CURRENT_ID,
    OLDER_COMMIT,
    OLDER_ID,
    PANEL_HASH,
    _write_release_bundle,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_production_probe import _start  # pyright: ignore[reportPrivateUsage]


def _reseal_view(bundle: Path, view: dict[str, Any]) -> None:
    path = bundle / "data/publication_view_model.json"
    path.write_bytes(canonical_json_bytes(view))
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["artifact_hashes"]["data/publication_view_model.json"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def _archive(
    root: Path, *, election_id: str = CURRENT_ID, commit: str = COMMIT, schema: str = "1.9"
) -> tuple[Path, PublishedElection, dict[str, Any]]:
    registry_hash = "d" * 64 if schema == "1.14" else None
    bundle = _write_release_bundle(
        root,
        election_id=election_id,
        release_version="primary.2",
        git_commit=commit,
        html=b"<main>Archived presentation</main>",
        source_registry_hash=registry_hash,
    )
    view = json.loads((bundle / "data/publication_view_model.json").read_bytes())
    view["metadata"].update(
        git_commit=commit,
        generated_at="2026-07-21T12:00:00Z",
        data_as_of="2026-07-20T12:00:00Z",
        source_panel_id="test-panel-v2",
        source_panel_hash=PANEL_HASH,
    )
    view["personalization"].update(panel_id="test-panel-v2", panel_hash=PANEL_HASH)
    view["schema_version"] = schema
    _reseal_view(bundle, view)
    declaration = PublishedElection(
        election_id=election_id,
        bundle_id=election_id + "-archive",
        release_version="primary.2",
        source_panel_id="test-panel-v2",
        source_panel_hash=PANEL_HASH,
        source_registry_hash=registry_hash,
    )
    return bundle, declaration, view


def _results(view: dict[str, Any]) -> dict[str, Any]:
    race = next(
        race
        for section in view["sections"]
        for race in section["races"]
        if race["explicit_endorsement_count"] >= 2
    )
    candidate_id = "recorded-choice"
    race["race_type"] = "candidate"
    race["candidates"] = [{"id": candidate_id, "label": "Recorded choice"}]
    view["metadata"]["election_type"] = "primary"
    results = {
        "schema_version": "1.0",
        "election_id": view["metadata"]["election_id"],
        "status": "certified",
        "certified_on": "2026-08-18",
        "captures": [
            {"kind": "certified", "captured_at": "2026-08-19T12:00:00Z", "evidence": "receipt"}
        ],
        "races": [
            {
                "race_id": race["id"],
                "authority": "Recorded authority",
                "capture_evidence": "receipt",
                "ballots_counted": 10,
                "outcomes": [
                    {"choice_id": candidate_id, "votes": 10, "share": 1.0, "advanced": True}
                ],
            }
        ],
    }
    view["results"] = results
    return results


@pytest.mark.parametrize("schema", ["1.9", "1.13", "1.14"])
def test_legacy_no_results_archive_remains_renderable_without_modern_facts(
    tmp_path: Path, schema: str
) -> None:
    bundle, declaration, view = _archive(tmp_path, schema=schema)
    view["schema_version"] = schema
    view.pop("results", None)
    view.pop("corrections", None)
    _reseal_view(bundle, view)
    before = {p.relative_to(bundle): p.read_bytes() for p in bundle.rglob("*") if p.is_file()}

    admitted = _verify_bundle(declaration, bundle, current_presentation=True)

    assert admitted.view_model.results is None
    assert admitted.view_model.metadata.election_type is None
    assert admitted.view_model.sections[0].races[0].candidates == []
    assert before == {
        p.relative_to(bundle): p.read_bytes() for p in bundle.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "fault",
    ["election", "roster", "type", "election-type", "choice", "race", "counting", "capture"],
)
def test_result_bearing_archive_rejects_ambiguous_or_mismatched_facts(
    tmp_path: Path, fault: str
) -> None:
    bundle, declaration, view = _archive(tmp_path)
    results = _results(view)
    race = next(
        race
        for section in view["sections"]
        for race in section["races"]
        if race["id"] == results["races"][0]["race_id"]
    )
    if fault == "election":
        results["election_id"] = "another-election"
    elif fault == "roster":
        race.pop("candidates")
    elif fault == "type":
        race.pop("race_type")
    elif fault == "election-type":
        view["metadata"].pop("election_type")
    elif fault == "choice":
        results["races"][0]["outcomes"][0]["choice_id"] = "unknown-choice"
    elif fault == "race":
        results["races"][0]["race_id"] = "unknown-race"
    elif fault == "counting":
        results["status"] = "counting"
        results["certified_on"] = None
    else:
        results["races"][0]["capture_evidence"] = "missing-receipt"
    _reseal_view(bundle, view)

    with pytest.raises(ValueError, match="presentation"):
        _verify_bundle(declaration, bundle, current_presentation=True)


def test_archive_requires_an_explicit_publication_schema(tmp_path: Path) -> None:
    bundle, declaration, view = _archive(tmp_path, schema="1.14")
    view.pop("schema_version")
    # A missing schema must not acquire today's default merely because a hash is supplied.
    _reseal_view(bundle, view)
    with pytest.raises(ValueError, match=r"presentation.*schema"):
        _verify_bundle(declaration, bundle, current_presentation=True)


@pytest.mark.parametrize("schema", ["1.11", "2.0", [], None])
def test_unsupported_or_corrupt_publication_schema_fails_closed(
    tmp_path: Path, schema: object
) -> None:
    bundle, declaration, view = _archive(tmp_path)
    view["schema_version"] = schema
    _reseal_view(bundle, view)
    with pytest.raises(ValueError, match=r"presentation.*schema"):
        _verify_bundle(declaration, bundle, current_presentation=True)


def _current_site(root: Path) -> tuple[Path, dict[str, Path], dict[str, bytes]]:
    current, declaration, current_view = _archive(root / "current")
    current_view["comparisons"]["policy"]["enabled"] = True
    _reseal_view(current, current_view)
    older, old_declaration, view = _archive(
        root / "older", election_id=OLDER_ID, commit=OLDER_COMMIT
    )
    _results(view)
    view["comparisons"]["policy"]["enabled"] = True
    view["corrections"] = {
        "schema_version": "1.2",
        "election_id": OLDER_ID,
        "entries": [
            {
                "slug": "recorded-update",
                "corrected_on": "2026-08-19",
                "headline": "Recorded result",
                "body": "The recorded result remains unchanged.",
                "topics": ["results"],
                "actions": ["certified"],
            }
        ],
    }
    _reseal_view(older, view)
    old_declaration = old_declaration.model_copy(
        update={
            "git_commit": OLDER_COMMIT,
            "release_manifest_sha256": hashlib.sha256(
                (older / "release-manifest.json").read_bytes()
            ).hexdigest(),
            "bundle_sha256": bundle_hash(older),
        }
    )
    path = root / "site.yaml"
    path.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "1.1",
                "canonical_origin": "https://seattleelections.guide",
                "current_election_id": CURRENT_ID,
                "elections": [declaration.model_dump(), old_declaration.model_dump()],
            }
        )
    )
    assignments = {declaration.bundle_id: current, old_declaration.bundle_id: older}
    before = {
        f"{key}/{p.relative_to(bundle)}": p.read_bytes()
        for key, bundle in assignments.items()
        for p in bundle.rglob("*")
        if p.is_file()
    }
    return path, assignments, before


def test_current_presentation_renders_all_historical_html_without_replacing_the_archive(
    tmp_path: Path,
) -> None:
    manifest, bundles, before = _current_site(tmp_path)
    output = tmp_path / "site"

    stage_pages_site(manifest, bundles, output, expected_current_git_commit=COMMIT)

    deployed = verify_staged_pages_site(output, manifest, expected_current_git_commit=COMMIT)
    assert deployed.schema_version == "3.0"
    raw = json.loads((output / "deployment-manifest.json").read_bytes())
    old = raw["elections"][1]
    assert old["git_commit"] == OLDER_COMMIT
    assert old["presentation"]["source_git_commit"] == COMMIT
    assert old["presentation"]["archive_git_commit"] == OLDER_COMMIT
    assert old["presentation"]["generated_at"] == "2026-07-21T12:00:00Z"
    root = output / "e" / OLDER_ID
    expected = {"index.html", "sources/index.html", "comparisons/index.html", "updates/index.html"}
    expected.add("updates/recorded-update/index.html")
    expected.update(p.relative_to(root).as_posix() for p in root.glob("races/*/index.html"))
    assert len(expected) > 5
    for relative in expected:
        html = (root / relative).read_text()
        assert f'<meta name="seg-data-source" content="{OLDER_COMMIT}">' in html
        assert f'<meta name="seg-presentation-source" content="{COMMIT}">' in html
        assert f'/commit/{COMMIT}"' in html
        assert "Archived presentation" not in html
    overview = (root / "index.html").read_text()
    assert "Recorded choice" in overview
    assert "10 ballots" in overview
    assert "Certified on Aug 18, 2026" in overview
    assert before == {
        f"{key}/{p.relative_to(bundle)}": p.read_bytes()
        for key, bundle in bundles.items()
        for p in bundle.rglob("*")
        if p.is_file()
    }


def _reseal_site(site: Path) -> None:
    manifest_path = site / "deployment-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())

    def write_hashes() -> None:
        manifest["assets"] = {
            p.relative_to(site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in site.rglob("*")
            if p.is_file() and p != manifest_path
        }
        manifest_path.write_bytes(canonical_json_bytes(manifest))

    write_hashes()
    (site / "updates-snapshot.json").write_bytes(
        canonical_json_bytes(build_updates_snapshot(site).model_dump(mode="json"))
    )
    write_hashes()


def _replace_archive_overview(bundle: Path, html: bytes) -> None:
    status = json.loads((bundle / "release-status.json").read_bytes())
    path = bundle / status["guide_html_artifact"]
    path.write_bytes(html)
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["artifact_hashes"][status["guide_html_artifact"]] = hashlib.sha256(html).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def _refresh_synthetic_archive_pins(
    manifest_path: Path, bundles: dict[str, Path]
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_bytes())
    for declaration in manifest["elections"]:
        if declaration.get("git_commit") is not None:
            bundle = bundles[declaration["bundle_id"]]
            declaration["release_manifest_sha256"] = hashlib.sha256(
                (bundle / "release-manifest.json").read_bytes()
            ).hexdigest()
            declaration["bundle_sha256"] = bundle_hash(bundle)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    return manifest


def test_current_projection_can_use_old_presentation_bytes_without_serving_retired_ui(
    tmp_path: Path,
) -> None:
    manifest, bundles, _ = _current_site(tmp_path)
    older = bundles[OLDER_ID + "-archive"]
    _replace_archive_overview(
        older, b'<main style="--meter-fill:100%">Archived presentation</main>'
    )
    declaration = _refresh_synthetic_archive_pins(manifest, bundles)
    before = bundle_hash(older)
    stage_pages_site(manifest, bundles, tmp_path / "projected")
    page = (tmp_path / "projected/e" / OLDER_ID / "index.html").read_text()
    assert "--meter-fill" not in page and "Archived presentation" not in page
    assert "Recorded choice" in page
    assert before == bundle_hash(older)

    declaration["schema_version"] = "1.0"
    manifest.write_bytes(canonical_json_bytes(declaration))
    with pytest.raises(ValueError, match="retired endorsement meter"):
        stage_pages_site(manifest, bundles, tmp_path / "legacy")


def test_original_schema2_baseline_and_current_projection_share_snapshot6_facts(
    tmp_path: Path,
) -> None:
    manifest, bundles, _ = _current_site(tmp_path)
    configuration = read_rendering_configuration(Path("config/rendering/guide.yaml"))
    for bundle in bundles.values():
        view = PublicationViewModel.model_validate_json(
            (bundle / "data/publication_view_model.json").read_bytes()
        )
        _replace_archive_overview(bundle, render_html_document(view, configuration).encode())
    declaration = _refresh_synthetic_archive_pins(manifest, bundles)
    declaration["schema_version"] = "1.0"
    manifest.write_bytes(canonical_json_bytes(declaration))
    baseline = tmp_path / "published"
    stage_pages_site(manifest, bundles, baseline)
    declaration["schema_version"] = "1.1"
    manifest.write_bytes(canonical_json_bytes(declaration))
    candidate = tmp_path / "candidate"
    stage_pages_site(manifest, bundles, candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"
    assert build_updates_snapshot(baseline).schema_version == "6.0"
    assert build_updates_snapshot(candidate).schema_version == "6.0"
    page = candidate / "e" / OLDER_ID / "index.html"
    page.write_text(page.read_text().replace("10 ballots", "11 ballots"))
    _reseal_site(candidate)
    report = check_updates(baseline, candidate)
    assert report["result"] == "fail"
    assert report["elections"][OLDER_ID]["new_entries"] == []


@pytest.mark.parametrize(
    "route",
    [
        "index.html",
        "sources/index.html",
        "comparisons/index.html",
        "updates/recorded-update/index.html",
    ],
)
def test_independent_verifier_rejects_rehashed_historical_page_provenance(
    tmp_path: Path, route: str
) -> None:
    manifest, bundles, _ = _current_site(tmp_path)
    site = tmp_path / "site"
    stage_pages_site(manifest, bundles, site)
    page = site / "e" / OLDER_ID / route
    page.write_text(
        page.read_text().replace(
            f'<meta name="seg-presentation-source" content="{COMMIT}">',
            f'<meta name="seg-presentation-source" content="{OLDER_COMMIT}">',
        )
    )
    _reseal_site(site)

    with pytest.raises(ValueError, match="presentation"):
        verify_staged_pages_site(site, manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_git_commit", "b" * 40),
        ("generated_at", "2026-07-22T12:00:00Z"),
        ("archive_git_commit", "b" * 40),
        ("archive_release_version", "another.1"),
        ("publication_view_model_sha256", "b" * 64),
        ("release_manifest_sha256", "b" * 64),
    ],
)
def test_projection_provenance_is_bound_to_both_source_and_archive(
    tmp_path: Path, field: str, value: str
) -> None:
    manifest, bundles, _ = _current_site(tmp_path)
    site = tmp_path / "site"
    stage_pages_site(manifest, bundles, site)
    path = site / "deployment-manifest.json"
    raw = json.loads(path.read_bytes())
    raw["elections"][1]["presentation"][field] = value
    path.write_bytes(canonical_json_bytes(raw))
    with pytest.raises(ValueError, match="presentation"):
        verify_staged_pages_site(site, manifest)


@pytest.mark.parametrize(
    "fault", [None, "bytes", "metadata", "status-election", "archive-manifest"]
)
def test_production_rejects_http_200_historical_html_with_wrong_bytes_or_provenance(
    tmp_path: Path, fault: str | None
) -> None:
    manifest, bundles, _ = _current_site(tmp_path)
    site = tmp_path / "site"
    stage_pages_site(manifest, bundles, site)
    page = site / "e" / OLDER_ID / "index.html"
    if fault == "metadata":
        page.write_text(
            page.read_text().replace(
                f'<meta name="seg-presentation-source" content="{COMMIT}">',
                f'<meta name="seg-presentation-source" content="{OLDER_COMMIT}">',
            )
        )
        _reseal_site(site)
    elif fault == "bytes":
        page.write_text("<main>Obsolete overview with wrong election facts</main>")
    elif fault == "status-election":
        status_path = site / "e" / CURRENT_ID / "release-status.json"
        status = json.loads(status_path.read_bytes())
        status["election_id"] = "another-election"
        status_path.write_bytes(canonical_json_bytes(status))
        _reseal_site(site)
    elif fault == "archive-manifest":
        release_path = site / "e" / OLDER_ID / "release-manifest.json"
        release = json.loads(release_path.read_bytes())
        release["release_version"] = "other.1"
        release_path.write_bytes(canonical_json_bytes(release))
        _reseal_site(site)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/" or self.path.endswith("/voter-guide.pdf"):
                self.send_response(307 if self.path == "/" else 301)
                self.send_header("Location", f"https://seattleelections.guide/e/{CURRENT_ID}/")
                self.end_headers()
                return
            path = site / self.path.lstrip("/")
            if self.path.endswith("/"):
                path /= "index.html"
            self.send_response(200 if path.is_file() else 404)
            self.end_headers()
            if path.is_file():
                self.wfile.write(path.read_bytes())

    with contextmanager(_start)(Handler) as origin:
        report = run_production_check(
            origin,
            expected_git_commit=COMMIT,
            timeout=5,
            site_manifest=read_site_manifest(manifest),
        )
    assert report.deployment_contract is not None and report.deployment_contract.ok
    if fault is None:
        assert report.ok
        assert len(report.presentation_assets) >= 14
    else:
        assert not report.ok
        assert "presentation" in " ".join(
            error for check in report.presentation_assets for error in check.errors
        )
