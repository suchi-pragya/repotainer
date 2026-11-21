from pathlib import Path
from typing import Annotated

import typer

from repotainer.scanning.inventory import scan_inventory
from repotainer.scanning.repository import inspect_repository


def detect(
    path: Annotated[Path, typer.Argument(help="Directory to inventory.")] = Path("."),
) -> None:
    """Inventory the files and directories beneath a scan root."""
    try:
        context = inspect_repository(path)
        if context.has_git_directory:
            typer.echo(f"Found a .git directory at {context.scan_root}.")
        else:
            typer.echo(f"No .git directory found at {context.scan_root}. Continuing with inventory.")
        result = scan_inventory(context.scan_root, _confirm_large_scan)
    except typer.Abort as exc:
        typer.echo("Error: Scan confirmation interrupted or input unavailable.", err=True)
        raise typer.Exit(code=2) from exc
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if result is None:
        typer.echo("Inventory cancelled.", err=True)
        raise typer.Exit(code=1)

    files = sum(entry.kind == "file" for entry in result.entries)
    typer.echo(f"Scan root: {result.scan_root}")
    typer.echo(f"Files: {files}")
    typer.echo(f"Directories: {len(result.entries) - files}")
    typer.echo(f"Pruned directories: {result.pruned_directories}")


def _confirm_large_scan(path: Path, threshold: int) -> bool:
    return typer.confirm(f"Inventory at {path} exceeds {threshold:,} entries. Continue?", default=False, err=True)
