"""Command-line entry point for the election guide pipeline."""

import hashlib
import importlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from pydantic import ValidationError

from election_guide import __version__
from election_guide.collection import read_adapter_spec, refresh_source, validate_adapter
from election_guide.collection.http import fetch_http
from election_guide.collection.refresh import RefreshOrderError, record_refresh_failure
from election_guide.evidence.manual import (
    import_manual_draft,
    read_manual_draft,
    validate_manual_draft,
)
from election_guide.evidence.models import CaptureRequest, UnavailableRequest
from election_guide.evidence.storage import (
    read_capture_manifest,
    record_capture,
    record_unavailable,
    verify_capture,
)
from election_guide.initialization import initialize_election, read_election_configuration
from election_guide.inventory.importer import (
    extract_public_inputs,
    import_inventory,
    read_inventory,
    write_inventory,
)
from election_guide.inventory.initialized import (
    import_initialized_inventory,
    write_initialized_inventory,
)
from election_guide.normalization.matching import normalize_claim
from election_guide.normalization.models import (
    CanonicalDataset,
    ExtractedClaim,
    NormalizedEndorsement,
    OverrideRecord,
    ReviewDecision,
    ReviewItem,
    equal_allocation,
)
from election_guide.normalization.records import (
    list_records,
    list_review_decisions,
    list_review_items,
    new_override,
    new_review_decision,
    read_record,
    unresolved_review_items,
    write_record,
    write_review_decision,
    write_review_item,
)
from election_guide.publication import build_publication_bundle, write_publication_bundle
from election_guide.release import (
    build_release,
    compile_release_dataset,
    verify_release_compilation,
)
from election_guide.rendering import build_rendered_guide
from election_guide.scoring import (
    ConsensusReport,
    PublicationBlockedError,
    read_scoring_configuration,
    score_dataset,
)
from election_guide.serialization import canonical_json_bytes, read_json
from election_guide.sources.registry import read_source_registry, validate_registry_inventory
from election_guide.sources.report import render_discovery_report

app = typer.Typer(
    help="Build and audit the Seattle election endorsement consensus guide.",
    no_args_is_help=True,
)
inventory_app = typer.Typer(help="Import and validate the official Seattle ballot inventory.")
election_app = typer.Typer(help="Initialize and validate configuration for an election.")
sources_app = typer.Typer(help="Inspect and validate the frozen endorsement-source panel.")
evidence_app = typer.Typer(help="Capture, verify, and manually transcribe source evidence.")
manual_app = typer.Typer(help="Validate and import structured manual transcriptions.")
normalize_app = typer.Typer(help="Match and validate canonical endorsement records.")
review_app = typer.Typer(help="Inspect and resolve ambiguous normalization records.")
export_app = typer.Typer(help="Generate canonical machine-readable publication artifacts.")
render_app = typer.Typer(help="Render and validate the responsive HTML and concise PDF guide.")
release_app = typer.Typer(help="Compile, audit, and package a versioned public release.")
collect_app = typer.Typer(help="Refresh source-specific endorsement adapters.")
app.add_typer(inventory_app, name="inventory")
app.add_typer(election_app, name="election")
app.add_typer(sources_app, name="sources")
app.add_typer(evidence_app, name="evidence")
app.add_typer(normalize_app, name="normalize")
app.add_typer(review_app, name="review")
app.add_typer(export_app, name="export")
app.add_typer(render_app, name="render")
app.add_typer(release_app, name="release")
app.add_typer(collect_app, name="collect")
evidence_app.add_typer(manual_app, name="manual")


