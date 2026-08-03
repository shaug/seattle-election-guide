"""Cloudflare Pages archive composition and routing tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.hosting import (
    stage_pages_site,
    verify_staged_pages_site,
)
from election_guide.hosting.models import PublishedElection, SiteManifest
from election_guide.hosting.pages import _about_html  # pyright: ignore[reportPrivateUsage]
from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.release.models import REQUIRED_RELEASE_ARTIFACTS, ReleaseStatus
from election_guide.rendering.renderer import render_sources_document
from election_guide.serialization import canonical_json_bytes
from tests.test_rendering import (  # pyright: ignore[reportPrivateUsage]
    _evaluate_in_chrome,  # pyright: ignore[reportPrivateUsage]
    _lens_fragment,  # pyright: ignore[reportPrivateUsage]
    _personalization_enabled_view_model,  # pyright: ignore[reportPrivateUsage]
    _tallying_selectable,  # pyright: ignore[reportPrivateUsage]
)

COMMIT = "a" * 40
OLDER_COMMIT = "c" * 40
PANEL_HASH = "b" * 64
PROJECT_ROOT = Path(__file__).parents[1]
CURRENT_ID = "wa-2026-primary"
OLDER_ID = "wa-2025-general"
CURRENT_BUNDLE_ID = "wa-2026-primary-release"
OLDER_BUNDLE_ID = "wa-2025-general-release"


def test_stage_pages_site_composes_verified_election_archive(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(
        tmp_path,
        current_html=b"<!doctype html><title>Current guide</title>\n",
        older_html=b"<!doctype html><title>Older guide</title>\n",
    )
    manifest = _write_site_manifest(tmp_path, current_first=True)
    output = tmp_path / "site"
    output.mkdir()
    (output / "stale.txt").write_text("old deployment", encoding="utf-8")

    result = stage_pages_site(
        manifest,
        {
            CURRENT_BUNDLE_ID: current,
            OLDER_BUNDLE_ID: older,
        },
        output,
        expected_current_git_commit=COMMIT,
    )

    assert result.output_dir == output
    assert result.current_election_id == CURRENT_ID
    assert result.release_version == "primary.2"
    assert result.git_commit == COMMIT
    assert result.html_path == output / "e" / CURRENT_ID / "index.html"
    assert result.election_paths == (
        output / "e" / CURRENT_ID,
        output / "e" / OLDER_ID,
    )
    assert not (output / "stale.txt").exists()
    assert not (output / "index.html").exists()
    assert result.html_path.read_bytes() == b"<!doctype html><title>Current guide</title>\n"
    assert (output / "e" / OLDER_ID / "index.html").read_bytes() == (
        b"<!doctype html><title>Older guide</title>\n"
    )
    # Issue 193: the archive stages no generated PDF edition.
    assert not list((output / "e" / CURRENT_ID).glob("*.pdf"))
    assert (output / "e" / CURRENT_ID / "release-status.json").is_file()
    assert (output / "e" / CURRENT_ID / "release-manifest.json").is_file()

    archive = (output / "e" / "index.html").read_text(encoding="utf-8")
    assert archive.index(CURRENT_ID) < archive.index(OLDER_ID)
    assert f'href="/e/{CURRENT_ID}/"' in archive
    assert "current" in archive
    assert '<link rel="canonical" href="https://seattleelections.guide/e/">' in archive
    assert "August 4, 2026 Washington primary" in archive
    assert "November 4, 2025 Washington general" in archive
    archive_title = "Guide archive — Seattle Elections Guide"
    assert f'<meta property="og:title" content="{archive_title}">' in archive
    assert f'<meta name="twitter:title" content="{archive_title}">' in archive
    assert f"<title>{archive_title}</title>" in archive
    assert (
        '<meta property="og:description" content="Published Seattle election '
        'endorsement guides.">' in archive
    )
    assert '<meta name="twitter:card" content="summary_large_image">' in archive
    assert (
        '<meta name="twitter:description" content="Published Seattle election '
        'endorsement guides.">' in archive
    )
    assert "noindex" not in archive
    assert "Every guide stays up after its election &mdash; unchanged, at the same address." in (
        archive
    )
    assert "<ul>" in archive
    assert "<ol>" not in archive
    assert '<div class="site-footer-audit"><span class="audit-data">' in archive
    assert f'Data updated 2026-07-20 (<a href="/e/{CURRENT_ID}/release-manifest.json">' in archive
    assert " · Panel " not in archive
    assert (
        f'Site updated 2026-07-21 (<a href="https://github.com/shaug/'
        f'seattle-election-guide/commit/{COMMIT}"'
        f' target="_blank" rel="noopener">{COMMIT[:12]}</a>)' in archive
    )

    about = (output / "about" / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://seattleelections.guide/about/">' in about
    about_title = "How this works — Seattle Elections Guide"
    assert f'<meta property="og:title" content="{about_title}">' in about
    assert f'<meta name="twitter:title" content="{about_title}">' in about
    assert f"<title>{about_title}</title>" in about
    assert '<meta property="og:url" content="https://seattleelections.guide/about/">' in about
    assert '<meta name="twitter:card" content="summary_large_image">' in about
    assert f'href="/e/{CURRENT_ID}/"' in about
    assert "mailto:seattle-elections@dobravoda.dev" in about
    assert "not an official voter pamphlet" in about
    assert "not affiliated with any campaign" in about
    normalized_about = " ".join(about.split())
    assert (
        "This guide covers the Seattle races we tracked for this election; your ballot may not "
        "include all of them, and may include a race this guide doesn&rsquo;t cover."
        in normalized_about
    )
    # The shared footer's own links (Share/Contact/GitHub/How this works)
    # replaced the old page-footer nav, which was the site's only link to the
    # guide archive; that link now lives in About's own body prose instead.
    assert '<a href="/e/">guide archive</a>' in about
    assert '<div class="site-footer-audit"><span class="audit-data">' in about
    assert " · Panel " not in about
    assert f">{COMMIT[:12]}</a>" in about

    headers = (output / "_headers").read_text(encoding="utf-8")
    assert "X-Frame-Options: DENY" in headers
    assert "X-Robots-Tag" not in headers
    worker = (output / "_worker.js").read_text(encoding="utf-8")
    assert 'const CANONICAL_HOST = "seattleelections.guide";' in worker
    assert "return redirectPath(url, CURRENT_ELECTION_PATH, 307);" in worker
    assert "return new Response(NOT_FOUND_HTML" in worker
    # K48: the worker's 404 is a minimal branded page, not bare text/plain
    # (the page is JSON-encoded into the worker source, so its own quotes
    # are backslash-escaped there).
    assert "Page not found" in worker
    assert r"Page not found \u2014 Seattle Elections Guide" in worker
    assert "site-band" in worker
    assert f'href=\\"/e/{CURRENT_ID}/\\"' in worker
    assert "site-footer-band" in worker
    assert "Data updated 2026-07-20" in worker
    assert "Site updated 2026-07-21" in worker
    assert " \\u00b7 Panel " not in worker

    deployment = json.loads((output / "deployment-manifest.json").read_text(encoding="utf-8"))
    assert deployment["schema_version"] == "2.0"
    assert deployment["current_election_id"] == CURRENT_ID
    assert [election["election_id"] for election in deployment["elections"]] == [
        CURRENT_ID,
        OLDER_ID,
    ]
    assert set(deployment["assets"]) >= {
        "_headers",
        "_worker.js",
        f"e/{CURRENT_ID}/index.html",
        f"e/{OLDER_ID}/index.html",
        "e/index.html",
        "about/index.html",
        "favicon.svg",
        "favicon-32.png",
        "apple-touch-icon.png",
        "og-image.png",
    }


def test_changing_current_election_preserves_historical_election_bytes(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(
        tmp_path,
        current_html=b"new election bytes\n",
        older_html=b"historical bytes stay fixed\n",
    )
    assignments = {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older}
    first_manifest = _write_site_manifest(tmp_path / "first", current_first=False)
    second_manifest = _write_site_manifest(tmp_path / "second", current_first=True)

    first_output = tmp_path / "first-site"
    second_output = tmp_path / "second-site"
    stage_pages_site(first_manifest, assignments, first_output)
    before = _tree_bytes(first_output / "e" / OLDER_ID)
    stage_pages_site(second_manifest, assignments, second_output)
    after = _tree_bytes(second_output / "e" / OLDER_ID)

    assert before == after
    first_redirect = _run_worker(
        first_output / "_worker.js",
        ["https://seattleelections.guide/?deployment=first"],
    )[0]
    second_redirect = _run_worker(
        second_output / "_worker.js",
        ["https://seattleelections.guide/?deployment=second"],
    )[0]
    assert first_redirect == {
        "status": 307,
        "location": f"https://seattleelections.guide/e/{OLDER_ID}/?deployment=first",
        "robots": None,
        "body": "",
    }
    assert second_redirect == {
        "status": 307,
        "location": f"https://seattleelections.guide/e/{CURRENT_ID}/?deployment=second",
        "robots": None,
        "body": "",
    }


def test_generated_worker_enforces_route_contract(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    output = tmp_path / "site"
    stage_pages_site(
        _write_site_manifest(tmp_path, current_first=True),
        {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
        output,
    )

    worker_path = output / "_worker.js"
    urls = [
        "https://seattleelections.guide/?from=root",
        "https://seattleelections.guide/e",
        "https://seattleelections.guide/e/",
        f"https://seattleelections.guide/e/{CURRENT_ID}",
        f"https://seattleelections.guide/e/{CURRENT_ID}/",
        f"https://seattleelections.guide/e/{CURRENT_ID}/Current_Guide.pdf",
        "https://seattleelections.guide/e/not-an-election/",
        f"https://seattleelections.guide/e/{CURRENT_ID}/missing.pdf",
        f"https://seattle-elections.guide/e/{OLDER_ID}/?source=legacy",
        "https://seattleelections.guide/about?ref=footer",
        "https://seattleelections.guide/about/",
    ]
    results = _run_worker(worker_path, urls)

    assert results[0]["status"] == 307
    assert results[0]["location"] == (f"https://seattleelections.guide/e/{CURRENT_ID}/?from=root")
    assert results[1]["status"] == 308
    assert results[1]["location"] == "https://seattleelections.guide/e/"
    assert results[2] == {
        "status": 200,
        "location": None,
        "robots": None,
        "body": "asset:/e/",
    }
    assert results[3]["status"] == 308
    assert results[3]["location"] == f"https://seattleelections.guide/e/{CURRENT_ID}/"
    assert results[4]["body"] == f"asset:/e/{CURRENT_ID}/"
    # Issue 193: every PDF path this election ever published redirects to its
    # guide page instead of 404ing.
    assert results[5]["status"] == 301
    assert results[5]["location"] == f"https://seattleelections.guide/e/{CURRENT_ID}/"
    assert results[6]["status"] == 404
    assert results[6]["robots"] == "noindex"
    # K48: a minimal branded 404 page, not the old bare text/plain response.
    assert "Page not found" in cast(str, results[6]["body"])
    assert f'href="/e/{CURRENT_ID}/"' in cast(str, results[6]["body"])
    assert '<footer class="site-footer">' in cast(str, results[6]["body"])
    assert "Data updated 2026-07-20" in cast(str, results[6]["body"])
    assert "Site updated 2026-07-21" in cast(str, results[6]["body"])
    assert " · Panel " not in cast(str, results[6]["body"])
    # The 404 still carries og:image (shared by every page), but stays out of
    # the summary_large_image unfurling pattern -- it is noindex and not
    # meant to be shared (issue 135's non-goal).
    assert "twitter:card" not in cast(str, results[6]["body"])
    assert results[7]["status"] == 301
    assert results[7]["location"] == f"https://seattleelections.guide/e/{CURRENT_ID}/"
    assert results[8]["status"] == 301
    assert results[8]["location"] == (f"https://seattleelections.guide/e/{OLDER_ID}/?source=legacy")
    assert results[9]["status"] == 308
    assert results[9]["location"] == "https://seattleelections.guide/about/?ref=footer"
    assert results[10] == {
        "status": 200,
        "location": None,
        "robots": None,
        "body": "asset:/about/",
    }


def test_generated_worker_indexes_only_the_canonical_host(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    output = tmp_path / "site"
    stage_pages_site(
        _write_site_manifest(tmp_path, current_first=True),
        {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
        output,
    )

    guide = f"/e/{CURRENT_ID}/"
    canonical_asset, canonical_missing, pages_asset, pages_missing, preview_asset, legacy = (
        _run_worker(
            output / "_worker.js",
            [
                f"https://seattleelections.guide{guide}",
                "https://seattleelections.guide/e/not-an-election/",
                f"https://seattle-elections.pages.dev{guide}",
                "https://seattle-elections.pages.dev/e/not-an-election/",
                f"https://pr-42.seattle-elections.pages.dev{guide}",
                f"https://seattle-elections.dobravoda.dev{guide}",
            ],
        )
    )

    # Issue 209: the canonical host is the only one search engines may index.
    assert canonical_asset == {
        "status": 200,
        "location": None,
        "robots": None,
        "body": f"asset:{guide}",
    }
    # Every other hostname serves the same guide with noindex attached, so a
    # preview deployment cannot compete with the real site in search results.
    for off_canonical in (pages_asset, preview_asset):
        assert off_canonical["status"] == 200
        assert off_canonical["robots"] == "noindex"
        assert off_canonical["body"] == f"asset:{guide}"

    # The 404 is noindex everywhere, canonical included -- that predates this
    # rule and is not host-dependent.
    assert canonical_missing["status"] == 404
    assert canonical_missing["robots"] == "noindex"
    assert pages_missing["status"] == 404
    assert pages_missing["robots"] == "noindex"

    # A legacy host still redirects to canonical before any header applies, so
    # the hop stays a bare 301 rather than a noindex response.
    assert legacy == {
        "status": 301,
        "location": f"https://seattleelections.guide{guide}",
        "robots": None,
        "body": "",
    }


def test_enabled_comparisons_stage_verify_and_route_exact_asset(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    _enable_comparisons(current)
    manifest = _write_site_manifest(tmp_path, current_first=True)
    output = tmp_path / "site"

    stage_pages_site(
        manifest,
        {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
        output,
    )
    verified = verify_staged_pages_site(output, manifest)

    compare_relative = f"e/{CURRENT_ID}/comparisons/index.html"
    compare_path = output / compare_relative
    assert compare_path.is_file()
    assert (
        verified.assets[compare_relative] == hashlib.sha256(compare_path.read_bytes()).hexdigest()
    )
    assert not (output / "e" / OLDER_ID / "compare").exists()

    compare_html = compare_path.read_text(encoding="utf-8")
    assert 'data-default-columns="gall,strn,stim"' in compare_html
    assert (
        'href="/e/wa-2026-primary/comparisons/" aria-current="page">Comparisons</a>' in compare_html
    )
    sources_html = (output / "e" / CURRENT_ID / "sources" / "index.html").read_text(
        encoding="utf-8"
    )
    assert f'href="/e/{CURRENT_ID}/comparisons/">Comparisons</a>' in sources_html
    assert f'href="/e/{CURRENT_ID}/comparisons/">Comparisons</a>' in (
        output / "about" / "index.html"
    ).read_text(encoding="utf-8")
    assert f'href="/e/{CURRENT_ID}/comparisons/">Comparisons</a>' in (
        output / "e" / "index.html"
    ).read_text(encoding="utf-8")

    results = _run_worker(
        output / "_worker.js",
        [
            f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons",
            f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons/",
            "https://seattleelections.guide/e/not-an-election/comparisons/",
            # The page shipped at /compare/ before issue 192 renamed it, so
            # anything already linked or bookmarked must still arrive.
            f"https://seattleelections.guide/e/{CURRENT_ID}/compare",
            f"https://seattleelections.guide/e/{CURRENT_ID}/compare/",
        ],
    )
    # Trailing-slash normalisation stays a 308; the rename is a permanent 301,
    # so caches and search engines learn the new address.
    assert results[0]["status"] == 308
    assert results[0]["location"] == (f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons/")
    assert results[1]["body"] == f"asset:/e/{CURRENT_ID}/comparisons/"
    assert results[2]["status"] == 404
    for legacy in (results[3], results[4]):
        assert legacy["status"] == 301
        assert legacy["location"] == f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons/"


def test_comparison_preview_stages_only_the_current_direct_route(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    baseline_manifest = _write_site_manifest(tmp_path / "baseline", current_first=True)
    preview_manifest = _write_site_manifest(tmp_path / "preview", current_first=True)
    preview_payload = yaml.safe_load(preview_manifest.read_text(encoding="utf-8"))
    preview_payload["elections"][0]["comparison_route_preview"] = True
    preview_manifest.write_text(yaml.safe_dump(preview_payload, sort_keys=False), encoding="utf-8")
    assignments = {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older}
    baseline_output = tmp_path / "baseline-site"
    preview_output = tmp_path / "preview-site"

    stage_pages_site(baseline_manifest, assignments, baseline_output)
    stage_pages_site(preview_manifest, assignments, preview_output)
    verified = verify_staged_pages_site(preview_output, preview_manifest)

    compare_relative = f"e/{CURRENT_ID}/comparisons/index.html"
    compare_path = preview_output / compare_relative
    assert compare_path.is_file()
    assert (
        verified.assets[compare_relative] == hashlib.sha256(compare_path.read_bytes()).hexdigest()
    )
    assert not (preview_output / "e" / OLDER_ID / "compare").exists()
    compare_html = compare_path.read_text(encoding="utf-8")
    assert 'data-default-columns="gall,strn,stim"' in compare_html
    assert compare_html.index(">Endorsements</a>") < compare_html.index(">Comparisons</a>")
    assert compare_html.index(">Sources</a>") < compare_html.index(">Comparisons</a>")
    assert compare_html.index(">Sources</a>") < compare_html.index(">How this works</a>")

    hidden_compare_pages = (
        preview_output / "e" / CURRENT_ID / "index.html",
        preview_output / "e" / CURRENT_ID / "sources" / "index.html",
        preview_output / "about" / "index.html",
    )
    for page in hidden_compare_pages:
        assert f'href="/e/{CURRENT_ID}/comparisons/">Comparisons</a>' not in page.read_text(
            encoding="utf-8"
        )

    existing_html = sorted(
        path.relative_to(baseline_output) for path in baseline_output.rglob("*.html")
    )
    assert existing_html
    for relative in existing_html:
        baseline_bytes = (baseline_output / relative).read_bytes()
        assert (preview_output / relative).read_bytes() == baseline_bytes
        assert b"/comparisons/" not in baseline_bytes

    unknown_baseline = _run_worker(
        baseline_output / "_worker.js",
        ["https://seattleelections.guide/e/not-an-election/comparisons/"],
    )[0]
    results = _run_worker(
        preview_output / "_worker.js",
        [
            f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons",
            f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons/",
            f"https://seattleelections.guide/e/{OLDER_ID}/comparisons/",
            "https://seattleelections.guide/e/not-an-election/comparisons/",
        ],
    )
    assert results[0]["status"] == 308
    assert results[0]["location"] == f"https://seattleelections.guide/e/{CURRENT_ID}/comparisons/"
    assert results[1]["body"] == f"asset:/e/{CURRENT_ID}/comparisons/"
    assert results[2]["status"] == 404
    assert results[3] == unknown_baseline

    consistent_omission = tmp_path / "preview-route-omitted"
    shutil.copytree(preview_output, consistent_omission)
    (consistent_omission / compare_relative).unlink()
    deployment_path = consistent_omission / "deployment-manifest.json"
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    del deployment["assets"][compare_relative]
    deployment_path.write_bytes(canonical_json_bytes(deployment))
    with pytest.raises(ValueError, match="missing required public archive assets"):
        verify_staged_pages_site(consistent_omission, preview_manifest)


def test_disabled_comparisons_stage_no_page_or_nav_exposure(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    manifest = _write_site_manifest(tmp_path, current_first=True)
    output = tmp_path / "site"

    stage_pages_site(
        manifest,
        {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
        output,
    )

    assert not (output / "e" / CURRENT_ID / "compare").exists()
    assert not (output / "e" / OLDER_ID / "compare").exists()
    worker = (output / "_worker.js").read_text(encoding="utf-8")
    assert "/comparisons/" not in worker
    assert "COMPARISON_ROOTS" not in worker
    assert "/comparisons/" not in (output / "e" / CURRENT_ID / "sources" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "/comparisons/" not in (output / "about" / "index.html").read_text(encoding="utf-8")
    assert "/comparisons/" not in (output / "e" / "index.html").read_text(encoding="utf-8")


def test_bundle_drift_does_not_replace_existing_output(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    output = tmp_path / "site"
    output.mkdir()
    (output / "sentinel.txt").write_text("keep", encoding="utf-8")
    (current / "guide/guide.html").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match=r"artifact hash mismatch: guide/guide\.html"):
        stage_pages_site(
            _write_site_manifest(tmp_path, current_first=True),
            {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
            output,
        )

    assert (output / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert not (output / "e").exists()


def test_verify_staged_site_rejects_tamper_deletion_and_unexpected_assets(
    tmp_path: Path,
) -> None:
    current, older = _write_archive_bundles(tmp_path)
    manifest = _write_site_manifest(tmp_path, current_first=True)
    output = tmp_path / "site"
    stage_pages_site(
        manifest,
        {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
        output,
    )

    verified = verify_staged_pages_site(
        output,
        manifest,
        expected_current_git_commit=COMMIT,
    )
    assert verified.current_election_id == CURRENT_ID
    assert len(verified.assets) == 16

    tampered = tmp_path / "tampered"
    shutil.copytree(output, tampered)
    (tampered / "e" / CURRENT_ID / "index.html").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="asset hash mismatch"):
        verify_staged_pages_site(tampered, manifest)

    missing = tmp_path / "missing"
    shutil.copytree(output, missing)
    (missing / "e" / CURRENT_ID / "sources" / "index.html").unlink()
    with pytest.raises(ValueError, match=r"missing=.*sources/index\.html"):
        verify_staged_pages_site(missing, manifest)

    consistent_omission = tmp_path / "omitted-sources"
    shutil.copytree(output, consistent_omission)
    (consistent_omission / "e" / CURRENT_ID / "sources" / "index.html").unlink()
    deployment_path = consistent_omission / "deployment-manifest.json"
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    del deployment["assets"][f"e/{CURRENT_ID}/sources/index.html"]
    deployment_path.write_bytes(canonical_json_bytes(deployment))
    with pytest.raises(ValueError, match="missing required public archive assets"):
        verify_staged_pages_site(consistent_omission, manifest)

    unexpected = tmp_path / "unexpected"
    shutil.copytree(output, unexpected)
    (unexpected / "extra.txt").write_text("not declared\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"unexpected=.*extra\.txt"):
        verify_staged_pages_site(unexpected, manifest)


def test_site_manifest_rejects_duplicate_elections_and_path_traversal(tmp_path: Path) -> None:
    invalid_elections = [
        _manifest_election(CURRENT_ID, CURRENT_BUNDLE_ID, "primary.2"),
        _manifest_election(CURRENT_ID, OLDER_BUNDLE_ID, "primary.2"),
    ]
    invalid = {
        "schema_version": "1.0",
        "canonical_origin": "https://seattleelections.guide",
        "current_election_id": CURRENT_ID,
        "elections": invalid_elections,
    }
    duplicate_path = tmp_path / "duplicate.yaml"
    duplicate_path.write_text(yaml.safe_dump(invalid, sort_keys=False), encoding="utf-8")
    output = tmp_path / "site"

    with pytest.raises(ValueError, match="repeats an election ID"):
        stage_pages_site(duplicate_path, {}, output)
    assert not output.exists()

    invalid_elections[1]["election_id"] = "../escape"
    traversal_path = tmp_path / "traversal.yaml"
    traversal_path.write_text(yaml.safe_dump(invalid, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="string_pattern_mismatch"):
        stage_pages_site(traversal_path, {}, output)
    assert not output.exists()


def test_stage_rejects_missing_bundle_and_wrong_current_revision(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    manifest = _write_site_manifest(tmp_path, current_first=True)

    with pytest.raises(ValueError, match=r"missing=.*wa-2025-general-release"):
        stage_pages_site(manifest, {CURRENT_BUNDLE_ID: current}, tmp_path / "missing")
    with pytest.raises(ValueError, match="current release bundle was built from"):
        stage_pages_site(
            manifest,
            {CURRENT_BUNDLE_ID: current, OLDER_BUNDLE_ID: older},
            tmp_path / "wrong-revision",
            expected_current_git_commit="d" * 40,
        )


def test_hosting_stage_cli_reports_composed_site(tmp_path: Path) -> None:
    current, older = _write_archive_bundles(tmp_path)
    manifest = _write_site_manifest(tmp_path, current_first=True)
    output = tmp_path / "site"

    result = CliRunner().invoke(
        app,
        [
            "hosting",
            "stage",
            str(manifest),
            "--bundle",
            f"{CURRENT_BUNDLE_ID}={current}",
            "--bundle",
            f"{OLDER_BUNDLE_ID}={older}",
            "--output-dir",
            str(output),
            "--expected-git-commit",
            COMMIT,
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"Pages site: {output}" in result.output
    assert f"2 elections; current {CURRENT_ID} primary.2" in result.output
    assert (output / "e" / CURRENT_ID / "index.html").is_file()

    verify_result = CliRunner().invoke(
        app,
        [
            "hosting",
            "verify",
            str(manifest),
            str(output),
            "--expected-git-commit",
            COMMIT,
        ],
    )
    assert verify_result.exit_code == 0, verify_result.output
    assert f"current {CURRENT_ID}; 16 assets" in verify_result.output


def _current_election_manifest() -> SiteManifest:
    return SiteManifest(
        canonical_origin="https://seattleelections.guide",
        current_election_id=CURRENT_ID,
        elections=[
            PublishedElection(
                election_id=CURRENT_ID,
                bundle_id=CURRENT_BUNDLE_ID,
                release_version="primary.2",
                source_panel_id="test-panel-v2",
                source_panel_hash=PANEL_HASH,
            ),
        ],
    )


def test_about_page_share_button_uses_web_share_then_falls_back_to_copy(
    tmp_path: Path,
) -> None:
    """Issue 66: the About page's share action degrades cleanly like the guide's."""
    manifest = _current_election_manifest()
    html_path = tmp_path / "about.html"
    html_path.write_text(
        _about_html(
            manifest,
            data_updated_date="2026-07-23",
            site_updated_date="2026-07-30",
            data_version="data-version-123456",
            git_commit=COMMIT,
            data_href=f"/e/{CURRENT_ID}/release-manifest.json",
        ),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = () => new Promise((resolve) => setTimeout(resolve, 50));
          const button = document.querySelector('[data-shell-share]');
          const status = document.querySelector('[data-shell-share-status]');

          Object.defineProperty(navigator, 'share', {
            value: (details) => Promise.resolve(details),
            configurable: true,
          });
          button.click();
          await pause();
          const afterShare = status.textContent;

          status.textContent = 'SENTINEL';
          Object.defineProperty(navigator, 'share', {
            value: () => Promise.reject(
              Object.assign(new Error('cancelled'), { name: 'AbortError' })
            ),
            configurable: true,
          });
          button.click();
          await pause();
          const afterCancelledShare = status.textContent;

          Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async () => {} },
            configurable: true,
          });
          button.click();
          await pause();
          const afterClipboardCopy = status.textContent;

          // See the equivalent guide-footer test for why execCommand is stubbed
          // rather than exercised for real under headless Chrome.
          Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
          document.execCommand = () => true;
          button.click();
          await pause();
          const afterExecCommandCopy = status.textContent;

          return JSON.stringify({
            afterShare,
            afterCancelledShare,
            afterClipboardCopy,
            afterExecCommandCopy,
          });
        })()
        """,
    )
    assert result["afterShare"] == "Share menu opened."
    assert result["afterCancelledShare"] == "SENTINEL"
    assert result["afterClipboardCopy"] == "Link copied."
    assert result["afterExecCommandCopy"] == "Link copied."


