# Dev container scaffold generation

- Author: Suchi Pragya
- Review status: Author-approved design. All 12 EGM review findings resolved.
- Implementation state: Implemented and [verified locally](#implementation-verification).
- Updated: 2026-11-22

## Overview

Running `repotainer [PATH]` will inventory the selected directory, print detected tool evidence, and generate three static dev container files. If the project has no mise configuration, Repotainer also creates a root `mise.toml` with an empty `[tools]` table. Mise installs and manages tools inside the container.

## The problem

Before scaffold generation, the CLI stopped after reporting evidence and users created the container build and setup files themselves. A static scaffold lets users set up a project before [evidence can be mapped to tool selections](repository-evidence-detection.md#handoff-to-mise-generation). Generation must preserve existing project configuration and avoid changing which dev container opens by default. [Current CLI contract](repository-inspection.md)

## Goals

- Keep `repotainer [PATH]` as the entry point. Use the current directory when `PATH` is omitted. Support projects with or without Git metadata.
- Keep the inventory and evidence report. Generate the same static dev container files for any detection result.
- Preserve existing mise config and create an empty `mise.toml` only when the selected project root has no mise config of its own.
- Check all safely reachable dev container destinations and alternate configurations before creating anything. List all conflicts, including a blocked `.devcontainer` directory path, and exit without writing.

## Non-goals

- Evidence-driven tool selection or Dockerfile generation in this milestone. The next use of evidence is to populate `mise.toml`. A later milestone can consider a generated Dockerfile if the static baseline no longer meets project needs.
- Overwriting or merging existing configuration.
- Building or starting the container during the Repotainer invocation. The dev container runner builds the image and invokes the setup script.

## Technical plan

### Command flow

The [root command](../../src/repotainer/commands/main.py) runs the inventory and detector, prints the existing report, and passes the resolved root to the scaffold writer. A user who declines the large-scan prompt, a scan failure, or an unexpected detector failure ends the command before generation. A declaration-read diagnostic, such as an invalid `pyproject.toml`, is part of a completed detection result and does not block generation. The writer works from the resolved root and does not consume tool evidence.

```text
repotainer [PATH]
  → resolve root → inventory → detect → print report
  → check dev container conflicts and project mise config
  → report conflicts or write the scaffold
```

### Generated files

| Destination | Contents |
| --- | --- |
| `.devcontainer/devcontainer.json` | Uses `.` as the build context relative to the config file, `Dockerfile` as the build file, and `bash .devcontainer/setup.sh` as `postCreateCommand`. |
| `.devcontainer/Dockerfile` | Uses `mcr.microsoft.com/devcontainers/base:ubuntu26.04`, copies the mise binary from `jdxcode/mise` to `/usr/local/bin/`, and activates mise in the `vscode` user's Bash and Zsh startup files. The hand-maintained template omits the uv, `python3`, and `tmux` installation steps from [Repotainer's development Dockerfile](../../.devcontainer/Dockerfile). |
| `.devcontainer/setup.sh` | Runs Bash with strict error handling, derives the workspace root from the script location without invoking Git, and runs `mise install` from that root. |
| `mise.toml` | Created only when project mise config is absent. Contains a single empty `[tools]` table, so the generated file requests no tools. |

The three dev container templates ship with Repotainer. The generated configuration has no project-specific settings or host token forwarding.

The setup script uses mise's normal discovery, environment selection, and trust behavior inside the container. Running `mise install` can install tools and run configured hooks. Mise can also load other configuration available in that container. Repotainer's root-only presence check controls file generation only. The setup command passes any install failure to the dev container runner. [Mise configuration](https://mise.jdx.dev/configuration.html) · [Mise trust](https://mise.jdx.dev/cli/trust.html)

The templates produce identical bytes for a given Repotainer build. Building the container requires Docker and access to the base and mise images. Image tags can move, so identical scaffold files can produce different images. [Docker image tag behavior](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)

### Project mise configuration

Check the documented project config locations anchored at the selected root using filesystem metadata. A match is enough to skip generating `mise.toml`, even when the config belongs to an environment that is currently inactive. Preserve every existing config. This check runs independently of inventory ignore rules, so an ignored `mise.local.toml` still counts.

| Location relative to the selected root | What counts |
| --- | --- |
| Root | `mise.toml`, `mise.local.toml`, `mise.<env>.toml`, `mise.<env>.local.toml`, their documented dotfile forms, and `.tool-versions`. |
| `mise/`, `.mise/`, and `.config/mise/` | `config.toml` and its local and environment variants. Also check the documented `mise.toml` family directly in `.config/` and `.config/mise/`. |
| `mise/conf.d/`, `.mise/conf.d/`, and `.config/mise/conf.d/` | Documented TOML fragments and config files or variants inside one-level named fragment directories. Skip hidden fragment names. |
| Root and `.config/` | Documented project environment and discovery settings at `.miserc.toml`, `.miserc.local.toml`, and `.config/miserc.toml`. |

This is a bounded location check. The writer does not recurse into nested projects or inspect ancestor, user, global, or system config. It neither parses config values nor uses custom discovery settings to expand the checked locations. Do not traverse a config directory link or junction outside the project root. Preserve a link at a recognized file path without reading its contents. If `mise.toml` itself is occupied by an unusable entry such as a directory, report the path and stop before writes. [Mise config locations](https://mise.jdx.dev/configuration.html#config-file-locations) · [Config environments](https://mise.jdx.dev/configuration/environments.html#file-names-and-precedence) · [Mise discovery settings](https://mise.jdx.dev/configuration.html#miserc-toml)

### Destination checks and writes

Inspect the actual destination paths before creating anything. Any existing entry at a dev container file destination is a conflict, including directories and valid or broken links. Check for root `.devcontainer.json` and for `.devcontainer/<name>/devcontainer.json` one level below the main config directory. The generated primary config would otherwise take precedence over those alternate configurations. Check named directories that can be inspected within the root. [Dev Container discovery order](https://github.com/devcontainers/spec/blob/main/docs/specs/devcontainer-reference.md#devcontainerjson)

Reuse an ordinary `.devcontainer` directory. If the path is a symlink, Windows junction, or non-directory, report it as a conflict and skip its children. Still check the root alternate `.devcontainer.json` and root-level `mise.toml` independently. A usable existing `mise.toml` is reported as preserved, alongside any conflict report if applicable. Exit with status `2` before writes when preflight finds a conflict or cannot check a required path. [Existing scan-root junction check](../../src/repotainer/scanning/paths.py)

The resolved root, its ancestors, and the checked or newly created `.devcontainer` directory must stay in place from preflight through cleanup. Entries created by this invocation must stay in place during their ownership check and removal. Exclusive creation fails if the final destination becomes occupied before it is opened. If `.devcontainer` was absent and appears before the writer creates it, stop and report that path.

Write the Dockerfile, setup script, and optional `mise.toml` before writing `devcontainer.json`. On a handled write failure, report the failing path and attempt cleanup of only the entries this run created and can still identify. Preserve and report replacements or entries of uncertain ownership. If the writer observes that `.devcontainer` has been replaced, stop accessing files through that path. Remove a directory created by this run only when it can still be identified and is empty.

Abrupt termination can leave partial output. On retry, existing dev container files are reported as conflicts. Users can inspect those paths, remove files they can identify as partial scaffold output, and retry. If a generated `mise.toml` remains, report it as preserved under the same rule as any other existing mise config.

## Alternatives considered

### Require an explicit generation command or flag

A separate invocation would preserve the read-only behavior of `repotainer [PATH]` and add a step for users who want the scaffold. The existing invocation will generate the scaffold after preflight.

### Populate mise config from evidence in the first milestone

This would require tool and version selection rules before users could try generation. The first milestone reuses existing mise config or supplies an empty table. Evidence reporting stays available while tool selection is developed.

### Generate over an existing dev container setup

Overwriting or merging would require compatibility rules across JSON, Dockerfile instructions, and Bash. Generating beside an alternate config can change the default container even when no existing bytes change. Existing dev container configuration blocks generation.

### Keep files after a partial write failure

Keeping those files would avoid cleanup work, but users would need to clear scaffold conflicts before retrying. The writer attempts to remove only identifiable entries created in the failed run.

## Detailed implementation plan

### 1. Add the writer and resources

- **Create `src/repotainer/scaffold.py`.** Define `write_scaffold(root: Path) -> tuple[Path, ...]`. Return the project-relative paths actually created, in write order. Define `ScaffoldConflictError` with an ordered tuple of preflight conflict paths and a flag for an existing root `mise.toml`. Define `ScaffoldWriteError` with the failed path or resource name, cause, and ordered cleanup problems. Check dev container and mise paths, order diagnostic paths lexically, and load all three bundled resources before writing. Prepare the optional mise bytes as `[tools]` followed by a newline.
- **Create `src/repotainer/scaffold_templates/devcontainer.json`, `src/repotainer/scaffold_templates/Dockerfile`, and `src/repotainer/scaffold_templates/setup.sh`.** Store the files described under [Generated files](#generated-files) and load them with `importlib.resources` relative to the `repotainer` package. Mark the shebang-bearing template `setup.sh` executable for the [repository hook](../../.pre-commit-config.yaml). The generated script is invoked through Bash. Verify wheel inclusion with the existing [build configuration](../../pyproject.toml).
- **Implement creation and cleanup in the writer.** Open files in exclusive binary creation mode and register each new entry as soon as it is created. Record each file's identity from its open descriptor and record the identity of any directory created by this invocation. On failure, compare device and inode values with current no-follow metadata before removal. A missing entry needs no cleanup. Cleanup failures and unverified ownership are reported alongside the original failure. Use a nonrecursive removal for an empty parent created by this run. Follow the [write boundary](#destination-checks-and-writes) for observed replacements.
- **Create `tests/test_scaffold.py`.** Verify exact output and order with and without existing project mise config, including dotfiles, local and environment files, project config directories, fragments, and discovery settings. Cover nested-project and ancestor-only config, blocked parents including a platform-guarded junction case, occupied destinations, alternate dev container configs, metadata and resource failures before writes, and a late parent or destination collision. Inject failures after partial writes and observed entry replacement. Check the original error, cleanup results, preservation of foreign entries, and retry after a clean rollback.

Run `uv run --locked python -m unittest discover -s tests -p test_scaffold.py`. The writer tests must pass before wiring the command.

### 2. Wire the CLI and verify command behavior

- **Modify [src/repotainer/commands/main.py](../../src/repotainer/commands/main.py).** Update the help text and call the writer after the inventory and evidence report. Print the paths created on stdout and exit with status `0` on success. When only three files were created, report that the existing project mise config was preserved. Print conflicts or generation errors and cleanup details to stderr with status `2`. If the conflict result flags an existing root `mise.toml`, list it as preserved separately from blocking paths. Keep exit status `1` for a declined scan and status `2` for existing handled scan errors. Ensure that a completed detection with declaration diagnostics still reaches the writer.
- **Modify [tests/test_repository.py](../../tests/test_repository.py).** Check explicit and default targets, evidence output before the generation report, and both the three-file and four-file successes. Use a clean target for each independent confirmation outcome. Verify that declined or failed scans and unexpected detector failures leave the scaffold absent. Cover multiple concurrent preflight conflicts, including an ignored path, and check all reported paths and unchanged file bytes. Verify reuse of an ordinary `.devcontainer` directory containing unrelated entries.

Run `uv run --locked python -m unittest discover -s tests -p test_repository.py`. The CLI tests must pass with generation enabled.

### 3. Verify the installed release path and update documentation

- **Modify [README.md](../../README.md) and [repository-inspection.md](repository-inspection.md).** Document that the command writes to the target, which configs it preserves, output order, conflicts, and failure and retry behavior.
- **Modify [cli-evidence-output.md](cli-evidence-output.md), [root-command.md](root-command.md), and [repository-inventory.md](repository-inventory.md).** Mark superseded read-only command behavior and evidence-only completion as historical where described. Link those passages to the current scaffold behavior and keep historical verification intact.
- **Modify this design and [SITEMAP.md](SITEMAP.md).** Record implementation status and actual verification results, including the assessed commit or working-tree state.

### Verification plan

- From the checkout, run `uv run --locked repotainer <fixture>` against a temporary Python project without Git metadata. Check status `0`, the evidence before the success message, the exact four output paths, and unchanged inputs. Parse JSON and TOML and check the Dockerfile instructions, setup command, and empty `[tools]` table. Rerun the command. Expect status `2`, all three dev container destination conflicts, and preservation of the existing `mise.toml` and all file contents.
- Run the console command on a fresh project with only an ignored `.mise/config.toml` or a root `mise.<env>.local.toml`. Verify that only the three dev container files are added. Run on a separate fixture containing only an alternate dev container config. Expect a conflict and no added files.
- Run `uv build --wheel --out-dir <artifact-dir>`. Install the resulting wheel into a fresh virtual environment with `uv pip install --python <venv-python> <wheel>`. Run its console entry point with an absolute fixture path from outside the checkout and compare its output files with the checkout run.
- Run `bash -n` and ShellCheck on the generated setup script. Run it in a project without Git metadata with a stub `mise` on `PATH`. Assert that the stub received `install` as its sole argument and that its working directory was the project root. In an isolated fixture with real mise and a benign existing project config, verify that its normal discovery includes that config and that the setup invocation succeeds. Verify the actual container build and post-create hook when a dev container runner is available, and record those results separately.
- Run `uv run --locked python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, `ty check`, `rumdl check AGENTS.md README.md docs`, and `git diff --check`. [Development checks](../development.md#checks)

## Implementation verification

Verified the uncommitted implementation on working-tree base `f2ef6c1` with Python 3.14.6 on Linux on 2026-11-22.

| Check | Result |
| --- | --- |
| Writer and CLI tests | The writer checkpoint ran 16 cases with one Windows-only junction skip. All 15 CLI tests passed. The full suite ran 60 cases, with 59 passing and the Windows-only case skipped. |
| Checkout console command | A temporary Python project without Git metadata printed its inventory and Python evidence before creating the four expected files. JSON and TOML parsed, the Dockerfile matched the agreed baseline, and input bytes were unchanged. A rerun exited with status `2`, listed all three dev container conflicts, preserved `mise.toml`, and left file contents unchanged. |
| Existing configurations | Temporary projects with ignored `.mise/config.toml` or `mise.dev.local.toml` kept those files and received three scaffold files. Root and one-level named dev container configurations each blocked generation. |
| Installed wheel | Built the wheel offline, installed it into a fresh virtual environment with dependencies copied from the locked checkout environment because index access was blocked, and passed `uv pip check`. The console entry point imported the installed package from outside the checkout and produced four byte-identical files. |
| Setup script | Bash syntax and ShellCheck passed. The stub recorded the project root and the sole argument `install`. In an isolated fixture, mise 2026.8.16 discovered `mise.local.toml`, loaded its fixture environment value, and the generated setup script exited successfully. |
| Container build and post-create hook | Docker socket access was denied. The actual image build and dev container lifecycle were unverified. |
| Static and documentation checks | Ruff lint and format, ty, uv lock, Markdown lint, local links, and whitespace checks passed. |

*Drafted with EGM*