@election_app.command("init")
def election_init(
    seed_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output_path: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Create deterministic election configuration from an offline seed."""
    try:
        configuration, created = initialize_election(seed_path, output_path)
    except (OSError, ValueError) as error:
        typer.echo(f"election initialization failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    status = "created" if created else "unchanged"
    typer.echo(
        f"election configuration: {status} ({configuration.election.id}; "
        f"{len(configuration.jurisdictions)} jurisdictions, "
        f"{len(configuration.races)} declared races) -> {output_path}"
    )


@election_app.command("validate")
def election_validate(
    configuration_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate an initialized election configuration."""
    try:
        configuration = read_election_configuration(configuration_path)
    except ValueError as error:
        typer.echo(f"election configuration invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"election configuration: valid ({configuration.election.id}; "
        f"source panel {configuration.source_panel.id}@{configuration.source_panel.version}; "
        f"scoring {configuration.scoring_policy.id}@{configuration.scoring_policy.version})"
    )


@collect_app.command("refresh")
def collect_refresh(
    adapter_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    checked_at: Annotated[str, typer.Option(help="Deterministic ISO 8601 refresh time.")],
    input_path: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Offline artifact."),
    ] = None,
    live: Annotated[
        bool, typer.Option(help="Fetch the registered public URL; never enabled implicitly.")
    ] = False,
    media_type: Annotated[str | None, typer.Option(help="Required for offline artifacts.")] = None,
    title: Annotated[str | None, typer.Option()] = None,
    ocr_text_path: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = None,
    ocr_confidence: Annotated[str | None, typer.Option()] = None,
    inventory_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    storage_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/snapshots"),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
    extraction_dir: Annotated[Path, typer.Option(file_okay=False)] = Path(
        "data/collection/extractions"
    ),
    refresh_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/collection/refreshes"),
) -> None:
    """Create an immutable capture and semantic diff, or record an explicit failure."""
    timestamp: datetime | None = None
    spec = None
    try:
        if live == (input_path is not None):
            raise ValueError("choose exactly one of --live or --input-path")
        timestamp = _parse_aware_datetime(checked_at)
        spec = read_adapter_spec(adapter_path)
        inventory = read_inventory(inventory_path)
        registry = read_source_registry(registry_path)
        validate_registry_inventory(registry, inventory)
        validate_adapter(spec, inventory, registry)
        source = next(item for item in registry.sources if item.id == spec.source_id)
        if live and spec.adapter_kind == "dynamic_html":
            raise ValueError(
                "dynamic HTML live refresh requires a reviewed final-DOM artifact via --input-path"
            )

        temporary_path: Path | None = None
        if live:
            artifact = fetch_http(source.discovery.requested_url)
            with tempfile.NamedTemporaryFile(prefix="election-guide-", delete=False) as temporary:
                temporary.write(artifact.content)
                temporary.flush()
            temporary_path = Path(temporary.name)
            selected_path = temporary_path
            selected_media_type = artifact.media_type
            canonical_url = artifact.canonical_url
            redirect_chain = artifact.redirect_chain
            http_status = artifact.status
        else:
            if input_path is None or media_type is None:
                raise ValueError("offline refresh requires --input-path and --media-type")
            selected_path = input_path
            selected_media_type = media_type
            canonical_url = source.discovery.canonical_url or source.discovery.requested_url
            redirect_chain = []
            http_status = None

        try:
            request = CaptureRequest.model_validate(
                {
                    "source_id": spec.source_id,
                    "requested_url": (source.discovery.requested_url if live else canonical_url),
                    "canonical_url": canonical_url,
                    "redirect_chain": redirect_chain,
                    "retrieved_at": timestamp,
                    "http_status": http_status,
                    "media_type": selected_media_type,
                    "title": title or source.name,
                    "published_at": source.discovery.published_at,
                    "updated_at": source.discovery.updated_at,
                    "browser_required": spec.adapter_kind == "dynamic_html",
                    "redistribution": "restricted",
                    "redistribution_note": (
                        "Raw source retained locally for audit; not redistributed."
                    ),
                    "capture_method": {
                        "static_html": "static_html",
                        "dynamic_html": "browser",
                        "pdf": "pdf",
                        "image": "image",
                    }[spec.adapter_kind]
                    if live
                    else "manual_upload",
                }
            )
            event = refresh_source(
                spec,
                request,
                selected_path,
                storage_root=storage_root,
                manifest_dir=manifest_dir,
                extraction_dir=extraction_dir,
                refresh_dir=refresh_dir,
                ocr_text=(
                    ocr_text_path.read_text(encoding="utf-8") if ocr_text_path is not None else None
                ),
                ocr_confidence=ocr_confidence,
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        if isinstance(error, RefreshOrderError):
            typer.echo(f"source refresh failed: {error}", err=True)
        elif spec is not None and timestamp is not None:
            try:
                event = record_refresh_failure(
                    spec.source_id,
                    timestamp,
                    str(error),
                    refresh_dir,
                    extraction_dir=extraction_dir,
                )
            except RefreshOrderError as order_error:
                typer.echo(
                    f"source refresh failed: {error}; failure event not appended: {order_error}",
                    err=True,
                )
            else:
                typer.echo(f"source refresh failed: {event.id}: {event.error}", err=True)
        else:
            typer.echo(f"source refresh failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"source refresh: {event.status} ({event.id}, {len(event.diff)} semantic changes)")
    if event.status == "failed":
        typer.echo(f"source refresh error: {event.error}", err=True)
        raise typer.Exit(code=1)


@release_app.command("compile")
def release_compile(
    ledger_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    inventory_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    output_path: Annotated[Path, typer.Option(dir_okay=False)] = Path(
        "data/normalized/canonical-dataset.json"
    ),
    snapshot_root: Annotated[Path, typer.Option(file_okay=False)] = Path(
        "data/releases/wa-2026-primary/snapshots"
    ),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path(
        "data/releases/wa-2026-primary/manifests"
    ),
) -> None:
    """Compile audited source decisions into permitted snapshots and canonical data."""
    try:
        dataset = compile_release_dataset(
            ledger_path,
            inventory_path,
            registry_path,
            output_path,
            snapshot_root,
            manifest_dir,
        )
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"release compilation failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"release dataset: {output_path} "
        f"({len(dataset.captures)} sources, {len(dataset.endorsements)} decisions)"
    )


@release_app.command("build")
def release_build(
    ledger_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    release_version: Annotated[str, typer.Option()],
    generated_at: Annotated[str, typer.Option(help="Deterministic ISO 8601 build timestamp.")],
    inventory_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    dataset_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data/normalized/canonical-dataset.json"
    ),
    scoring_config_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("config/scoring/default.yaml"),
    rendering_config_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("config/rendering/pdf.yaml"),
    snapshot_root: Annotated[Path, typer.Option(file_okay=False, readable=True)] = Path(
        "data/releases/wa-2026-primary/snapshots"
    ),
    manifest_dir: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)] = Path(
        "data/releases/wa-2026-primary/manifests"
    ),
    output_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("dist/primary-release"),
    git_commit: Annotated[
        str | None, typer.Option(help="Code revision recorded in release manifests.")
    ] = None,
    chrome_path: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = None,
    pdftoppm_path: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = None,
) -> None:
    """Run scoring, export, rendering, final audit, and deterministic packaging."""
    try:
        result = build_release(
            ledger_path=ledger_path,
            inventory_path=inventory_path,
            registry_path=registry_path,
            dataset_path=dataset_path,
            scoring_config_path=scoring_config_path,
            rendering_config_path=rendering_config_path,
            snapshot_root=snapshot_root,
            manifest_dir=manifest_dir,
            output_dir=output_dir,
            release_version=release_version,
            generated_at=_parse_aware_datetime(generated_at),
            git_commit=git_commit or _git_commit(),
            chrome_path=chrome_path,
            pdftoppm_path=pdftoppm_path,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        ValidationError,
        ValueError,
    ) as error:
        typer.echo(f"release build failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"release: {result.archive_path} "
        f"({result.status.displayed_endorsement_count} source decisions)"
    )


