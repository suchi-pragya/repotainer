from pathlib import Path
from typing import Annotated

import typer

from repotainer.scanning.paths import describe_path

app = typer.Typer()


@app.command()
def detect(path: Annotated[Path, typer.Argument(help="File or directory to scan.")] = Path(".")) -> None:
    """Identify the requested path before scanning its contents."""
    try:
        target, kind = describe_path(path)
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Working directory: {Path.cwd()}")
    typer.echo(f"Target: {target}")
    typer.echo(f"Type: {kind}")
