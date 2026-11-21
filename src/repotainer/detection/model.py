from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal, Protocol

from repotainer.scanning.inventory import InventoryEntry

type RelativePath = tuple[str, ...]
type EntryKind = Literal["file", "directory"]
type TomlValue = str | bool | int | float | date | datetime | time | Mapping[str, TomlValue] | tuple[TomlValue, ...]


def is_path_component(value: str) -> bool:
    path = Path(value)
    return not path.anchor and path.parts == (value,) and value != ".." and "\0" not in value


@dataclass(frozen=True, slots=True)
class Selector:
    path: RelativePath | None = None
    filename: str | None = None
    directory_name: str | None = None
    extension: str | None = None
    kind: EntryKind | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    path: RelativePath
    field: tuple[str, ...] | None = None
    value: str | None = None


@dataclass(frozen=True, slots=True)
class ToolEvidence:
    tool: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    path: RelativePath
    reader: str
    reason: str


@dataclass(frozen=True, slots=True)
class DetectionResult:
    tools: tuple[ToolEvidence, ...]
    diagnostics: tuple[Diagnostic, ...]


class EntryReader(Protocol):
    def read_text(self, entry: InventoryEntry) -> str | None: ...
    def read_toml(self, entry: InventoryEntry) -> Mapping[str, TomlValue] | None: ...


type Evaluator = Callable[[InventoryEntry, EntryReader], Iterable[tuple[str, Evidence]]]


@dataclass(frozen=True, slots=True)
class EvidenceSharing:
    receiver: str
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    selectors: tuple[Selector, ...]
    evaluate: Evaluator
    evidence_sharing: EvidenceSharing | None = None
