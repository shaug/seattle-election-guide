"""Command-line entry point for the election guide pipeline."""

from pathlib import Path
from typing import Annotated

import typer

from election_guide import __version__
from election_guide.inventory.importer import (
    extract_public_inputs,
    import_inventory,
    read_inventory,
    write_inventory,
)
from election_guide.sources.registry import read_source_registry, validate_registry_inventory
from election_guide.sources.report import render_discovery_report

app = typer.Typer(
    help="Build and audit the Seattle election endorsement consensus guide.",
    no_args_is_help=True,
)
inventory_app = typer.Typer(help="Import and validate the official Seattle ballot inventory.")
sources_app = typer.Typer(help="Inspect and validate the frozen endorsement-source panel.")
app.add_typer(inventory_app, name="inventory")
app.add_typer(sources_app, name="sources")


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
