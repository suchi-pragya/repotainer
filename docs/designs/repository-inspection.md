# Repository inspection

- Updated: 2026-11-24
- Author: Suchi Pragya
- Status: Current source contract. [Repository inventory](repository-inventory.md), [CLI evidence output](cli-evidence-output.md), [Dev container scaffold generation](devcontainer-scaffold.md), and [Tool version resolution](tool-version-resolution.md) own their feature decisions and verification evidence.

## Behavior and architecture

`repotainer [PATH]` resolves a directory, reports whether it contains a `.git` directory, scans its contents, and passes the completed inventory to the detector with `BUILTIN_RULES`. After printing evidence, the command recommends Python and uv requests, inspects the root scaffold destinations, and collects any version choices and separate replacement approvals before writing. The installed entry point is `repotainer.cli:main`. The Typer app registers `repotainer.commands.main.run` as its sole command. Omitting `PATH` uses the working directory. `--help` displays generated usage. [CLI entry point](../../src/repotainer/cli.py) · [Command handler](../../src/repotainer/commands/main.py) · [Version and replacement policy](tool-version-resolution.md#technical-plan)

| Interface | Contract |
| --- | --- |
| `resolve_scan_root(path: Path) -> Path` | Expands `~`, checks the final entry without following links, and resolves an existing directory. Rejects file and link targets and roots within a `.git` directory. [Path handling](../../src/repotainer/scanning/paths.py) |
| `inspect_repository(path: Path) -> RepositoryContext` | Returns the resolved `scan_root` and `has_git_directory` in a frozen dataclass. The Git check covers only the root. A missing `.git`, regular marker file, or symlink yields `False`. Other metadata errors propagate. [Repository inspection code](../../src/repotainer/scanning/repository.py) |
| `scan_inventory(scan_root, confirm_large_scan) -> Inventory \| None` | Takes a validated root and a callback receiving the root and retained-entry threshold. Returns a frozen inventory with the absolute root, sorted tuple of `InventoryEntry` records, and prune count. Returns `None` on decline and propagates scan failures. [Inventory builder](../../src/repotainer/scanning/inventory.py) |
| `read_ignore_rules(directory) -> tuple[IgnoreRule, ...]` | Reads a regular `.gitignore` in the given directory and returns ordered rules. The walker applies those rules within their original directory scope. [Ignore matcher](../../src/repotainer/scanning/ignore.py) |
| `detect(inventory, BUILTIN_RULES) -> DetectionResult` | Evaluates the built-in rules against the completed inventory and returns evidence and declaration read diagnostics. [Detector contract](repository-evidence-detection.md#detection-input-and-output) |
| `resolve_tool(tool: ToolEvidence) -> VersionResolution` | Derives a Mise request or returns a version conflict with evidence and menu candidates. [Resolver](../../src/repotainer/version_resolution.py) |
| `inspect_scaffold(root)` and `plan_scaffold(destinations, tool_requests)` | Read root destination state and prepare proposed payloads. Invalid destination types and invalid requests fail before writes. [Scaffold writer](../../src/repotainer/scaffold.py) |
| `write_scaffold(plan, *, replace_devcontainer=False, replace_mise=False)` | Applies the approved write set and returns created and replaced paths and any backup left after cleanup. [Scaffold writer](../../src/repotainer/scaffold.py) |

## Invariants and side effects

- The scanner only descends into eligible directories beneath the resolved root. The walk skips observed symlinks and assumes entries stay in place between classification and access. Inventory records filesystem observations made during the walk.
- During inventory, the scanner opens applicable `.gitignore` files and reads metadata. Detection may then open matched declarations. The scaffold preview can read the existing root Mise tool table. Scaffold creation and approved replacements write files, including temporary backups where needed. The CLI performs the work on the host without subprocesses, network operations, or container setup.
- The CLI prints the `.git` directory message, inventory counts, and the Python representation of `DetectionResult` to stdout in that order. Recommendations, prompts, and warnings go to stderr. A completed detector result with declaration diagnostics still reaches the scaffold flow. On success, stdout reports what happened to the scaffold and the command exits with status `0`.
- Declining a large scan exits with status `1`. Invalid paths, scan failures, and unavailable or interrupted scan confirmation exit with status `2` before detection. Unexpected detector exceptions propagate before the inventory report. A version or replacement prompt interrupted by EOF or Ctrl+C exits with status `2` before backup or writes. Declined replacement groups are preserved. Blocked destinations and write failures exit with status `2`. The writer creates new files exclusively and attempts to roll back changes after a handled write failure. [Write boundary and recovery](devcontainer-scaffold.md#destination-checks-and-writes)

## Previous command

At `fa5f3ac`, `repotainer detect [PATH]` accepted files and selected their parents. It searched ancestors for a `.git` directory or worktree file and required `--allow-no-git` if none was found. The inventory cutover removed that behavior. The historical contract was checked against the source during EGM Bootstrap.

## Verification

[CLI and inspection tests](../../tests/test_repository.py) exercise the main invocation, path and `.git` directory handling, confirmation outcomes, detector output, and scaffold handoff. [Inventory tests](../../tests/test_inventory.py) cover the catalog, scoped exclusions, Git comparisons, and failure handling. [Scaffold tests](../../tests/test_scaffold.py) exercise config discovery, conflicts, and rollback.
