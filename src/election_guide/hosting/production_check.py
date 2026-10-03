"""Verify a deployed Pages site against its manifest and the public route contract.

The plan and evaluation here are pure — no network access — so both the
scheduled monitor (O14) and a future promote-on-demand smoke test (O4) can
share it without duplicating the route contract (`docs/SITE_OPERATIONS_PLAN.md`,
O4: "Shares the smoke-check logic with O14 — build it once and call it from
both."). Fetching over the network lives in `production_probe`.
"""

from __future__ import annotations

import json
from datetime import timedelta
from html.parser import HTMLParser

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from election_guide.hosting.models import DeploymentManifest, SiteManifest
from election_guide.release.models import ReleaseManifest

MANIFEST_PATH = "/deployment-manifest.json"
STALE_DATA_THRESHOLD_DAYS = 7


class RouteCheck(BaseModel):
    """One request the public route contract (`docs/HOSTING.md`) makes a claim about."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    expected_status: int
    expected_location: str | None = None


MANIFEST_CHECK = RouteCheck(name="deployment manifest", path=MANIFEST_PATH, expected_status=200)


def release_manifest_check(current_election_id: str) -> RouteCheck:
    return RouteCheck(
        name="current release manifest",
        path=f"/e/{current_election_id}/release-manifest.json",
        expected_status=200,
    )


class Observation(BaseModel):
    """What one live request actually returned, or why it could not be made."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: int | None = None
    location: str | None = None
    raw_location: str | None = None
    error: str | None = None


class RouteCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check: RouteCheck
    observed: Observation

    @property
    def ok(self) -> bool:
        if self.observed.status != self.check.expected_status:
            return False
        return (
            self.check.expected_location is None
            or self.observed.location == self.check.expected_location
        )


class CommitCheck(BaseModel):
    """The manifest's current-election commit against the commit `main` is on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected: str
    observed: str | None

    @property
    def ok(self) -> bool:
        return self.observed == self.expected


class DeploymentContractCheck(BaseModel):
    """Public deployment identity compared with repository-owned expectations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_site: SiteManifest
    observed: DeploymentManifest
    expected_git_commit: str
    representative_race_path: str | None = None
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


class ArchiveIndexCheck(BaseModel):
    """Election links and the current marker rendered by the public archive."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: RouteCheckResult
    expected_election_ids: tuple[str, ...]
    observed_election_ids: tuple[str, ...] = ()
    expected_current_election_id: str
    observed_current_election_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def observed_current_election_id(self) -> str | None:
        if len(self.observed_current_election_ids) == 1:
            return self.observed_current_election_ids[0]
        return None

    @property
    def ok(self) -> bool:
        return self.route.ok and not self.errors


class DataFreshnessCheck(BaseModel):
    """The published release age, gated by the calendar-derived active window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    published_at: AwareDatetime
    checked_at: AwareDatetime
    threshold_days: int = Field(default=STALE_DATA_THRESHOLD_DAYS, ge=0)

    @property
    def age(self) -> timedelta:
        return self.checked_at - self.published_at

    @property
    def ok(self) -> bool:
        return self.age <= timedelta(days=self.threshold_days)


class ProductionCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str | None = None
    checked_at: AwareDatetime | None = None
    manifest: RouteCheckResult
    manifest_parse_error: str | None = None
    deployment_contract: DeploymentContractCheck | None = None
    archive_index: ArchiveIndexCheck | None = None
    current_election_id: str | None = None
    release_manifest: RouteCheckResult | None = None
    release_manifest_parse_error: str | None = None
    route_results: tuple[RouteCheckResult, ...] = ()
    commit: CommitCheck | None = None
    data_freshness: DataFreshnessCheck | None = None

    @property
    def ok(self) -> bool:
        if not self.manifest.ok or self.manifest_parse_error is not None:
            return False
        if self.deployment_contract is not None and not self.deployment_contract.ok:
            return False
        if self.archive_index is not None and not self.archive_index.ok:
            return False
        if self.release_manifest is not None and not self.release_manifest.ok:
            return False
        if self.release_manifest_parse_error is not None:
            return False
        if any(not result.ok for result in self.route_results):
            return False
        if self.commit is not None and not self.commit.ok:
            return False
        return self.data_freshness is None or self.data_freshness.ok


