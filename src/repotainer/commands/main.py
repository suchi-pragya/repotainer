import sys
from pathlib import Path
from typing import Annotated

import typer

from repotainer.detection import BUILTIN_RULES, detect
from repotainer.detection.model import Evidence
from repotainer.scaffold import (
    ScaffoldConflictError,
    ScaffoldDestinations,
    ScaffoldPlan,
    ScaffoldWriteError,
    ToolRequests,
    existing_mise_tools,
    inspect_scaffold,
    plan_scaffold,
    write_scaffold,
)
from repotainer.scanning.inventory import scan_inventory
from repotainer.scanning.repository import inspect_repository
from repotainer.version_resolution import SUPPORTED_TOOLS, VersionResolution, resolve_tool

_MISE = Path("mise.toml")


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

    resolutions = tuple(resolve_tool(tool) for tool in result.tools if tool.tool in SUPPORTED_TOOLS and tool.evidence)
    _report_recommendations(resolutions)
    try:
        destinations = inspect_scaffold(inventory.scan_root)
        _report_existing(destinations)
        interactive = _can_prompt()
        try:
            requests = _choose_requests(resolutions, interactive=interactive)
            plan = plan_scaffold(destinations, requests)
            replace_devcontainer, replace_mise = _approve_replacements(plan, interactive=interactive)
        except (typer.Abort, EOFError, KeyboardInterrupt) as exc:
            typer.echo("Error: Scaffold selection cancelled.", err=True)
            raise typer.Exit(code=2) from exc
        writes = write_scaffold(plan, replace_devcontainer=replace_devcontainer, replace_mise=replace_mise)
    except ScaffoldConflictError as exc:
        typer.echo("Error: Scaffold conflicts. No files created.", err=True)
        for conflict in exc.paths:
            typer.echo(f"  {_display_path(conflict)}", err=True)
        if exc.preserves_root_mise:
            typer.echo("Preserved existing mise.toml.", err=True)
        raise typer.Exit(code=2) from exc
    except ScaffoldWriteError as exc:
        reason = exc.cause.strerror or str(exc.cause)
        typer.echo(
            f"Error: Scaffold generation failed at {_display_text(str(exc.path))}: {_display_text(reason)}", err=True
        )
        if exc.rolled_back:
            typer.echo("  Rolled back scaffold writes from this run.", err=True)
        for path in exc.restored:
            typer.echo(f"  Restored: {_display_path(path)}", err=True)
        for leftover, problem in exc.cleanup_problems:
            typer.echo(f"  Cleanup: {_display_path(leftover)}: {_display_text(problem)}", err=True)
        if exc.backup is not None:
            typer.echo(f"  Backup retained at {_display_path(exc.backup)}", err=True)
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    for label, paths in (("Created", writes.created), ("Replaced", writes.replaced)):
        if paths:
            typer.echo(f"{label} scaffold files:")
            for file in paths:
                typer.echo(f"  {_display_path(file)}")
    if not writes.created and not writes.replaced:
        typer.echo("No scaffold files changed.")
    if _MISE in destinations.existing and not replace_mise:
        typer.echo("Preserved existing project mise configuration.")
    if destinations.existing - {_MISE} and not replace_devcontainer:
        typer.echo("Preserved existing Dev Container scaffold.")
    if writes.leftover_backup is not None:
        typer.echo(f"Warning: Could not remove backup at {_display_path(writes.leftover_backup)}", err=True)


def _display_text(value: str) -> str:
    return value if value.isprintable() else repr(value)


def _display_path(path: Path) -> str:
    return _display_text(path.as_posix())


def _source(evidence: Evidence) -> str:
    path = _display_path(Path(*evidence.path))
    field = f" {'.'.join(evidence.field)!r}" if evidence.field else ""
    return f"{path}{field} = {evidence.value!r}"


def _report_recommendations(resolutions: tuple[VersionResolution, ...]) -> None:
    for resolution in resolutions:
        for diagnostic in resolution.diagnostics:
            typer.echo(f"Warning: {resolution.tool}: {diagnostic.message}", err=True)
            for source in diagnostic.evidence:
                typer.echo(f"  {_source(source)}", err=True)
            for source in diagnostic.ignored:
                typer.echo(f"  Set aside: {_source(source)}", err=True)
        if resolution.request is None:
            typer.echo(f"Conflicting {resolution.tool} version declarations:", err=True)
            for source in resolution.conflict:
                typer.echo(f"  {_source(source)}", err=True)
        else:
            typer.echo(f'Recommended Mise request: {resolution.tool} = "{resolution.request}"', err=True)


def _report_existing(destinations: ScaffoldDestinations) -> None:
    if not destinations.existing:
        return
    typer.echo("Existing scaffold files:", err=True)
    for path in sorted(destinations.existing):
        typer.echo(f"  {_display_path(path)}", err=True)
    if _MISE in destinations.existing:
        tools = existing_mise_tools(destinations)
        if tools is None:
            typer.echo("  Could not read the existing Mise tool table.", err=True)
        else:
            for tool, request in tools:
                display = f'"{request}"' if request is not None else "custom request"
                typer.echo(f"  Current Mise request: {tool!r} = {display}", err=True)


def _can_prompt() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def _choose_requests(resolutions: tuple[VersionResolution, ...], *, interactive: bool) -> ToolRequests:
    requests = []
    for resolution in resolutions:
        request = resolution.request
        if request is None:
            if interactive and resolution.choices:
                for number, choice in enumerate(resolution.choices, 1):
                    sources = "; ".join(map(_source, choice.evidence))
                    typer.echo(f"  {number}. {choice.request} from {sources}", err=True)
                options = tuple(choice.request for choice in resolution.choices) + ("latest",)
                typer.echo(f"  {len(options)}. latest", err=True)
                while True:
                    choice_number = typer.prompt(f"Choose a {resolution.tool} version", type=int, err=True)
                    if 1 <= choice_number <= len(options):
                        request = options[choice_number - 1]
                        break
                    typer.echo(f"Choose a number from 1 to {len(options)}.", err=True)
                typer.echo(f'Selected Mise request: {resolution.tool} = "{request}"', err=True)
            else:
                reason = "no usable candidate" if not resolution.choices else "unattended run"
                typer.echo(f'Warning: {resolution.tool}: using "latest" ({reason}).', err=True)
                request = "latest"
        requests.append((resolution.tool, request))
    return tuple(requests)


def _approve_replacements(plan: ScaffoldPlan, *, interactive: bool) -> tuple[bool, bool]:
    existing = plan.destinations.existing
    approvals = []
    for label, is_mise in (("Dev Container scaffold", False), ("Mise configuration", True)):
        group = tuple((path, content) for path, content in plan.contents if (path == _MISE) == is_mise)
        has_existing = any(path in existing for path, _ in group)
        if not interactive or not has_existing:
            approvals.append(False)
            continue
        typer.echo(f"Proposed {label} changes:", err=True)
        for path, content in group:
            action = "Replace entire file" if path in existing else "Create"
            typer.echo(f"  {action} {_display_path(path)}:", err=True)
            for line in content.decode().splitlines():
                typer.echo(f"    {line}", err=True)
        approvals.append(typer.confirm(f"Replace existing {label}?", default=False, err=True))
    return approvals[0], approvals[1]


def _confirm_large_scan(path: Path, threshold: int) -> bool:
    return typer.confirm(f"Inventory at {path} exceeds {threshold:,} entries. Continue?", default=False, err=True)
