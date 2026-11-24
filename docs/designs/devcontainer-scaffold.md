# Dev container scaffold generation

- Author: Suchi Pragya
- Review status: Author-approved design. All 12 EGM review findings resolved.
- Implementation state: Implemented and [verified locally](#implementation-verification).
- Updated: 2026-11-24

## Overview

Running `repotainer [PATH]` inventories the selected directory, prints detected tool evidence, and recommends tool requests for the generated scaffold. The command can create the three static Dev Container files and a root `mise.toml`. It offers separate approvals for replacing existing files in either group after the scan. [Tool version resolution and approvals](tool-version-resolution.md)

## The problem

Before scaffold generation, the CLI stopped after reporting evidence and users created the container build and setup files themselves. The static scaffold prepares the container and uses the generated tool list. Existing root configurations can be kept or explicitly replaced after the recommendations are available. [Current CLI contract](repository-inspection.md)

## Goals

- Keep `repotainer [PATH]` as the entry point and use the current directory when `PATH` is omitted. Support projects with or without Git metadata.
- Keep the inventory and evidence report. Use bundled templates for the Dev Container files.
- Create missing configuration groups and preserve existing groups unless the user approves replacement.
- Check fixed root destinations before writes. Report blocked paths, and back up the approved originals for recovery.

## Non-goals

- Rendering a project-specific Dockerfile or merging existing configuration.
- Building or starting the container during the Repotainer invocation. The Dev Container runner builds the image and invokes the setup script.

## Technical plan

### Command flow

The [root command](../../src/repotainer/commands/main.py) runs the inventory and detector, prints evidence, and derives recommendations from the detected tool groups. It inspects the root destinations, collects any required version choice, and asks about replacements after showing the proposed writes. The writer applies the plan once the decisions are complete. A declaration-read diagnostic can coexist with other usable evidence. [Current CLI contract](repository-inspection.md) · [Version and replacement policy](tool-version-resolution.md#technical-plan)

```text
repotainer [PATH]
  → resolve root → inventory → detect → print evidence
  → recommend requests → inspect root destinations → show choices and preview
  → obtain separate approvals → back up approved originals → write scaffold
```

### Generated files

| Destination | Contents |
| --- | --- |
| `.devcontainer/devcontainer.json` | Uses `.` as the build context relative to the config file, `Dockerfile` as the build file, and `bash .devcontainer/setup.sh` as `postCreateCommand`. |
| `.devcontainer/Dockerfile` | Uses `mcr.microsoft.com/devcontainers/base:ubuntu26.04`, copies the mise binary from `jdxcode/mise` to `/usr/local/bin/`, and activates mise in the `vscode` user's Bash and Zsh startup files. The hand-maintained template omits the uv, `python3`, and `tmux` installation steps from [Repotainer's development Dockerfile](../../.devcontainer/Dockerfile). |
| `.devcontainer/setup.sh` | Runs Bash with strict error handling, derives the workspace root from the script location without invoking Git, and runs `mise install` from that root. |
| `mise.toml` | Created when root `mise.toml` is absent or replaced with explicit approval. Contains one resolved request per selected tool and an empty `[tools]` table when the selection is empty. |

The three static Dev Container templates ship with Repotainer and contain no project-specific settings or host token forwarding.

The setup script uses mise's normal discovery, environment selection, and trust behavior inside the container. Running `mise install` can install tools and run configured hooks. Mise can also load other configuration available in that container. Repotainer's root-only presence check controls file generation only. The setup command passes any install failure to the dev container runner. [Mise configuration](https://mise.jdx.dev/configuration.html) · [Mise trust](https://mise.jdx.dev/cli/trust.html)

The templates produce identical bytes for a given Repotainer build. Building the container requires Docker and access to the base and mise images. Image tags can move, so identical scaffold files can produce different images. [Docker image tag behavior](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)

### Project mise configuration

Inspect only `mise.toml` at the selected root for the scaffold preview and writes. The check uses the destination path independently of inventory exclusions. The preview can summarize tool requests from an existing regular file. Alternate and nested Mise configurations remain outside this workflow. Mise can discover other configuration when it runs in the container. [Replacement scope](tool-version-resolution.md#replacement-scope)

### Destination checks and writes

Inspect root `mise.toml` and the three generated files directly in the root `.devcontainer/` directory. Reuse an ordinary directory. A symlink, Windows junction, or non-directory at `.devcontainer/` blocks writes, as does a non-regular entry at any generated file path. Other files in the directory stay outside the write plan. A regular file can be replaced by approving its group after the preview. [Root paths and approval](tool-version-resolution.md#review-and-approve-writes-after-scanning)

Back up all approved originals before writing. Create new files exclusively and stage replacement bytes beside each destination before replacing it. Write in Dockerfile, setup script, Mise, and Dev Container configuration order, skipping declined groups. On a handled error, remove identifiable files created during the run and restore originals already replaced. Retain and report a backup if restoration fails. Abrupt termination while writing can leave partial output and a backup. [Backup and restore contract](tool-version-resolution.md#back-up-and-restore-approved-replacements)

## Alternatives considered

### Require an explicit generation command or flag

A separate invocation would preserve the read-only behavior of `repotainer [PATH]` and add a step for users who want the scaffold. The existing invocation will generate the scaffold after preflight.

### Populate mise config from evidence in the first milestone

The original scaffold milestone reused existing Mise config or supplied an empty table so users could try generation while selection rules were being developed. The follow-up milestone populates the table from detected tools. [Mise tool configuration](mise-tool-configuration.md)

### Generate over an existing dev container setup

The original scaffold milestone blocked generation at existing destinations. The follow-up supports explicit replacement of the three generated files after the user reviews the plan. Merging configuration remains outside that workflow. [Replacement scope](tool-version-resolution.md#replacement-scope)

### Keep files after a partial write failure

Keeping those files would avoid cleanup work, but users would need to clear scaffold conflicts before retrying. The original milestone removed identifiable files created by the failed run. Approved replacement adds restoration of backed-up originals.

## Detailed implementation plan

These steps describe the original scaffold milestone. The [tool version resolution plan](tool-version-resolution.md#detailed-implementation-plan) owns the current writer interfaces and replacement behavior.

This historical plan describes the original static scaffold milestone.

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

These checks describe the original scaffold milestone.

- From the checkout, run `uv run --locked repotainer <fixture>` against a temporary Python project without Git metadata. Check status `0`, the evidence before the success message, the exact four output paths, and unchanged inputs. Parse JSON and TOML and check the Dockerfile instructions, setup command, and empty `[tools]` table. Rerun the command. Expect status `2`, all three dev container destination conflicts, and preservation of the existing `mise.toml` and all file contents.
- Run the console command on a fresh project with only an ignored `.mise/config.toml` or a root `mise.<env>.local.toml`. Verify that only the three dev container files are added. Run on a separate fixture containing only an alternate dev container config. Expect a conflict and no added files.
- Run `uv build --wheel --out-dir <artifact-dir>`. Install the resulting wheel into a fresh virtual environment with `uv pip install --python <venv-python> <wheel>`. Run its console entry point with an absolute fixture path from outside the checkout and compare its output files with the checkout run.
- Run `bash -n` and ShellCheck on the generated setup script. Run it in a project without Git metadata with a stub `mise` on `PATH`. Assert that the stub received `install` as its sole argument and that its working directory was the project root. In an isolated fixture with real mise and a benign existing project config, verify that its normal discovery includes that config and that the setup invocation succeeds. Verify the actual container build and post-create hook when a dev container runner is available, and record those results separately.
- Run `uv run --locked python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, `ty check`, `rumdl check AGENTS.md README.md docs`, and `git diff --check`. [Development checks](../development.md#checks)

## Implementation verification

The original static scaffold milestone was verified on working-tree base `f2ef6c1` with Python 3.14.6 on Linux on 2026-11-22. See the [Mise tool configuration verification](mise-tool-configuration.md#implementation-verification) for the populated-table milestone.

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
