from pathlib import Path
from typing import Annotated

import typer

from repotainer.detection import BUILTIN_RULES, detect
from repotainer.scaffold import ScaffoldConflictError, ScaffoldWriteError, write_scaffold
from repotainer.scanning.inventory import scan_inventory
from repotainer.scanning.repository import inspect_repository


def run(
    path: Annotated[Path, typer.Argument(help="Directory to inventory and scaffold.")] = Path("."),
) -> None:
    """Inventory a directory, print detected tool evidence, and generate a dev container scaffold."""
    try:
        context = inspect_repository(path)
        if context.has_git_directory:
            typer.echo(f"Found a .git directory at {context.scan_root}.")
        else:
            typer.echo(f"No .git directory found at {context.scan_root}. Continuing with inventory.")
        inventory = scan_inventory(context.scan_root, _confirm_large_scan)
    except typer.Abort as exc:
        typer.echo("Error: Scan confirmation interrupted or input unavailable.", err=True)
        raise typer.Exit(code=2) from exc
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if inventory is None:
        typer.echo("Inventory cancelled.", err=True)
        raise typer.Exit(code=1)

    result = detect(inventory, BUILTIN_RULES)
    files = sum(entry.kind == "file" for entry in inventory.entries)
    typer.echo(f"Scan root: {inventory.scan_root}")
    typer.echo(f"Files: {files}")
    typer.echo(f"Directories: {len(inventory.entries) - files}")
    typer.echo(f"Pruned directories: {inventory.pruned_directories}")
    typer.echo(repr(result))

    selected_tools = tuple(tool.tool for tool in result.tools if tool.tool in ("python", "uv") and tool.evidence)
    try:
        created = write_scaffold(inventory.scan_root, selected_tools=selected_tools)
    except ScaffoldConflictError as exc:
        typer.echo("Error: Scaffold conflicts. No files created.", err=True)
        for conflict in exc.paths:
            typer.echo(f"  {conflict.as_posix()}", err=True)
        if exc.preserves_root_mise:
            typer.echo("Preserved existing mise.toml.", err=True)
        raise typer.Exit(code=2) from exc
    except ScaffoldWriteError as exc:
        typer.echo(f"Error: Scaffold generation failed at {exc}", err=True)
        for leftover, problem in exc.cleanup_problems:
            typer.echo(f"  Cleanup: {leftover}: {problem}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo("Created scaffold files:")
    for created_path in created:
        typer.echo(f"  {created_path.as_posix()}")
    if Path("mise.toml") not in created:
        typer.echo("Preserved existing project mise configuration.")


def _confirm_large_scan(path: Path, threshold: int) -> bool:
    return typer.confirm(f"Inventory at {path} exceeds {threshold:,} entries. Continue?", default=False, err=True)