@release_app.command("verify")
def release_verify(
    ledger_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    inventory_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    dataset_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "data/normalized/canonical-dataset.json"
    ),
    snapshot_root: Annotated[
        Path, typer.Option(exists=True, file_okay=False, readable=True)
    ] = Path("data/releases/wa-2026-primary/snapshots"),
    manifest_dir: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)] = Path(
        "data/releases/wa-2026-primary/manifests"
    ),
) -> None:
    """Recompile and byte-compare every tracked canonical release input."""
    try:
        dataset = verify_release_compilation(
            ledger_path,
            inventory_path,
            registry_path,
            dataset_path,
            snapshot_root,
            manifest_dir,
        )
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"release verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"release inputs: reproducible "
        f"({len(dataset.captures)} sources, {len(dataset.endorsements)} decisions)"
    )


@app.command()
def version() -> None:
    """Print the installed package version."""
    typer.echo(__version__)


@app.command()
def doctor(
    project_root: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Repository root to inspect.",
        ),
    ] = None,
) -> None:
    """Check that the foundational project configuration exists."""
    root = (project_root or Path.cwd()).resolve()
    required_paths = (
        Path("PROJECT.md"),
        Path("DECISIONS.md"),
        Path("config/elections/wa-2026-primary.yaml"),
        Path("config/scoring/default.yaml"),
        Path("config/sources/default.yaml"),
    )
    missing = [path for path in required_paths if not (root / path).is_file()]
    if missing:
        for path in missing:
            typer.echo(f"missing: {path}", err=True)
        raise typer.Exit(code=1)
    typer.echo("foundation: ok")


