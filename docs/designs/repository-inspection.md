# Repository inspection

- Updated: 2026-11-21.
- Author: Suchi Pragya (repository author identity); consolidated with EGM Draft.
- Review status: current-state design reconstructed from source, tests, and the source README contracts; documentation consolidation requested by the user, with no new approval of behavioral choices.
- Implementation state: path and Git-context reporting implemented; repository inventory and configuration generation absent.
- Components: CLI composition, detect command, path classification, repository inspection.

## Purpose and scope

Repotainer aims to generate reproducible Dev Container configurations from repository files. Its current `detect` command only identifies an existing target and its containing Git marker. Repository inventory, ecosystem/requirement detection, configuration planning, and configuration generation have no implementation in the current source tree.

## Behavior and architecture

This document is the single current-state design for the implemented source tree, including interfaces, invariants, side effects, reasoning, and verification limits. Future work can use a separate proposed design that links to this baseline. Shared tooling and development practices remain in [Development](../development.md).

| Component             | Responsibility                                                           | Source                                                       |
| --------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------ |
| Installed command     | Maps `repotainer` to `repotainer.cli:main`                               | [pyproject.toml](../../pyproject.toml)                       |
| CLI composition       | Creates the Typer app and registers commands                             | [cli.py](../../src/repotainer/cli.py)                        |
| Detect command        | Accepts input and renders context, warnings, and errors                  | [detect.py](../../src/repotainer/commands/detect.py)         |
| Repository inspection | Builds immutable `RepositoryContext` and searches for Git markers        | [repository.py](../../src/repotainer/scanning/repository.py) |
| Path classification   | Expands `~`, resolves an existing path, and identifies file or directory | [paths.py](../../src/repotainer/scanning/paths.py)           |

The flow is synchronous:

```text
repotainer → cli.main → Typer dispatch → commands.detect.detect
  → scanning.repository.inspect_repository
    → scanning.paths.describe_path
    → scanning.repository._find_git_root
  → command output or handled exit
```

`src/` has no direct source modules. The `repotainer`, `commands`, and `scanning` package `__init__.py` files are empty; callers import the module symbols below. CLI presentation stays in `commands`, filesystem/domain behavior stays in `scanning`, and `cli.py` composes the application.

### CLI composition interface

[cli.py](../../src/repotainer/cli.py) exposes `app = typer.Typer(no_args_is_help=True)`. It registers the imported `commands.detect.app` through `app.add_typer(detect_app)` without a group name. `root() -> None` is the registered root callback and has no application behavior of its own. `main() -> None` invokes `app()`; [pyproject.toml](../../pyproject.toml) maps the installed executable to `repotainer.cli:main`. The app requests help when invoked without arguments.

### Detect command interface and output

[detect.py](../../src/repotainer/commands/detect.py) exposes a `typer.Typer` app and registers `detect` with `@app.command()`. The function accepts `path: Path = Path(".")` as a positional argument and `allow_no_git: bool = False` as `--allow-no-git`, returning `None` on normal completion. `Annotated` metadata declares the CLI argument/option and their help text.

`repotainer detect [PATH]` defaults to the working directory. The command passes the path to `inspect_repository`. On success it prints five lines to stdout: `Working directory`, `Target`, `Type`, `Scan root`, and `Git root`. The working directory comes from `Path.cwd()`; the other values come from the returned context, with a missing Git root rendered as `none` when continuation is allowed.

| Condition | stderr | Outcome |
| --- | --- | --- |
| Inspection raises `OSError` or `ValueError` | `Error: {exception}` | Raises `typer.Exit(code=2)` chained from the exception. |
| No Git root, default options | `Warning: no Git integration detected for {scan_root}.` followed by `Use --allow-no-git to continue.` | Raises `typer.Exit(code=2)` before normal context output. |
| No Git root, `--allow-no-git` supplied | The same warning, without the override hint | Continues with normal context output, including `Git root: none`. |
| Git root found | No warning from this branch | Continues with normal context output. |

The exception translation surrounds the inspection call; it does not catch every exception from subsequent rendering or `Path.cwd()`. A Git marker does not prove a valid worktree.