def plan_route_checks(current_election_id: str) -> list[RouteCheck]:
    """The route-contract checks that follow from one manifest-declared current election.

    Any filename satisfies the legacy-PDF rule (`docs/HOSTING.md`, "Archive
    manifest and routes"): every `.pdf` under an election root redirects to
    that election's guide.
    """
    election_path = f"/e/{current_election_id}/"
    return [
        RouteCheck(
            name="home redirect",
            path="/",
            expected_status=307,
            expected_location=election_path,
        ),
        RouteCheck(
            name="current election guide",
            path=election_path,
            expected_status=200,
        ),
        RouteCheck(
            name="legacy PDF redirect",
            path=f"{election_path}voter-guide.pdf",
            expected_status=301,
            expected_location=election_path,
        ),
    ]


def plan_publication_route_checks(
    site_manifest: SiteManifest, *, representative_race_path: str
) -> list[RouteCheck]:
    """Complete publication-day route contract derived from trusted expectations."""
    current = site_manifest.current_election_id
    current_path = f"/e/{current}/"
    checks = [
        RouteCheck(
            name="home redirect",
            path="/",
            expected_status=307,
            expected_location=current_path,
        ),
        RouteCheck(name="election archive", path="/e/", expected_status=200),
        RouteCheck(name="current election guide", path=current_path, expected_status=200),
    ]
    checks.extend(
        RouteCheck(
            name=f"historical election guide: {election.election_id}",
            path=f"/e/{election.election_id}/",
            expected_status=200,
        )
        for election in site_manifest.elections
        if election.election_id != current
    )
    checks.extend(
        [
            RouteCheck(
                name="representative current-election race",
                path=representative_race_path,
                expected_status=200,
            ),
            RouteCheck(
                name="current election comparisons",
                path=f"{current_path}comparisons/",
                expected_status=200,
            ),
            RouteCheck(
                name="unknown election",
                path="/e/production-check-unknown-election/",
                expected_status=404,
            ),
            RouteCheck(
                name="legacy PDF redirect",
                path=f"{current_path}voter-guide.pdf",
                expected_status=301,
                expected_location=current_path,
            ),
        ]
    )
    return checks


def evaluate_manifest(
    observation: Observation, body: bytes | None
) -> tuple[RouteCheckResult, DeploymentManifest | None, str | None]:
    """Check the manifest fetch itself, then try to parse a well-formed manifest.

    A non-200 or a failed request stops here with no parse error recorded —
    the fetch is what failed, not the parse. Once the fetch reports its
    expected 200, a JSON or schema failure is recorded separately so a caller
    can tell "production served something, but it wasn't a manifest" apart
    from "production didn't answer."
    """
    result = RouteCheckResult(check=MANIFEST_CHECK, observed=observation)
    if not result.ok or body is None:
        return result, None, None
    try:
        # ValueError covers json.JSONDecodeError, ValidationError, and a
        # non-UTF-8 body's UnicodeDecodeError (json.loads decodes bytes
        # itself) in one catch — all three are ValueError subclasses, and a
        # production response that fails any of them should FAIL this check,
        # not crash the caller uncaught.
        manifest = DeploymentManifest.model_validate(json.loads(body))
    except ValueError as error:
        return result, None, str(error)
    return result, manifest, None


def evaluate_release_manifest(
    check: RouteCheck, observation: Observation, body: bytes | None
) -> tuple[RouteCheckResult, ReleaseManifest | None, str | None]:
    """Check and parse the current election's public release manifest."""
    result = RouteCheckResult(check=check, observed=observation)
    if not result.ok or body is None:
        return result, None, None
    try:
        manifest = ReleaseManifest.model_validate(json.loads(body))
    except ValueError as error:
        return result, None, str(error)
    return result, manifest, None


