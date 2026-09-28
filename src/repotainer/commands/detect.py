from pathlib import Path
from typing import Annotated

import typer

from repotainer.scanning.repository import inspect_repository

app = typer.Typer()


@app.command()
def detect(
    path: Annotated[Path, typer.Argument(help="File or directory to scan.")] = Path("."),
    allow_no_git: Annotated[
        bool, typer.Option("--allow-no-git", help="Continue when no Git worktree contains the path.")
    ] = False,
) -> None:
    """Identify the requested path and its containing Git worktree."""
    try:
        context = inspect_repository(path)
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if context.git_root is None:
        typer.echo(f"Warning: no Git integration detected for {context.scan_root}.", err=True)
        if not allow_no_git:
            typer.echo("Use --allow-no-git to continue.", err=True)
            raise typer.Exit(code=2)

    typer.echo(f"Working directory: {Path.cwd()}")
    typer.echo(f"Target: {context.target}")
    typer.echo(f"Type: {context.kind}")
    typer.echo(f"Scan root: {context.scan_root}")
    typer.echo(f"Git root: {context.git_root or 'none'}")
