"""Compose audited election releases into one Cloudflare Pages archive."""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from election_guide.hosting.models import (
    DeploymentManifest,
    PublishedElection,
    SiteManifest,
)
from election_guide.release.models import ReleaseManifest, ReleaseStatus
from election_guide.serialization import canonical_json_bytes, read_json, read_yaml

PAGES_HEADERS = """/*
  Cache-Control: public, max-age=0, must-revalidate
  Referrer-Policy: strict-origin-when-cross-origin
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), geolocation=(), microphone=()
"""

LEGACY_HOSTS = (
    "seattle-elections.dobravoda.dev",
    "seattle-elections.guide",
)

# The public About/FAQ page is site-wide rather than per-release, so it links to
# the source repository directly rather than through any per-election config.
PROJECT_URL = "https://github.com/shaug/seattle-election-guide"


@dataclass(frozen=True)
class StagedPagesSite:
    """Files prepared for one complete, immutable Pages deployment."""

    output_dir: Path
    current_election_id: str
    release_version: str
    git_commit: str
    source_panel_id: str
    source_panel_hash: str
    html_path: Path
    pdf_paths: tuple[Path, ...]
    election_paths: tuple[Path, ...]


@dataclass(frozen=True)
class _VerifiedBundle:
    declaration: PublishedElection
    directory: Path
    status: ReleaseStatus
    manifest: ReleaseManifest


def read_site_manifest(path: Path) -> SiteManifest:
    """Read a repository-owned archive manifest without accepting silent YAML overrides."""
    return SiteManifest.model_validate(read_yaml(path))


def verify_staged_pages_site(
    site_dir: Path,
    site_manifest_path: Path,
    *,
    expected_current_git_commit: str | None = None,
) -> DeploymentManifest:
    """Verify a completed Pages artifact against its repository-owned source of truth."""
    site_dir = site_dir.resolve()
    if not site_dir.is_dir():
        raise ValueError(f"staged Pages directory does not exist: {site_dir}")
    return _verify_staged_pages_site(
        site_dir,
        read_site_manifest(site_manifest_path.resolve()),
        expected_current_git_commit=expected_current_git_commit,
    )


def stage_pages_site(
    site_manifest_path: Path,
    bundle_dirs: Mapping[str, Path],
    output_dir: Path,
    *,
    expected_current_git_commit: str | None = None,
) -> StagedPagesSite:
    """Verify every declared release and atomically stage the complete public archive."""
    site_manifest_path = site_manifest_path.resolve()
    output_dir = output_dir.resolve()
    site_manifest = read_site_manifest(site_manifest_path)
    _validate_bundle_assignments(site_manifest, bundle_dirs)

    verified: list[_VerifiedBundle] = []
    for declaration in site_manifest.elections:
        bundle_dir = bundle_dirs[declaration.bundle_id].resolve()
        _validate_distinct_paths(bundle_dir, output_dir)
        verified.append(_verify_bundle(declaration, bundle_dir))

    current = next(
        bundle
        for bundle in verified
        if bundle.declaration.election_id == site_manifest.current_election_id
    )
    if (
        expected_current_git_commit is not None
        and current.status.git_commit != expected_current_git_commit
    ):
        raise ValueError(
            "current release bundle was built from a different Git commit: "
            f"expected {expected_current_git_commit}, found {current.status.git_commit}"
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        public_paths = _stage_verified_bundles(stage, verified)
        archive_path = stage / "e" / "index.html"
        archive_path.write_text(_archive_html(site_manifest), encoding="utf-8")
        public_paths.update({"/e/", "/e/index.html"})

        about_path = stage / "about" / "index.html"
        about_path.parent.mkdir(parents=True)
        about_path.write_text(_about_html(site_manifest), encoding="utf-8")
        public_paths.update({"/about/", "/about/index.html"})

        (stage / "_headers").write_text(PAGES_HEADERS, encoding="utf-8")
        public_paths.add("/deployment-manifest.json")
        (stage / "_worker.js").write_text(
            _pages_worker(site_manifest, public_paths),
            encoding="utf-8",
        )
        deployment_manifest = {
            "schema_version": "2.0",
            "canonical_origin": site_manifest.canonical_origin,
            "current_election_id": site_manifest.current_election_id,
            "elections": [
                {
                    "election_id": bundle.declaration.election_id,
                    "bundle_id": bundle.declaration.bundle_id,
                    "release_version": bundle.status.release_version,
                    "git_commit": bundle.status.git_commit,
                    "source_panel_id": bundle.status.source_panel_id,
                    "source_panel_hash": bundle.status.source_panel_hash,
                    "release_manifest_sha256": _sha256(bundle.directory / "release-manifest.json"),
                }
                for bundle in verified
            ],
            "assets": _artifact_hashes(stage),
        }
        (stage / "deployment-manifest.json").write_bytes(canonical_json_bytes(deployment_manifest))
        _verify_staged_pages_site(
            stage,
            site_manifest,
            expected_current_git_commit=expected_current_git_commit,
        )
        _replace_output(stage, output_dir)
        stage = Path()
    finally:
        if stage != Path() and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)

    current_root = output_dir / "e" / current.declaration.election_id
    pdf_paths = tuple(
        current_root / Path(relative).name for relative in _guide_pdf_artifacts(current.status)
    )
    return StagedPagesSite(
        output_dir=output_dir,
        current_election_id=current.declaration.election_id,
        release_version=current.status.release_version,
        git_commit=current.status.git_commit,
        source_panel_id=current.status.source_panel_id,
        source_panel_hash=current.status.source_panel_hash,
        html_path=current_root / "index.html",
        pdf_paths=pdf_paths,
        election_paths=tuple(
            output_dir / "e" / bundle.declaration.election_id for bundle in verified
        ),
    )