def test_about_page_folds_in_every_fact_the_removed_methodology_panel_stated() -> None:
    """Issue 109: the guide's inline methodology disclosure was removed, so
    every fact it stated that /about/ didn't already cover must now be
    findable there."""
    about = _about_html(
        _current_election_manifest(),
        data_updated_date="2026-07-23",
        site_updated_date="2026-07-30",
        data_version="data-version-123456",
        git_commit=COMMIT,
        data_href=f"/e/{CURRENT_ID}/release-manifest.json",
    )

    # "Agreement, not a grade": neither the percentage nor the source count
    # rates candidate quality.
    assert "neither number is a quality rating of the" in about
    # "What enters the count": the legislative-district broader-race rule.
    assert "Legislative-district organizations count on the broader races" in about
    # "Related organizations": disclosed, not deduplicated, one vote each.
    assert "disclosed rather than deduplicated" in about
    assert "keeps its own full vote" in about
    # Issue 124: the Times is documented, not offered — the Endorsements page
    # shows it nowhere, and About points at where it can still be compared.
    assert "the Endorsements page does not show" in about
    assert "the Comparisons page is where you can put" in about
    assert "hidden on screen by" not in about
    # Organizations may update endorsements after our capture snapshot.
    assert "Organizations can update their own endorsements after we capture them" in about
    # The Sources-page privacy aside belongs here as a reusable FAQ answer.
    assert '<section aria-labelledby="choices-anonymous">' in about
    assert "Are my choices anonymous?" in about
    assert "Your source selection lives entirely in this page's address" in about
    assert "Nothing is stored anywhere" in about


