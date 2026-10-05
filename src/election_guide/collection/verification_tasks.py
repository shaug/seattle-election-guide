"""Finite daily review tasks with immutable observation markers."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

from election_guide.calendar.github_tracker import GitHubIssueTracker
from election_guide.calendar.tracking import ISSUE_LABELS, IssueRequest
from election_guide.collection.refresh import read_refresh_event
from election_guide.collection.verification import (
    VerificationPolicy,
    baseline_reviewed,
    plan_verification,
    read_checks,
)
from election_guide.collection.verification_runtime import consecutive_failures
from election_guide.github_cli import ISSUE_QUERY_LIMIT, parse_issue_list, run_gh, trailing_line

TASK_PREFIX = "endorsement-verification:"
SECTION_PREFIX = "endorsement-observation:"


def require_committed_state(root: Path, revision: str) -> None:
    result = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--format=%(objectname) %(path)",
            revision,
            "--",
            "data/verification",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("evidence revision is not available in this checkout")
    committed = dict(line.split(" ", 1)[::-1] for line in result.stdout.splitlines())
    local: dict[str, str] = {}
    for path in root.rglob("*.json"):
        raw = path.read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        local[f"data/verification/{path.relative_to(root).as_posix()}"] = digest
    if committed != local:
        raise ValueError("task evidence must exactly match its committed Git revision")


def task_sections(
    policy: VerificationPolicy,
    root: Path,
    as_of: date,
    repository: str,
    revision: str,
    *,
    watch: bool,
) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository
    ):
        raise ValueError("task references require a repository and exact Git revision")
    sections: list[dict[str, Any]] = []
    for election in policy.elections:
        election_root = root / election.election_id
        checks = read_checks(election_root)
        overrides = {source.source_id: source for source in election.sources}
        for check in checks:
            if check.scheduled_for > as_of or check.status == "manual":
                continue
            relative = (election_root / "checks").relative_to(root)
            from election_guide.evidence.models import evidence_fingerprint

            identity = evidence_fingerprint(check.model_dump(mode="json"))
            marker = f"{SECTION_PREFIX} {election.election_id}/{check.source_id}/{identity}"
            if check.status == "missed":
                marker = (
                    f"{SECTION_PREFIX} {election.election_id}/{check.source_id}/"
                    f"missing-{check.scheduled_for}"
                )
            detail = (
                f"Status: **{check.status}**. Scheduled for {check.scheduled_for}; "
                f"checked at {check.checked_at.isoformat()}. Mode: {check.mode}."
            )
            escalated = False
            if check.event_id:
                event_path = election_root / "refreshes" / f"{check.event_id}.json"
                event = read_refresh_event(event_path)
                if (
                    event.source_id != check.source_id
                    or event.checked_at != check.checked_at
                    or event.status != check.status
                ):
                    raise ValueError("scheduled check contradicts its refresh event")
                reviewed = baseline_reviewed(election_root, event.snapshot_id)
                # Only identical bytes with an explicit human-approved snapshot
                # are quiet. Unknown/new wording and article edits always route.
                if event.status == "unchanged" and reviewed and check.mode == "live":
                    continue
                link = f"https://github.com/{repository}/blob/{revision}/data/verification/{election.election_id}/refreshes/{event.id}.json"
                detail += (
                    f"\n\n[Immutable refresh event]({link}). Capture: `{event.capture_id}`. "
                    f"Snapshot: `{event.snapshot_id or event.previous_snapshot_id}`."
                )
                if not reviewed and event.status != "failed":
                    detail += (
                        "\n\nHuman baseline spot-check required. Verify the entire official "
                        "publication and adapter mappings before approving this snapshot."
                    )
                if event.content_changed and not event.diff:
                    detail += (
                        "\n\nPublication bytes changed without a recognized decision change. "
                        "Review unrecognized wording, article content, and parser coverage."
                    )
                for diff in event.diff:
                    before = diff.before.candidate_ids if diff.before else []
                    after = diff.after.candidate_ids if diff.after else []
                    detail += f"\n- **{diff.kind}** `{diff.race_id}`: {before} → {after}"
                if any(diff.kind == "removed" for diff in event.diff):
                    detail += (
                        "\n\nRemoval requires official-source review to distinguish "
                        "withdrawal from parser failure."
                    )
                if event.error:
                    detail += f"\n\nFailure: {event.error}"
                escalated = (
                    consecutive_failures(election_root, check.source_id, check.scheduled_for) >= 3
                )
            elif check.status == "manual_due":
                if any(
                    item.status == "manual"
                    and item.source_id == check.source_id
                    and item.scheduled_for == check.scheduled_for
                    for item in checks
                ):
                    continue
                limitation = (
                    overrides[check.source_id].limitation
                    if check.source_id in overrides
                    else "Manual official-publication review required; no automatic adapter."
                )
                detail += (
                    f"\n\nManual review due {check.scheduled_for}. {limitation} "
                    "Record reviewer, actual review time, and durable official evidence."
                )
            elif check.status == "missed":
                escalated = (
                    consecutive_failures(election_root, check.source_id, check.scheduled_for) >= 3
                )
            if escalated:
                detail += (
                    "\n\n**Escalation: three consecutive scheduled failures or missing "
                    "checks. Diagnose access, scheduler, or parser changes before retrying.**"
                )
            observation_link = f"https://github.com/{repository}/blob/{revision}/data/verification/{relative}/{identity}.json"
            detail += (
                f"\n\n[Scheduled observation]({observation_link}). Resolve through "
                f"reviewed correction and release/publication evidence.\n\n{marker}"
            )
            sections.append(
                {
                    "election_id": election.election_id,
                    "day": check.scheduled_for.isoformat(),
                    "source_id": check.source_id,
                    "marker": marker,
                    "body": f"### {check.source_id}\n\n{detail}",
                    "escalated": escalated,
                }
            )
    if watch:
        plan = plan_verification(policy, root, as_of)
        for missed in plan.missed:
            # Persisted missed records above already have their own sections.
            if any(
                section["source_id"] == missed.source_id
                and section["election_id"] == missed.election_id
                and section["day"] == missed.scheduled_for.isoformat()
                for section in sections
            ):
                continue
            marker = (
                f"{SECTION_PREFIX} {missed.election_id}/{missed.source_id}/"
                f"missing-{missed.scheduled_for}"
            )
            source_misses = [
                item
                for item in plan.missed
                if item.source_id == missed.source_id and item.election_id == missed.election_id
            ]
            escalated = (
                consecutive_failures(
                    root / missed.election_id,
                    missed.source_id,
                    as_of,
                    {item.scheduled_for for item in source_misses},
                )
                >= 3
            )
            sections.append(
                {
                    "election_id": missed.election_id,
                    "day": missed.scheduled_for.isoformat(),
                    "source_id": missed.source_id,
                    "marker": marker,
                    "body": (
                        f"### {missed.source_id}\n\nScheduled check for {missed.scheduled_for} "
                        f"never appeared in committed state `{revision}`. Diagnose the source "
                        f"job or scheduler. Repeated-check escalation: {escalated}.\n\n{marker}"
                    ),
                    "escalated": escalated,
                }
            )
        # First activation has no invented history. If the source job has never
        # produced state, make today's failed startup visible to the watcher.
        for election in plan.elections:
            if not (root / election.election_id / "activation.json").exists():
                marker = f"{SECTION_PREFIX} {election.election_id}/startup/{as_of}"
                sections.append(
                    {
                        "election_id": election.election_id,
                        "day": as_of.isoformat(),
                        "source_id": "startup",
                        "marker": marker,
                        "body": (
                            "No verification activation or check records exist for the "
                            "current active window. Check workflow enablement, App permissions, "
                            "and evidence key. Current obligations need execution; no historical "
                            f"checks are claimed.\n\n{marker}"
                        ),
                        "escalated": False,
                    }
                )
    return sections


def _body_command(command: list[str], body: str) -> str:
    with tempfile.TemporaryDirectory(prefix="verification-task-") as directory:
        path = Path(directory) / "body.md"
        path.write_text(body)
        return run_gh([*command, "--body-file", str(path)], "could not reconcile verification task")


def reconcile_tasks(sections: list[dict[str, Any]], repository: str) -> list[str]:
    """The workflows share one concurrency group around read/create/append."""
    payload = run_gh(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--limit",
            str(ISSUE_QUERY_LIMIT),
            "--json",
            "number,body,state",
        ],
        "could not read verification tasks",
    )
    issues = parse_issue_list(payload)
    if len(issues) >= ISSUE_QUERY_LIMIT:
        raise ValueError("verification task listing reached its completeness bound")
    tasks: dict[str, list[dict[str, Any]]] = {}
    markers: set[str] = set()
    for issue in issues:
        marker = trailing_line(str(issue.get("body", "")))
        if not marker.startswith(TASK_PREFIX):
            continue
        tasks.setdefault(marker, []).append(issue)
        comments = cast(
            dict[str, Any],
            json.loads(
                run_gh(
                    [
                        "gh",
                        "issue",
                        "view",
                        str(issue["number"]),
                        "--repo",
                        repository,
                        "--json",
                        "comments",
                    ],
                    "could not read verification task observations",
                )
            ),
        )
        for comment in comments["comments"]:
            markers.add(trailing_line(comment["body"]))
    touched: list[str] = []
    tracker = GitHubIssueTracker(repository)
    for section in sections:
        if section["marker"] in markers:
            continue
        if section["source_id"] == "startup":
            prefix = f"{SECTION_PREFIX} {section['election_id']}/startup/"
            today = date.fromisoformat(section["day"])
            observed = markers | {section["marker"]}
            if all(f"{prefix}{today - timedelta(days=offset)}" in observed for offset in range(3)):
                section["escalated"] = True
                section["body"] = section["body"].removesuffix(section["marker"]) + (
                    "Escalation: three observed days without verification startup. "
                    f"Restore the workflow and its evidence key.\n\n{section['marker']}"
                )
        marker = f"{TASK_PREFIX} {section['election_id']}/{section['day']}"
        existing = tasks.get(marker, [])
        if len(existing) > 1:
            raise ValueError(
                "duplicate daily verification task markers require operator reconciliation"
            )
        if existing:
            number = str(existing[0]["number"])
            if existing[0]["state"] == "CLOSED":
                run_gh(
                    ["gh", "issue", "reopen", number, "--repo", repository],
                    "could not reopen daily verification task",
                )
                existing[0]["state"] = "OPEN"
        else:
            tracker.ensure_milestone(section["election_id"])
            request = IssueRequest(
                marker=marker,
                title=f"{section['election_id']}: endorsement verification {section['day']}",
                body=(
                    "Review the source observations in this day's comments. Detection does not "
                    f"approve ledger changes or publication.\n\nRefs #497\n\n{marker}"
                ),
                labels=(*ISSUE_LABELS, "data: endorsements"),
                milestone=section["election_id"],
            )
            # A structured body file avoids losing newlines or interpreting data.
            command = [
                "gh",
                "issue",
                "create",
                "--repo",
                repository,
                "--title",
                request.title,
                "--milestone",
                request.milestone,
            ]
            for label in request.labels:
                command.extend(["--label", label])
            url = _body_command(command, request.body).strip()
            number = url.rsplit("/", 1)[-1]
            if not number.isdigit():
                raise ValueError("GitHub returned no created issue identity")
            tasks[marker] = [{"number": int(number), "state": "OPEN"}]
        if section["escalated"]:
            run_gh(
                [
                    "gh",
                    "issue",
                    "edit",
                    number,
                    "--repo",
                    repository,
                    "--add-label",
                    "priority: high",
                ],
                "could not escalate repeated verification failures",
            )
        _body_command(["gh", "issue", "comment", number, "--repo", repository], section["body"])
        markers.add(section["marker"])
        touched.append(f"https://github.com/{repository}/issues/{number}")
    return sorted(set(touched))