def _verify_staged_pages_site(
    site_dir: Path,
    site_manifest: SiteManifest,
    *,
    expected_current_git_commit: str | None,
) -> DeploymentManifest:
    deployment = DeploymentManifest.model_validate(read_json(site_dir / "deployment-manifest.json"))
    if deployment.canonical_origin != site_manifest.canonical_origin:
        raise ValueError("deployment manifest canonical origin differs from site manifest")
    if deployment.current_election_id != site_manifest.current_election_id:
        raise ValueError("deployment manifest current election differs from site manifest")
    if len(deployment.elections) != len(site_manifest.elections):
        raise ValueError("deployment manifest election count differs from site manifest")

    required_assets = {"_headers", "_worker.js", "e/index.html", "about/index.html"}
    for declared, deployed in zip(site_manifest.elections, deployment.elections, strict=True):
        expected_values = {
            "election ID": (declared.election_id, deployed.election_id),
            "bundle ID": (declared.bundle_id, deployed.bundle_id),
            "release version": (declared.release_version, deployed.release_version),
            "source panel ID": (declared.source_panel_id, deployed.source_panel_id),
            "source panel hash": (declared.source_panel_hash, deployed.source_panel_hash),
        }
        for label, (declared_value, deployed_value) in expected_values.items():
            if declared_value != deployed_value:
                raise ValueError(f"deployment manifest {label} differs from site manifest")
        if declared.git_commit is not None and declared.git_commit != deployed.git_commit:
            raise ValueError("deployment manifest Git commit differs from site manifest")
        if (
            declared.release_manifest_sha256 is not None
            and declared.release_manifest_sha256 != deployed.release_manifest_sha256
        ):
            raise ValueError("deployment manifest release-manifest hash differs from site manifest")

        election_root = site_dir / "e" / declared.election_id
        status = ReleaseStatus.model_validate(read_json(election_root / "release-status.json"))
        if (
            status.election_id != deployed.election_id
            or status.release_version != deployed.release_version
            or status.git_commit != deployed.git_commit
            or status.source_panel_id != deployed.source_panel_id
            or status.source_panel_hash != deployed.source_panel_hash
        ):
            raise ValueError(f"staged release status differs for election {declared.election_id!r}")
        if _sha256(election_root / "release-manifest.json") != deployed.release_manifest_sha256:
            raise ValueError(
                f"staged release manifest differs for election {declared.election_id!r}"
            )
        required_assets.update(
            {
                f"e/{declared.election_id}/index.html",
                f"e/{declared.election_id}/release-status.json",
                f"e/{declared.election_id}/release-manifest.json",
                *(
                    f"e/{declared.election_id}/{Path(relative).name}"
                    for relative in _guide_pdf_artifacts(status)
                ),
            }
        )

    current = next(
        election
        for election in deployment.elections
        if election.election_id == deployment.current_election_id
    )
    if (
        expected_current_git_commit is not None
        and current.git_commit != expected_current_git_commit
    ):
        raise ValueError(
            "deployed current release was built from a different Git commit: "
            f"expected {expected_current_git_commit}, found {current.git_commit}"
        )

    actual_assets = _artifact_hashes(site_dir, exclude={"deployment-manifest.json"})
    if set(actual_assets) != set(deployment.assets):
        missing = sorted(set(deployment.assets) - set(actual_assets))
        unexpected = sorted(set(actual_assets) - set(deployment.assets))
        raise ValueError(
            f"staged Pages assets differ from deployment manifest; "
            f"missing={missing}, unexpected={unexpected}"
        )
    mismatched = sorted(
        path
        for path, expected_hash in deployment.assets.items()
        if actual_assets[path] != expected_hash
    )
    if mismatched:
        raise ValueError(f"staged Pages asset hash mismatch: {mismatched}")

    if not required_assets.issubset(deployment.assets):
        raise ValueError("deployment manifest is missing required public archive assets")
    return deployment