@pytest.mark.parametrize("mobile_width", [None, 720], ids=["desktop", "720px"])
def test_about_and_sources_ledes_follow_their_page_measure(
    tmp_path: Path,
    mobile_width: int | None,
) -> None:
    """Issue 182: ledes inherit each page's deliberate reading measure."""
    about_path = tmp_path / "about.html"
    about_path.write_text(
        _about_html(
            _current_election_manifest(),
            data_updated_date="2026-07-23",
            site_updated_date="2026-07-30",
            data_version="data-version-123456",
            git_commit=COMMIT,
            data_href=f"/e/{CURRENT_ID}/release-manifest.json",
        ),
        encoding="utf-8",
    )
    about = _evaluate_in_chrome(
        about_path,
        """
        (() => {
          const lede = document.querySelector('.page-head .page-tagline');
          const bodyParagraph = document.querySelector('main section p');
          const style = getComputedStyle(lede);
          return JSON.stringify({
            ledeWidth: lede.getBoundingClientRect().width,
            measureWidth: bodyParagraph.getBoundingClientRect().width,
            maxWidth: style.maxWidth,
            color: style.color,
            fontSize: style.fontSize,
          });
        })()
        """,
        mobile_width=mobile_width,
    )

    view_model = _personalization_enabled_view_model(tmp_path)
    sources_path = tmp_path / "sources.html"
    sources_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    sources = _evaluate_in_chrome(
        sources_path,
        """
        (() => {
          const head = document.querySelector('.page-head');
          const lede = head.querySelector('.page-tagline');
          const style = getComputedStyle(lede);
          return JSON.stringify({
            ledeWidth: lede.getBoundingClientRect().width,
            headWidth: head.getBoundingClientRect().width,
            maxWidth: style.maxWidth,
            color: style.color,
            fontSize: style.fontSize,
          });
        })()
        """,
        mobile_width=mobile_width,
    )

    # Issue 192 replaced two bespoke intro blocks with one page head that has two
    # measure modes, so the rule is now stated per mode rather than per page.
    #
    # A head on a page that sets a book measure (About) shares that column
    # outright: same width as the prose beneath it, and no second measure of its
    # own.
    assert about["ledeWidth"] == pytest.approx(about["measureWidth"], abs=1)
    assert about["maxWidth"] == "none"

    # A full-bleed head (Sources, whose body is a wide multi-column tree) carries
    # the measure itself, and must never let prose span the 76rem frame.
    assert sources["ledeWidth"] < sources["headWidth"]
    assert sources["maxWidth"] != "none"

    # A measured head is prose above prose, so it takes the body's size exactly.
    # A full-bleed head is a deck and scales with the frame, so it is not pinned.
    assert about["fontSize"] == "16px"

    for page in (about, sources):
        assert page["color"] == "rgb(82, 96, 109)"


