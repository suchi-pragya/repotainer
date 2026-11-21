from collections import defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path

from repotainer.detection.model import (
    DetectionResult,
    Diagnostic,
    Evidence,
    Rule,
    Selector,
    ToolEvidence,
    is_path_component,
)
from repotainer.detection.readers import MatchedEntryReader
from repotainer.scanning.inventory import Inventory, InventoryEntry

type LookupKey = tuple[str, tuple[str, ...]]


def detect(inventory: Inventory, rules: Sequence[Rule]) -> DetectionResult:
    """Collect tool evidence from a completed inventory."""
    index, receivers_by_source = _index_rules(rules)
    evidence: dict[str, set[Evidence]] = defaultdict(set)
    diagnostics: list[Diagnostic] = []

    for entry in inventory.entries:
        matched: dict[str, Rule] = {}
        for key in _entry_keys(entry):
            for selector, rule in index.get(key, ()):
                if _matches(selector, entry):
                    matched[rule.id] = rule

        if not matched:
            continue

        reader = MatchedEntryReader(inventory.scan_root, entry)
        for rule_id in sorted(matched):
            rule = matched[rule_id]
            for tool, observation in rule.evaluate(entry, reader):
                if observation.path != entry.relative_path:
                    raise ValueError(f"{rule_id}: evidence must refer to the matched entry")
                evidence[tool].add(observation)
                for receiver in receivers_by_source.get(tool, ()):
                    evidence[receiver].add(observation)
        diagnostics.extend(reader.diagnostics)
        # Drop the parsed content before creating the reader for the next matched entry.
        del reader

    return DetectionResult(
        tools=tuple(ToolEvidence(tool, tuple(sorted(evidence[tool], key=_evidence_key))) for tool in sorted(evidence)),
        diagnostics=tuple(sorted(diagnostics, key=lambda item: (item.path, item.reader, item.reason))),
    )


def _evidence_key(item: Evidence) -> tuple[tuple[str, ...], bool, tuple[str, ...], bool, str]:
    return item.path, item.field is not None, item.field or (), item.value is not None, item.value or ""


def _index_rules(
    rules: Sequence[Rule],
) -> tuple[dict[LookupKey, list[tuple[Selector, Rule]]], dict[str, set[str]]]:
    index: dict[LookupKey, list[tuple[Selector, Rule]]] = defaultdict(list)
    receivers_by_source: dict[str, set[str]] = defaultdict(set)
    rule_ids: set[str] = set()
    for rule in rules:
        if not rule.id or rule.id in rule_ids:
            raise ValueError(f"empty or duplicate rule ID: {rule.id!r}")
        if not rule.selectors:
            raise ValueError(f"{rule.id}: expected at least one selector")
        rule_ids.add(rule.id)
        for selector in rule.selectors:
            index[_selector_key(selector)].append((selector, rule))
        sharing = rule.evidence_sharing
        if sharing is not None:
            if not sharing.receiver:
                raise ValueError(f"{rule.id}: expected a nonempty receiving tool ID")
            if not sharing.sources or not all(sharing.sources):
                raise ValueError(f"{rule.id}: expected one or more nonempty source tool IDs")
            for source in sharing.sources:
                receivers_by_source[source].add(sharing.receiver)
    return index, receivers_by_source


def _selector_key(selector: Selector) -> LookupKey:
    file_only = selector.filename is not None or selector.extension is not None
    directory_only = selector.directory_name is not None
    if selector.kind not in (None, "file", "directory"):
        raise ValueError("unsupported selector kind")
    if (file_only and (directory_only or selector.kind == "directory")) or (directory_only and selector.kind == "file"):
        raise ValueError("contradictory selector kinds")

    for name in (selector.filename, selector.directory_name):
        if name is not None and not is_path_component(name):
            raise ValueError("selector name must be one path component")
    if selector.extension is not None:
        filename = f"file{selector.extension}"
        if not selector.extension or not is_path_component(filename) or Path(filename).suffix != selector.extension:
            raise ValueError("selector extension must be a dotted suffix")

    if selector.path is not None:
        if not selector.path or not all(map(is_path_component, selector.path)):
            raise ValueError("selector path must contain relative path components")
        return "path", selector.path
    if selector.filename is not None:
        return "file", (selector.filename,)
    if selector.directory_name is not None:
        return "directory", (selector.directory_name,)
    if selector.extension is not None:
        return "extension", (selector.extension,)
    raise ValueError("selector needs a path, filename, directory name, or extension")


def _entry_keys(entry: InventoryEntry) -> Iterator[LookupKey]:
    yield "path", entry.relative_path
    yield entry.kind, (entry.relative_path[-1],)
    if entry.kind == "file" and entry.extension is not None:
        yield "extension", (entry.extension,)


def _matches(selector: Selector, entry: InventoryEntry) -> bool:
    name = entry.relative_path[-1]
    return (
        (selector.path is None or entry.relative_path == selector.path)
        and (selector.kind is None or entry.kind == selector.kind)
        and (selector.filename is None or (entry.kind == "file" and name == selector.filename))
        and (selector.directory_name is None or (entry.kind == "directory" and name == selector.directory_name))
        and (selector.extension is None or (entry.kind == "file" and entry.extension == selector.extension))
    )