def _validate_bundle_assignments(
    site_manifest: SiteManifest,
    bundle_dirs: Mapping[str, Path],
) -> None:
    expected = {election.bundle_id for election in site_manifest.elections}
    actual = set(bundle_dirs)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"bundle assignments do not match site manifest; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _verify_bundle(declaration: PublishedElection, bundle_dir: Path) -> _VerifiedBundle:
    status = ReleaseStatus.model_validate(read_json(bundle_dir / "release-status.json"))
    manifest_path = bundle_dir / "release-manifest.json"
    manifest = ReleaseManifest.model_validate(read_json(manifest_path))
    if status.election_id != declaration.election_id:
        raise ValueError(
            f"bundle {declaration.bundle_id!r} election differs: "
            f"expected {declaration.election_id}, found {status.election_id}"
        )
    expected_values = {
        "release version": (declaration.release_version, status.release_version),
        "source panel ID": (declaration.source_panel_id, status.source_panel_id),
        "source panel hash": (declaration.source_panel_hash, status.source_panel_hash),
    }
    for label, (expected, actual) in expected_values.items():
        if expected != actual:
            raise ValueError(
                f"bundle {declaration.bundle_id!r} {label} differs: "
                f"expected {expected}, found {actual}"
            )
    if declaration.git_commit is not None and declaration.git_commit != status.git_commit:
        raise ValueError(f"bundle {declaration.bundle_id!r} Git commit differs")
    if (
        declaration.release_manifest_sha256 is not None
        and declaration.release_manifest_sha256 != _sha256(manifest_path)
    ):
        raise ValueError(f"bundle {declaration.bundle_id!r} release manifest hash differs")

    if manifest.release_version != status.release_version:
        raise ValueError("release manifest and release status versions differ")
    if manifest.generated_at != status.generated_at:
        raise ValueError("release manifest and release status timestamps differ")
    if (
        manifest.source_panel_id != status.source_panel_id
        or manifest.source_panel_hash != status.source_panel_hash
    ):
        raise ValueError("release manifest and release status source panels differ")
    expected_artifacts = set(status.included_artifacts) - {"release-manifest.json"}
    if set(manifest.artifact_hashes) != expected_artifacts:
        raise ValueError("release manifest does not cover the complete release artifact set")
    _verify_artifact_hashes(bundle_dir, manifest.artifact_hashes)
    if declaration.bundle_sha256 is not None and declaration.bundle_sha256 != _bundle_hash(
        bundle_dir
    ):
        raise ValueError(f"bundle {declaration.bundle_id!r} bundle hash differs")
    return _VerifiedBundle(declaration, bundle_dir, status, manifest)


def _stage_verified_bundles(stage: Path, bundles: list[_VerifiedBundle]) -> set[str]:
    public_paths: set[str] = set()
    for bundle in bundles:
        election_root = stage / "e" / bundle.declaration.election_id
        election_root.mkdir(parents=True)
        html_source = bundle.directory / bundle.status.guide_html_artifact
        shutil.copy2(html_source, election_root / "index.html")

        names = [
            *(Path(relative).name for relative in _guide_pdf_artifacts(bundle.status)),
            "release-status.json",
            "release-manifest.json",
        ]
        if len(names) != len(set(names)) or "index.html" in names:
            raise ValueError(f"bundle {bundle.declaration.bundle_id!r} repeats a public asset name")
        for relative in _guide_pdf_artifacts(bundle.status):
            shutil.copy2(bundle.directory / relative, election_root / Path(relative).name)
        shutil.copy2(
            bundle.directory / "release-status.json",
            election_root / "release-status.json",
        )
        shutil.copy2(
            bundle.directory / "release-manifest.json",
            election_root / "release-manifest.json",
        )

        root_path = f"/e/{bundle.declaration.election_id}/"
        public_paths.update({root_path, f"{root_path}index.html"})
        public_paths.update(f"{root_path}{name}" for name in names)
    return public_paths