def _selectable_tallying_codes(view_model: PublicationViewModel) -> list[str]:
    return sorted(
        {
            code
            for category in view_model.personalization.categories
            if _tallying_selectable(category)
            for code in category.member_source_codes
        }
    )


def _selectable_comparison_codes(view_model: PublicationViewModel) -> list[str]:
    return sorted(
        {
            code
            for category in view_model.personalization.categories
            if category.selectable and category.panel_role == "comparison"
            for code in category.member_source_codes
        }
    )


def test_sources_page_renders_every_category_and_source_like_the_guide_tree(
    tmp_path: Path,
) -> None:
    """Issue 107: the standalone page is the new home for the guide's own
    merged sources tree, not a redesign of it, so every selectable category
    and source must render with the same content and structure."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html = render_sources_document(
        view_model,
        public_site_url="https://seattleelections.guide",
        project_url="https://github.com/shaug/seattle-election-guide",
    )

    tallying_codes = _selectable_tallying_codes(view_model)
    comparison_codes = _selectable_comparison_codes(view_model)
    assert tallying_codes, "fixture must exercise at least one tallying source"
    assert comparison_codes, "fixture must exercise the comparison source"

    for category in view_model.personalization.categories:
        if not category.selectable:
            continue
        assert f'data-sources-category="{category.code}"' in html
        for member_code in category.member_source_codes:
            assert f'data-sources-source-row="{member_code}"' in html
            if member_code in comparison_codes:
                continue
            assert f'data-sources-source="{member_code}"' in html
            assert f'data-sources-category-member="{category.code}"' in html

    # Issue 124: the comparison section still documents the Times — name,
    # evidence link, and endorsement overview — but offers no checkbox and
    # points at the Comparisons page instead.
    assert "sources-category-comparison" in html
    assert "sources-comparison-note" in html
    assert f'href="/e/{view_model.metadata.election_id}/comparisons/">Comparisons page</a>' in html
    for code in comparison_codes:
        assert f'data-sources-source="{code}"' not in html
        row = html.split(f'data-sources-source-row="{code}"')[1].split("</div>")[0]
        assert "sources-source-link" in row
        assert "sources-count" in row

    # Every tallying source starts checked (the audited default).
    for row in html.split('<div class="sources-row"')[1:]:
        if any(f'data-sources-source="{code}"' in row for code in tallying_codes):
            assert "checked" in row

    assert '<link rel="canonical" href="https://seattleelections.guide/e/' in html
    assert f"/e/{view_model.metadata.election_id}/sources/" in html
    election_name = "August 2026 Primary"
    document_title = f"Sources — {election_name} — Seattle Elections Guide"
    assert f'<meta property="og:title" content="{document_title}">' in html
    assert (
        '<meta property="og:description" content="Choose which sources count '
        f'toward your personalized {election_name} results.">' in html
    )
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert f'<meta name="twitter:title" content="{document_title}">' in html
    assert (
        '<meta name="twitter:description" content="Choose which sources count '
        f'toward your personalized {election_name} results.">' in html
    )
    assert "Choose which sources count &mdash; the guide recalculates from your selection." in html
    coverage_model = view_model.model_copy(deep=True)
    coverage_source = coverage_model.sources[0]
    coverage_source.contribution_status = "coverage_gap"
    coverage_source.coverage_gap_status = "not_found"
    coverage_source.coverage_gap_note = "No usable endorsement list was found."
    coverage_source.endorsement_count = 0
    coverage_source.split_endorsement_count = 0
    coverage_model.metadata.contributing_source_count -= 1
    coverage_model.metadata.coverage_gap_count += 1
    coverage_html = render_sources_document(
        coverage_model,
        public_site_url="https://seattleelections.guide",
    )
    assert (
        "We looked for endorsement lists from these organizations and found none we could\n"
        "              use. They don&rsquo;t count toward any score." in coverage_html
    )
    assert "data-sources-save" in html
    assert "data-sources-cancel" in html
    assert "data-sources-page-reset" in html
    assert 'class="sources-page-actions state-action-strip"' in html
    assert html.index("sources-page-actions state-action-strip") < html.index(
        '<main id="sources-main">'
    )
    assert (
        ".sources-page-actions { position: sticky; top: 0; z-index: 5; justify-content: center; }"
    ) in html
    assert (
        ".sources-page-controls { display: flex; flex-wrap: wrap; "
        "gap: .6rem 1rem; margin-left: auto; }"
    ) not in html
    assert ".sources-cancel, .sources-page-reset {" not in html
    assert ".sources-page-actions a { color: var(--mint); font-weight: 700; }" in html
    assert 'class="sources-save strip-action-primary"' in html
    assert 'class="sources-page-reset strip-action-quiet"' in html

    # Issue 155: the page header names the election at a deliberate measure,
    # while privacy and audit details live in their site-wide homes.
    # Issue 192: the bespoke intro became the shared page head, the eyebrow
    # names only the election, and the h1 agrees with the nav label (R5).
    assert '<header class="page-head">' in html
    assert '<p class="page-eyebrow">August 2026 Primary</p>' in html
    assert "<h1>Sources</h1>" in html
    assert "· Sources" not in html
    assert "Your selection lives entirely" not in html
    assert "sources-version" not in html
    data_updated_date = (
        (view_model.metadata.data_as_of or view_model.metadata.generated_at).date().isoformat()
    )
    site_updated_date = view_model.metadata.generated_at.date().isoformat()
    assert f"Data updated {data_updated_date} (" in html
    assert f"Site updated {site_updated_date} (" in html
    assert f"Panel {view_model.metadata.source_panel_id} (" in html
    assert (
        f'<a href="/e/{view_model.metadata.election_id}/release-manifest.json">'
        f"{view_model.metadata.data_version[:12]}</a>"
    ) in html
    assert f"({view_model.metadata.source_panel_hash[:12]})" in html


def test_sources_page_action_strip_stays_visible_with_count_and_actions(tmp_path: Path) -> None:
    """Issue 154/M68: the state and all form actions share one sticky surface."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "sources.html"
    html_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          window.scrollTo(0, document.body.scrollHeight);
          await new Promise((resolve) => setTimeout(resolve, 60));
          const strip = document.querySelector('.sources-page-actions');
          const count = strip.querySelector('[data-sources-count]');
          return JSON.stringify({
            top: strip.getBoundingClientRect().top,
            height: strip.getBoundingClientRect().height,
            count: count.textContent,
            actions: [...strip.querySelectorAll('a')].map((link) => link.textContent.trim()),
            saveBackground: getComputedStyle(
              strip.querySelector('[data-sources-save]')
            ).backgroundColor,
            saveColor: getComputedStyle(strip.querySelector('[data-sources-save]')).color,
            cancelColor: getComputedStyle(strip.querySelector('[data-sources-cancel]')).color,
            resetColor: getComputedStyle(strip.querySelector('[data-sources-page-reset]')).color,
            background: getComputedStyle(strip).backgroundColor,
            position: getComputedStyle(strip).position,
            visible: strip.getBoundingClientRect().bottom > 0,
          });
        })()
        """,
        initial_url=html_path.resolve().as_uri(),
    )
    assert result["top"] == pytest.approx(0, abs=1)
    assert result["height"] <= 42
    assert result["count"].startswith("Counting ")
    assert result["actions"] == ["Save", "Cancel", "Reset to defaults"]
    assert result["saveBackground"] == "rgb(158, 231, 223)"
    assert result["saveColor"] == "rgb(16, 42, 67)"
    assert result["cancelColor"] == "rgb(158, 231, 223)"
    assert result["resetColor"] == "rgb(215, 230, 239)"
    assert result["background"] == "rgb(16, 42, 67)"
    assert result["position"] == "sticky"
    assert result["visible"] is True


def test_sources_page_loading_with_a_fragment_checks_exactly_its_sources(
    tmp_path: Path,
) -> None:
    """Acceptance criterion: loading the page with a fragment shows exactly
    the sources that fragment encodes as checked."""
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = _selectable_tallying_codes(view_model)
    chosen = tallying_codes[0]
    fragment = _lens_fragment(view_model, mode="s", source_codes=(chosen,))

    html_path = tmp_path / "sources.html"
    html_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const codes = new Set();
          document.querySelectorAll('[data-sources-source]').forEach((input) => {
            if (input.checked) codes.add(input.dataset.sourcesSource);
          });
          return JSON.stringify({
            checked: [...codes].sort(),
            count: document.querySelector('[data-sources-count]').textContent,
          });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["checked"] == [chosen]
    assert result["count"] == f"Counting 1 of {len(tallying_codes)} sources."


def _sources_page_actions_script(setup: str) -> str:
    """Read the Save/Cancel/Reset links' `href` after `setup` runs.

    These are real `<a href>` elements kept in sync reactively (see
    `refreshSelectionUi`/`saveTarget` in sources.html.j2), so their target can
    be read directly without ever clicking through a real navigation."""
    return f"""
        (() => {{
          {setup}
          return JSON.stringify({{
            save: document.querySelector('[data-sources-save]').getAttribute('href'),
            cancel: document.querySelector('[data-sources-cancel]').getAttribute('href'),
            reset: document.querySelector('[data-sources-page-reset]').getAttribute('href'),
          }});
        }})()
    """


def test_sources_page_save_at_the_default_selection_redirects_with_no_fragment(
    tmp_path: Path,
) -> None:
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "sources.html"
    html_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(html_path, _sources_page_actions_script(""))
    assert result["save"] == f"/e/{view_model.metadata.election_id}/"


def test_sources_page_save_re_encodes_the_edited_selection(tmp_path: Path) -> None:
    """Acceptance criterion: Save re-encodes the edited selection and
    redirects to `/e/<election_id>/#<fragment>`.

    Issue 124: a comparison source has no checkbox to edit any more, and its
    code never reaches the saved fragment.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = _selectable_tallying_codes(view_model)
    comparison_codes = _selectable_comparison_codes(view_model)
    dropped = tallying_codes[0]

    html_path = tmp_path / "sources.html"
    html_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        _sources_page_actions_script(
            f"""
              const uncheck = document.querySelector('[data-sources-source="{dropped}"]');
              uncheck.checked = false;
              uncheck.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """
        ),
    )
    captured = result["save"]
    assert captured.startswith(f"/e/{view_model.metadata.election_id}/#")
    fragment = captured.split("#", 1)[1]
    params = {
        key: value
        for key, _, value in (part.partition("=") for part in fragment.split("&") if part)
    }
    selection = params.get("sel", "")
    tokens = [selection[i : i + 4] for i in range(0, len(selection), 4)]
    assert dropped not in tokens
    for code in comparison_codes:
        assert code not in tokens
    for code in tallying_codes:
        if code != dropped:
            assert code in tokens