def evaluate_deployment_contract(
    expected: SiteManifest,
    observed: DeploymentManifest,
    *,
    expected_git_commit: str,
) -> DeploymentContractCheck:
    """Compare production with the checked-in site declaration and selected commit."""
    errors: list[str] = []
    if observed.canonical_origin != expected.canonical_origin:
        errors.append(
            "deployment manifest canonical origin differs from site manifest: "
            f"expected {expected.canonical_origin}, found {observed.canonical_origin}"
        )
    if observed.current_election_id != expected.current_election_id:
        errors.append(
            "deployment manifest current election differs from site manifest: "
            f"expected {expected.current_election_id}, found {observed.current_election_id}"
        )

    expected_ids = [election.election_id for election in expected.elections]
    observed_ids = [election.election_id for election in observed.elections]
    if observed_ids != expected_ids:
        errors.append(
            "deployment manifest election set/order differs from site manifest: "
            f"expected {expected_ids}, found {observed_ids}"
        )

    observed_by_id = {election.election_id: election for election in observed.elections}
    for declared in expected.elections:
        deployed = observed_by_id.get(declared.election_id)
        if deployed is None:
            continue
        values = (
            ("bundle ID", declared.bundle_id, deployed.bundle_id),
            ("release version", declared.release_version, deployed.release_version),
            ("source panel ID", declared.source_panel_id, deployed.source_panel_id),
            ("source panel hash", declared.source_panel_hash, deployed.source_panel_hash),
            (
                "source registry hash",
                declared.source_registry_hash,
                deployed.source_registry_hash,
            ),
        )
        for label, declared_value, deployed_value in values:
            if deployed_value != declared_value:
                errors.append(
                    f"deployment manifest {label} differs for {declared.election_id}: "
                    f"expected {declared_value}, found {deployed_value}"
                )

        is_current = declared.election_id == expected.current_election_id
        if is_current:
            if deployed.git_commit != expected_git_commit:
                errors.append(
                    "deployment manifest production candidate commit differs: "
                    f"expected {expected_git_commit}, found {deployed.git_commit}"
                )
        else:
            required_pins = (
                ("Git commit", declared.git_commit, deployed.git_commit),
                (
                    "release-manifest hash",
                    declared.release_manifest_sha256,
                    deployed.release_manifest_sha256,
                ),
            )
            for label, declared_value, deployed_value in required_pins:
                if declared_value is None:
                    errors.append(
                        f"historical site declaration lacks {label} for {declared.election_id}"
                    )
                elif deployed_value != declared_value:
                    errors.append(
                        f"deployment manifest {label} differs for {declared.election_id}: "
                        f"expected {declared_value}, found {deployed_value}"
                    )
            if declared.bundle_sha256 is None:
                errors.append(
                    f"historical site declaration lacks bundle hash for {declared.election_id}"
                )

    prefix = f"e/{expected.current_election_id}/races/"
    race_paths = sorted(
        f"/{path.removesuffix('index.html')}"
        for path in observed.assets
        if path.startswith(prefix) and path.endswith("/index.html")
    )
    representative_race_path = race_paths[0] if race_paths else None
    if representative_race_path is None:
        errors.append(
            "deployment manifest has no current-election race route for deterministic probing"
        )

    return DeploymentContractCheck(
        expected_site=expected,
        observed=observed,
        expected_git_commit=expected_git_commit,
        representative_race_path=representative_race_path,
        errors=tuple(errors),
    )


class _ArchiveIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[tuple[str, bool]] = []
        self._entry_id: str | None = None
        self._inside_strong = False
        self._strong_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "li":
            self._entry_id = None
            self._strong_text = []
        elif tag == "a" and self._entry_id is None:
            href = attributes.get("href")
            if href is not None and href.startswith("/e/") and href.endswith("/"):
                self._entry_id = href.removeprefix("/e/").removesuffix("/")
        elif tag == "strong":
            self._inside_strong = True

    def handle_data(self, data: str) -> None:
        if self._inside_strong:
            self._strong_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "strong":
            self._inside_strong = False
        elif tag == "li" and self._entry_id is not None:
            marker = "".join(self._strong_text).strip() == "(current)"
            self.entries.append((self._entry_id, marker))
            self._entry_id = None
            self._strong_text = []


