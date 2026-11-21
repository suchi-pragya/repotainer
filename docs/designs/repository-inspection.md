# Repository inspection

- Updated: 2026-11-21
- Author: Suchi Pragya
- Status: Current source contract. [Repository inventory](repository-inventory.md) owns the feature decisions and verification evidence.

## Behavior and architecture

`repotainer [PATH]` resolves a directory, reports whether that directory contains `.git`, and inventories its contents. The installed entry point remains `repotainer.cli:main`. The Typer app registers `repotainer.commands.main.run` as its sole command. Omitting `PATH` uses the working directory. `--help` displays generated usage. [CLI entry point](../../src/repotainer/cli.py) · [Command handler](../../src/repotainer/commands/main.py)

| Interface | Contract |
| --- | --- |
| `resolve_scan_root(path: Path) -> Path` | Expands `~`, checks the final entry without following links, and resolves an existing directory. Rejects file and link targets and roots within a `.git` directory. [Path handling](../../src/repotainer/scanning/paths.py) |
| `inspect_repository(path: Path) -> RepositoryContext` | Returns the resolved `scan_root` and `has_git_directory` in a frozen dataclass. The Git check covers only the root. A missing `.git`, regular marker file, or symlink yields `False`. Other metadata errors propagate. [Repository inspection code](../../src/repotainer/scanning/repository.py) |
| `scan_inventory(scan_root, confirm_large_scan) -> Inventory \| None` | Takes a validated root and a callback receiving the root and retained-entry threshold. Returns a frozen inventory with the absolute root, sorted tuple of `InventoryEntry` records, and prune count. Returns `None` on decline and propagates scan failures. [Inventory builder](../../src/repotainer/scanning/inventory.py) |
| `read_ignore_rules(directory) -> tuple[IgnoreRule, ...]` | Reads a regular `.gitignore` in the given directory and returns ordered rules. The walker applies those rules within their original directory scope. [Ignore matcher](../../src/repotainer/scanning/ignore.py) |

## Invariants and side effects

- The scanner only descends into eligible directories beneath the resolved root. The walk skips observed symlinks and assumes entries stay in place between classification and access. Inventory records filesystem observations made during the walk.
- The scanner opens applicable `.gitignore` files and reads metadata. Project declarations stay unopened. Runtime scanning performs no file writes, subprocess calls, or network operations.
- The CLI reports Git status and successful inventory counts on stdout. It writes prompts and diagnostics to stderr. Declining a large scan exits with status `1`. Invalid paths, scan failures, and unavailable or interrupted confirmation exit with status `2`. Failure and cancellation omit the success summary.

## Previous command

At `fa5f3ac`, `repotainer detect [PATH]` accepted files and selected their parents. It searched ancestors for a `.git` directory or worktree file and required `--allow-no-git` if none was found. The inventory cutover removed that behavior. The historical contract was checked against the source during EGM Bootstrap.

## Verification

[CLI and inspection tests](../../tests/test_repository.py) exercise the main invocation, path and Git status handling, and the confirmation outcomes. [Inventory tests](../../tests/test_inventory.py) cover the catalog, scoped exclusions, Git comparisons, and failure handling. See the [recorded verification](repository-inventory.md#implementation-verification).