def test_sources_page_cancel_redirects_with_the_original_incoming_fragment(
    tmp_path: Path,
) -> None:
    """Acceptance criterion: Cancel redirects using the original incoming
    fragment, unchanged, even after the reader edited checkboxes."""
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = _selectable_tallying_codes(view_model)
    fragment = _lens_fragment(view_model, mode="s", source_codes=(tallying_codes[0],))

    html_path = tmp_path / "sources.html"
    html_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        _sources_page_actions_script(
            f"""
              const toggle = document.querySelector('[data-sources-source="{tallying_codes[1]}"]');
              toggle.checked = true;
              toggle.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """
        ),
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["cancel"] == f"/e/{view_model.metadata.election_id}/#{fragment}"


def test_sources_page_reset_redirects_with_no_fragment(tmp_path: Path) -> None:
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = _selectable_tallying_codes(view_model)
    fragment = _lens_fragment(view_model, mode="s", source_codes=(tallying_codes[0],))

    html_path = tmp_path / "sources.html"
    html_path.write_text(
        render_sources_document(view_model, public_site_url="https://seattleelections.guide"),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        _sources_page_actions_script(""),
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["reset"] == f"/e/{view_model.metadata.election_id}/"


def test_wrangler_and_workflow_keep_deployment_pinned_and_gated() -> None:
    site_manifest = yaml.safe_load(
        (PROJECT_ROOT / "config/hosting/site.yaml").read_text(encoding="utf-8")
    )
    wrangler = json.loads((PROJECT_ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert wrangler["name"] == "seattle-elections"
    assert wrangler["pages_build_output_dir"] == "./dist/cloudflare-site"
    assert package["devDependencies"]["wrangler"] == "4.113.0"
    current_election = next(
        election
        for election in site_manifest["elections"]
        if election["election_id"] == site_manifest["current_election_id"]
    )
    assert "comparison_route_preview" not in current_election
    deploy = workflow["jobs"]["deploy"]
    assert deploy["needs"] == "check"
    assert deploy["environment"]["name"] == "production"
    assert deploy["concurrency"]["cancel-in-progress"] == "false"
    assert "vars.CLOUDFLARE_PAGES_ENABLED == 'true'" in deploy["if"]
    deploy_step = next(
        step for step in deploy["steps"] if step.get("name") == "Deploy production site"
    )
    assert deploy_step["env"] == {
        "CLOUDFLARE_ACCOUNT_ID": "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}",
        "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
    }
    check_steps = workflow["jobs"]["check"]["steps"]
    # The check job runs on pull requests, including from forks, so no deployment
    # credential may reach it. The automatic job token is not one: it is bounded by
    # the workflow's read-only permissions, and listing published releases needs it.
    assert not any("secrets" in json.dumps(step) for step in check_steps)
    assert workflow["permissions"] == {"contents": "read"}
    releases_step = next(
        step
        for step in check_steps
        if step.get("name") == "Verify declared release versions are published"
    )
    assert releases_step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "hosting verify-releases config/hosting/site.yaml" in releases_step["run"]
    stage_step = next(
        step for step in check_steps if step.get("name") == "Stage verified Cloudflare Pages site"
    )
    assert "config/hosting/site.yaml" in stage_step["run"]
    assert "--bundle wa-2026-primary-2026-primary.2=" in stage_step["run"]
    assert "hosting verify" in stage_step["run"]
    # Any election not built from source above is resolved from its published
    # release, which reads GitHub with the same read-only job token (issue 215).
    assert "--released-bundle-dir dist/released-bundles" in stage_step["run"]
    assert stage_step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    deploy_steps = deploy["steps"]
    verify_step = next(
        step for step in deploy_steps if step.get("name") == "Verify downloaded Pages site"
    )
    assert "hosting verify" in verify_step["run"]
    assert "--expected-git-commit=" in verify_step["run"]


def test_pr_preview_workflow_is_label_gated_fork_safe_and_head_bound() -> None:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/deploy-pr-preview.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))

    # `pull_request_target` would run a fork's code with the Cloudflare token in
    # scope. It must never appear here (issue 210).
    assert set(workflow["on"]) == {"pull_request"}
    assert workflow["on"]["pull_request"]["types"] == [
        "labeled",
        "synchronize",
        "reopened",
        "closed",
    ]
    # Concurrency is per job, not per workflow. A cancelling workflow-level
    # group would also cover teardown, and a teardown cancelled mid-run leaves
    # a live preview with no second `closed` event to retry it.
    assert "concurrency" not in workflow
    deploy = workflow["jobs"]["deploy"]
    assert deploy["concurrency"]["group"].endswith("pr-${{ github.event.pull_request.number }}")
    assert deploy["concurrency"]["cancel-in-progress"] == "true"
    # Teardown shares the deploy job's group so a close landing mid-build queues
    # behind the upload rather than racing it, and never cancels.
    teardown_concurrency = workflow["jobs"]["teardown"]["concurrency"]
    assert teardown_concurrency["group"] == deploy["concurrency"]["group"]
    assert teardown_concurrency["cancel-in-progress"] == "false"

    fork_guard = "github.event.pull_request.head.repo.full_name == github.repository"
    # A fork's pull request fails this job-level condition, so the job is
    # skipped rather than failed and the token is never in scope.
    assert fork_guard in deploy["if"]
    assert "contains(github.event.pull_request.labels.*.name, 'deploy preview')" in deploy["if"]
    # State, not action: labeling an already-closed pull request would otherwise
    # deploy a preview that no later close event could tear down.
    assert "github.event.pull_request.state == 'open'" in deploy["if"]
    assert deploy["environment"]["name"] == "pr-${{ github.event.pull_request.number }}"
    assert deploy["environment"]["url"] == "${{ steps.deploy.outputs.url }}"

    # The audit footer must show a commit that exists in the repository, not the
    # ephemeral merge commit the pull_request event checks out by default.
    head_sha = "${{ github.event.pull_request.head.sha }}"
    assert deploy["env"]["HEAD_SHA"] == head_sha
    assert deploy["env"]["PAGES_BRANCH"] == "pr-${{ github.event.pull_request.number }}"
    checkout = next(
        step for step in deploy["steps"] if step.get("uses", "").startswith("actions/checkout")
    )
    assert checkout["with"]["ref"] == head_sha
    build_step = next(
        step
        for step in deploy["steps"]
        if step.get("name") == "Build the primary release at the pull request head"
    )
    assert '--git-commit "$HEAD_SHA"' in build_step["run"]
    stage_step = next(
        step for step in deploy["steps"] if step.get("name") == "Stage and verify the Pages site"
    )
    assert '--expected-git-commit "$HEAD_SHA"' in stage_step["run"]
    # Staging is verified before anything is uploaded, exactly as production is.
    assert "hosting verify" in stage_step["run"]
    assert deploy["steps"].index(stage_step) < deploy["steps"].index(
        next(step for step in deploy["steps"] if step.get("name") == "Deploy the preview")
    )

    # Teardown is deliberately not label-gated: a preview whose label was
    # removed before the pull request closed must still be cleaned up.
    teardown = workflow["jobs"]["teardown"]
    assert "github.event.action == 'closed'" in teardown["if"]
    assert fork_guard in teardown["if"]
    assert "labels" not in teardown["if"]
    delete_step = next(
        step
        for step in teardown["steps"]
        if step.get("name") == "Delete this pull request's preview deployments"
    )
    # The checkout is pinned to the base branch: a bare checkout resolves
    # refs/pull/<number>/merge, which GitHub retires exactly when this job runs.
    teardown_checkout = next(
        step for step in teardown["steps"] if step.get("uses", "").startswith("actions/checkout")
    )
    assert teardown_checkout.get("with", {}).get("ref") == (
        "${{ github.event.pull_request.base.ref }}"
    )
    assert "wrangler pages deployment list" in delete_step["run"]
    assert "wrangler pages deployment delete" in delete_step["run"]
    # Wrangler 4.113.0 does not print the Cloudflare API objects: it maps each
    # one to {Id, Environment, Branch, Source, Deployment, Status, Build} first.
    # Selecting on the raw API field names matches nothing, deletes nothing, and
    # still exits 0, so the exact field names are the contract here.
    assert "'.[] | select(.Branch == $branch) | .Id'" in delete_step["run"]

    # Production keeps its own call site untouched: the script still defaults to
    # main, so `pages:deploy` with no PAGES_BRANCH is byte-identical to before.
    assert package["scripts"]["pages:deploy"] == (
        "wrangler pages deploy --branch=${PAGES_BRANCH:-main}"
    )
    ci = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    production_deploy = next(
        step
        for step in ci["jobs"]["deploy"]["steps"]
        if step.get("name") == "Deploy production site"
    )
    assert "PAGES_BRANCH" not in json.dumps(production_deploy)
    assert "--branch" not in production_deploy["run"]


def _run_worker(worker_path: Path, urls: list[str]) -> list[dict[str, object]]:
    script = """
(async () => {
const fs = require("node:fs");
const workerSource = fs.readFileSync(process.argv[1], "utf8");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(workerSource).toString("base64")}`;
const worker = (await import(moduleUrl)).default;
const env = {
  ASSETS: {
    fetch(request) {
      return new Response(`asset:${new URL(request.url).pathname}`, {status: 200});
    },
  },
};
const urls = JSON.parse(process.argv[2]);
const results = [];
for (const url of urls) {
  const response = await worker.fetch(new Request(url), env);
  results.push({
    status: response.status,
    location: response.headers.get("location"),
    robots: response.headers.get("x-robots-tag"),
    body: await response.text(),
  });
}
process.stdout.write(JSON.stringify(results));
})();
"""
    completed = subprocess.run(
        ["node", "-e", script, str(worker_path), json.dumps(urls)],
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(list[dict[str, object]], json.loads(completed.stdout))


def _write_site_manifest(
    root: Path,
    *,
    current_first: bool,
    older_bundle_sha256: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    current = _manifest_election(CURRENT_ID, CURRENT_BUNDLE_ID, "primary.2")
    older = _manifest_election(OLDER_ID, OLDER_BUNDLE_ID, "general.1")
    if older_bundle_sha256 is not None:
        older["bundle_sha256"] = older_bundle_sha256
    elections = [current, older] if current_first else [older, current]
    manifest = {
        "schema_version": "1.0",
        "canonical_origin": "https://seattleelections.guide",
        "current_election_id": elections[0]["election_id"],
        "elections": elections,
    }
    path = root / "site.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path


def _manifest_election(
    election_id: str,
    bundle_id: str,
    release_version: str,
) -> dict[str, str]:
    return {
        "election_id": election_id,
        "bundle_id": bundle_id,
        "release_version": release_version,
        "source_panel_id": "test-panel-v2",
        "source_panel_hash": PANEL_HASH,
    }


def _write_archive_bundles(
    root: Path,
    *,
    current_html: bytes = b"current\n",
    older_html: bytes = b"older\n",
) -> tuple[Path, Path]:
    current = _write_release_bundle(
        root / "current",
        election_id=CURRENT_ID,
        release_version="primary.2",
        git_commit=COMMIT,
        html=current_html,
    )
    older = _write_release_bundle(
        root / "older",
        election_id=OLDER_ID,
        release_version="general.1",
        git_commit=OLDER_COMMIT,
        html=older_html,
    )
    return current, older


def _bundle_view_model(root: Path, *, election_id: str) -> PublicationViewModel:
    """A real, valid `PublicationViewModel` for one hosting-fixture bundle.

    The shared rendering fixture's own election identity is unrelated to this
    archive's election IDs, so metadata is overridden and revalidated to match.
    """
    election_year = 2026 if election_id == CURRENT_ID else 2025
    election_month = "August" if election_id == CURRENT_ID else "November"
    election_type = "primary" if election_id == CURRENT_ID else "general"
    election_type_label = election_type.title()
    election_date = f"{election_year}-{'08-04' if election_id == CURRENT_ID else '11-04'}"
    base = _personalization_enabled_view_model(root)
    updated = base.model_copy(
        update={
            "metadata": base.metadata.model_copy(
                update={
                    "election_id": election_id,
                    "election_name": (
                        f"{election_year} Washington {election_month} {election_type_label}"
                    ),
                    "election_type": election_type,
                    "election_date": election_date,
                }
            ),
            # These fixtures model already-published bundles from before the
            # comparison policy existed. Individual tests explicitly enable a
            # current bundle when exercising the new route.
            "comparisons": base.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=False)}
            ),
        }
    )
    return PublicationViewModel.model_validate(updated.model_dump(mode="json"))