### Scanning interfaces and data model

| Symbol | Contract |
| --- | --- |
| [paths.py:PathKind](../../src/repotainer/scanning/paths.py) | `Literal["file", "directory"]`. |
| [paths.py:describe_path](../../src/repotainer/scanning/paths.py) | `describe_path(path: Path) -> tuple[Path, PathKind]`; expands `~`, resolves with `strict=True`, and classifies the resolved target. Resolution errors propagate; unsupported types raise `ValueError`. |
| [repository.py:RepositoryContext](../../src/repotainer/scanning/repository.py) | Frozen, slotted dataclass with required fields `target: Path`, `kind: PathKind`, `scan_root: Path`, and `git_root: Path \| None`. Direct construction does not validate field values or relationships. |
| [repository.py:inspect_repository](../../src/repotainer/scanning/repository.py) | `inspect_repository(path: Path) -> RepositoryContext`; composes classification, scan-root selection, and Git-marker discovery. |
| [repository.py:_find_git_root](../../src/repotainer/scanning/repository.py) | Internal `_find_git_root(scan_root: Path) -> Path \| None` helper; checks the selected directory and then its ancestors. It is not a separate CLI or Git validation service. |

### Implemented invariants and limitations

`describe_path` follows symlinks through strict resolution, then checks for a regular file before checking for a directory. Other existing target types raise `ValueError("Unsupported path type: ...")`.

`inspect_repository` uses the resolved directory itself as the scan root, or the resolved file's parent for file input. `_find_git_root` checks that root and its ancestors in order, returning the first directory containing a `.git` directory or regular-file marker, or `None` if no marker matches. It does not invoke Git or read marker contents. The scan root and Git root can differ; these relationships are produced by the inspector and are not enforced by the dataclass constructor.

`RepositoryContext` uses `frozen=True` to prevent ordinary field assignment and `slots=True` to provide slots. Filesystem observations are not an atomic snapshot and do not guarantee that a path remains present afterward. These are implemented properties, not acceptance of the unresolved Git-root semantics.

### Side effects and ownership

Importing `cli.py` constructs the Typer app and registers its command app and callback. Calling `main()` dispatches through Typer. The detect command reads the current directory, writes informational output to stdout and warnings/errors to stderr, and can raise CLI exits.

Scanning performs path resolution and filesystem metadata reads without console output or translation into CLI exits. The inspected source modules contain no file-writing, subprocess, or network operations. Repository inventory and configuration generation remain unimplemented.

## Choices, alternatives, and consequences

### Python filesystem inspection

Current code uses `pathlib` and a frozen dataclass, separating path/domain behavior from Typer output. The established project instruction is to follow that filesystem approach and not introduce shell scanning without an agreed reason. No comparative performance or correctness evidence for a shell-based alternative has been established.

### Ancestor Git-marker discovery

The implemented ancestor search supports nested targets and `.git` file markers. Its consequence is that a selected directory without its own marker can inherit an ancestor's Git root. An alternative would warn when the selected directory lacks its own marker; that alternative has not been accepted. Existing tests document current behavior and do not settle the design question.

## Open questions

- Should a selected directory without its own `.git` warn even if an ancestor is a repository? Resolve with the user before changing these semantics.
- Which ecosystems and inferred requirements should the first useful release support?
- What evidence will establish the correctness and usefulness of generated configurations? No comparative results have been established.

## Verification

[tests/test_repository.py](../../tests/test_repository.py) covers ancestor discovery for a nested file, acceptance of `.git` file markers, and the no-Git rejection/override through Typer’s `CliRunner` using `cli.app`. It does not have dedicated tests for strict resolution or unsupported path types, cover every error/output or CLI composition branch, or prove validity of a discovered Git worktree. For behavior changes, run `uv run python -m unittest discover -s tests` from the repository root and add verification appropriate to the changed contract.

This baseline was inspected against the source working tree on 2026-11-21 (HEAD `1a634d4`, with no Python source diff at inspection). The application tests were read, not executed during documentation setup. The source README contracts were consolidated here without changing Python source or resolving open questions. Documentation lint, link checks, and rendering establish documentation checks only; they do not establish runtime behavior.
