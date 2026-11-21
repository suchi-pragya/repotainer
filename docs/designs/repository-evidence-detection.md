# Repository evidence detection

- Updated: 2026-11-21
- Author: Suchi Pragya
- Review status: Author-approved. All nine agreed EGM resolutions applied.
- Implementation state: Implemented and [verified locally](#implementation-verification).

## Overview

Add a read-only detector that consumes the existing [repository inventory](repository-inventory.md#catalog-storage-and-lifetime). Registered rules identify tools and workflows from eligible entries. Detection groups observations by tool and retains their sources for later use in `mise.toml` generation.

The first milestone delivered an in-memory detector with Python, uv, and Poetry rules. At that milestone the root command ended with its inventory summary, and an integration test exercised the scanner-to-detector handoff. A test-only Go rule verified that the same detector could support another ecosystem. The root command now consumes the detector and prints its result. [CLI evidence output](cli-evidence-output.md)

## The problem

The scanner records eligible files and directories under the selected root, and the CLI prints the inventory counts. A recorded path can suggest a tool, while some declarations need to be read to establish what the file indicates. Several files can describe the same tool, and one file can describe several tools. Repotainer needs a common way to add rules and retain each distinct observation as coverage grows. [Current CLI and scanner contract](repository-inspection.md)

## Goals

- Use the completed inventory as the source of candidate paths.
- Let each rule recognize one or more kinds of entry and evaluate each matching entry independently.
- Group the result by tool or workflow ID. Keep the relative path and, where available, the field and extracted value for each distinct observation.
- Make it possible to add support for another structure by adding a rule, registering it, and verifying it with fixtures.

## Non-goals

- Changes to scan-root selection, exclusions, inventory format, or CLI behavior.
- Rules that require a combination of files, infer file pairings, or assign evidence to projects.
- Version reconciliation, workflow recommendations, installation choices, and configuration writing.

## Technical plan

```text
Completed inventory + registered rules
                 |
                 v
        Match inventory entries
                 |
                 v
Evaluate each matched entry with each interested rule
        |                         ^
        +--> Shared reader -------+
             data or failure
        |
        +--> Evidence grouped by tool
        +--> Diagnostics
                 |
                 v
           DetectionResult
```

| Component | Responsibility |
| --- | --- |
| Inventory | Supply the resolved scan root and eligible entries. |
| Matcher | Index selectors and identify all rules that accept each inventory entry. |
| Evaluator | Interpret the matched entry and emit evidence from its metadata or a supported declaration. |
| Readers | Read matched files on demand and share read or parse outcomes while an entry is being evaluated. |
| Detector | Evaluate matching rules and assemble ordered evidence groups and diagnostics. |

### Detection input and output

Detection consumes an `Inventory`. Each entry already has relative path components, an entry kind, and an optional extension. The name is the final path component. An entry can contribute to several tool groups, and a group can retain evidence from several entries. An unmatched entry, or a match from which a rule extracts no evidence, adds no evidence item.

| Evidence field | Contract |
| --- | --- |
| `path` | Required. Copy the inventory entry's relative path tuple. |
| `field` | Optional. A tuple of key components within a structured file. Use `None` for file presence or a plain-text declaration. |
| `value` | Optional. The extracted text. Use `None` when the presence of a file or field is sufficient evidence. |

For example, the result can contain these records:

| Tool group | Path | Field | Value |
| --- | --- | --- | --- |
| `python` | `.python-version` | `None` | `3.12` |
| `python` | `app/pyproject.toml` | `("project", "requires-python")` | `>=3.12` |
| `python` | `samples/pyproject.toml` | `("project", "requires-python")` | `>=3.12` |
| `poetry` | `app/pyproject.toml` | `("tool", "poetry")` | `None` |
| `uv` | `uv.lock` | `None` | `None` |

The two manifests remain separate Python sources even though they declare equal values. The app manifest can also provide Poetry evidence. A Poetry field with no extracted value records the presence of a supported section. The uv record relies on file presence alone.

### Match metadata first

Index the registered selectors and walk the inventory once. For each entry, probe the applicable keys, check the remaining selector conditions, and evaluate each interested rule once for that entry. Several selectors in a rule are alternatives. A rule recognizing both `.python-version` and `pyproject.toml` can extract evidence from either independently. A matching manifest in another directory receives its own evaluation.

Each entry probes a fixed number of keys. The work after lookup depends on the selector references returned by those keys. An extension bucket such as `.toml` can return many selectors, so use an exact path or name where a rule knows it.

### Handoff to Mise generation

The detector hands off observations and diagnostics. A later stage will decide which observations apply to the requested environment, reconcile version declarations, and write `mise.toml`.

## Alternatives considered

### Compare every inventory entry with every selector

A nested loop is easy to implement and can be a reference for matcher tests. Swapping the outer loop changes the order while retaining the product of entries and selectors. The design uses a selector index so entries route to rules with applicable keys.

### Index inventory entries and let rules query the index

Inventory indexes give similar expected lookup costs for exact keys and would let a rule look up a path discovered in a declaration. They also store indexes for the whole inventory and give evaluators responsibility for queries. The approved plan puts routing in the matcher. Revisit inventory queries when a supported rule needs to follow a path found in file contents.

### Define the rules in TOML or YAML

A data file could express simple file-to-tool mappings. Rules that interpret structured declarations would still need callable handlers or a rule language with its own validation. The detector uses Python evaluators behind one registration contract. Revisit external rules when a concrete use case calls for contributions outside the source tree.

## Detailed implementation plan

### Component interfaces

Expose `detect` and `BUILTIN_RULES` from the detection package. The built-in registry is a tuple of rules. A caller passes that tuple explicitly or supplies its own sequence for a test.

```text
detect(inventory: Inventory, rules: Sequence[Rule]) -> DetectionResult
Rule(id: str, selectors: tuple[Selector, ...], evaluate: Evaluator)
Selector(
    path: tuple[str, ...] | None,
    filename: str | None,
    directory_name: str | None,
    extension: str | None,
    kind: Literal["file", "directory"] | None,
)
Evaluator(entry: InventoryEntry, reader: EntryReader) -> Iterable[tuple[str, Evidence]]
EntryReader.read_text(entry: InventoryEntry) -> str | None
EntryReader.read_toml(entry: InventoryEntry) -> Mapping[str, TomlValue] | None
DetectionResult(tools: tuple[ToolEvidence, ...], diagnostics: tuple[Diagnostic, ...])
ToolEvidence(tool: str, evidence: tuple[Evidence, ...])
Evidence(path: tuple[str, ...], field: tuple[str, ...] | None, value: str | None)
Diagnostic(path: tuple[str, ...], reader: str, reason: str)
```

Each evaluator receives one matched entry. Its reader is bound to that entry and refuses requests for a different entry or for an entry recorded as a directory. If an evaluator requests an inadmissible entry or emits evidence with a path other than the matched entry's path, raise `ValueError` as a rule-definition error. Keep the rule ID internal to validation and dispatch. Each emitted tool ID selects an evidence group.

A TOML value is a scalar from the standard-library parser, a read-only mapping for a table, or a tuple for an array. Apply read-only mappings and tuples recursively. The reader returns `None` for a failed content request and records the original inventory path, reader name (`text` or `toml`), and failure reason in the result's diagnostics. Other applicable rules and entries remain eligible.

### Selector validation and matching

A selector declares one or more of `path`, `filename`, `directory_name`, and `extension`. It can also specify entry `kind` as a filter. Treat all conditions on one selector as required. Compare original inventory spelling exactly and use these keys in priority order:

| Condition | Key and matching behavior |
| --- | --- |
| Exact relative path | Use the tuple of path components. Apply any other conditions as filters. |
| Exact filename | Use the file kind and final path component. |
| Exact directory name | Use the directory kind and final path component. |
| Exact extension | Use the stored suffix, including its leading dot. Only a file with that suffix matches. |

Validate the full registry before evaluating entries. Raise `ValueError` for a duplicate or empty rule ID, a rule with no selectors, a selector with no lookup key, an unsupported kind, or contradictory kind requirements. Filename and extension imply `file`. Directory name implies `directory`. Names must be single nonempty path components. Paths must be nonempty relative component tuples, and extension keys must be nonempty dotted suffixes.

Probe the path key, kind-and-name key, and extension key when present. Use the rule ID to ensure each rule receives an entry once even if more than one selector matches. Evaluate interested rules in rule ID order. A different rule can evaluate the same entry, and a single rule can emit evidence for several tools.

### Reader boundary and limits

Evaluate all interested rules for one entry before moving to the next. A presence-only evaluator uses inventory metadata. On a content request, examine each path component below the resolved scan root without following links. Reject observed symlinks and junctions, require directories for intermediate components and a regular file for the final component, and check resolved containment before opening. Use the original catalog path in diagnostics. Use `missing` for a missing component and `rejected-path` for a detected link, unexpected entry type, or failed containment check.

The pre-open checks follow the scanner's [stable-tree assumption](repository-inventory.md#catalog-invariants). They detect changes visible when checked. The filesystem can still change between a check and an open. The detector makes no concurrent-mutation or atomic-snapshot guarantee.

Read at most 1 MiB plus one byte from a matched file. A read of more than 1 MiB produces a size diagnostic and skips decoding or parsing. An exactly 1 MiB payload is eligible. Decode text as UTF-8 and parse TOML with the standard library. Use `too-large`, `invalid-utf8`, and `invalid-toml` for the corresponding failures and `read-error` for other filesystem failures. TOML that the Python parser cannot process within its integer conversion or nesting limits also produces `invalid-toml`. Share one bounded byte read for the current entry, and cache each requested reader's outcome, including failure, for that entry. Release the bytes and parsed contents when its last interested rule finishes. Retain only the observations and diagnostics needed for the result.

### Observation identity and ordering

Within a tool group, merge exact duplicates of `(path, field, value)`. Different sources, different fields, different values, and observations in different tool groups remain distinct. Order tool groups by tool ID. Within each group, order evidence lexicographically by path, field, and value, placing `None` before a present field or value. Order diagnostics lexicographically by path, reader, and reason. A cached read or parse failure contributes one diagnostic for its path and reader.

### Initial rules

| Rule | Selectors and extraction |
| --- | --- |
| Python runtime | Match regular files named `.python-version` or `pyproject.toml`. For a version file, strip whitespace from each line and retain the text only if exactly one line remains nonblank. For a manifest, retain the string at `("project", "requires-python")` when it contains non-whitespace text. Preserve the extracted TOML string. Both sources contribute independently to `python`. |
| uv workflow | Match a regular file named `uv.lock`. Emit path-only evidence for `uv`. |
| Poetry workflow | Match a regular file named `pyproject.toml`. Emit evidence for `poetry` with field `("tool", "poetry")` and no value when that field is a TOML table. Reuse the same TOML result if the Python rule requested it. |

A blank or multiline nonblank version request file, an absent or unsupported field, and a manifest value of the wrong type yield no evidence for that declaration. A failed content request still produces the reader diagnostic specified above.

### Files and delivery order

| Checkpoint | Repository-relative path | Action | Change |
| --- | --- | --- | --- |
| 1. Detector core | `src/repotainer/detection/__init__.py` | Create | Create the package and expose `detect` when its engine exists. |
| 1. Detector core | `src/repotainer/detection/model.py` | Create | Define selectors, rules, evaluator and reader contracts, and the result records. |
| 1. Detector core | `src/repotainer/detection/engine.py` | Create | Implement validation, keyed matching, per-entry evaluation, deduplication, and ordering. |
| 1. Detector core | `src/repotainer/detection/readers.py` | Create | Apply the file access and size checks, parse supported formats, and share outcomes per entry. |
| 1. Detector core | `tests/test_detection.py` | Create | Verify matching, reader limits and failures, cache lifetime, and result semantics with test rules. |
| 2. Built-ins and handoff | `src/repotainer/detection/rules.py` | Create | Define and register the Python, uv, and Poetry rules. |
| 2. Built-ins and handoff | `src/repotainer/detection/__init__.py` | Modify | Expose `BUILTIN_RULES` alongside `detect`. |
| 2. Built-ins and handoff | `tests/test_detection.py` | Modify | Exercise the built-in rules against a real inventory and verify extension with a test-only Go rule. |
| 3. Documentation and final checks | [`docs/designs/repository-evidence-detection.md`](repository-evidence-detection.md) | Modify | Record shipped rule coverage and actual implementation verification. |
| 3. Documentation and final checks | [`docs/designs/SITEMAP.md`](SITEMAP.md) | Modify | Record implementation state after verification. |

For checkpoint 1, run `uv run python -m unittest discover -s tests -p test_detection.py`. Expect the core package to import and each synthetic fixture to pass. For checkpoint 2, run `uv run python -m unittest discover -s tests`. Expect the new integration and extension tests and existing scanner and CLI tests to pass. For checkpoint 3, run the suite again, `ruff check .`, `ruff format --check .`, `ty check`, Markdown lint, the local-link check, and `git diff --check`. Record the tested revision and actual results using the [development checks](../development.md#checks).

### Verification plan

| Checkpoint | Fixture | Expected result |
| --- | --- | --- |
| 1 | Exact path, file name, directory name, dotfile, and extension selectors, with overlapping and differently cased entries | Each selector respects kind and exact spelling. Two selectors for one rule deliver an entry once. Two rules both receive an entry they accept. Duplicate rule IDs, invalid selector definitions, and reader calls outside the matched entry are rejected. |
| 1 | Two rules ask for TOML from the same file | They share one parse and cannot mutate the cached data. A later detection call after editing the file sees its new contents. A matched entry remains unopened when its rule requests no content. |
| 1 | Same-source duplicate evidence, a presence record and a field record from the same path, equal values from different paths, and multiple diagnostics | Merge only identical observations within one tool. Verify the exact evidence and diagnostic order before and after reversing the registry. |
| 1 | A disappeared file, an observed final link to an excluded file inside the root, and an observed parent link outside the root | Each produces a diagnostic at the catalog path. Other eligible files still produce evidence. Use platform-appropriate link or junction fixtures. |
| 1 | One file at the byte limit, one over the limit, and another valid file | The exact-limit file can be inspected. The oversized file produces one diagnostic for the requested reader and is not decoded or parsed. The valid file still contributes. Measure parse count and peak memory on a tree with many matching manifests to check that cached source data is released as entries finish. |
| 2 | A manifest contains both `project.requires-python` and `tool.poetry`, alongside `.python-version`, `uv.lock`, and a second manifest in a directory with no version file | All three Python sources remain in one group. Poetry and Python share the first manifest. uv has path-only evidence. Begin counting file opens after scanning. Verify one parse of the shared manifest and no content opens for `uv.lock` or ignored or unmatched files. |
| 2 | Blank or multiline version files, absent, blank, and non-string manifest fields, invalid UTF-8, and malformed TOML requested by two rules | Unsupported declarations produce no evidence. Content failures produce one diagnostic per path and reader, and an unaffected match still produces evidence. |
| 2 | An empty inventory and an extension rule registered only in the test for `go.mod` | The empty result has no evidence or diagnostics. The extension emits path-only Go evidence through the existing matcher and readers, and the built-in registry stays unchanged. |

## Implementation verification

Verified the uncommitted implementation on working-tree base `a6db052` with Python 3.14.6 on Linux on 2026-11-21. The [detection package](../../src/repotainer/detection/__init__.py) exports `detect` and the Python, uv, and Poetry registry. The [detection tests](../../tests/test_detection.py) exercise the actual inventory handoff and add Go through a test-only rule.

| Checkpoint | Actual results |
| --- | --- |
| 1. Detector core | `uv run --locked python -m unittest discover -s tests -p test_detection.py` passed all 8 tests before the built-ins were added. Verified selector overlap, exact evidence deduplication and ordering, cached reads and immutable TOML, replacement links, missing and unreadable files, and the 1 MiB limit. |
| 2. Built-ins and handoff | `uv run --locked python -m unittest discover -s tests` passed all 33 tests. The integration fixture retained three Python observations, shared the app manifest with Poetry, and left the uv lockfile and ignored and unmatched files unopened. Parser-limit cases returned diagnostics and preserved other observations. A CLI run on a directory containing a malformed manifest printed the inventory summary and exited successfully. |
| 3. Documentation and final checks | All 33 tests passed again. Ruff lint and format checks, ty, Markdown lint, local links, and whitespace checks passed. |

Measured detection with `tracemalloc` after building each fixture and its inventory. Each manifest contained a Python and Poetry observation and a larger unused TOML array (50,765 bytes per file). The parse counter retained no parser inputs. Timings include tracing overhead.

| Manifests | TOML parses | Evidence items | Elapsed | Peak traced memory |
| --- | --- | --- | --- | --- |
| 8 | 8 | 16 | 0.029 s | 1,157.0 KiB |
| 128 | 128 | 256 | 0.460 s | 1,190.7 KiB |

These measurements cover synthetic manifests on Linux. The replacement fixtures exercised symlinks. Windows junction behavior was outside this run. The reader follows the documented stable-tree assumption.
