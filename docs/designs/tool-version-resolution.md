# Tool version resolution from repository evidence

- Updated: 2026-11-24
- Author: Suchi Pragya
- Review status: Author-approved design. All 11 EGM review findings resolved.
- Implementation state: Implemented and [verified locally](#implementation-verification).

## Overview

Repotainer will use version declarations from the selected scan to recommend tool requests for Mise. The resolution policy applies across tools, with Python as the first case because Repotainer already reads `.python-version` and `project.requires-python`. The host derives requests from repository evidence. Before writing files, Repotainer shows its recommendations and collects separate decisions for replacing existing Dev Container and Mise configuration. The Dev Container post-create script runs `mise install` to attempt installation. [Version format research](../../version-format-research.md) · [Current Mise generation](mise-tool-configuration.md#from-detection-to-configuration)

## The problem

The original scaffold requested `latest` for every selected tool even while reporting version declarations. A repository could explicitly request Python `3.12.8` and declare compatibility with `>=3.12.5,<3.13`, yet the generated container could install a Python release outside that range. Developers had to translate the evidence into a usable tool request themselves. [Previous milestone](mise-tool-configuration.md#expected-results) · [CLI verification](../../tests/test_repository.py)

Declarations can express different things. A version file may ask for a particular release or series, while a manifest gives a compatibility range. They can agree even when the strings differ. The selected scan can also include several packages whose requirements are incompatible. Version resolution needs to use each tool's comparison rules, preserve the source of each declaration, and explain which evidence drove the generated setting.

## Goals

- Consider all version evidence the detector finds for a tool within the selected scan, including nested packages and examples. Scanning a subdirectory limits consideration to evidence from that scan. A declaration's directory depth gives it no extra priority. [Scan-root behavior](repository-inventory.md#choose-the-scan-root)
- Keep extraction independent of comparison. Interpret a value using its declaration type and the tool's version rules. Retain the file path, field, and original value for diagnostics and choices.
- Preserve an exact requested version when every applicable declaration accepts it. For a range with a lower bound, choose the lowest compatible major and minor. Let Mise choose the patch within that series when the patch range is open above. For a finite patch range, request the highest permitted stable patch by number. Leave availability to the normal Mise install step inside the container.
- Apply an explicit, per-tool order of precedence when the declarations conflict. For Python, `project.requires-python` takes precedence over `.python-version`. Report which evidence was overridden and why.
- When equally ranked evidence leaves a conflict, show a numbered selection in interactive runs if at least one declaration yields a request. List each option with its source files, fields, and declared values. Put `latest` last and wait for a valid selection before writing. In unattended runs or when no declaration yields a candidate, report the conflict and use `latest` for the affected tool. Use `latest` also when a detected tool has no version evidence.
- Generate version requests offline on the host, including when existing configuration is present. Show the current configuration and proposed changes after scanning. Ask for independent approval before replacing the root Mise file or root Dev Container scaffold files. Preserve existing files when replacement is declined or the run is unattended. [Replacement scope](#replacement-scope)

## Non-goals

- Host-side Mise installation, CLI or SDK integration, remote release catalog lookup, and GitHub authentication.
- Release availability checks during generation or container setup, beyond what Mise does during installation. Automatic retries with a different version after setup failure.
- Adding detectors for every versioning ecosystem in this iteration. Python provides the first concrete resolution rules. Other detected tools can continue to use the no-version fallback when they supply no version evidence.
- Discovery and replacement of alternate or nested Mise and Dev Container configurations as part of the recommendation and approval workflow.

## Review results and resolution

Suchi Pragya accepted the resolutions for all three blockers, six major findings, and two wording findings. The technical and implementation sections record the accepted decisions.

## Critical user journeys

### Use the repository's requested interpreter

A developer runs `repotainer` in a directory where `.python-version` requests `3.12.8`, `pyproject.toml` declares `>=3.12.5,<3.13`, and the scaffold can create `mise.toml`. Repotainer generates `python = "3.12.8"` without prompting. Mise attempts to install that release when the container starts its setup.

### Choose a version for a scan with incompatible projects

The root `pyproject.toml` declares `>=3.13,<3.14` and `examples/legacy/pyproject.toml` declares `>=3.12,<3.13`. An interactive root run offers `3.12`, `3.13`, and `latest`, in that order. It includes the two declarations and their paths, then waits for a numbered selection. An unattended root run prints the conflict and writes `latest`. A run scoped to `examples/legacy` writes `3.12` without prompting.

### Resolve a nested manifest against a root pin

The root `.python-version` pins `3.13.2` and `examples/legacy/pyproject.toml` declares `requires-python = ">=3.12,<3.13"`. A root scan reports both paths, explains that the higher-priority manifest determines the recommendation, and requests `3.12`. Precedence resolves the conflict without a version menu. In a fresh fixture, `repotainer examples/legacy` sees only the nested requirement and creates the scaffold and `mise.toml` under `examples/legacy`.

## Technical plan

```text
Selected scan → Inventory → DetectionResult → Tool version resolution
                                  │                      │
                                  ▼                      ▼
                            Evidence report       Requests, diagnostics,
                                                  or conflict candidates
                                                         │
                                                         ▼
                              CLI shows evidence and current configuration
                                                         │
                                                         ▼
                             CLI collects version and replacement choices
                                                         │
                                                         ▼
                                   Scaffold writer applies approved writes
                                                         │
                                                         ▼
                                      Dev Container runs mise install
```

### Evidence and tool rules

Reuse the completed `DetectionResult`. Each `ToolEvidence` group identifies the tool and contains `Evidence` records with a scan-relative path, an optional field, and an optional value. The detector continues to own file matching, reading, and extraction. The resolver interprets the extracted declarations in memory using their source and field. It does not reopen files, search ancestor directories, or give root declarations priority over nested declarations of the same type. [Detection model](../../src/repotainer/detection/model.py) · [Python evidence rule](../../src/repotainer/detection/rules/python.py)

The resolver diagnoses only declarations returned as version evidence. The existing detector omits empty or multiline `.python-version` files and blank or non-string `project.requires-python` values. Treat those omitted values as absent during resolution. Preserve existing file-read and TOML diagnostics in the evidence report. [Python evidence rule](../../src/repotainer/detection/rules/python.py)

Keep the existing Python and uv allowlist for generated Mise entries. Python version declarations come from `.python-version` and the `project.requires-python` field. The detector uses `uv.lock` as evidence that Python and uv are present, with no version request for either. A `tool.poetry` table likewise establishes Python presence without a version request. Each tool that gains version-bearing evidence needs source rules that identify whether a value supplies an exact version, a prefix, or a range. [Detector handoff](repository-evidence-detection.md#handoff-to-mise-generation)

### Per-tool resolution

The resolver receives the selected tool's evidence and produces a Mise request, which may be `latest`, or a conflict with candidate requests and their source declarations. Diagnostics retain the extracted values and identify the tool and source. The CLI owns terminal output and user interaction. The scaffold writer consumes the final per-tool requests.

| Evidence outcome | Resolution |
| --- | --- |
| No version-bearing declaration | Use `latest` for the detected tool. |
| A declaration in the highest-priority tier is malformed or unsupported | Use `latest` with a warning and continue generation. Lower-priority declarations cannot supply a replacement request in this case. |
| A declaration in a lower-priority tier is malformed or unsupported | Warn and resolve using the supported declarations. |
| A supported exact request satisfies all supported declarations | Preserve the exact request. |
| Supported prefixes or ranges have a shared stable candidate | Determine the series and patch request from their intersection using the rules below. |
| The supported declarations have an empty intersection | Resolve from the highest-priority tier alone and report any lower tiers that were set aside. |
| The highest-priority tier has an empty intersection | Derive candidate requests from that tier's individual declarations. Apply the interactive or unattended policy below. |
| Supported constraints overlap, but no usable request can be derived | Use `latest` with a warning about why the constraints could not yield a request. |

For unusable version evidence, the warning names the tool, scan-relative path, field when present, extracted value, and reason. If the result is `latest`, explain that Repotainer could not establish compatibility with the declaration. For example, if `project.requires-python` is `>=3.15.0rc1,<3.16` and `.python-version` is `3.13.7`, write `python = "latest"` and identify the unsupported prerelease bound in the manifest. When both sources are supported, the normal agreement and conflict rules apply.

### Apply precedence after a conflict

Compare all supported declarations for the tool before applying precedence. If they agree, keep a compatible exact pin or resolve their shared constraints. If they conflict, intersect the supported declarations at the highest priority and resolve from that tier alone. Lower-priority evidence remains visible for explanation, even when it agrees with the highest tier. For example, root `requires-python = ">=3.13,<3.14"`, root `.python-version = 3.13.7`, and `examples/legacy/.python-version = 3.12.8` produce `3.13` once the resolver applies precedence. The manifest determines the request because the full set conflicts.

If the highest-priority tier also conflicts, derive at most one Mise request per declaration in that tier. Group identical requests and retain every contributing path, field, and extracted value. Include declarations with no usable standalone request in the conflict diagnostic. This keeps candidate generation bounded by the number of declarations and defers searching compatible groups of declarations.

### Offline Python release selection

Repotainer owns one resolver for stable numeric versions. Compare major, minor, and patch as integer triples. Build exact pins, series prefixes, and ranges with exclusions from the meaning of the source field. The shared resolver compares those constraints, applies precedence, and selects a request. Python supplies the first source translations. Future sources that fit the same model reuse the resolver, and new ordering or constraint semantics can be added when actual evidence requires them. The initial resolver uses the Python standard library alone.

In `.python-version`, a canonical `major.minor.patch` is exact and `major.minor` constrains the series. In `project.requires-python`, accept a comma-separated conjunction of the PEP 440 numeric forms of `>=`, `>`, `<=`, `<`, `==`, `!=`, and `~=` with up to three release components. Accept one- or two-component wildcard prefixes with `==` and `!=`. Pad a numeric operand with zeroes for ordered comparison and exact equality. Preserve its component count when interpreting a wildcard or `~=`. For example, `~=3.12.5` means `>=3.12.5,==3.12.*`. Prereleases, dev and post releases, epochs, local or build labels, alternate runtimes, channels, and arbitrary equality are unsupported in this iteration. [Python version specifiers](https://packaging.python.org/en/latest/specifications/version-specifiers/)

Preserve a compatible exact pin first. For the numeric subset, represent allowed stable versions as intervals over triples. Intersect the positive bounds and subtract excluded versions and prefixes. Convert a strict lower bound on a release triple to the next patch. A series prefix spans from patch zero through the start of the next series, excluding that next series. For an excluded version, split at the excluded triple and its next patch. An excluded series can be skipped at its endpoint. This arithmetic uses only boundaries from the declarations and terminates without enumerating patches or asking which versions were released. An empty intersection of supported constraints is distinct from an unsupported declaration.

With a lower bound, exact constraint, or positive series constraint, take the earliest allowed major and minor. For an upper-only range with no exact pin, use the newest series the cap identifies arithmetically. For example, `<3.12` selects the `3.11` series. When a cap crosses a major-version boundary and gives no last eligible minor, leave the request unresolved unless other evidence determines it. An exclusion alone does not identify a series.

Within the selected series, inspect the allowed patch numbers. If they form a contiguous unbounded tail, write the series as the Mise request. This includes a patch floor such as `>=3.13.4`. The prefix delegates patch selection to Mise and carries no separate floor check. If the allowed patch numbers have a finite maximum, write that exact triple after testing it against the retained constraints. If the set is unbounded and has holes that a prefix could admit, leave the request unresolved. Neither generation nor the generated setup performs a separate availability lookup. Mise attempts the requested install, so the highest permitted patch by number may be unavailable. [Mise Python version requests](https://mise.jdx.dev/lang/python.html#choosing-a-version)

| Evidence | Mise request or outcome |
| --- | --- |
| `.python-version` is `3.11.9` and `requires-python` is `<3.12` | `3.11.9` |
| `.python-version` contains `3.12` | `3.12` |
| `requires-python` is `==3.12` | `3.12.0` |
| `requires-python` is `==3.12.*` | `3.12` |
| `requires-python` is `>=3.12,!=3.12.*` | `3.13` |
| `requires-python` is `<3.12` | `3.11` |
| `requires-python` is `>=3.13.4` | `3.13` |
| `requires-python` is `>=3.13.4,<3.13.8` | `3.13.7` |
| `requires-python` is `>=3.13.4,<3.13.8,!=3.13.7` | `3.13.6` |
| `requires-python` is `>=3.13.4,<3.13.8,!=3.13.*` | Empty intersection in the supported domain. |

Successful scaffold generation confirms that Repotainer wrote the request. Installation happens separately during the Dev Container's post-create step. If `mise install` fails because the requested release is unavailable for that target, the Dev Container runner reports the failure. The user can edit the generated `mise.toml` and retry setup with a known available version that still satisfies the project. For example, if `3.13.7` is unavailable, `3.13.6` can also satisfy `>=3.13.4,<3.13.8` if Mise can install it for that target. [Current post-create behavior](devcontainer-scaffold.md#generated-files)

### Conflict interaction and scaffold generation

The CLI prints the evidence that drove the request and the evidence set aside by precedence. The menu lists requests from the highest-priority tier. Within that tier, order distinct requests by their earliest contributing scan-relative path and field, in lexical order, and put `latest` last. If `examples/legacy/pyproject.toml` yields `3.12` and both `packages/api/pyproject.toml` and `packages/worker/pyproject.toml` yield `3.13`, show `3.12`, `3.13` with both sources, and `latest`. Wait for a valid choice before writing. If the run is unattended or no declaration produces a usable candidate, report the conflict and select `latest` without prompting. A choice or fallback sets an installation request even though the declarations remain incompatible.

### Review and approve writes after scanning

Finish the selected scan and prepare a recommendation even when an existing Dev Container or Mise configuration is present. Show the detected declarations, the existing configuration, the proposed requests, and any version conflict. Collect version choices and present the exact replacement paths and changes before requesting approval to replace an existing file. Complete the required decisions before creating or modifying files.

Dev Container and Mise replacements have separate approvals. If both are present, ask about Dev Container files first and Mise configuration second. A yes applies only to the group named in that prompt. A no preserves that group and still lets the user decide about the other. An unattended run preserves existing files. For example, a user can accept a recommended Dev Container update and keep their current `mise.toml`.

### Terminal input and cancellation

After inventory completes, offer version choices and replacement approvals only when both stdin and stderr are terminals. Send menus, prompts, conflict diagnostics, and warnings to stderr. Keep the evidence and final file report on stdout. Redirecting stdout alone, such as with `repotainer . > report.txt`, still permits interaction. If stdin or stderr is redirected, use the unattended version fallback for ties and preserve existing configuration.

Require a valid numbered menu selection and retry invalid input. Choosing `latest` from the menu requires selecting its number. If EOF or Ctrl+C interrupts a version or replacement prompt, print a cancellation message to stderr, exit with status `2`, and perform no scaffold writes or backups. An explicit decline of one replacement group still permits the remaining decisions. These rules apply to the version and replacement steps after inventory. The existing large-scan confirmation has its own policy. [Current large-scan confirmation](repository-inventory.md#large-scans)

### Validate requests and display evidence

Before rendering a plan, accept only known tool IDs and at most one request per tool. For Python, accept a canonical stable numeric series or exact release triple, or `latest`. For uv, accept `latest`. An invalid request reaching the writer is a planning error and stops before any backup or scaffold write. An invalid repository declaration follows the [unusable-evidence policy](#per-tool-resolution). Its extracted value remains available for the diagnostic.

Render validated values as quoted TOML strings in alphabetical tool order. The initial request formats contain only ASCII digits, dots, or the literal `latest`, so the existing quoted form is sufficient. Render repository-derived paths, fields, and extracted values as literal, single-line text in menu labels and diagnostics. Escape line breaks and control characters for display while retaining the extracted data for comparison and provenance. For example, a newline in a path is shown as `\n` in one menu option.

### Replacement scope

The replacement workflow checks these paths relative to the selected project root. The writer proposes changes to individual scaffold files. It never replaces the `.devcontainer/` directory as a unit.

| Approval group | In-scope paths |
| --- | --- |
| Mise | `mise.toml` |
| Dev Container | `.devcontainer/devcontainer.json`, `.devcontainer/Dockerfile`, `.devcontainer/setup.sh` |

Other files in `.devcontainer/` remain outside the preview and write set, along with alternate and nested configurations. Version evidence still comes from the entire selected scan. Keep the path list with the scaffold writer so later additions can use the same preview and approval flow. This changes the existing preserve-or-conflict policy for eligible files. The CLI constructs version choices and collects consent. [Current destination and write behavior](devcontainer-scaffold.md#destination-checks-and-writes) · [Current scaffold paths](../../src/repotainer/scaffold.py)

Assume the checkout and scaffold destinations stay in place throughout the run, including while the user reviews the preview. After approval, the writer applies the approved replacements using that plan directly. New destinations use exclusive creation.

### Back up and restore approved replacements

After collecting both approval decisions, back up every existing regular file the run will replace. Complete all backups before the first scaffold write. The backup contains only the original files in the approved write plan and keeps their relative paths. A create-only run has no existing files to back up. If a backup fails, stop before writing scaffold files and report the failure.

On a handled write failure, remove files created by this run and restore all backed-up originals that the run replaced or removed. Include writes from both groups when both were approved. Remove a newly created `.devcontainer/` directory only if it is empty. Report the original write failure and the recovery result. Remove the temporary backup after successful writes or successful recovery. If restoration fails, retain the backup and report its location and the paths that still need recovery. If backup cleanup fails after a successful write or restore, report where the backup remains.

## Alternatives considered

### Always request `latest`

The current behavior keeps generation simple and lets Mise select a release at setup time. A newer release can fall outside a declared range or differ from the version the project uses for development. Use a repository-derived request wherever the resolution rules produce one. Keep `latest` for missing evidence, the specified fallbacks, and the final interactive menu option. [Current expected results](mise-tool-configuration.md#expected-results) · [Conflict discussion](../../version-format-research.md#when-source-priority-cannot-break-a-tie)

### Require a release lookup on the host

`mise ls-remote` can list backend versions and help find a published patch that meets a constraint. Requiring it on the host would add a CLI dependency. A hosted catalog would require network access, and its results would depend on coverage, freshness, and rate limits. The upstream Rust library is internal, and the reviewed cache documentation provides no third-party resolver contract. Derive requests from repository evidence offline and let Mise attempt installation in the container. Revisit catalog lookup if finding a substitute for an unavailable candidate becomes a requirement. [Mise integration research](../../version-format-research.md#mise-integration-on-the-host)

### Prefer the root manifest or consider only root declarations

Either rule reduces prompts caused by nested examples. Root-only evidence can miss projects whose declarations all live in subdirectories. Giving the root extra priority would silently choose its version when an equally ranked nested declaration conflicts. Use the selected scan as the evidence boundary. A developer can narrow it by running Repotainer in the relevant subdirectory. [Whole-scan example](../../version-format-research.md#when-source-priority-cannot-break-a-tie)

### Stop generation when an unattended conflict cannot be resolved

Exiting before writing avoids generating a request that may violate a declared requirement. It also prevents unattended callers from receiving a scaffold they can inspect or edit. Report the conflict and use `latest` for the affected tool so unattended generation can proceed. The warning explains why the result is a fallback. [Conflict discussion](../../version-format-research.md#when-source-priority-cannot-break-a-tie)

## Detailed implementation plan

These are the completed delivery checkpoints. See [implementation verification](#implementation-verification) for the checks that ran.

### Checkpoint 1 · Standalone resolver

1. **Create `src/repotainer/version_resolution.py`.** Add an in-memory resolver that consumes `ToolEvidence` from the completed `DetectionResult`. Represent a resolved request with its tool, request string, and diagnostics. Represent a conflict with the participating declarations and the candidate requests derived from them. Preserve each declaration's relative path, field, and extracted value before normalization. Provide distinct outcomes for missing version evidence, a proven conflict, and a declaration or constraint set that cannot yield a request. Keep the resolver independent of Typer, filesystem access, network access, and host Mise. Python is the first comparison rule. Give `project.requires-python` higher priority than `.python-version` and implement [the Python series and patch policy](#offline-python-release-selection). Include both winning and overridden evidence in an automatic precedence diagnostic. Preserve the source declarations even when different inputs produce the same candidate request.
2. **Create `tests/test_version_resolution.py`.** Exercise the resolver with small in-memory evidence groups. Cover the request examples under [Offline Python release selection](#offline-python-release-selection), a strict lower patch bound, a bounded range spanning several series, unbounded patch exclusions, no version evidence, a disjoint pin and higher-priority manifest, and a tie between disjoint manifests in different directories. Cover unsupported evidence by itself and at both precedence tiers, and supported constraints that cannot be expressed as a Mise request. For multi-source precedence, assert that a compatible exact pin is kept when all sources agree, and that both pins in the mixed-priority conflict are set aside. Cover a same-tier conflict with identical requests from two sources and a conflict with no usable individual candidate. Assert the exact request, all contributing evidence, and the reason for any fallback. Make fixtures independent of the host's installed tools and remote release data.

Run `uv run python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, and `ty check`. The installed command continues using the existing scaffold flow at this checkpoint.

### Checkpoint 2 · CLI and scaffold writer

1. **Modify [the scaffold writer](../../src/repotainer/scaffold.py).** Add `inspect_scaffold(root)` to return the read-only state of the in-scope destinations and `plan_scaffold(destinations, tool_requests)` to produce the proposed paths and replacement contents for display. Pass that plan to `write_scaffold` with separate keyword-only `replace_devcontainer` and `replace_mise` approvals that default to false. The writer owns plan construction and file operations. The CLI supplies the requests and approvals and prints the returned created and replaced paths. Use the [in-scope root paths](#replacement-scope), exclusive creation for new files, and [backup and restore](#back-up-and-restore-approved-replacements) for approved replacements. Generate one TOML string per tool under `[tools]`, in alphabetical order, and retain the header-only output for an empty selection. Reuse the static template payloads.
2. **Modify [the root command](../../src/repotainer/commands/main.py).** Keep the current inventory and stdout evidence report and select the same supported tool groups. Prepare and report recommendations even when configuration exists. After scanning, check the stdin and stderr terminal predicate, apply the numbered version menu or unattended fallback, then show proposed changes and obtain separate approval for any Dev Container and Mise replacements. Handle EOF or Ctrl+C before calling any write or backup operation. Pass the final per-tool requests and separately approved writes to the scaffold writer. [Terminal input and cancellation](#terminal-input-and-cancellation)
3. **Modify [CLI tests](../../tests/test_repository.py).** Replace the current conflicting prefix-and-manifest fixture's `latest` assertion with the manifest-derived request and a diagnostic identifying the pin. Add a case with an unsupported manifest constraint and a readable pin that verifies the warning and generated `latest` request. Add root and subdirectory runs with incompatible manifests. At the root, verify each menu choice and its provenance, invalid input recovery, and unattended fallback without input. Simulate terminal and redirected streams through the CLI's interactivity check. Cover stdout-only redirection, stderr output, and status `2` with no writes or backups on EOF or Ctrl+C. In the subdirectory, verify the single derived version and the absence of a prompt. When both existing configurations are eligible, cover all four combinations of the two approvals and assert that the evidence and preview appear before the replacement prompts. Assert that a declined group remains unchanged. Check the generated TOML and the original evidence report through the public command.
4. **Modify [scaffold tests](../../tests/test_scaffold.py).** Migrate writer callers to the inspection and plan interface. Pass distinct tool request strings and parse the result with `tomllib` to verify string serialization and stable ordering. Retain the empty table, unapproved configuration preservation, and destination collision cases. Assert that an extra file under `.devcontainer/` stays intact when scaffold files are replaced. Test that backup failure leaves all scaffold files unchanged. Fail a late write after an approved replacement and a new file creation, then assert that original bytes are restored and new files and backups are removed. Test success cleanup and the recovery diagnostic and retained backup when restoration fails.
5. **Update the owning documentation alongside the code.** In [README.md](../../README.md), explain version choices, the conflict menu, the unattended fallback, and host requirements. Distinguish successful scaffold generation from a successful `mise install` and explain how to edit `mise.toml` and retry if a request is unavailable. In [Repository inspection](repository-inspection.md), update the CLI flow and scaffold handoff once they match the source. In [Mise tool configuration](mise-tool-configuration.md), retain the original milestone's verification as history and point readers to this design for version resolution. In [Dev container scaffold generation](devcontainer-scaffold.md), update the destination-check and write sequence if its interface or observable behavior changes. Record the implemented decisions and actual verification here and update the [design index](SITEMAP.md) once the corresponding work is complete.

Change the writer, caller, and integration tests together so the active command uses a single matching interface. Run the full [verification plan](#verification-plan) for source and documentation checks before the installed checks.

### Checkpoint 3 · Installed CLI verification

Run the [installed command smoke checks](#installed-command-smoke-checks). Record the results in this design document and update the implementation state in [docs/designs/SITEMAP.md](SITEMAP.md). This checkpoint uses the verified build from the preceding checkpoint.

### Verification plan

For request validation, parse generated output with `tomllib` and assert its key order separately. Reject an unknown tool, duplicate tool, or invalid request before writing. Through the CLI, verify that a malformed declaration such as `3.13.` appears as evidence and follows the fallback policy. Check that a path or value containing a line break or terminal control character is displayed as single-line text without changing the value held by the resolver.

Run `uv run python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, `ty check`, and `rumdl check AGENTS.md README.md docs`. Inspect local links and the final diff. [Repository checks](../development.md#checks)

Add public CLI regression coverage in `tests/test_repository.py` for the [nested manifest and root pin journey](#resolve-a-nested-manifest-against-a-root-pin). In the root run, assert `python = "3.12"`, both paths in the precedence diagnostic, and no version menu. In a fresh nested-only run, assert that the scaffold and `mise.toml` are created inside `examples/legacy` and the root pin is outside the scan.

Update `test_prints_complete_evidence_after_inventory` in [the CLI tests](../../tests/test_repository.py). For `.python-version = 3.13`, `requires-python = ">=3.12"`, and `uv.lock`, expect `python = "3.13"` and `uv = "latest"` while preserving the stdout evidence assertion. Keep `test_conflicting_python_versions_still_generate_latest` as the series-versus-manifest fixture, rename it to reflect precedence, and add a separate exact-pin conflict. Reuse the existing populated rollback fixture for new-file cleanup and add the approved-replacement failure fixtures separately. [Current scaffold tests](../../tests/test_scaffold.py)

#### Installed command smoke checks

Install Repotainer and its dependencies before disabling network access. Run the installed `repotainer` entry point with host Mise unavailable. Use a fresh project directory for each case, with no existing scaffold or `mise.toml`. Keep the fixtures below the inventory confirmation threshold. For the terminal case, use a terminal or pseudoterminal for stdin and stderr. For the unattended case, redirect stdin and verify the command completes without input. Assert exit status `0`, parsed `mise.toml`, and the generated Dev Container files at the selected scan root in each case.

| Fixture and invocation | Expected Python request | Prompt and diagnostic |
| --- | --- | --- |
| Root `.python-version` is `3.12.8` and `requires-python` is `>=3.12.5,<3.13`. Run from the root. | `3.12.8` | No version menu or conflict warning. |
| Root manifest requires `>=3.13,<3.14` and `examples/legacy` requires `>=3.12,<3.13`. Run at the root with terminal input and select the root manifest's option. | `3.13` | Menu lists `3.12`, `3.13`, and `latest` in order, with both manifest paths. |
| Same manifest conflict in a fresh fixture. Run at the root with stdin redirected. | `latest` | No menu. The warning names both manifest paths and the fallback. |
| Same manifest layout in a fresh fixture. Run `repotainer examples/legacy` from the root. | `3.12` | No menu or conflict warning. The evidence and generated paths are scoped to the subdirectory. |

Treat container installation as a separate check of release availability for the target. Record which host and container checks were actually run and their results.

## Implementation verification

Verified locally on 2026-11-24 in the working tree based on `87a2034`. The same Windows-only junction test was skipped on Linux in both suite runs.

| Checkpoint | Observed results |
| --- | --- |
| 1. Standalone resolver | `uv run python -m unittest discover -s tests` ran 73 tests with one skip. Ruff lint, Ruff format check, and `ty check` passed. |
| 2. CLI and scaffold writer | The same test command with `UV_NO_CACHE=1` ran 86 tests with one skip. Ruff lint, Ruff format check, ty, Markdown lint, local links, and whitespace checks passed. Tests covered independent replacement approvals, backup failure before writes, rollback across both groups, and backup retention on failed restoration. |
| 3. Installed CLI | Built and installed a noneditable wheel in a temporary environment with the app's locked dependencies staged from the local development environment. `uv pip check` passed. All four smoke cases exited successfully in an isolated network namespace with no Mise on `PATH`. An additional terminal case preserved an existing Dev Container file while replacing `mise.toml`. |

The smoke checks verified host-side generation and approvals. Container setup and installation availability were outside this verification run.

*Drafted with EGM*