def _guide_pdf_artifacts(status: ReleaseStatus) -> tuple[str, ...]:
    return (
        status.guide_pdf_artifact,
        *(
            (status.detailed_guide_pdf_artifact,)
            if status.detailed_guide_pdf_artifact is not None
            else ()
        ),
    )


def _archive_html(site_manifest: SiteManifest) -> str:
    rows = "\n".join(
        "      <li>"
        f'<a href="/e/{election.election_id}/">{html.escape(election.name)}</a>'
        + (
            " <strong>(current)</strong>"
            if election.election_id == site_manifest.current_election_id
            else ""
        )
        + "</li>"
        for election in site_manifest.elections
    )
    canonical_url = f"{site_manifest.canonical_origin}/e/"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Published Seattle election endorsement guides.">
  <meta property="og:type" content="website">
  <meta property="og:title" content="Seattle election guide archive">
  <meta property="og:url" content="{html.escape(canonical_url, quote=True)}">
  <link rel="canonical" href="{html.escape(canonical_url, quote=True)}">
  <title>Seattle election guide archive</title>
</head>
<body>
  <main>
    <h1>Seattle election guide archive</h1>
    <p>Published guides remain available at permanent election-scoped paths.</p>
    <ol>
{rows}
    </ol>
  </main>
</body>
</html>
"""


_TEMPLATES_DIR = Path(__file__).parents[1] / "rendering" / "templates"


def _about_html(site_manifest: SiteManifest) -> str:
    current = next(
        election
        for election in site_manifest.elections
        if election.election_id == site_manifest.current_election_id
    )
    current_path = f"/e/{current.election_id}/"
    canonical_url = f"{site_manifest.canonical_origin}/about/"
    # Shared verbatim with the rendered guide (src/election_guide/rendering/
    # renderer.py) so the design tokens, accessibility utilities, and the
    # share/copy-link fallback policy have exactly one implementation each.
    base_css = (_TEMPLATES_DIR / "base.css").read_text(encoding="utf-8")
    share_link_script = (_TEMPLATES_DIR / "share-link.mjs").read_text(encoding="utf-8")
    description = (
        "How this guide aggregates organizational endorsements, why the source panel is "
        "versioned, how to verify a result, and how to report a correction."
    )
    escaped_description = html.escape(description, quote=True)
    escaped_canonical = html.escape(canonical_url, quote=True)
    escaped_current_path = html.escape(current_path, quote=True)
    escaped_election_name = html.escape(current.name)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escaped_description}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="About the Seattle election guide">
  <meta property="og:description" content="{escaped_description}">
  <meta property="og:url" content="{escaped_canonical}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="About the Seattle election guide">
  <meta name="twitter:description" content="{escaped_description}">
  <link rel="canonical" href="{escaped_canonical}">
  <title>About &amp; FAQ &mdash; Seattle election guide</title>
  <style>
    {base_css}
    .page {{ max-width: 46rem; margin: 0 auto; background: var(--paper); min-height: 100vh; }}
    .page-header {{
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
      gap: .75rem 1.5rem; color: var(--white); background: var(--navy);
      padding: 1.25rem clamp(1rem, 4vw, 2.5rem); border-bottom: .4rem solid var(--teal);
    }}
    .page-header p {{
      margin: 0; font-size: .78rem; font-weight: 800;
      letter-spacing: .1em; text-transform: uppercase;
    }}
    .page-header nav a {{
      color: #9ee7df; font-weight: 800; font-size: .85rem; white-space: nowrap;
    }}
    main {{ padding: 1.5rem clamp(1rem, 4vw, 2.5rem) 3rem; }}
    main h1 {{
      margin: 0 0 .35rem; color: var(--navy);
      font: 800 clamp(1.8rem, 4vw, 2.6rem)/1.05 Georgia, serif;
    }}
    main > p.lede {{ margin: 0 0 2rem; color: var(--muted); max-width: 46ch; }}
    section {{ margin: 0 0 2rem; }}
    section h2 {{ color: var(--navy); font-size: 1.25rem; margin: 0 0 .5rem; }}
    section p {{ margin: 0 0 .75rem; }}
    section p:last-child {{ margin-bottom: 0; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: .6rem 1rem; align-items: center; }}
    .share-button {{
      padding: .45rem .9rem; border: 1px solid #829ab1; border-radius: .3rem;
      background: var(--white); color: var(--ink);
      font: inherit; font-weight: 700; cursor: pointer;
    }}
    .share-button:hover {{ background: #eef3f6; }}
    .share-button:focus-visible {{ outline: .2rem solid #f0a928; outline-offset: .15rem; }}
    .page-footer {{
      border-top: 1px solid #cbd2d9; padding: 1.25rem clamp(1rem, 4vw, 2.5rem) 2rem;
      color: var(--muted); font-size: .85rem;
    }}
    .page-footer a {{ font-weight: 700; }}
  </style>
</head>
<body>
  <a class="skip-link" href="#about-main">Skip to content</a>
  <div class="page">
    <header class="page-header">
      <p>Seattle election guide</p>
      <nav aria-label="Guide links">
        <a href="{escaped_current_path}">Back to the {escaped_election_name} guide</a>
      </nav>
    </header>
    <main id="about-main">
      <h1>About this guide, and how to check our work</h1>
      <p class="lede">{html.escape(description)}</p>

      <section aria-labelledby="what-this-is">
        <h2 id="what-this-is">What this guide is &mdash; and is not</h2>
        <p>This site aggregates endorsements that progressive and left-of-center organizations have
          already published. It is not an official voter pamphlet, it does not independently vet any
          candidate, and it does not predict who will win. A high agreement percentage means many of
          the organizations we track agree with each other, not that we do.</p>
      </section>

      <section aria-labelledby="how-the-numbers-work">
        <h2 id="how-the-numbers-work">How the numbers work</h2>
        <p>Each organization gets one point per race. If it endorses more than one candidate, that
          point splits evenly among them unless the organization states its own split. Silence, "no
          endorsement," and races an organization simply did not cover are shown as counts but
          never count toward a candidate's share, so a small sample never looks more decisive than
          it is.</p>
        <p>The Seattle Times is shown separately, as a comparison, and is off by default: it never
          adds to the progressive consensus above, no matter how you choose to view the guide.</p>
      </section>

      <section aria-labelledby="why-ballot-varies">
        <h2 id="why-ballot-varies">Why your ballot may look different</h2>
        <p>Exact ballot contents vary by voter registration address. This guide covers the races on
          the ballot inventory built for this election; some races shown here may not appear on your
          own ballot, and your ballot may include a race this guide does not cover.</p>
      </section>

      <section aria-labelledby="source-panel">
        <h2 id="source-panel">The source panel is versioned, not frozen forever</h2>
        <p>The set of organizations tracked for a given guide is preregistered and locked before
          scoring begins, so results can't be adjusted after the fact to fit an outcome. When
          legitimate new evidence turns up &mdash; a source we missed, or one that was misclassified
          &mdash; it is added to a later, explicitly versioned panel rather than silently
          rewriting this one. Every guide states its exact panel ID and hash in its footer, so a
          later revision is always visible, never hidden.</p>
      </section>

      <section aria-labelledby="verify-it">
        <h2 id="verify-it">Verify it yourself</h2>
        <p>Every guide records a data version, a source-panel ID and hash, and the exact code
          revision that built it, in its footer. Each source row links directly to the
          organization's own endorsement page or document, so any displayed result can be checked
          against the original evidence.</p>
        <p><a href="{escaped_current_path}release-status.json">Current release status</a> and
          <a href="{escaped_current_path}release-manifest.json">release manifest</a> are public JSON
          files for the current guide. The complete decision ledger, source metadata, and validation
          reports for every release are published in the
          <a href="{PROJECT_URL}">project's source repository</a>, alongside the code that produced
          them.</p>
      </section>

      <section aria-labelledby="report-a-correction">
        <h2 id="report-a-correction">Report a correction or suggest a source</h2>
        <p>Found a stale or wrong endorsement, or know an organization we should be tracking?
          Email <a href="mailto:seattle-elections@dobravoda.dev">seattle-elections@dobravoda.dev</a>
          &mdash; no GitHub account needed. If you already use GitHub, you are also welcome to
          open an issue directly against the source repository below.</p>
      </section>

      <section aria-labelledby="who-maintains-this">
        <h2 id="who-maintains-this">Who maintains this</h2>
        <p>This is an independent, volunteer-run project, not affiliated with any campaign,
          party, or any organization it tracks. Its code and methodology are public at
          <a href="{PROJECT_URL}">{PROJECT_URL.removeprefix("https://")}</a>.</p>
      </section>

      <div class="actions">
        <button type="button" class="share-button" data-share-about>Share this page</button>
        <p class="visually-hidden" role="status" aria-live="polite" data-share-about-status></p>
      </div>
    </main>
    <footer class="page-footer">
      <nav aria-label="Guide links">
        <a href="{escaped_current_path}">{escaped_election_name} guide</a> &middot;
        <a href="/e/">All published guides</a>
      </nav>
    </footer>
  </div>
  <script type="module">
{share_link_script}
    const shareButton = document.querySelector('[data-share-about]');
    const shareStatus = document.querySelector('[data-share-about-status]');
    shareButton?.addEventListener('click', async () => {{
      const value = window.location.href;
      const result = await shareOrCopyLink(value, document.title);
      if (!shareStatus) return;
      if (result === 'copied') shareStatus.textContent = 'Link copied.';
      else if (result === 'shared') shareStatus.textContent = 'Share menu opened.';
      else if (result === 'failed') shareStatus.textContent = `Copy failed. Link: ${{value}}`;
    }});
  </script>
</body>
</html>
"""