def evaluate_archive_index(
    site_manifest: SiteManifest, observation: Observation, body: bytes | None
) -> ArchiveIndexCheck:
    """Verify `/e/` lists the complete archive and marks only the current guide."""
    route = RouteCheckResult(
        check=RouteCheck(name="election archive", path="/e/", expected_status=200),
        observed=observation,
    )
    expected_ids = tuple(election.election_id for election in site_manifest.elections)
    errors: list[str] = []
    entries: list[tuple[str, bool]] = []
    if route.ok and body is not None:
        try:
            parser = _ArchiveIndexParser()
            parser.feed(body.decode("utf-8"))
            entries = parser.entries
        except (UnicodeError, ValueError) as error:
            errors.append(f"archive index could not be parsed: {error}")
    elif route.ok:
        errors.append("archive index returned no body")

    observed_ids = tuple(election_id for election_id, _ in entries)
    observed_current = tuple(election_id for election_id, current in entries if current)
    if route.ok and observed_ids != expected_ids:
        errors.append(
            "archive index election set/order differs from site manifest: "
            f"expected {list(expected_ids)}, found {list(observed_ids)}"
        )
    if route.ok and observed_current != (site_manifest.current_election_id,):
        errors.append(
            "archive index current marker differs from site manifest: "
            f"expected {site_manifest.current_election_id}, found {list(observed_current)}"
        )
    return ArchiveIndexCheck(
        route=route,
        expected_election_ids=expected_ids,
        observed_election_ids=observed_ids,
        expected_current_election_id=site_manifest.current_election_id,
        observed_current_election_ids=observed_current,
        errors=tuple(errors),
    )


def _check_line(result: RouteCheckResult) -> str:
    status = "PASS" if result.ok else "FAIL"
    check = result.check
    observed = result.observed
    if observed.error is not None:
        detail = f"request failed: {observed.error}"
    elif check.expected_location is not None:
        raw_location = (
            f" (raw Location: {observed.raw_location})" if observed.raw_location is not None else ""
        )
        detail = (
            f"expected {check.expected_status} -> {check.expected_location}, "
            f"got {observed.status} -> {observed.location}{raw_location}"
        )
    else:
        detail = f"expected {check.expected_status}, got {observed.status}"
    return f"{status} {check.name} ({check.path}): {detail}"


def render_summary_lines(report: ProductionCheckReport) -> list[str]:
    """Human-readable per-check lines, for a CLI summary or an alert body."""
    lines = [_check_line(report.manifest)]
    if report.manifest_parse_error is not None:
        lines.append(f"FAIL deployment manifest ({MANIFEST_PATH}): {report.manifest_parse_error}")
    if report.deployment_contract is not None:
        contract = report.deployment_contract
        status = "PASS" if contract.ok else "FAIL"
        lines.append(
            f"{status} deployment manifest contract: expected current "
            f"{contract.expected_site.current_election_id} at {contract.expected_git_commit}"
        )
        lines.extend(f"FAIL deployment manifest contract: {error}" for error in contract.errors)
        if contract.representative_race_path is not None:
            lines.append(f"PASS representative race selection: {contract.representative_race_path}")
    if report.archive_index is not None:
        lines.extend(f"FAIL archive index {error}" for error in report.archive_index.errors)
    if report.release_manifest is not None:
        lines.append(_check_line(report.release_manifest))
    if report.release_manifest_parse_error is not None:
        path = report.release_manifest.check.path if report.release_manifest is not None else ""
        lines.append(
            f"FAIL current release manifest ({path}): {report.release_manifest_parse_error}"
        )
    lines.extend(_check_line(result) for result in report.route_results)
    if report.commit is not None:
        status = "PASS" if report.commit.ok else "FAIL"
        lines.append(
            f"{status} commit: expected {report.commit.expected}, found {report.commit.observed}"
        )
    if report.data_freshness is not None:
        freshness = report.data_freshness
        status = "PASS" if freshness.ok else "FAIL"
        age_days = freshness.age.total_seconds() / 86_400
        lines.append(
            f"{status} published data freshness: {age_days:.1f} days old at "
            f"{freshness.checked_at.isoformat()} (maximum {freshness.threshold_days} days)"
        )
    return lines
