"""Explicit commands for recurring verification and Git-backed evidence custody."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from election_guide.collection.models import AccessFailureDiagnostic
from election_guide.collection.vault import read_key, restore_store, seal_store
from election_guide.collection.verification import plan_verification, read_policy
from election_guide.collection.verification_access import (
    InitialReviewEvidence,
    qualify_initial_review,
    record_manual_access_failure,
)
from election_guide.collection.verification_review import acknowledge_manual, approve_baseline
from election_guide.collection.verification_runtime import run_verification
from election_guide.collection.verification_state import validate_state
from election_guide.collection.verification_tasks import (
    reconcile_tasks,
    require_committed_state,
    task_sections,
)
from election_guide.serialization import read_json

app = typer.Typer(help="Check endorsement sources and retain public facts and observations in Git.")


@app.command("qualify-initial-review")
def qualify_review(
    election_root: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    evidence_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    recorded_by: Annotated[str, typer.Option(help="Actual qualification-recording actor.")],
    policy_path: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "config/verification.yaml"
    ),
) -> None:
    """Attest an already accepted COMPLETE review; normal repository review is required.

    This does not conduct or approve a source review, approve a collector baseline,
    or convert a generic manual acknowledgement into complete-publication evidence.
    """
    try:
        qualification = qualify_initial_review(
            read_policy(policy_path),
            election_root,
            InitialReviewEvidence.model_validate(read_json(evidence_path)),
            recorded_by,
        )
    except (OSError, ValueError, StopIteration) as error:
        typer.echo(f"Could not qualify initial review: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(qualification.model_dump_json())


@app.command("record-access-failure")
def access_failure(
    policy_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    election_id: Annotated[str, typer.Option()],
    source_id: Annotated[str, typer.Option()],
    scheduled_for: Annotated[str, typer.Option()],
    checked_at: Annotated[str, typer.Option()],
    reviewer: Annotated[str, typer.Option(help="Actual failed-attempt observer.")],
    evidence: Annotated[str, typer.Option(help="Durable actual failed-access reference.")],
    category: Annotated[str, typer.Option()],
    http_status: Annotated[int | None, typer.Option()] = None,
    state_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/verification"),
) -> None:
    """Record an observed manual access failure without fetching or claiming success."""
    try:
        policy = read_policy(policy_path)
        validate_state(policy, state_root)
        check = record_manual_access_failure(
            policy,
            state_root,
            election_id,
            source_id,
            date.fromisoformat(scheduled_for),
            datetime.fromisoformat(checked_at.replace("Z", "+00:00")),
            reviewer,
            evidence,
            AccessFailureDiagnostic.model_validate(
                {"category": category, "http_status": http_status}
            ),
        )
    except (OSError, ValueError, StopIteration) as error:
        typer.echo(f"Could not record failed access: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(check.model_dump_json())


@app.command("run")
def run(
    policy_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    checked_at: Annotated[str, typer.Option(help="Actual timezone-aware UTC check time.")],
    live: Annotated[
        bool, typer.Option(help="Explicitly permit bounded public HTTP fetches.")
    ] = False,
    fixtures: Annotated[Path | None, typer.Option(file_okay=False, exists=True)] = None,
    state_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/verification"),
) -> None:
    """Execute current due work without interpreting or approving endorsements."""
    try:
        policy = read_policy(policy_path)
        validate_state(policy, state_root)
        result = run_verification(
            policy,
            state_root,
            datetime.fromisoformat(checked_at.replace("Z", "+00:00")),
            live=live,
            fixtures=fixtures,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Could not run verification: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(result, indent=2))


@app.command("validate")
def validate(
    policy_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    state_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/verification"),
) -> None:
    """Verify policy and all committed archive links without exposing raw bytes."""
    try:
        count = validate_state(read_policy(policy_path), state_root)
    except (OSError, ValueError) as error:
        typer.echo(f"Invalid verification archive: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Verification policy and {count} archive records are valid.")


@app.command("reconcile")
def reconcile(
    policy_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    repository: Annotated[str, typer.Option()],
    revision: Annotated[str, typer.Option(help="Exact committed evidence revision.")],
    as_of: Annotated[str, typer.Option(help="Pacific date, YYYY-MM-DD.")],
    state_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/verification"),
    watch: Annotated[bool, typer.Option(help="Also report absent scheduled checks.")] = False,
    dry_run: Annotated[bool, typer.Option(help="Print tasks without GitHub mutation.")] = False,
) -> None:
    """Append immutable observations to one finite review task per election/day."""
    try:
        policy = read_policy(policy_path)
        validate_state(policy, state_root)
        sections = task_sections(
            policy, state_root, date.fromisoformat(as_of), repository, revision, watch=watch
        )
        if not dry_run:
            require_committed_state(state_root, revision)
        result = sections if dry_run else reconcile_tasks(sections, repository)
    except (OSError, ValueError) as error:
        typer.echo(f"Could not reconcile verification: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(result, indent=2))


@app.command("approve-baseline")
def approve(
    election_root: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    snapshot_id: Annotated[str, typer.Option()],
    reviewer: Annotated[str, typer.Option()],
    reviewed_at: Annotated[str, typer.Option()],
    evidence: Annotated[str, typer.Option(help="Durable human spot-check reference.")],
) -> None:
    """Record a human spot-check; commit this attestation through normal PR review."""
    try:
        approve_baseline(
            election_root,
            snapshot_id,
            reviewer,
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00")),
            evidence,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Could not approve baseline: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo("Human baseline attestation recorded; repository review is still required.")


@app.command("acknowledge-manual")
def acknowledge(
    election_root: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    source_id: Annotated[str, typer.Option()],
    scheduled_for: Annotated[str, typer.Option()],
    reviewer: Annotated[str, typer.Option()],
    reviewed_at: Annotated[str, typer.Option()],
    evidence: Annotated[str, typer.Option()],
) -> None:
    """Record completed human review against a finite manual obligation."""
    try:
        acknowledge_manual(
            election_root,
            source_id,
            date.fromisoformat(scheduled_for),
            reviewer,
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00")),
            evidence,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Could not acknowledge manual review: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo("Manual verification attestation recorded; commit it through repository review.")


@app.command("plan")
def plan(
    policy_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    as_of: Annotated[str, typer.Option(help="Pacific calendar date, YYYY-MM-DD.")],
    state_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/verification"),
) -> None:
    """Show all eligible sources, due work, and missing checks without mutation."""
    try:
        result = plan_verification(read_policy(policy_path), state_root, date.fromisoformat(as_of))
    except (OSError, ValueError) as error:
        typer.echo(f"Could not plan verification: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(result.model_dump_json(indent=2))


@app.command("seal")
def seal(
    storage_root: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    vault_root: Annotated[Path, typer.Argument(file_okay=False)],
) -> None:
    """Encrypt local content-addressed captures without printing their contents."""
    try:
        count = seal_store(storage_root, vault_root, read_key())
    except (OSError, ValueError) as error:
        typer.echo(f"Could not seal evidence: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Verified {count} encrypted captures.")


@app.command("restore")
def restore(
    vault_root: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    storage_root: Annotated[Path, typer.Argument(file_okay=False)],
) -> None:
    """Authenticate committed captures before restoring them for local review."""
    try:
        count = restore_store(vault_root, storage_root, read_key())
    except (OSError, ValueError) as error:
        typer.echo(f"Could not restore evidence: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Verified {count} restored captures.")