def _pages_worker(site_manifest: SiteManifest, public_paths: set[str]) -> str:
    current_path = f"/e/{site_manifest.current_election_id}/"
    election_roots = [f"/e/{election.election_id}/" for election in site_manifest.elections]
    return f"""const CANONICAL_HOST = {json.dumps(site_manifest.canonical_origin.removeprefix("https://"))};
const LEGACY_HOSTS = new Set({json.dumps(list(LEGACY_HOSTS))});
const CURRENT_ELECTION_PATH = {json.dumps(current_path)};
const ELECTION_ROOTS = {json.dumps(election_roots)};
const PUBLIC_PATHS = new Set({json.dumps(sorted(public_paths))});

function redirectPath(url, pathname, status) {{
  const target = new URL(url);
  target.pathname = pathname;
  return Response.redirect(target.toString(), status);
}}

function notFound() {{
  return new Response("Not found\\n", {{
    status: 404,
    headers: {{
      "Content-Type": "text/plain; charset=utf-8",
      "X-Robots-Tag": "noindex",
    }},
  }});
}}

export default {{
  async fetch(request, env) {{
    const url = new URL(request.url);

    if (LEGACY_HOSTS.has(url.hostname)) {{
      url.protocol = "https:";
      url.hostname = CANONICAL_HOST;
      url.port = "";
      return Response.redirect(url.toString(), 301);
    }}
    if (url.pathname === "/") {{
      return redirectPath(url, CURRENT_ELECTION_PATH, 307);
    }}
    if (url.pathname === "/e") {{
      return redirectPath(url, "/e/", 308);
    }}
    if (url.pathname === "/about") {{
      return redirectPath(url, "/about/", 308);
    }}
    for (const root of ELECTION_ROOTS) {{
      if (url.pathname === root.slice(0, -1)) {{
        return redirectPath(url, root, 308);
      }}
    }}
    if (!PUBLIC_PATHS.has(url.pathname)) {{
      return notFound();
    }}
    return env.ASSETS.fetch(request);
  }},
}};
"""


