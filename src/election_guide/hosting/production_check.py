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

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from election_guide.hosting.models import DeploymentManifest
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


class DataFreshnessCheck(BaseModel):
    """The published release age, gated by the calendar-derived active window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    published_at: AwareDatetime
    checked_at: AwareDatetime
    active_window: bool
    threshold_days: int = Field(default=STALE_DATA_THRESHOLD_DAYS, ge=0)

    @property
    def age(self) -> timedelta:
        return self.checked_at - self.published_at

    @property
    def ok(self) -> bool:
        return not self.active_window or self.age <= timedelta(days=self.threshold_days)


class ProductionCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: RouteCheckResult
    manifest_parse_error: str | None = None
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


def _check_line(result: RouteCheckResult) -> str:
    status = "PASS" if result.ok else "FAIL"
    check = result.check
    observed = result.observed
    if observed.error is not None:
        detail = f"request failed: {observed.error}"
    elif check.expected_location is not None:
        detail = (
            f"expected {check.expected_status} -> {check.expected_location}, "
            f"got {observed.status} -> {observed.location}"
        )
    else:
        detail = f"expected {check.expected_status}, got {observed.status}"
    return f"{status} {check.name} ({check.path}): {detail}"


def render_summary_lines(report: ProductionCheckReport) -> list[str]:
    """Human-readable per-check lines, for a CLI summary or an alert body."""
    lines = [_check_line(report.manifest)]
    if report.manifest_parse_error is not None:
        lines.append(f"FAIL deployment manifest ({MANIFEST_PATH}): {report.manifest_parse_error}")
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
        if not freshness.active_window:
            lines.append(
                "PASS published data freshness: outside the active election window; "
                f"published {freshness.published_at.isoformat()}"
            )
        else:
            status = "PASS" if freshness.ok else "FAIL"
            age_days = freshness.age.total_seconds() / 86_400
            lines.append(
                f"{status} published data freshness: {age_days:.1f} days old at "
                f"{freshness.checked_at.isoformat()} (maximum {freshness.threshold_days} days)"
            )
    return lines
