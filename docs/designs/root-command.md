# Repotainer’s root command

- **Author** — Suchi Pragya
- **Status** — Author-approved design. Implemented and verified locally.
- **Date** — 2026-11-21

## Overview

Repotainer has one public command, `repotainer [PATH]`. [`cli.py`](../../src/repotainer/cli.py) imports the handler from [`commands/main.py`](../../src/repotainer/commands/main.py) and registers it with Typer. The handler owns the CLI inputs, coordinates the workflow, and handles prompts, output, and exit status. Feature modules own the work each stage performs.

## The Problem

The inventory cutover removed the `detect` subcommand and kept `commands/detect.py` as the home of the root handler. That name suggests a subcommand and describes one stage of the workflow. The handler currently inventories a directory.

## Goals

- Keep one public command. Express new CLI inputs through positional arguments and options, including boolean flags.
- Make the root handler easy to find. Keep Typer setup and registration in `cli.py`, command handling in `commands/main.py`, and repository scanning in `scanning/`.
- Preserve the [current command contract](repository-inspection.md#behavior-and-architecture), including the working-directory default, explicit paths, generated help, prompts, output, and exit codes.

## Non-Goals

- New flags, detection rules, or generation features in this refactor.
- Changes to the [scan boundary and `.git` directory check](repository-inventory.md#choose-the-scan-root).

## Technical plan

Keep the installed `repotainer` script pointing to `repotainer.cli:main`. In `cli.py`, import `run` from `repotainer.commands.main` and register it as the app’s sole command. Typer exposes a sole registered command directly when the app has no root callback or subgroups. Keep the positional path and its `.` default on `run` so Typer parses the path and generates help from the handler’s signature.

```text
repotainer [PATH]
  └─ cli.py:main → Typer app
       └─ commands/main.py:run
            ├─ inspect_repository → resolved root and .git directory presence
            ├─ scan_inventory → inventory catalog or cancellation
            └─ detect → evidence and read diagnostics after a successful scan
```

The handler reports whether the resolved scan root contains a `.git` directory and passes its confirmation callback to the scanner. The scanner calls it once before retaining entry 1,001. On success, the scanner returns the catalog and the number of excluded directories it skipped. The handler renders the result and maps cancellation and failures to the existing messages and exit codes. [Large scans](repository-inventory.md#large-scans) · [Scanner side effects](repository-inspection.md#invariants-and-side-effects)

The handler passes the completed catalog to detection and prints the result after the inventory counts. Each stage owns its rules and data. Keep `commands/main.py` focused on deciding which stages to call and translating their results into terminal output. Adding another Typer command or a root callback can change how Typer parses the first positional argument. The CLI tests and console-script checks in the implementation plan cover that risk. [CLI evidence output](cli-evidence-output.md)

## Alternatives considered

| Alternative | Benefit and trade-off | Decision |
| --- | --- | --- |
| Keep the handler in `commands/detect.py` | Avoids moving code. The name still suggests a `detect` subcommand and describes only one future stage of the workflow. | Use `commands/main.py` for the root handler. |
| Define the handler directly in `cli.py` | Puts the Typer app and handler in one place. It also puts argument definitions, prompts, and output alongside the app setup as the command grows. | Import the handler from `commands/` and keep Typer setup in `cli.py`. |
| Expose inventory or detection as a subcommand | Gives each operation its own arguments and help. It adds a command-selection step and would change how Typer interprets the first positional token. | Keep one public command with positional arguments and options, including boolean flags. |

## Detailed implementation plan

1. Make the source edits together so the CLI can always import its handler.
   - Create `src/repotainer/commands/main.py` by moving the handler and renaming `detect` to `run`. Carry over the path annotation and default, help text, prompt callback, and error and output handling.
   - Remove `src/repotainer/commands/detect.py` after moving its handler.
   - Update [`src/repotainer/cli.py`](../../src/repotainer/cli.py) to import and register `run` as the sole command. Keep `app` available to the CLI tests and keep `main()` as the installed script entry point.
2. Update [`docs/designs/repository-inspection.md`](repository-inspection.md) to name and link the new handler. In [`docs/designs/repository-inventory.md`](repository-inventory.md), update the live handler link in the component table and preserve the historical cutover’s original file path as text. In its [Command interface](repository-inventory.md#command-interface) and [Alternatives considered](repository-inventory.md#alternatives-considered), replace the suggestions of a future subcommand with links to this design and preserve the first milestone’s decision.
3. From the checkout, run `uv sync --locked` and `uv run python -m unittest discover -s tests`. The existing [`CliRunner` cases](../../tests/test_repository.py) cover default and explicit directories, errors, and confirmation outcomes.
4. Resolve the absolute path to the checkout’s console script, `.venv/bin/repotainer` on Unix or `.venv/Scripts/repotainer.exe` on Windows. Use it for the following checks.
   - Run with `--help` and require exit status 0, one optional path, and no subcommand list.
   - Create a temporary parent directory with a child named `detect` containing one regular file. Run with no argument from inside `detect`, with its absolute path from the parent, and with the literal argument `detect` from the parent.
   - For each scan, require exit status 0, `Scan root:` with the resolved fixture path, and counts of one file, zero directories, and zero pruned directories.
5. Run `ruff check .`, `ruff format --check .`, and `ty check`. After verifying the refactor, record the actual results and update the implementation status in `docs/designs/root-command.md`. Update [`docs/designs/SITEMAP.md`](SITEMAP.md) and link its status to those results. Run Markdown lint, verify the updated links, and inspect the diff.

## Implementation verification

Verified the working-tree refactor based on `7154512` on 2026-11-21 with Python 3.14.6 and Git 2.43.0 on Linux. `uv sync --locked` succeeded, and all 22 tests passed. Ruff lint, Ruff format, type checking, Markdown lint, and local link checks passed.

The checkout’s console script showed one optional path with `.` as the default and no subcommand list. The omitted path, absolute fixture path, and literal `detect` argument from the fixture’s parent each exited with status 0 and reported the same resolved scan root, one file, zero directories, and zero pruned directories.