def _verify_artifact_hashes(bundle_dir: Path, artifact_hashes: dict[str, str]) -> None:
    for relative, expected in sorted(artifact_hashes.items()):
        path = bundle_dir / relative
        if not path.is_file():
            raise ValueError(f"release artifact is missing: {relative}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"release artifact hash mismatch: {relative}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _artifact_hashes(root: Path, *, exclude: set[str] | None = None) -> dict[str, str]:
    excluded = exclude or set()
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    }


def _validate_distinct_paths(bundle_dir: Path, output_dir: Path) -> None:
    if not bundle_dir.is_dir():
        raise ValueError(f"release bundle directory does not exist: {bundle_dir}")
    if (
        bundle_dir == output_dir
        or bundle_dir in output_dir.parents
        or output_dir in bundle_dir.parents
    ):
        raise ValueError("release bundle and Pages output directories must not overlap")


def _replace_output(stage: Path, output_dir: Path) -> None:
    backup: Path | None = None
    if output_dir.exists():
        backup = output_dir.with_name(f".{output_dir.name}.backup-{os.getpid()}")
        if backup.exists():
            raise ValueError(f"Pages output backup path already exists: {backup}")
        os.replace(output_dir, backup)
    try:
        os.replace(stage, output_dir)
    except OSError:
        if backup is not None and backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
