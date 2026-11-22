# Mise tool configuration from repository evidence

- Author: Suchi Pragya
- Review status: Author-approved design. All ten EGM review findings resolved.
- Implementation state: Implemented and [verified locally](#implementation-verification).
- Updated: 2026-11-22

## Overview

When the selected root has no Mise configuration at a recognized location, Repotainer will use its existing Python and uv detection rules to populate the generated `mise.toml`. Each detected tool in this milestone gets the literal value `"latest"`. The generated file gives developers an editable tool list for the Dev Container setup. [Existing detection rules](repository-evidence-detection.md#initial-rules) · [Scaffold generation](devcontainer-scaffold.md)

## The problem

Repotainer already prints evidence for Python and uv, but it creates a `mise.toml` with an empty `[tools]` table. Developers still have to turn the printed evidence into tool entries before the scaffold can install those tools. Filling that table is the first step toward using repository declarations to configure the environment.

A floating `"latest"` request can install a Python version outside the project's declared range, and the installed version can change over time. For this iteration, success means that the generated file lists the tools Repotainer detected. Applying the project's version declarations comes in the next iteration.

## Goals

- Use the existing Python and uv rules as the source of tool evidence.
- Put one entry under `[tools]` for each detected tool in scope. Write `"latest"` for each entry, even when the evidence includes a version declaration.
- Create `mise.toml` only when the scaffold's existing check finds no Mise configuration at a recognized location anchored at the selected root. Preserve existing files. [Project Mise configuration](devcontainer-scaffold.md#project-mise-configuration)

## Non-goals

- Version lookup, compatibility checks, and conflict resolution. Keep those for the next iteration.
- Generating Mise entries for tools beyond Python and uv.
- Syncing project dependencies or changing the Dev Container templates.

## Technical plan

### From detection to configuration

The [root command](../../src/repotainer/commands/main.py) already receives a `DetectionResult` after scanning. Reuse that result for the terminal report and tool selection. Each nonempty `python` or `uv` group produces one entry using the returned evidence from the entire scan, including shared evidence. Leave the registry and detection rules intact. [Detector handoff](repository-evidence-detection.md#handoff-to-mise-generation)

The detector shares evidence from `uv.lock` with the Python group, so the lockfile can contribute both tools. A detected `[tool.poetry]` table can also supply Python evidence through this mechanism. Poetry evidence, version values, and diagnostics remain visible in the report. Each selected tool gets the same `"latest"` request, including when readable files declare conflicting versions.

```text
Repository inventory → Existing detector → Detection result
                                              ├─ Evidence report
                                              └─ Select Python and uv → Scaffold writer
```

### Render and write

The command passes the selected tool IDs to the [scaffold writer](../../src/repotainer/scaffold.py), which renders each ID with the fixed request `"latest"` for this milestone. The writer owns destination checks, existing Mise configuration discovery, and file creation. When the existing check permits creating `mise.toml`, write the `[tools]` header followed by one line per selected tool in alphabetical order, with a final newline. With zero selected tools, keep the current header-only file. Repotainer performs no version lookup or install during generation.

Reuse the current exclusive creation, write order, and cleanup behavior for the generated file. When the existing Mise check finds a config, skip writing `mise.toml` and preserve the existing files byte-for-byte. The writer checks Dev Container destination conflicts after detection and before any files are written. Moving that check before inventory is deferred. [Destination checks and writes](devcontainer-scaffold.md#destination-checks-and-writes)

### Container setup

When a Dev Container is created, its existing post-create script runs `mise install` from the workspace root. This milestone uses that hook so the generated tool list feeds the existing installation step. Repotainer adds requests only for Python and uv. Developers can review and edit the generated `mise.toml` after generation and before creating the container. The Dev Container runner receives any failure from `mise install`, including failures caused by network access or configuration trust. [Scaffold setup behavior](devcontainer-scaffold.md#generated-files)

### Evidence scope

Whole-scan evidence covers layouts where declarations live below the selected root and may also include tools used only by examples or nested projects. Users can select a subdirectory to limit both scanning and generation to that directory. [Scan-root behavior](repository-inventory.md#choose-the-scan-root)

The writer checks recognized Mise configuration locations anchored at the selected root, independently of inventory ignore rules. With `app/uv.lock` and `app/mise.toml`, selecting the parent can produce a parent `mise.toml` from the nested lockfile evidence. Selecting `app` preserves its existing `mise.toml`. Mise can load other configuration through its normal discovery when the container setup runs. [Project Mise configuration](devcontainer-scaffold.md#project-mise-configuration)

### Expected results

| Input | Expected outcome |
| --- | --- |
| A root `.python-version` containing a single nonblank version line such as `3.13` | `python = "latest"` |
| Root `uv.lock` | `python = "latest"` and `uv = "latest"`, once each |
| A nested `uv.lock` with no supported evidence at the root | Both entries in the selected root's `mise.toml` |
| Root `[tool.poetry]` evidence only | `python = "latest"` through evidence sharing |
| Conflicting root Python version declarations | `python = "latest"`. Both declarations remain in the evidence report. |
| An unreadable or malformed root `pyproject.toml` and a root `uv.lock` | Both tool entries. The manifest diagnostic remains visible. |
| No nonempty Python or uv detector groups | The existing empty `[tools]` table |
| An existing Mise config at a recognized location anchored at the selected root | Existing config stays byte-for-byte identical. Skip creating a new `mise.toml`. |
| A Dev Container destination conflict | The existing conflict report. Generation creates zero files. |

## Alternatives considered

### Select tools using only evidence at the root

This would match only declarations directly in the directory passed to Repotainer. It would keep a nested example's tools out of the top-level configuration, but a repository with all its declarations below the root could get an empty tool table. The author chose the whole scan so tool selection covers the same directory tree as the existing detection report.

### Apply version declarations in this milestone

This would use version evidence to make more specific tool requests. It would reduce the risk of installing an incompatible runtime, but it would require rules for combining pins and ranges and handling contradictions. The author deferred version resolution to the next iteration so this milestone can establish which tools flow from detection into the generated file. The existing report retains the declarations that the later rules can use.

## Detailed implementation plan

1. **Modify [src/repotainer/scaffold.py](../../src/repotainer/scaffold.py).** Extend `write_scaffold` with a keyword-only `selected_tools` argument of type `tuple[str, ...]`, defaulting to an empty tuple for callers that only need the baseline scaffold. The argument carries unique internal tool IDs selected by the caller. Pass them to `_template_payloads`. When the existing Mise presence check permits generation, build UTF-8 bytes with `[tools]` on the first line and one `<tool> = "latest"` line per ID in alphabetical order. Use an LF after every line. With no tools, the bytes are exactly `[tools]\n`. Keep the Mise payload in the existing write sequence between `setup.sh` and `devcontainer.json` so the same conflict, exclusive creation, and rollback logic covers it.
2. **Modify [tests/test_scaffold.py](../../tests/test_scaffold.py).** Keep the current empty-table test. Verify that passing uv and Python in reverse order produces the exact alphabetical UTF-8 bytes and parses to the two expected TOML entries. Exercise the supported existing-config locations with a nonempty selection and confirm the same paths and bytes are preserved. Run the existing partial-write and retry case with a nonempty selection so it proves that cleanup covers a populated `mise.toml` created before the final config write.
3. **Modify [src/repotainer/commands/main.py](../../src/repotainer/commands/main.py).** After printing the existing report, select the IDs of the nonempty `python` and `uv` groups in `DetectionResult.tools` and pass the tuple by keyword to `write_scaffold`. The detector provides one group per tool, with paths from the whole scan. The command needs no path-depth filter, version parser, or second scan. Use the fixed IDs as the allowlist so future detection rules cannot add new Mise entries by themselves. Keep the existing report, exit statuses, and preservation and conflict messages.
4. **Modify [tests/test_repository.py](../../tests/test_repository.py).** Extend the evidence-report fixture to assert that multiple observations yield one entry per tool and that Poetry receives no entry. Extend the malformed-manifest fixture to check that valid uv evidence still generates both tool entries. Add focused cases for a nested-only `uv.lock`, Poetry-only evidence contributing Python, and conflicting Python declarations yielding one `"latest"` request while both declarations remain in the report. Give the ignored existing Mise configuration fixture positive detection evidence so it proves that preservation takes precedence even when tools were selected. Add a separate fixture with `uv.lock`, a conflicting root `.devcontainer.json`, and no Mise configuration. Expect status `2` and `.devcontainer.json` in the conflict list. Compare the relative paths and file bytes before and after invocation and confirm that neither `mise.toml` nor a scaffold directory was created. Keep the existing no-evidence, scan failure, conflict, and generation error assertions.
5. **Modify [README.md](../../README.md).** Explain that a new `mise.toml` lists detected Python and uv with floating `"latest"` values, with an empty table when neither is detected. Tell users they can review and edit the file before creating the Dev Container. Explain that its post-create script invokes `mise install`, which resolves the requested versions. A resolved version can differ from a version declared by the project, and installation failures surface in the runner after successful generation.
6. **Modify [repository-inspection.md](repository-inspection.md).** Update the current command flow and writer interface to show the selected-tool handoff. Link the selection rules to this design so the current contract and the feature policy have clear owners.
7. **Modify [devcontainer-scaffold.md](devcontainer-scaffold.md).** Update the overview, goals, non-goals, command flow and diagram, and generated-files table to describe the selected-tool handoff and optional populated `mise.toml`. Link selection and value policy to this design. Mark the original rollout and verification as historical. Keep its existing configuration discovery and write-safety rules as the authority for the writer.
8. **Modify [repository-evidence-detection.md](repository-evidence-detection.md).** Update **Handoff to Mise generation** to identify the command as the consumer of the existing detection result and link to the implemented selection and writer flow. State that version reconciliation remains deferred.
9. **Modify [this design](mise-tool-configuration.md) and the [design index](SITEMAP.md).** Record implementation and verification against the tested revision or working tree after the checks below. Keep implementation and author review status distinct.

### Verification plan

Run the checkpoints in this order. Each checkpoint must pass before proceeding.

1. After the writer and scaffold test changes, run `uv run --locked python -m unittest discover -s tests -p test_scaffold.py`. Require the empty and populated outputs, preservation, and rollback tests to pass.
2. After wiring the CLI and updating its tests, run `uv run --locked python -m unittest discover -s tests -p test_repository.py`. Require the selection, reporting, preservation, and destination conflict tests to pass.
3. After updating the documentation, check local links and heading anchors. Run `uv run --locked python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, `ty check`, `rumdl check AGENTS.md README.md docs`, and `git diff --check`. Complete the smoke cases below.

Use `uv run --locked repotainer <fixture>` for each smoke case.

- Use two identical clean targets containing only `app/uv.lock`. Expect status `0` and identical `mise.toml` bytes with the entries in alphabetical order. Parse both outputs with `tomllib` and verify `python = "latest"` and `uv = "latest"`. Compare the input `app/uv.lock` bytes before and after each run. Rerun on one generated tree. Expect status `2`, conflicts at `.devcontainer/Dockerfile`, `.devcontainer/devcontainer.json`, and `.devcontainer/setup.sh`, the message `Preserved existing mise.toml.`, and unchanged paths and bytes for the entire fixture.
- Use a fresh target with `uv.lock`, `.mise/config.toml`, and a `.gitignore` containing `.mise/`. Expect status `0` and the message `Preserved existing project mise configuration.` Verify that the only added files are `.devcontainer/Dockerfile`, `.devcontainer/setup.sh`, and `.devcontainer/devcontainer.json`. Compare the input file bytes and confirm that there is no root `mise.toml`.

This milestone verifies generated configuration and write behavior. Container installation and Python compatibility are outside this verification.

## Implementation verification

Verified on the working tree based on `284d785` on Linux with Python 3.14.6 on 2026-11-22.

| Check | Result |
| --- | --- |
| Scaffold and CLI checkpoints | The scaffold module ran 17 cases, including rollback of a populated Mise file, with one Windows-only junction case skipped. All 19 CLI cases passed, including the fresh Dev Container conflict. |
| Full suite | 64 passed and one Windows-only junction case skipped. Ruff lint and format checks and ty passed. |
| Nested evidence and repeat generation | Two fresh fixtures with only `app/uv.lock` exited with status `0` and produced byte-identical Mise files. The files parsed with Python and uv set to `"latest"`, in alphabetical order, and the input lockfiles kept their original bytes. |
| Conflict on rerun | The console command exited with status `2`, reported all three Dev Container destinations, reported preserving `mise.toml`, and left every fixture path and file unchanged. |
| Existing configuration | The console command exited with status `0`, added only the three scaffold files, and preserved all inputs, including the ignored `.mise/config.toml`. It reported preservation and created no root `mise.toml`. |

The smoke checks used a temporary writable uv cache because the default cache was read-only in the test environment.