@app.command("score")
def score(
    dataset_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data/normalized/canonical-dataset.json"),
    config: Annotated[
        str,
        typer.Option(help="Scoring configuration name or YAML path."),
    ] = "default",
    output_path: Annotated[
        Path,
        typer.Option(dir_okay=False),
    ] = Path("data/normalized/consensus.json"),
    computed_at: Annotated[
        str | None,
        typer.Option(help="Deterministic ISO 8601 build timestamp."),
    ] = None,
    allow_unresolved: Annotated[
        bool,
        typer.Option(help="Publish with a visible warning despite high-severity review work."),
    ] = False,
) -> None:
    """Compute exact consensus results from a canonical dataset."""
    try:
        timestamp = _score_timestamp(computed_at)
        configuration_path = (
            Path("config/scoring/default.yaml") if config == "default" else Path(config)
        )
        configuration = read_scoring_configuration(configuration_path)
        dataset = CanonicalDataset.model_validate(read_json(dataset_path))
        report = score_dataset(
            dataset,
            configuration,
            computed_at=timestamp,
            allow_unresolved=allow_unresolved,
        )
        _write_generated_json(output_path, report.model_dump(mode="json"))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        PublicationBlockedError,
        ValueError,
    ) as error:
        typer.echo(f"scoring failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"consensus: {output_path} ({len(report.races)} races)")


@export_app.command("build")
def export_build(
    dataset_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data/normalized/canonical-dataset.json"),
    consensus_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data/normalized/consensus.json"),
    output_dir: Annotated[
        Path,
        typer.Option(file_okay=False),
    ] = Path("build"),
    snapshot_root: Annotated[
        Path,
        typer.Option(file_okay=False, readable=True),
    ] = Path("data/snapshots"),
    git_commit: Annotated[
        str | None,
        typer.Option(help="Code revision recorded in the build manifest."),
    ] = None,
) -> None:
    """Generate deterministic exports and the shared publication view model."""
    try:
        dataset = CanonicalDataset.model_validate(read_json(dataset_path))
        consensus = ConsensusReport.model_validate(
            read_json(consensus_path),
            context={"canonical_dataset": dataset},
        )
        bundle = build_publication_bundle(
            dataset,
            consensus,
            git_commit=git_commit or _git_commit(),
            snapshot_root=snapshot_root,
        )
        outputs = write_publication_bundle(bundle, output_dir)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        ValidationError,
        ValueError,
    ) as error:
        typer.echo(f"publication export failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"publication exports: {output_dir} ({len(outputs)} artifacts)")


@render_app.command("build")
def render_build(
    view_model_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("build/publication_view_model.json"),
    config_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("config/rendering/pdf.yaml"),
    output_dir: Annotated[
        Path,
        typer.Option(file_okay=False),
    ] = Path("output/rendered"),
    chrome_path: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = None,
    pdftoppm_path: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = None,
) -> None:
    """Build responsive HTML, a two-page PDF, and rendered visual checks."""
    try:
        rendered = build_rendered_guide(
            view_model_path,
            config_path,
            output_dir,
            chrome_path=chrome_path,
            pdftoppm_path=pdftoppm_path,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        ValidationError,
        ValueError,
    ) as error:
        typer.echo(f"guide rendering failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    outputs = f"{rendered.html_path} and {rendered.pdf_path}"
    if rendered.detailed_pdf_path is not None:
        outputs = f"{outputs}, with detailed fallback {rendered.detailed_pdf_path}"
    typer.echo(
        f"rendered guide: {outputs} "
        f"({rendered.validation_report.edition}, "
        f"{rendered.validation_report.page_count} concise pages)"
    )


@evidence_app.command("capture")
def evidence_capture(
    input_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    source_id: Annotated[str, typer.Option()],
    requested_url: Annotated[str, typer.Option()],
    canonical_url: Annotated[str, typer.Option()],
    retrieved_at: Annotated[str, typer.Option()],
    media_type: Annotated[str, typer.Option()],
    title: Annotated[str, typer.Option()],
    capture_method: Annotated[str, typer.Option()],
    redistribution: Annotated[str, typer.Option()],
    redistribution_note: Annotated[str, typer.Option()],
    http_status: Annotated[int | None, typer.Option()] = None,
    redirect_url: Annotated[list[str] | None, typer.Option("--redirect-url")] = None,
    published_at: Annotated[str | None, typer.Option()] = None,
    updated_at: Annotated[str | None, typer.Option()] = None,
    browser_required: Annotated[bool, typer.Option()] = False,
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    storage_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/snapshots"),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
) -> None:
    """Ingest a local artifact into immutable content-addressed storage."""
    try:
        _require_registered_source(source_id, registry_path)
        request = CaptureRequest.model_validate(
            {
                "source_id": source_id,
                "requested_url": requested_url,
                "canonical_url": canonical_url,
                "redirect_chain": redirect_url or [],
                "retrieved_at": retrieved_at,
                "http_status": http_status,
                "media_type": media_type,
                "title": title,
                "published_at": published_at,
                "updated_at": updated_at,
                "capture_method": capture_method,
                "browser_required": browser_required,
                "redistribution": redistribution,
                "redistribution_note": redistribution_note,
            }
        )
        output = record_capture(request, input_path, storage_root, manifest_dir)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"evidence capture failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"evidence capture: {output}")


@evidence_app.command("unavailable")
def evidence_unavailable(
    source_id: Annotated[str, typer.Option()],
    requested_url: Annotated[str, typer.Option()],
    retrieved_at: Annotated[str, typer.Option()],
    unavailable_reason: Annotated[str, typer.Option()],
    redistribution_note: Annotated[str, typer.Option()],
    canonical_url: Annotated[str | None, typer.Option()] = None,
    http_status: Annotated[int | None, typer.Option()] = None,
    media_type: Annotated[str | None, typer.Option()] = None,
    title: Annotated[str | None, typer.Option()] = None,
    redirect_url: Annotated[list[str] | None, typer.Option("--redirect-url")] = None,
    browser_required: Annotated[bool, typer.Option()] = False,
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
) -> None:
    """Record a source that could not be captured without bypassing access controls."""
    try:
        _require_registered_source(source_id, registry_path)
        request = UnavailableRequest.model_validate(
            {
                "source_id": source_id,
                "requested_url": requested_url,
                "canonical_url": canonical_url,
                "redirect_chain": redirect_url or [],
                "retrieved_at": retrieved_at,
                "http_status": http_status,
                "media_type": media_type,
                "title": title,
                "capture_method": "unavailable",
                "browser_required": browser_required,
                "redistribution": "restricted",
                "redistribution_note": redistribution_note,
                "unavailable_reason": unavailable_reason,
            }
        )
        output = record_unavailable(request, manifest_dir)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"unavailable evidence record failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"unavailable evidence: {output}")


@evidence_app.command("verify")
def evidence_verify(
    manifest_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    storage_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/snapshots"),
) -> None:
    """Verify captured evidence bytes against an immutable manifest."""
    try:
        manifest = read_capture_manifest(manifest_path)
        verify_capture(manifest, storage_root)
    except (OSError, ValueError) as error:
        typer.echo(f"evidence verification failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"evidence: valid ({manifest.id}, {manifest.availability})")


@manual_app.command("validate")
def manual_validate(
    draft_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    storage_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/snapshots"),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
) -> None:
    """Validate a manual transcription and its captured evidence reference."""
    try:
        draft = read_manual_draft(draft_path)
        _require_registered_source(draft.source_id, registry_path)
        entry = validate_manual_draft(draft, manifest_dir, storage_root)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"manual entry invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"manual entry: valid ({entry.id}, {entry.review_status})")


@manual_app.command("import")
def manual_import(
    draft_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    storage_root: Annotated[Path, typer.Option(file_okay=False)] = Path("data/snapshots"),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
    output_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/manual"),
) -> None:
    """Import a validated manual transcription as immutable canonical JSON."""
    try:
        draft = read_manual_draft(draft_path)
        _require_registered_source(draft.source_id, registry_path)
        output = import_manual_draft(draft, manifest_dir, storage_root, output_dir)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"manual entry import failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"manual entry: {output}")


@sources_app.command("validate")
def sources_validate(
    registry_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ] = Path("config/sources/default.yaml"),
    inventory_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
) -> None:
    """Validate panel roles, discovery state, eligibility, and overlap metadata."""
    try:
        registry = read_source_registry(registry_path)
        inventory = read_inventory(inventory_path)
        validate_registry_inventory(registry, inventory)
    except ValueError as error:
        typer.echo(f"source registry invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    role_counts = {
        role: sum(source.panel_role == role for source in registry.sources)
        for role in ("consensus", "comparison", "excluded")
    }
    typer.echo(
        f"source registry: valid ({len(registry.sources)} proposed; "
        f"{role_counts['consensus']} consensus, {role_counts['comparison']} comparison, "
        f"{role_counts['excluded']} excluded)"
    )


@sources_app.command("report")
def sources_report(
    registry_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("config/sources/default.yaml"),
    output: Annotated[Path, typer.Option(dir_okay=False)] = Path("docs/SOURCE_DISCOVERY.md"),
    inventory_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
) -> None:
    """Render the human-readable discovery report from the frozen registry."""
    try:
        registry = read_source_registry(registry_path)
        inventory = read_inventory(inventory_path)
        validate_registry_inventory(registry, inventory)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_discovery_report(registry), encoding="utf-8")
    except (OSError, ValueError) as error:
        typer.echo(f"source report failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"source report: {len(registry.sources)} proposed sources -> {output}")


@inventory_app.command("import")
def inventory_import(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    candidates: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    pco_democrats: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    pco_republicans: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    precinct_crosswalk: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option(dir_okay=False)] = Path(
        "data/normalized/wa-2026-primary-inventory.json"
    ),
) -> None:
    """Import captured King County files after verifying their hashes."""
    try:
        inventory = import_inventory(
            config,
            {
                "candidates": candidates,
                "pco_democrats": pco_democrats,
                "pco_republicans": pco_republicans,
                "precinct_crosswalk": precinct_crosswalk,
            },
        )
        write_inventory(inventory, output)
    except ValueError as error:
        typer.echo(f"inventory import failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"inventory: {len(inventory.races)} races, "
        f"{sum(len(race.choices) for race in inventory.races)} choices -> {output}"
    )


@inventory_app.command("import-initialized")
def inventory_import_initialized(
    configuration_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    manifest_path: Annotated[
        Path, typer.Option("--manifest", exists=True, dir_okay=False, readable=True)
    ],
    ballot_path: Annotated[
        Path, typer.Option("--ballot-choices", exists=True, dir_okay=False, readable=True)
    ],
    output: Annotated[Path, typer.Option(dir_okay=False)] = Path(
        "data/normalized/initialized-election-inventory.json"
    ),
) -> None:
    """Materialize initialized IDs from hash-verified canonical offline ballot rows."""
    try:
        inventory = import_initialized_inventory(
            configuration_path,
            manifest_path,
            ballot_path,
        )
        created = write_initialized_inventory(inventory, output)
    except (OSError, UnicodeError, ValueError) as error:
        typer.echo(f"initialized inventory import failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    status = "created" if created else "unchanged"
    typer.echo(
        f"initialized inventory: {status} ({len(inventory.races)} races, "
        f"{sum(len(race.choices) for race in inventory.races)} choices) -> {output}"
    )


@inventory_app.command("extract")
def inventory_extract(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    candidates: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    pco_democrats: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    pco_republicans: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    output_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/extracted/official"),
) -> None:
    """Write privacy-stripped extracts from hash-verified official CSVs."""
    try:
        outputs = extract_public_inputs(
            config,
            {
                "candidates": candidates,
                "pco_democrats": pco_democrats,
                "pco_republicans": pco_republicans,
            },
            output_dir,
        )
    except ValueError as error:
        typer.echo(f"inventory extract failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    for output in outputs:
        typer.echo(f"extracted: {output}")


@inventory_app.command("validate")
def inventory_validate(
    inventory_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
) -> None:
    """Validate canonical IDs, provenance, hierarchy, and race membership."""
    try:
        inventory = read_inventory(inventory_path)
    except ValueError as error:
        typer.echo(f"inventory invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"inventory: valid ({len(inventory.races)} races, "
        f"{sum(len(race.choices) for race in inventory.races)} choices)"
    )


@normalize_app.command("validate")
def normalize_validate(
    dataset_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a complete canonical dataset and all cross-record references."""
    try:
        dataset = CanonicalDataset.model_validate(read_json(dataset_path))
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        typer.echo(f"canonical dataset invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"canonical dataset: valid ({len(dataset.claims)} claims, "
        f"{len(dataset.endorsements)} endorsements, "
        f"{len(dataset.review_items)} review items)"
    )


@normalize_app.command("match")
def normalize_match(
    claim_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    created_at: Annotated[str, typer.Option(help="Review timestamp in ISO 8601 format.")],
    inventory_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
    queue_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/queue"),
    output_dir: Annotated[Path, typer.Option(file_okay=False)] = Path(
        "data/normalized/endorsements"
    ),
) -> None:
    """Normalize one extracted claim, queuing any ambiguity instead of guessing."""
    try:
        claim = read_record(claim_path, ExtractedClaim)
        inventory = read_inventory(inventory_path)
        registry = read_source_registry(registry_path)
        validate_registry_inventory(registry, inventory)
        capture = read_capture_manifest(manifest_dir / f"{claim.capture_id}.json")
        normalization = normalize_claim(
            claim,
            inventory,
            capture,
            created_at=_parse_aware_datetime(created_at),
            source_registry=registry,
        )
        if normalization.match.review_item is not None:
            output = write_review_item(normalization.match.review_item, queue_dir)
            typer.echo(f"normalization review queued: {output}")
            return
        if normalization.endorsement is None:
            raise ValueError("claim produced neither an endorsement nor a review item")
        output = write_record(normalization.endorsement, output_dir)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"claim normalization failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"normalized endorsement: {output}")


@review_app.command("list")
def review_list(
    queue_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/queue"),
    decisions_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/decisions"),
) -> None:
    """List unresolved review items in stable record-ID order."""
    try:
        items = unresolved_review_items(queue_dir, decisions_dir)
    except ValueError as error:
        typer.echo(f"review queue invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    if not items:
        typer.echo("review queue: empty")
        return
    for item in items:
        typer.echo(f"{item.id}\t{item.severity}\t{item.reason}\t{item.summary}")


@review_app.command("show")
def review_show(
    record_id: Annotated[str, typer.Argument()],
    queue_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/queue"),
) -> None:
    """Show one review record, including evidence and competing matches."""
    try:
        item = _read_review_item(record_id, queue_dir)
    except ValueError as error:
        typer.echo(f"review item invalid: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(canonical_json_bytes(item.model_dump(mode="json")).decode(), nl=False)


@review_app.command("approve")
def review_approve(
    record_id: Annotated[str, typer.Argument()],
    author: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option()],
    evidence: Annotated[str, typer.Option()],
    created_at: Annotated[str, typer.Option(help="Decision timestamp in ISO 8601 format.")],
    race_id: Annotated[str, typer.Option(help="Authoritative race selected by the reviewer.")],
    status: Annotated[str, typer.Option(help="Resolved canonical endorsement status.")],
    claim_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Extracted claim JSON."),
    ],
    candidate_id: Annotated[list[str] | None, typer.Option("--candidate-id")] = None,
    inventory_path: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("data/normalized/wa-2026-primary-inventory.json"),
    registry_path: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)] = Path(
        "config/sources/default.yaml"
    ),
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
    queue_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/queue"),
    decisions_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/decisions"),
) -> None:
    """Append an approval for one unresolved review item."""
    _record_review_decision(
        record_id,
        "approve",
        author,
        reason,
        evidence,
        created_at,
        queue_dir,
        decisions_dir,
        resolution={
            "race_id": race_id,
            "status": status,
            "candidate_ids": candidate_id or [],
        },
        approval_context=(claim_path, inventory_path, registry_path, manifest_dir),
    )


@review_app.command("reject")
def review_reject(
    record_id: Annotated[str, typer.Argument()],
    author: Annotated[str, typer.Option()],
    reason: Annotated[str, typer.Option()],
    evidence: Annotated[str, typer.Option()],
    created_at: Annotated[str, typer.Option(help="Decision timestamp in ISO 8601 format.")],
    queue_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/queue"),
    decisions_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/review/decisions"),
) -> None:
    """Append a rejection for one unresolved review item."""
    _record_review_decision(
        record_id,
        "reject",
        author,
        reason,
        evidence,
        created_at,
        queue_dir,
        decisions_dir,
        resolution=None,
        approval_context=None,
    )


@review_app.command("override")
def review_override(
    target_record_id: Annotated[str, typer.Argument()],
    field: Annotated[str, typer.Option()],
    old_value: Annotated[str, typer.Option(help="Previous value encoded as JSON.")],
    new_value: Annotated[str, typer.Option(help="Replacement value encoded as JSON.")],
    reason: Annotated[str, typer.Option()],
    evidence: Annotated[str, typer.Option()],
    author: Annotated[str, typer.Option()],
    created_at: Annotated[str, typer.Option(help="Override timestamp in ISO 8601 format.")],
    target_path: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True, help="Canonical target JSON."),
    ],
    manifest_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/manifests/evidence"),
    overrides_dir: Annotated[Path, typer.Option(file_okay=False)] = Path("data/overrides"),
) -> None:
    """Append an explicit field override with complete audit metadata."""
    try:
        target_record = _read_override_target(target_path, target_record_id)
        target = target_record.model_dump(mode="json")
        parsed_old_value = _parse_json_value(old_value)
        parsed_new_value = _parse_json_value(new_value)
        override_time = _parse_aware_datetime(created_at)
        if override_time < _override_lower_bound(target_record, manifest_dir):
            raise ValueError("override timestamp cannot predate its canonical target")
        with _locked_override_field(overrides_dir, target_record_id, field):
            existing = list_records(overrides_dir, OverrideRecord)
            related = [
                item
                for item in existing
                if item.target_record_id == target_record_id and item.field == field
            ]
            if related and override_time <= max(item.created_at for item in related):
                raise ValueError("override timestamp must be later than the current chain head")
            current_value = _current_override_value(
                target,
                target_record_id,
                field,
                existing,
            )
            if current_value != parsed_old_value:
                raise ValueError("override old value does not match the target's current value")
            record = new_override(
                target_record_id=target_record_id,
                field=field,
                old_value=parsed_old_value,
                new_value=parsed_new_value,
                reason=reason,
                evidence=evidence,
                author=author,
                created_at=override_time,
            )
            _validate_projected_override(target_record, existing, record)
            output = write_record(record, overrides_dir)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"review override failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"review override: {output}")


def _require_registered_source(source_id: str, registry_path: Path) -> None:
    registry = read_source_registry(registry_path)
    if source_id not in {source.id for source in registry.sources}:
        raise ValueError(f"unknown source id {source_id!r}")


def _read_review_item(record_id: str, queue_dir: Path) -> ReviewItem:
    if re.fullmatch(r"review-[0-9a-f]{16}", record_id) is None:
        raise ValueError("review record ID has an invalid format")
    item = next((item for item in list_review_items(queue_dir) if item.id == record_id), None)
    if item is None:
        raise ValueError(f"unknown review item {record_id!r}")
    return item


def _record_review_decision(
    record_id: str,
    action: str,
    author: str,
    reason: str,
    evidence: str,
    created_at: str,
    queue_dir: Path,
    decisions_dir: Path,
    resolution: dict[str, Any] | None,
    approval_context: tuple[Path, Path, Path, Path] | None,
) -> None:
    try:
        item = _read_review_item(record_id, queue_dir)
        decisions = list_review_decisions(decisions_dir)
        if any(decision.review_item_id == record_id for decision in decisions):
            raise ValueError(f"review item {record_id!r} already has a terminal decision")
        decision_time = _parse_aware_datetime(created_at)
        if decision_time < item.created_at:
            raise ValueError("review decision cannot predate its review item")
        resolution_payload: dict[str, Any] | None = None
        if resolution is not None:
            candidate_ids = cast(list[str], resolution["candidate_ids"])
            resolution_payload = {
                **resolution,
                "allocation": equal_allocation(candidate_ids) if candidate_ids else {},
            }
        decision = new_review_decision(
            review_item_id=record_id,
            action=action,
            author=author,
            reason=reason,
            evidence=evidence,
            created_at=decision_time,
            resolution=resolution_payload,
        )
        if approval_context is not None:
            claim_path, inventory_path, registry_path, manifest_dir = approval_context
            claim = read_record(claim_path, ExtractedClaim)
            if claim.id != item.claim_id:
                raise ValueError("approval claim does not match the review item")
            inventory = read_inventory(inventory_path)
            registry = read_source_registry(registry_path)
            validate_registry_inventory(registry, inventory)
            capture = read_capture_manifest(manifest_dir / f"{claim.capture_id}.json")
            CanonicalDataset(
                inventory=inventory,
                source_registry=registry,
                captures=[capture],
                claims=[claim],
                endorsements=[],
                review_items=[item],
                review_decisions=[decision],
            )
        output = write_review_decision(decision, decisions_dir)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(f"review decision failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"review decision: {output}")


def _parse_aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must use ISO 8601 format") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed


def _score_timestamp(value: str | None) -> datetime:
    if value is not None:
        return _parse_aware_datetime(value)
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is None:
        raise ValueError("scoring requires --computed-at or SOURCE_DATE_EPOCH")
    try:
        seconds = int(epoch)
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError("SOURCE_DATE_EPOCH must be a supported integer Unix timestamp") from error


def _git_commit() -> str:
    environment_commit = os.environ.get("GITHUB_SHA")
    if environment_commit:
        return environment_commit
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not commit:
        raise ValueError("git returned an empty revision")
    return commit


def _write_generated_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(canonical_json_bytes(value))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _parse_json_value(value: str) -> Any:
    try:
        parsed: Any = json.loads(value, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("override values must be valid JSON") from error
    return parsed


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r} is not allowed")


def _read_override_target(
    path: Path,
    record_id: str,
) -> ExtractedClaim | NormalizedEndorsement | ReviewItem | ReviewDecision:
    raw: Any = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("override target must be a JSON object")
    raw_target = cast(dict[str, Any], raw)
    record_type: type[ExtractedClaim | NormalizedEndorsement | ReviewItem | ReviewDecision]
    if record_id.startswith("claim-"):
        record_type = ExtractedClaim
    elif record_id.startswith("endorsement-"):
        record_type = NormalizedEndorsement
    elif record_id.startswith("review-"):
        record_type = ReviewItem
    elif record_id.startswith("decision-"):
        record_type = ReviewDecision
    else:
        raise ValueError("override target uses an unsupported canonical record type")
    target_record = record_type.model_validate(raw_target)
    if target_record.id != record_id:
        raise ValueError("override target ID does not match the target file")
    expected_filename = (
        f"{target_record.claim_id}.json"
        if isinstance(target_record, ReviewItem)
        else f"{target_record.review_item_id}.json"
        if isinstance(target_record, ReviewDecision)
        else f"{target_record.id}.json"
    )
    if path.name != expected_filename:
        raise ValueError("override target filename does not match canonical storage identity")
    return target_record


@contextmanager
def _locked_override_field(
    overrides_dir: Path,
    record_id: str,
    field: str,
) -> Generator[None, None, None]:
    lock_dir = Path(tempfile.gettempdir()) / "seattle-election-guide-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{overrides_dir.resolve()}\0{record_id}\0{field}".encode()).hexdigest()
    lock_path = lock_dir / f"{digest}.lock"
    with lock_path.open("a+b") as lock:
        _set_file_lock(lock, acquire=True)
        try:
            yield
        finally:
            _set_file_lock(lock, acquire=False)


def _set_file_lock(lock: Any, *, acquire: bool) -> None:
    if os.name == "nt":
        locking: Any = importlib.import_module("msvcrt")
        lock.seek(0)
        if lock.read(1) == b"":
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        mode = locking.LK_LOCK if acquire else locking.LK_UNLCK
        locking.locking(lock.fileno(), mode, 1)
        return
    locking = importlib.import_module("fcntl")
    mode = locking.LOCK_EX if acquire else locking.LOCK_UN
    locking.flock(lock.fileno(), mode)


def _override_lower_bound(
    target: ExtractedClaim | NormalizedEndorsement | ReviewItem | ReviewDecision,
    manifest_dir: Path,
) -> datetime:
    if isinstance(target, (ExtractedClaim, NormalizedEndorsement)):
        capture_id = (
            target.capture_id if isinstance(target, ExtractedClaim) else target.source_capture_id
        )
        return read_capture_manifest(manifest_dir / f"{capture_id}.json").retrieved_at
    return target.created_at


def _validate_projected_override(
    target: ExtractedClaim | NormalizedEndorsement | ReviewItem | ReviewDecision,
    existing: list[OverrideRecord],
    proposed: OverrideRecord,
) -> None:
    projected = target.model_dump(mode="json")
    for override in sorted((*existing, proposed), key=lambda item: (item.created_at, item.id)):
        if override.target_record_id != target.id:
            continue
        if projected.get(override.field) != override.old_value:
            raise ValueError("override chain has a stale old value")
        projected[override.field] = override.new_value
    type(target).model_validate(projected, context={"skip_record_identity": True})


def _current_override_value(
    target: dict[str, Any],
    record_id: str,
    field: str,
    overrides: list[OverrideRecord],
) -> Any:
    if field == "id":
        raise ValueError("record identity cannot be overridden")
    if field not in target:
        raise ValueError(f"override target has no field {field!r}")
    current = target[field]
    for existing in sorted(overrides, key=lambda item: (item.created_at, item.id)):
        if existing.target_record_id != record_id or existing.field != field:
            continue
        if existing.old_value != current:
            raise ValueError("existing override history has a stale old value")
        current = existing.new_value
    return current
