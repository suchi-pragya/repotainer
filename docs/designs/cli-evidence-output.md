# CLI evidence output

- Author: Suchi Pragya
- Status: Author-approved design, EGM review resolved
- Implementation state: Implemented
- Date: 2026-11-21

## Overview

`repotainer [PATH]` scans the directory, uses the built-in rules to collect evidence from the inventory, and prints the result in the terminal. This temporary output gives rule authors a way to check what the rules find in real repositories as coverage grows.

## The Problem

Before this change, the command stopped after reporting the scan root, whether it contains a `.git` directory, and the inventory counts. The detection package already exported `detect` and `BUILTIN_RULES`, which contains the Python runtime, uv, and Poetry rules. Tests passed a scanned inventory and those rules to the detector separately. A rule author needs to see the evidence and any file-read failures in the same run. [Current CLI behavior](repository-inspection.md#behavior-and-architecture) · [Detector contract](repository-evidence-detection.md)

## Goals

- Use the existing scan boundary and exclusions for the supplied directory, or the current directory when `PATH` is omitted. [Scan boundary](repository-inventory.md#choose-the-scan-root)
- After a successful scan, pass the resulting inventory to `detect(inventory, BUILTIN_RULES)` so the normal CLI command evaluates the existing Python runtime, uv, and Poetry rules.
- Print the full detector result in the terminal. Show each tool group with evidence, including the source path and any field or value for each observation. Keep observations from different files and from different tools visible even when they share a source.
- Include read diagnostics in the displayed result so an unreadable declaration is distinguishable from an empty result. Keep observations from other eligible files visible when a declaration fails to read.

## Non-Goals

- Version selection, conflict resolution, and generating or modifying Mise configuration.
- New detection rules and reorganizing the built-in rules into ecosystem modules.
- A stable output format for scripts or a permanent terminal report layout.

## Technical Plan

This section records the CLI at the evidence output milestone. The command now attempts scaffold generation after printing the evidence. See the [current command contract](repository-inspection.md#invariants-and-side-effects) and the [scaffold design](devcontainer-scaffold.md#command-flow) for current write behavior and exit status.

The [root command handler](../../src/repotainer/commands/main.py) owns the handoff. Once `scan_inventory` returns an inventory, the handler calls `detect(inventory, BUILTIN_RULES)` once through the [detection package exports](../../src/repotainer/detection/__init__.py). The detector uses the inventory's scan root and cataloged entries. It evaluates the existing rules and reads matched files as needed. This adds declaration reads to the command without initiating a second directory walk.

```text
repotainer [PATH]
  -> validate the root and report whether it contains a .git directory
  -> scan_inventory
  -> detect(inventory, BUILTIN_RULES)
  -> print inventory counts followed by DetectionResult on stdout
```

Keep the existing output through the inventory counts. Append the Python representation of `DetectionResult` to stdout as the temporary evidence report. It includes every tool group with evidence, the inventory-relative paths, the optional fields and values, and all read diagnostics in the detector's existing order. A matching file can yield no observations. The same observation appears in each tool group that receives it. For example, the `uv.lock` path can appear in both the uv and Python groups, with no version value in either. [Built-in evidence sharing](built-in-detection-rules.md#assemble-the-result) · [Evidence ordering](repository-evidence-detection.md#observation-identity-and-ordering)

| Outcome | CLI behavior |
| --- | --- |
| Detection returns without diagnostics | Print the inventory summary and the result. A result with neither evidence nor diagnostics is empty. The current representation is `DetectionResult(tools=(), diagnostics=())`. Exit with status `0`. |
| Detection returns declaration diagnostics | Print the inventory summary and the result, including the diagnostics and any evidence from other matches. Exit with status `0`. |
| User declines a large scan | Keep the cancellation message on stderr and exit with status `1`. Skip detection. |
| Invalid path, failed scan, or interrupted or unavailable confirmation | Keep the error on stderr and exit with status `2`. Skip detection. |
| Detection raises unexpectedly | Let the exception propagate through the existing CLI error path. The command fails after the initial `.git` message and before printing the inventory success summary or `DetectionResult`. |

The command keeps its positional argument and entry point. The `--help` description mentions evidence detection. The run reads the repository and prints the result without writing files, calling subprocesses, or making network requests.

### Output limits

The detector reads up to 1 MiB plus one byte per matched file it opens to enforce its 1 MiB content limit. The scan confirmation threshold counts entries. Total retained evidence and output can still grow across the scan. Rendering allocates another string, which can grow when values need escaping. Use a narrower scan root when inspecting one part of a large repository. [Reader limits](repository-evidence-detection.md#reader-boundary-and-limits) · [Scan confirmation](repository-inventory.md#large-scans)

The command emits the ordinary escaped Python representation as plain text. Captured stdout can include file paths and extracted declaration values. Detection follows the existing reader contract, which assumes paths stay in place during inspection. [Reader contract](repository-evidence-detection.md#reader-boundary-and-limits)

## Alternatives Considered

### Print a summary of detected tools

A list of tool names would be easy to scan. It would omit the source paths, declarations, and read diagnostics that rule authors need to check the result.

### Format the full result as a terminal report

One line per observation would make long results easier to read. A report would need its own layout for paths, fields, values, and diagnostics, along with code to maintain that layout. The approved plan prints the Python representation directly. Formatting can be revisited if long results become hard to inspect.

### Print or write generated Mise configuration

Mise would use selected versions to set up the development environment. Generating its configuration requires choosing versions and handling disagreements. The resulting file would show the selected version requests, while this milestone needs the evidence behind those choices.

## Detailed Implementation Plan

These steps describe the original CLI output delivery. See [Implementation verification](#implementation-verification) for those results and the [built-in detection rules follow-up](built-in-detection-rules.md#implementation-verification) for verification of shared evidence in the current output.

1. **Modify [src/repotainer/commands/main.py](../../src/repotainer/commands/main.py).** Import `detect` and `BUILTIN_RULES` from `repotainer.detection`. Call the detector once with the completed inventory, outside the scan exception handler and after the cancellation check. Run detection before printing the inventory success summary. Keep the current `.git` message and inventory summary, then append the Python representation of `DetectionResult` to stdout using the command's existing output mechanism. Update `--help` to mention evidence detection and keep the existing `PATH` argument and default.
2. **Modify [tests/test_repository.py](../../tests/test_repository.py).** Add checks for the detector handoff and for output through the normal CLI.
   - Spy on `repotainer.commands.main.detect`. Verify one call with the completed inventory and `BUILTIN_RULES` after a successful scan, including an approved large scan. Verify zero calls for an invalid path, scan error, or declined, defaulted, or unavailable confirmation. Separately check the existing exit statuses and confirm that unsuccessful scans omit `DetectionResult` from stdout. Inject a detector `ValueError` and verify a nonzero exit without a scan-error message, inventory success summary, or `DetectionResult`.
   - Use the real detector with `.python-version` containing `3.13`, `pyproject.toml` containing `[project]` with `requires-python = ">=3.12"` and a `[tool.poetry]` table, and an empty regular `uv.lock`. Expect exit `0` and the result as the final stdout line after `Pruned directories:`. Check two Python observations with their paths and values and the `project.requires-python` field on the manifest observation. Check the separate Poetry observation for the `tool.poetry` field and the uv observation for the `uv.lock` path alone.
   - Use the real detector with malformed `pyproject.toml` and a regular `uv.lock`. Expect exit `0`, the uv observation, and a diagnostic with path `pyproject.toml`, reader `toml`, and reason `invalid-toml`. Check empty evidence and diagnostics in the existing empty case. Keep the current-directory assertions and check the updated help description.
   - **CLI checkpoint.** Run `uv run --locked python -m unittest discover -s tests -p test_repository.py` and `uv run --locked repotainer --help`.
3. **Modify [README.md](../../README.md).** Describe how to inspect a project with `repotainer [PATH]` and explain that the command appends evidence and read diagnostics to the inventory summary. Identify the output as temporary terminal output.
4. **Modify [docs/designs/repository-inspection.md](repository-inspection.md).** Update the current CLI contract to cover the detector handoff, stdout ordering, and the distinction between scan errors on stderr and declaration diagnostics in the printed result. Keep the scanner's file-access contract scoped to the inventory stage.
5. **Modify [docs/designs/root-command.md](root-command.md) and [docs/designs/repository-evidence-detection.md](repository-evidence-detection.md).** Update the root-command workflow to describe the detector call as implemented and link to this design. Add a link from the detector design to the new CLI consumer while keeping the original detection milestone and its verification historical.
6. **Modify [docs/designs/repository-inventory.md](repository-inventory.md).** Mark the counts-only command overview as inventory milestone behavior and link to this design. Preserve the scanner contract and historical verification.
7. **Modify [docs/designs/cli-evidence-output.md](cli-evidence-output.md) and [docs/designs/SITEMAP.md](SITEMAP.md).** Record the implementation state and actual verification results after the change. Keep design approval and implementation status distinct.

### Documentation and final verification checkpoint

- Run `uv run --locked python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, and `ty check`.
- Recreate the three-file success fixture from step 2 in a temporary directory. Run `uv run --locked repotainer --help` and `uv run --locked repotainer <fixture-directory>` through the console script. Expect exit `0` and the same evidence and stdout ordering as in step 2. Compare the fixture's relative paths and file contents before and after the run to verify that it leaves the fixture intact.
- Run `rumdl check AGENTS.md README.md docs` and `git diff --check`. Check the changed documentation links and record the assessed revision or working-tree state and the actual results in this design. [Development checks](../development.md#checks)

## Implementation verification

Verified the uncommitted implementation on working-tree base `a6560b4` on 2026-11-21.

| Checkpoint | Results |
| --- | --- |
| CLI wiring and tests | All 12 tests in `test_repository.py` passed. Console `--help` described evidence output and retained the optional `PATH` argument. The tests covered the detector handoff, empty results, evidence and diagnostics, scan cancellation and failure, and unexpected detector exceptions. |
| Documentation and final verification | All 36 tests passed. Ruff lint and formatting, `ty check`, Markdown lint, local link checks, and `git diff --check` passed. The console smoke run exited `0` and printed the complete Python, uv, and Poetry result after the inventory counts. The fixture's paths and file contents were identical before and after the run. |

The final locked UV checks used a temporary cache because the default cache path was read-only in the verification environment.
