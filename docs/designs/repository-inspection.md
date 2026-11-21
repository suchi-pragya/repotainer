# Repository inspection

- Updated: 2026-11-21
- Author: Suchi Pragya
- Status: Current source contract. [Repository inventory](repository-inventory.md) and [CLI evidence output](cli-evidence-output.md) own their feature decisions and verification evidence.

## Behavior and architecture

`repotainer [PATH]` resolves a directory, reports whether it contains a `.git` directory, scans its contents, and passes the completed inventory to the detector with `BUILTIN_RULES`. The installed entry point remains `repotainer.cli:main`. The Typer app registers `repotainer.commands.main.run` as its sole command. Omitting `PATH` uses the working directory. `--help` displays generated usage. [CLI entry point](../../src/repotainer/cli.py) · [Command handler](../../src/repotainer/commands/main.py)

| Interface | Contract |
| --- | --- |
| `resolve_scan_root(path: Path) -> Path` | Expands `~`, checks the final entry without following links, and resolves an existing directory. Rejects file and link targets and roots within a `.git` directory. [Path handling](../../src/repotainer/scanning/paths.py) |
| `inspect_repository(path: Path) -> RepositoryContext` | Returns the resolved `scan_root` and `has_git_directory` in a frozen dataclass. The Git check covers only the root. A missing `.git`, regular marker file, or symlink yields `False`. Other metadata errors propagate. [Repository inspection code](../../src/repotainer/scanning/repository.py) |
| `scan_inventory(scan_root, confirm_large_scan) -> Inventory \| None` | Takes a validated root and a callback receiving the root and retained-entry threshold. Returns a frozen inventory with the absolute root, sorted tuple of `InventoryEntry` records, and prune count. Returns `None` on decline and propagates scan failures. [Inventory builder](../../src/repotainer/scanning/inventory.py) |
| `read_ignore_rules(directory) -> tuple[IgnoreRule, ...]` | Reads a regular `.gitignore` in the given directory and returns ordered rules. The walker applies those rules within their original directory scope. [Ignore matcher](../../src/repotainer/scanning/ignore.py) |
| `detect(inventory, BUILTIN_RULES) -> DetectionResult` | Evaluates the built-in rules against the completed inventory and returns evidence and declaration read diagnostics. [Detector contract](repository-evidence-detection.md#detection-input-and-output) |

## Invariants and side effects

- The scanner only descends into eligible directories beneath the resolved root. The walk skips observed symlinks and assumes entries stay in place between classification and access. Inventory records filesystem observations made during the walk.
- During inventory, the scanner opens applicable `.gitignore` files and reads metadata. Detection may then open matched declarations. The command performs no file writes, subprocess calls, or network operations.
- The CLI prints the `.git` directory message, inventory counts, and the Python representation of `DetectionResult` to stdout in that order. Declaration read diagnostics appear in the result and preserve a successful exit. Prompts and scan errors use stderr. Declining a large scan exits with status `1`. Invalid paths, scan failures, and unavailable or interrupted confirmation exit with status `2`. These paths skip detection and omit the inventory summary. Unexpected detector exceptions propagate before the inventory summary and result are printed.

## Previous command

At `fa5f3ac`, `repotainer detect [PATH]` accepted files and selected their parents. It searched ancestors for a `.git` directory or worktree file and required `--allow-no-git` if none was found. The inventory cutover removed that behavior. The historical contract was checked against the source during EGM Bootstrap.

## Verification

[CLI and inspection tests](../../tests/test_repository.py) exercise the main invocation, path and `.git` directory handling, confirmation outcomes, and detector handoff and output. [Inventory tests](../../tests/test_inventory.py) cover the catalog, scoped exclusions, Git comparisons, and failure handling. See the verification for [inventory](repository-inventory.md#implementation-verification) and [CLI evidence output](cli-evidence-output.md#implementation-verification).
