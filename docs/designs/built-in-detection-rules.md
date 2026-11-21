# Built-in detection rules

- Author: Suchi Pragya
- Updated: 2026-11-21
- Review status: Author-approved design. All eight EGM review findings resolved.
- Implementation state: Implemented and [verified locally](#implementation-verification).

## Overview

Group the built-in rules by tool under `detection/rules/` and keep `BUILTIN_RULES` as the single registry. A tool can collect evidence from several indicators, and the same observation can appear in every tool group it supports. The first use of this mechanism adds uv and Poetry evidence to the Python group. [Current built-in rules](repository-evidence-detection.md#initial-rules)

## The problem

Before this change, Python, uv, and Poetry rules shared one module. As the catalog grows, contributors need a predictable place to find each tool's match conditions and evidence extraction. An observation about one tool can also serve as evidence for another tool within the selected scan root. Previously, `uv.lock` and a `[tool.poetry]` table could each produce a tool group with no corresponding Python evidence. The detector now shares those observations while keeping each tool's checks together. [Current detector](../../src/repotainer/detection/engine.py)

## Goals

- Keep each built-in tool's rules in its own module. A tool can have multiple indicators or rules. Each built-in rule detects indicators for its own tool.
- Keep `BUILTIN_RULES` as the single registry. Preserve the existing imports from `repotainer.detection` and `repotainer.detection.rules`.
- Let one observation contribute to multiple tool groups with its original path, field, and value. Each group retains its distinct direct and shared observations.
- Make evidence sharing extensible to future tools and relationships without a Python-specific path through detection. Use the same mechanism to share every uv and Poetry observation with Python, including when there is no direct Python evidence.
- Preserve existing match conditions, diagnostics, and deterministic ordering. The built-in Python and Poetry rules reuse one TOML parse per matching inventory entry. The uv rule continues to use file presence alone.

## Non-goals

- Additional tool rules or indicators in the initial delivery, and changes to scan boundaries.
- Version selection, tool installation, and configuration generation.

## Technical plan

### Tool modules and registry

Replace `detection/rules.py` with a `detection/rules/` package. Put each rule definition, its selectors, and its evaluator in `python.py`, `uv.py`, or `poetry.py`. Keep the existing rule IDs and selectors. Assemble `BUILTIN_RULES` explicitly in `rules/__init__.py` and continue re-exporting it from `detection/__init__.py`. Each module can contribute several rules when its tool needs independently matched indicators. Callers still use `detect(inventory, rules)` and can supply their own rules.

### Evidence flow

```text
Inventory + rules passed to detect
                     |
                     v
          Match and evaluate entries
                     |
                     v
      Collect and share direct evidence
                     |
                     v
      Deduplicate and order each tool group
                     |
                     v
    Return tool groups and reader diagnostics
```

### Receiving tools declare their sources

Keep the declaration with a registered rule in the receiving tool's module. The Python rule declares `uv` and `poetry` as sources. The uv and Poetry rules emit evidence for their own tools. The detector reads sharing declarations from the rules passed to `detect`, even when the receiving rule matches no entries. A caller that omits the receiving rule also omits its declaration.

A declaration names the receiving tool ID and one or more source tool IDs. The detector matches source IDs against the tool IDs emitted by evaluators. Custom evaluators can still emit evidence for several tool IDs. All rules that emit evidence for a source contribute, including additional rules supplied by a caller. Several receiving tools can independently declare the same source, and each receiving tool can draw from several sources.

### Assemble the result

Reuse the original immutable `Evidence` records when grouping observations. Keep each record in its source group and add it to every declared receiving group, including a receiver with no direct evidence. Merge exact duplicates of `(path, field, value)` within each group and use the existing ordering for tool groups, observations, and diagnostics. Sharing uses observations already emitted by the evaluators. File reads, parse caching, and diagnostics stay in matching and evaluation.

Sharing uses explicit relationships and takes only direct observations as input. If A shares with B and B shares with C, a direct observation from A reaches B. It reaches C when an A-to-C declaration also exists. This keeps results independent of declaration order and prevents cycles from repeatedly sharing the same evidence.

Apply each distinct source–receiver pair once. A source with `E` distinct direct observations and `R` distinct recipients can add up to `E × R` group entries before deduplication against other observations. Each qualifying built-in uv or Poetry observation can add one entry to the Python group. The CLI prints every resulting group entry. [CLI output limits](cli-evidence-output.md#output-limits)

| Direct observation | Direct group | Receiving group | Evidence reused |
| --- | --- | --- | --- |
| A regular `uv.lock` | `uv` | `python` | The relative path with no field or value |
| A `pyproject.toml` containing a `[tool.poetry]` table | `poetry` | `python` | The relative path and `("tool", "poetry")` field with no value |

When a manifest also declares `project.requires-python`, that declaration and the shared Poetry observation remain separate in the Python group because their fields differ. For a malformed manifest, the built-in readers report the existing parse diagnostic and the built-in evaluators emit no observations from the failed parse.

The path, field, and value identify the observed indicator within the selected scan root. Later stages determine whether the workflow is active, which project it belongs to, whether the observation applies to the requested environment, and which version to select. [Detector handoff](repository-evidence-detection.md#handoff-to-mise-generation)

## Alternatives considered

### Source rules declare recipients

Each source rule could declare recipients. This gives each rule control over which findings go to other tools. It also distributes the receiving tool's policy among source rules. Adding an indicator for an existing source could then produce evidence that the other indicators share but the new indicator does not.

Keeping the declaration with the receiving tool lets every rule for a source contribute through the same relationship. Python lists uv and Poetry in its own module so the source rules can focus on their own tools.

### Source evaluators emit evidence for every recipient

The existing evaluator interface can emit the same observation for several tools. This approach would need no new sharing metadata. Each relevant evaluator would have to know its recipients, and a new recipient could require changes to several existing evaluators. A receiving-tool declaration adds the relationship in one place and keeps source evaluators focused on their own checks.

## Detailed implementation plan

| Action | File | Change and rationale |
| --- | --- | --- |
| Modify | [`src/repotainer/detection/model.py`](../../src/repotainer/detection/model.py) | Define a frozen `EvidenceSharing` record with `receiver: str` and `sources: tuple[str, ...]`. Add `evidence_sharing: EvidenceSharing \| None` to the end of `Rule` with a default of `None`. Existing three-argument rule construction and evaluator return types continue to work. |
| Modify | [`src/repotainer/detection/engine.py`](../../src/repotainer/detection/engine.py) | Collect evidence relationships from the rule sequence during validation. Apply each distinct source–receiver pair to direct evidence before sorting the result. Reuse the existing grouping and sorting behavior. |
| Create | `src/repotainer/detection/rules/python.py` | Move `python-runtime`, its `.python-version` and `pyproject.toml` selectors, and its evaluator here. Declare `python` as the receiver and `uv` and `poetry` as its sources. |
| Create | `src/repotainer/detection/rules/uv.py` | Move `uv-workflow`, its `uv.lock` selector, and its presence-only evaluator here. |
| Create | `src/repotainer/detection/rules/poetry.py` | Move `poetry-workflow`, its `pyproject.toml` selector, and its `[tool.poetry]` evaluator here. |
| Create | `src/repotainer/detection/rules/__init__.py` | Import the three rule definitions and assemble the one `BUILTIN_RULES` tuple in its existing order. The current re-export from `detection/__init__.py` resolves to the package with its existing import. |
| Remove | `src/repotainer/detection/rules.py` | Remove the old module when the package takes over. Keep one definition of `BUILTIN_RULES` in `rules/__init__.py` and retain both existing import paths. |
| Modify | [`tests/test_detection.py`](../../tests/test_detection.py) | Update built-in evidence expectations and add isolated fixtures for generic sharing, registry scope, and validation. Keep the reader-spy assertions for parse counts and unopened files. |
| Modify | [`tests/test_repository.py`](../../tests/test_repository.py) | Update the exact CLI output expectations for the full fixture and the malformed-manifest-plus-uv fixture. These exercise the normal CLI entry point and verify the shared Python evidence and existing diagnostics. |
| Modify | [`docs/designs/repository-evidence-detection.md`](repository-evidence-detection.md) | Update the current detector contract and built-in examples to describe the new rule package and shared observations. Link to this design for details and preserve the original milestone verification as historical evidence. |
| Modify | [`docs/designs/cli-evidence-output.md`](cli-evidence-output.md) | Update the output contract to reflect that the detector can report the same observation under multiple tools. Mark the original expected results and verification as historical where needed. |
| Modify | [`docs/designs/built-in-detection-rules.md`](built-in-detection-rules.md) and [`docs/designs/SITEMAP.md`](SITEMAP.md) | Record the delivered state, assessed revision, and actual verification results after implementation. |

### Registration and result assembly

1. Validate the rules and their sharing declarations before evaluating entries. Each declaration needs a nonempty receiver ID and a source tuple with at least one ID. Every source ID must be nonempty. Raise `ValueError` identifying the declaring rule on failure. Combine repeated relationships by source and receiver. Match IDs exactly as emitted by evaluators. A declaration can name a source that yields no evidence for the rules and inventory passed to `detect`. A self-reference reuses evidence already in the same group.
2. Gather direct observations using the existing selectors, evaluators, and per-entry reader. Keep the current check that each observation refers to the matched entry. For each distinct source–receiver pair, reuse the original `Evidence` records from the source's direct observations. Only direct observations can drive sharing, regardless of when grouping occurs. Create groups when they have evidence and leave file access to the existing evaluators and reader.
3. Use the current sort keys and `DetectionResult` fields. The CLI continues passing the same registry to `detect` and prints its result through the existing output path. A failed read remains a diagnostic for its original path and reader.

### Implementation checkpoints

1. Add the model and engine support with custom-rule fixtures. Keep the built-in rules in their current module for this checkpoint. Run `uv run --locked python -m unittest discover -s tests -p test_detection.py`.
2. Replace `rules.py` with the package, add Python's sharing declaration, and update the built-in detector and CLI expectations together. Run `uv run --locked python -m unittest discover -s tests`.
3. Reconcile the detector contract, CLI design, and design index. Run the full verification checks below and record actual results for the assessed source state.

### Verification plan

| Fixture or check | Expected result |
| --- | --- |
| A repository containing only `uv.lock` | Both `uv` and `python` contain its path-only observation. The lockfile stays unopened. |
| A repository containing only a manifest with `[tool.poetry]` | Both `poetry` and `python` contain the same field observation. The manifest is parsed once. |
| A `.python-version` file and `project.requires-python` in `pyproject.toml`, alongside uv and Poetry evidence | The Python group contains both direct declarations and the distinct shared observations in the existing sort order. The originating groups still contain their own evidence. |
| Malformed manifest alongside `uv.lock` | One TOML diagnostic for the manifest. Python and uv each retain the same lockfile observation. |
| Two independently registered rules with distinct IDs, including a caller-added rule, emit different observations under one source tool ID. Two tools declare that source, including one whose rule matches no entries. | Both recipients obtain both original observations. An identical direct and shared record appears once within a group, while differing paths, fields, or values remain distinct. Omitting a receiving rule removes its declaration. |
| Custom rules with a chain, a cycle, overlapping declarations, and an absent source | Sharing uses direct evidence only and produces the same result with the original and reversed rule sequences. Repeated relationships add no duplicates. An absent source creates no empty group. |
| An empty receiver ID, an empty source tuple, and a tuple with a valid source ID and an empty ID | Each fails with `ValueError` identifying the declaring rule. A matched evaluator spy receives zero calls. |
| Caller rules without sharing and both built-in import paths | Rules without sharing retain their existing behavior, including evaluators that emit multiple tool IDs. Both imports expose the same `BUILTIN_RULES` tuple. |

Run `uv run --locked python -m unittest discover -s tests`, `ruff check .`, `ruff format --check .`, `ty check`, `rumdl check AGENTS.md README.md docs`, and `git diff --check`. Verify affected documentation links and headings using the [development checks](../development.md#checks).

## Implementation verification

Verified the uncommitted implementation on working-tree base `1414161` with Python 3.14.6 on Linux on 2026-11-21. The detector indexes receivers by source tool ID during validation and adds an observation to its source and receiving groups when an evaluator emits it. Only evaluator emissions drive sharing. [Detector engine](../../src/repotainer/detection/engine.py) · [Built-in registry](../../src/repotainer/detection/rules/__init__.py)

| Checkpoint | Actual results |
| --- | --- |
| Generic sharing | All 14 targeted detector tests passed before the rules moved. The fixtures covered invalid declarations before evaluation, evidence from independently registered source rules, multiple recipients, and direct-only sharing under reversed rule order. |
| Built-in rule package | All 41 tests passed. The uv-only fixture verified Python evidence without opening `uv.lock`. The Poetry-only fixture verified Python evidence and one TOML parse. The CLI fixture kept the malformed manifest diagnostic alongside shared lockfile evidence. Both registry import paths returned the same tuple. |
| Final verification | All 41 tests passed again. Ruff lint and formatting, ty, Markdown lint, local links, and whitespace checks passed. The installed console script reported Python alongside uv and Poetry in separate single-indicator fixtures, with each fixture's path and contents intact. |

*Drafted with EGM*
