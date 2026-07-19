"""Command-line entry point for the election guide pipeline."""

from pathlib import Path
from typing import Annotated

import typer

from election_guide import __version__

app = typer.Typer(
    help="Build and audit the Seattle election endorsement consensus guide.",
    no_args_is_help=True,
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
    )
    missing = [path for path in required_paths if not (root / path).is_file()]
    if missing:
        for path in missing:
            typer.echo(f"missing: {path}", err=True)
        raise typer.Exit(code=1)
    typer.echo("foundation: ok")