def _write_release_bundle(
    root: Path,
    *,
    election_id: str,
    release_version: str,
    git_commit: str,
    html: bytes,
) -> Path:
    bundle = root / "bundle"
    html_relative = "guide/guide.html"
    public_artifacts = {
        html_relative,
        "validation/rendering/screenshots/desktop.png",
    }
    included = sorted(REQUIRED_RELEASE_ARTIFACTS | public_artifacts)
    for relative in included:
        if relative in {"release-manifest.json", "release-status.json"}:
            continue
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == html_relative:
            path.write_bytes(html)
        elif relative == "data/publication_view_model.json":
            view_model_payload = _bundle_view_model(
                root / "view-model-src", election_id=election_id
            ).model_dump(mode="json")
            # Hosting must continue to accept already-published schema-1.8
            # bundles, which predate the optional structured naming fields.
            view_model_payload["metadata"].pop("election_type")
            view_model_payload["metadata"].pop("state")
            path.write_bytes(canonical_json_bytes(view_model_payload))
        else:
            path.write_text(f"fixture for {relative}\n", encoding="utf-8")

    status = ReleaseStatus.model_validate(
        {
            "release_version": release_version,
            "election_id": election_id,
            "source_panel_id": "test-panel-v2",
            "source_panel_hash": PANEL_HASH,
            "data_as_of": "2026-07-20T12:00:00Z",
            "generated_at": "2026-07-21T12:00:00Z",
            "git_commit": git_commit,
            "source_count": 1,
            "captured_source_count": 1,
            "displayed_endorsement_count": 1,
            "unresolved_review_count": 0,
            "unresolved_high_severity_count": 0,
            "restricted_capture_count": 0,
            "source_access_failures": [],
            "incomplete_races": [],
            "validation_reports": {"publication": True, "rendering": True},
            "guide_html_artifact": html_relative,
            "included_artifacts": included,
            "warnings": [],
        }
    )
    (bundle / "release-status.json").write_bytes(
        canonical_json_bytes(status.model_dump(mode="json"))
    )
    hashes = {
        path.relative_to(bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }
    (bundle / "release-manifest.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "1.1",
                "release_version": status.release_version,
                "source_panel_id": status.source_panel_id,
                "source_panel_hash": status.source_panel_hash,
                "generated_at": status.generated_at.isoformat(),
                "artifact_hashes": hashes,
            }
        )
    )
    return bundle


def _enable_comparisons(bundle: Path) -> None:
    view_model_path = bundle / "data" / "publication_view_model.json"
    view_model = json.loads(view_model_path.read_text(encoding="utf-8"))
    view_model["comparisons"]["policy"]["enabled"] = True
    view_model_path.write_bytes(canonical_json_bytes(view_model))

    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"]["data/publication_view_model.json"] = hashlib.sha256(
        view_model_path.read_bytes()
    ).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
