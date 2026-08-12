"""Compose audited election releases into one Cloudflare Pages archive."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from election_guide.calendar import read_election_calendar
from election_guide.hosting.models import (
    DeploymentManifest,
    PublishedElection,
    SiteManifest,
)
from election_guide.hosting.releases import materialize_released_bundle
from election_guide.publication.calendar_feed import build_calendar_feed
from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.release.models import ReleaseManifest, ReleaseStatus
from election_guide.rendering.bundler import bundle_entry
from election_guide.rendering.documents import (
    render_comparison_document,
    render_corrections_document,
    render_race_document,
    render_sources_document,
    template_environment,
)
from election_guide.rendering.og_image import race_card, render_race_card
from election_guide.rendering.shell import (
    election_names,
    favicon_svg,
    page_title,
    race_og_image_path,
    race_page_path,
)
from election_guide.rendering.stylesheets import page_stylesheet
from election_guide.serialization import canonical_json_bytes, read_json, read_yaml

CALENDAR_FEED_NAME = "calendar.ics"
# Repository-relative, like every other configuration default in the CLI. The
# staging function takes it as a parameter so a caller can point elsewhere.
DEFAULT_CALENDAR_PATH = Path("config/calendar/elections.yaml")

PAGES_HEADERS = f"""/*
  Cache-Control: public, max-age=0, must-revalidate
  Referrer-Policy: strict-origin-when-cross-origin
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), geolocation=(), microphone=()

# A calendar client decides the file's type from this header, not the
# extension. Cache-Control is deliberately left to the wildcard rule above:
# Pages joins repeated headers rather than overriding them, so a second
# directive here would merge into a contradictory value.
/{CALENDAR_FEED_NAME}
  Content-Type: text/calendar; charset=utf-8
"""

LEGACY_HOSTS = (
    "seattle-elections.dobravoda.dev",
    "seattle-elections.guide",
)

# The public About/FAQ page is site-wide rather than per-release, so it links to
# the source repository directly rather than through any per-election config.
PROJECT_URL = "https://github.com/shaug/seattle-election-guide"

# Pre-rasterized copies of the shared site icon (see rendering/shell.py).
ASSET_DIR = Path(__file__).parent / "assets"


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
    election_paths: tuple[Path, ...]
    sources_path: Path


@dataclass(frozen=True)
class _VerifiedBundle:
    declaration: PublishedElection
    directory: Path
    status: ReleaseStatus
    manifest: ReleaseManifest
    view_model: PublicationViewModel


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
    released_bundle_dir: Path | None = None,
    calendar_path: Path = DEFAULT_CALENDAR_PATH,
) -> StagedPagesSite:
    """Verify every declared release and atomically stage the complete public archive."""
    site_manifest_path = site_manifest_path.resolve()
    output_dir = output_dir.resolve()
    site_manifest = read_site_manifest(site_manifest_path)
    if released_bundle_dir is not None:
        bundle_dirs = _resolve_released_bundles(
            site_manifest, bundle_dirs, released_bundle_dir.resolve()
        )
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
        public_paths = _stage_verified_bundles(stage, verified, site_manifest.canonical_origin)
        # Site-wide pages use the current release's data cutoff and deployed
        # revision timestamp, matching the election-scoped footer.
        current_data_updated_date = current.status.data_as_of.date().isoformat()
        current_site_updated_date = current.status.generated_at.date().isoformat()
        current_data_version = current.view_model.metadata.data_version
        current_git_commit = current.status.git_commit
        current_release_manifest_href = (
            f"/e/{current.declaration.election_id}/release-manifest.json"
        )
        current_compare_href = (
            f"/e/{current.declaration.election_id}/comparisons/"
            if current.view_model.comparisons.policy.enabled
            else None
        )
        current_corrections_href = (
            f"/e/{current.declaration.election_id}/corrections/"
            if current.view_model.corrections is not None and current.view_model.corrections.entries
            else None
        )
        archive_path = stage / "e" / "index.html"
        archive_path.write_text(
            _archive_html(
                site_manifest,
                election_names_by_id={
                    bundle.declaration.election_id: election_names(
                        bundle.view_model.metadata.election_date,
                        bundle.view_model.metadata.election_type,
                        bundle.view_model.metadata.state,
                        legacy_name=bundle.view_model.metadata.election_name,
                        election_id=bundle.view_model.metadata.election_id,
                    )[1]
                    for bundle in verified
                },
                data_updated_date=current_data_updated_date,
                site_updated_date=current_site_updated_date,
                data_version=current_data_version,
                git_commit=current_git_commit,
                data_href=current_release_manifest_href,
                compare_href=current_compare_href,
                corrections_href=current_corrections_href,
            ),
            encoding="utf-8",
        )
        public_paths.update({"/e/", "/e/index.html"})

        about_path = stage / "about" / "index.html"
        about_path.parent.mkdir(parents=True)
        about_path.write_text(
            _about_html(
                site_manifest,
                data_updated_date=current_data_updated_date,
                site_updated_date=current_site_updated_date,
                data_version=current_data_version,
                git_commit=current_git_commit,
                data_href=current_release_manifest_href,
                compare_href=current_compare_href,
                corrections_href=current_corrections_href,
            ),
            encoding="utf-8",
        )
        public_paths.update({"/about/", "/about/index.html"})

        # Site-wide brand assets (issue 115, item A4). The SVG favicon renders
        # from the one shared icon implementation; the PNG fallbacks and the
        # social-card image are pre-rasterized copies of the same mark.
        (stage / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
        for asset_name in ("favicon-32.png", "apple-touch-icon.png", "og-image.png"):
            shutil.copy2(ASSET_DIR / asset_name, stage / asset_name)
        public_paths.update(
            {"/favicon.svg", "/favicon-32.png", "/apple-touch-icon.png", "/og-image.png"}
        )

        # The subscribable election calendar (issue 259). Its DTSTAMP is the
        # current release's build time rather than the clock, so restaging the
        # same inputs produces identical bytes and a subscriber sees a revision
        # only when the declared calendar actually changed.
        # Written as bytes: RFC 5545 requires CRLF, and text mode would rewrite
        # those endings to the host platform's.
        (stage / CALENDAR_FEED_NAME).write_bytes(
            build_calendar_feed(
                read_election_calendar(calendar_path),
                canonical_origin=site_manifest.canonical_origin,
                published_at=current.status.generated_at,
                published_election_ids={bundle.declaration.election_id for bundle in verified},
            ).encode("utf-8")
        )
        public_paths.add(f"/{CALENDAR_FEED_NAME}")

        (stage / "_headers").write_text(PAGES_HEADERS, encoding="utf-8")
        public_paths.add("/deployment-manifest.json")
        (stage / "_worker.js").write_text(
            _pages_worker(
                site_manifest,
                public_paths,
                data_updated_date=current_data_updated_date,
                site_updated_date=current_site_updated_date,
                data_version=current_data_version,
                git_commit=current_git_commit,
                data_href=current_release_manifest_href,
                compare_href=current_compare_href,
                corrections_href=current_corrections_href,
            ),
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
    return StagedPagesSite(
        output_dir=output_dir,
        current_election_id=current.declaration.election_id,
        release_version=current.status.release_version,
        git_commit=current.status.git_commit,
        source_panel_id=current.status.source_panel_id,
        source_panel_hash=current.status.source_panel_hash,
        html_path=current_root / "index.html",
        election_paths=tuple(
            output_dir / "e" / bundle.declaration.election_id for bundle in verified
        ),
        sources_path=current_root / "sources" / "index.html",
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

    required_assets = {
        "_headers",
        "_worker.js",
        "e/index.html",
        "about/index.html",
        "favicon.svg",
        "favicon-32.png",
        "apple-touch-icon.png",
        "og-image.png",
        CALENDAR_FEED_NAME,
    }
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
                f"e/{declared.election_id}/sources/index.html",
            }
        )
        compare_asset = f"e/{declared.election_id}/comparisons/index.html"
        if declared.comparison_route_preview or compare_asset in deployment.assets:
            required_assets.add(compare_asset)
        corrections_asset = f"e/{declared.election_id}/corrections/index.html"
        if corrections_asset in deployment.assets:
            required_assets.add(corrections_asset)
        required_assets.update(_required_race_assets(declared.election_id, deployment.assets))

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


def _required_race_assets(election_id: str, assets: Mapping[str, str]) -> set[str]:
    """Every race page this election staged, and the card each one must carry.

    The declaration this function is checked against names a release, not a
    ballot, so the race ids come from what was staged rather than from a list
    this verifier could hold. What it therefore proves is the pairing and the
    floor: every election publishes at least one race page, and no race page
    ships without the social card its `og:image` points at — which is the way
    this could actually go wrong, since the page and the card are written by
    two different calls (issue #136).
    """
    prefix = f"e/{election_id}/races/"
    race_ids = sorted(
        path.removeprefix(prefix).removesuffix("/index.html")
        for path in assets
        if path.startswith(prefix) and path.endswith("/index.html")
    )
    if not race_ids:
        raise ValueError(f"staged archive has no race pages for election {election_id!r}")
    return {f"{prefix}{race_id}/{name}" for race_id in race_ids for name in _RACE_ASSET_NAMES}


_RACE_ASSET_NAMES = ("index.html", "og-image.png")


def _resolve_released_bundles(
    site_manifest: SiteManifest,
    bundle_dirs: Mapping[str, Path],
    released_bundle_dir: Path,
) -> dict[str, Path]:
    """Fill in every declared bundle not supplied locally from its published release.

    Only the current election is built from source. A historical election cannot be
    rebuilt — its pinned artifact hashes came from the rendering code of its own
    time — so its bundle is downloaded from the release that published it.
    """
    resolved = dict(bundle_dirs)
    for declaration in site_manifest.elections:
        if declaration.bundle_id in resolved:
            continue
        resolved[declaration.bundle_id] = materialize_released_bundle(
            declaration, released_bundle_dir
        )
    return resolved


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
    view_model = PublicationViewModel.model_validate(
        read_json(bundle_dir / "data/publication_view_model.json")
    )
    if view_model.metadata.election_id != declaration.election_id:
        raise ValueError(f"bundle {declaration.bundle_id!r} publication election differs")
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
    if declaration.bundle_sha256 is not None:
        # Naming both digests is what makes a drifted pin actionable: the fix is
        # to recompute it with `hosting bundle-hash` and review the difference,
        # which needs the value the archive actually hashed to (issue 270).
        found = bundle_hash(bundle_dir)
        if declaration.bundle_sha256 != found:
            raise ValueError(
                f"bundle {declaration.bundle_id!r} bundle hash differs: "
                f"expected {declaration.bundle_sha256}, found {found}"
            )
    return _VerifiedBundle(declaration, bundle_dir, status, manifest, view_model)


def _stage_verified_bundles(
    stage: Path,
    bundles: list[_VerifiedBundle],
    canonical_origin: str,
) -> set[str]:
    public_paths: set[str] = set()
    for bundle in bundles:
        election_root = stage / "e" / bundle.declaration.election_id
        election_root.mkdir(parents=True)
        html_source = bundle.directory / bundle.status.guide_html_artifact
        shutil.copy2(html_source, election_root / "index.html")

        # One list, so what is copied and what the worker will route are the
        # same set by construction.
        names = ("release-status.json", "release-manifest.json")
        for name in names:
            shutil.copy2(bundle.directory / name, election_root / name)

        sources_dir = election_root / "sources"
        sources_dir.mkdir()
        (sources_dir / "index.html").write_text(
            _sources_html(bundle.view_model, canonical_origin),
            encoding="utf-8",
        )

        root_path = f"/e/{bundle.declaration.election_id}/"
        public_paths.update({root_path, f"{root_path}index.html"})
        public_paths.update({f"{root_path}sources/", f"{root_path}sources/index.html"})
        public_paths.update(_stage_race_pages(bundle, election_root, canonical_origin))
        if (
            bundle.view_model.comparisons.policy.enabled
            or bundle.declaration.comparison_route_preview
        ):
            compare_dir = election_root / "comparisons"
            compare_dir.mkdir()
            (compare_dir / "index.html").write_text(
                _comparison_html(_comparison_route_view_model(bundle), canonical_origin),
                encoding="utf-8",
            )
            public_paths.update({f"{root_path}comparisons/", f"{root_path}comparisons/index.html"})
        if bundle.view_model.corrections is not None and bundle.view_model.corrections.entries:
            corrections_dir = election_root / "corrections"
            corrections_dir.mkdir()
            (corrections_dir / "index.html").write_text(
                _corrections_html(bundle.view_model, canonical_origin),
                encoding="utf-8",
            )
            public_paths.update({f"{root_path}corrections/", f"{root_path}corrections/index.html"})
        public_paths.update(f"{root_path}{name}" for name in names)
    return public_paths


def _stage_race_pages(
    bundle: _VerifiedBundle,
    election_root: Path,
    canonical_origin: str,
) -> set[str]:
    """One page and one social card per race in this election (issue #136).

    Race detail is a page rather than a dialog over the guide, so every race in
    every published election's inventory gets its own directory here — an
    archived guide's races included, exactly as the archived guide itself keeps
    its own address. Both files are rendered from the bundle's own verified view
    model, so a historical election's pages are a function of the data it was
    published with.
    """
    view_model = bundle.view_model
    election_id = bundle.declaration.election_id
    election_display_name, _ = election_names(
        view_model.metadata.election_date,
        view_model.metadata.election_type,
        view_model.metadata.state,
        legacy_name=view_model.metadata.election_name,
        election_id=view_model.metadata.election_id,
    )
    # The social card draws meter v2 from the same source cells the page
    # itself does (docs/METER_V2.md) — `context.meter_view` and every page
    # that calls it key sources the same way, by id.
    source_by_id = {source.id: source for source in view_model.sources}
    races_root = election_root / "races"
    races_root.mkdir()
    public_paths: set[str] = set()
    for section in view_model.sections:
        for race in section.races:
            directory = races_root / race.id
            directory.mkdir()
            (directory / "index.html").write_text(
                render_race_document(
                    view_model,
                    race.id,
                    public_site_url=canonical_origin,
                    project_url=PROJECT_URL,
                ),
                encoding="utf-8",
            )
            (directory / "og-image.png").write_bytes(
                render_race_card(race_card(race, source_by_id, election_name=election_display_name))
            )
            path = race_page_path(election_id, race.id)
            public_paths.update(
                {path, f"{path}index.html", race_og_image_path(election_id, race.id)}
            )
    return public_paths


def _comparison_route_view_model(bundle: _VerifiedBundle) -> PublicationViewModel:
    """Enable only the staged route when the current release is in preview."""
    if bundle.view_model.comparisons.policy.enabled:
        return bundle.view_model
    return bundle.view_model.model_copy(
        update={
            "comparisons": bundle.view_model.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=True)}
            )
        }
    )


def _sources_html(view_model: PublicationViewModel, canonical_origin: str) -> str:
    """Render the per-election sources/customization page (issue 107)."""
    return render_sources_document(
        view_model,
        public_site_url=canonical_origin,
        project_url=PROJECT_URL,
    )


def _comparison_html(view_model: PublicationViewModel, canonical_origin: str) -> str:
    """Render a per-election comparison route after hosting has admitted it."""
    return render_comparison_document(
        view_model,
        public_site_url=canonical_origin,
        project_url=PROJECT_URL,
    )


def _corrections_html(view_model: PublicationViewModel, canonical_origin: str) -> str:
    """Render the per-election corrections page (docs/RESULTS.md, "The
    corrections page"; issue #290) after `_stage_verified_bundles` has
    already gated its existence on this election carrying at least one
    entry."""
    return render_corrections_document(
        view_model,
        public_site_url=canonical_origin,
        project_url=PROJECT_URL,
    )


def _site_document(page: str, **context: object) -> str:
    """Render one of the three site-wide documents through the shared layout.

    About, the archive, and the 404 are not election-scoped, so they carry no
    view model and no source panel, but they extend the same `base.html.j2` and
    call the same shell macros as the guide, Sources, and Comparisons
    (docs/FRONTEND.md § Server-side templates).

    `page` names both the template and the page's declared CSS entry, which is
    `base.css` — the tokens and shell shared verbatim with every other page —
    plus this page's own stylesheet (rendering/stylesheets.py).
    """
    environment = template_environment()
    rendered = environment.get_template(f"{page}.html.j2").render(
        stylesheet=page_stylesheet(page),
        project_url=PROJECT_URL,
        **context,
    )
    # Jinja drops a template's single trailing newline; the f-strings these
    # three documents replaced ended with one. Restoring it keeps the published
    # bytes of the live About, archive, and 404 pages identical across this
    # conversion, which is the whole claim issue 241 makes about them. The
    # election-scoped pages were already Jinja and already end without it.
    return rendered + "\n"


def _archive_html(
    site_manifest: SiteManifest,
    *,
    election_names_by_id: Mapping[str, str],
    data_updated_date: str,
    site_updated_date: str,
    data_version: str,
    git_commit: str,
    data_href: str,
    compare_href: str | None = None,
    corrections_href: str | None = None,
) -> str:
    return _site_document(
        "archive",
        document_title=page_title(page="Guide archive"),
        page_description="Published Seattle election endorsement guides.",
        canonical_url=f"{site_manifest.canonical_origin}/e/",
        canonical_origin=site_manifest.canonical_origin,
        current_path=f"/e/{site_manifest.current_election_id}/",
        current_election_id=site_manifest.current_election_id,
        elections=site_manifest.elections,
        election_names_by_id=election_names_by_id,
        compare_href=compare_href,
        corrections_href=corrections_href,
        shell_entry_script=bundle_entry("shell-entry.mjs", global_name="ShellPage"),
        data_updated_date=data_updated_date,
        site_updated_date=site_updated_date,
        data_version=data_version,
        git_commit=git_commit,
        data_href=data_href,
    )


ABOUT_DESCRIPTION = (
    "How this guide aggregates organizational endorsements, why the source panel is "
    "versioned, how to verify a result, and how to report a correction."
)


def _about_html(
    site_manifest: SiteManifest,
    *,
    data_updated_date: str,
    site_updated_date: str,
    data_version: str,
    git_commit: str,
    data_href: str,
    compare_href: str | None = None,
    corrections_href: str | None = None,
) -> str:
    current_path = f"/e/{site_manifest.current_election_id}/"
    return _site_document(
        "about",
        document_title=page_title(page="How this works"),
        page_description=ABOUT_DESCRIPTION,
        canonical_url=f"{site_manifest.canonical_origin}/about/",
        canonical_origin=site_manifest.canonical_origin,
        current_path=current_path,
        compare_href=compare_href,
        corrections_href=corrections_href,
        project_url_label=PROJECT_URL.removeprefix("https://"),
        shell_entry_script=bundle_entry("shell-entry.mjs", global_name="ShellPage"),
        data_updated_date=data_updated_date,
        site_updated_date=site_updated_date,
        data_version=data_version,
        git_commit=git_commit,
        data_href=data_href,
    )


def _not_found_html(
    site_manifest: SiteManifest,
    *,
    data_updated_date: str,
    site_updated_date: str,
    data_version: str,
    git_commit: str,
    data_href: str,
    compare_href: str | None = None,
    corrections_href: str | None = None,
) -> str:
    """The worker's branded 404 with the shared global-page footer."""
    return _site_document(
        "not-found",
        document_title=page_title(page="Page not found"),
        canonical_origin=site_manifest.canonical_origin,
        shareable=False,
        current_path=f"/e/{site_manifest.current_election_id}/",
        compare_href=compare_href,
        corrections_href=corrections_href,
        data_updated_date=data_updated_date,
        site_updated_date=site_updated_date,
        data_version=data_version,
        git_commit=git_commit,
        data_href=data_href,
    )


def _pages_worker(
    site_manifest: SiteManifest,
    public_paths: set[str],
    *,
    data_updated_date: str,
    site_updated_date: str,
    data_version: str,
    git_commit: str,
    data_href: str,
    compare_href: str | None = None,
    corrections_href: str | None = None,
) -> str:
    current_path = f"/e/{site_manifest.current_election_id}/"
    election_roots = [f"/e/{election.election_id}/" for election in site_manifest.elections]
    comparison_roots = sorted(path for path in public_paths if path.endswith("/comparisons/"))
    comparison_root_declaration = (
        f"const COMPARISON_ROOTS = {json.dumps(comparison_roots)};\n" if comparison_roots else ""
    )
    comparison_redirect = (
        r"""    for (const root of COMPARISON_ROOTS) {
      if (url.pathname === root.slice(0, -1)) {
        return redirectPath(url, root, 308);
      }
      // The page shipped at /compare/ before issue 192 renamed it to match its
      // own name. Anything already linked or bookmarked keeps working, with a
      // permanent redirect so caches and search engines learn the new address.
      const renamed = root.replace(/comparisons\/$/, "compare");
      if (url.pathname === renamed || url.pathname === `${renamed}/`) {
        return redirectPath(url, root, 301);
      }
    }
"""
        if comparison_roots
        else ""
    )
    not_found_html = _not_found_html(
        site_manifest,
        data_updated_date=data_updated_date,
        site_updated_date=site_updated_date,
        data_version=data_version,
        git_commit=git_commit,
        data_href=data_href,
        compare_href=compare_href,
        corrections_href=corrections_href,
    )
    return f"""const CANONICAL_HOST = {json.dumps(site_manifest.canonical_origin.removeprefix("https://"))};
const LEGACY_HOSTS = new Set({json.dumps(list(LEGACY_HOSTS))});
const CURRENT_ELECTION_PATH = {json.dumps(current_path)};
const ELECTION_ROOTS = {json.dumps(election_roots)};
{comparison_root_declaration}const PUBLIC_PATHS = new Set({json.dumps(sorted(public_paths))});
const NOT_FOUND_HTML = {json.dumps(not_found_html)};

function redirectPath(url, pathname, status) {{
  const target = new URL(url);
  target.pathname = pathname;
  return Response.redirect(target.toString(), status);
}}

function notFound() {{
  return new Response(NOT_FOUND_HTML, {{
    status: 404,
    headers: {{
      "Content-Type": "text/html; charset=utf-8",
      "X-Robots-Tag": "noindex",
    }},
  }});
}}

function noindex(response) {{
  const marked = new Response(response.body, response);
  marked.headers.set("X-Robots-Tag", "noindex");
  return marked;
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
      // The generated PDF edition was retired (issue 193). Every PDF this
      // election ever published lived directly under its root, so anything
      // still linking one lands on the guide it was made from.
      if (url.pathname.startsWith(root) && url.pathname.endsWith(".pdf")) {{
        return redirectPath(url, root, 301);
      }}
    }}
{comparison_redirect}    // A directory addressed without its trailing slash is the same page
    // (issue #136 added thirty-odd race pages per election, and enumerating
    // each one's slashless form here would restate what PUBLIC_PATHS already
    // says). The named redirects above still come first, because each of those
    // is either older than this rule or means something other than "the same
    // page": `/` is a 307 to the current election, and the retired `/compare`
    // is a 301 to a renamed one.
    if (!PUBLIC_PATHS.has(url.pathname) && PUBLIC_PATHS.has(`${{url.pathname}}/`)) {{
      return redirectPath(url, `${{url.pathname}}/`, 308);
    }}
    if (!PUBLIC_PATHS.has(url.pathname)) {{
      return notFound();
    }}
    // Only the canonical host may be indexed (issue 209). Every other
    // hostname -- the Cloudflare *.pages.dev domain, and any per-pull-request
    // preview -- serves a complete copy of the guide whose endorsement data
    // may already be stale, so it must never compete with the real site in
    // search results. The 404 above is noindex on every host, canonical
    // included.
    const asset = await env.ASSETS.fetch(request);
    return url.hostname === CANONICAL_HOST ? asset : noindex(asset);
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


def bundle_hash(root: Path) -> str:
    """The `bundle_sha256` a released bundle must be pinned to: a hash of its whole tree.

    Length-prefixing each relative path and each body keeps two different trees
    from concatenating to the same bytes. This is the value `site.yaml` declares
    for a historical election, so it is public: obtaining it must not require
    reaching into this module (issue 270).
    """
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
