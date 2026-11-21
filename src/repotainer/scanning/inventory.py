from __future__ import annotations

import stat
from collections.abc import Callable
from dataclasses import dataclass
from os import DirEntry, fsencode, scandir
from pathlib import Path
from typing import Literal, NamedTuple, Protocol

from repotainer.scanning.ignore import IgnoreRule, read_ignore_rules

LARGE_SCAN_THRESHOLD = 1_000
_EXCLUDED_DIRECTORIES = frozenset({".venv", "node_modules"})


class InventoryEntry(NamedTuple):
    relative_path: tuple[str, ...]
    kind: Literal["file", "directory"]
    extension: str | None


@dataclass(frozen=True, slots=True)
class Inventory:
    scan_root: Path
    entries: tuple[InventoryEntry, ...]
    pruned_directories: int


@dataclass(slots=True)
class _Directory:
    path: Path
    parts: tuple[str, ...]
    rules: tuple[IgnoreRule, ...]
    children: _DirectoryEntries


class _DirectoryEntries(Protocol):
    def __next__(self) -> DirEntry[str]: ...

    def close(self) -> None: ...


def scan_inventory(scan_root: Path, confirm_large_scan: Callable[[Path, int], bool]) -> Inventory | None:
    """Inventory a validated directory. Return None if the caller declines the large scan."""
    entries: list[InventoryEntry] = []
    stack: list[_Directory] = []
    pruned_directories = 0
    active_path = scan_root

    try:
        stack.append(_open_directory(scan_root, ()))
        while stack:
            directory = stack[-1]
            active_path = directory.path
            child = next(directory.children, None)
            if child is None:
                stack.pop().children.close()
                continue

            active_path = Path(child.path)
            parts = (*directory.parts, child.name)
            kind = _entry_kind(child)
            if kind is None:
                continue

            if (
                child.name == ".git"
                or (kind == "directory" and child.name in _EXCLUDED_DIRECTORIES)
                or _is_ignored(stack, parts, kind == "directory")
            ):
                pruned_directories += kind == "directory"
                continue

            if len(entries) == LARGE_SCAN_THRESHOLD and not confirm_large_scan(scan_root, LARGE_SCAN_THRESHOLD):
                return None
            extension = (active_path.suffix or None) if kind == "file" else None
            entries.append(InventoryEntry(parts, kind, extension))
            if kind == "directory":
                stack.append(_open_directory(active_path, parts))
    except OSError as error:
        raise OSError(f"{error.filename or active_path}: {error.strerror or str(error)}") from error
    finally:
        for directory in reversed(stack):
            directory.children.close()

    entries.sort(key=lambda entry: entry.relative_path)
    return Inventory(scan_root, tuple(entries), pruned_directories)


def _open_directory(path: Path, parts: tuple[str, ...]) -> _Directory:
    rules = read_ignore_rules(path)
    return _Directory(path, parts, rules, scandir(path))


def _entry_kind(entry: DirEntry[str]) -> Literal["file", "directory"] | None:
    metadata = entry.stat(follow_symlinks=False)
    if getattr(metadata, "st_reparse_tag", 0) == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1):
        return None
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    if stat.S_ISREG(metadata.st_mode):
        return "file"
    return None


def _is_ignored(stack: list[_Directory], parts: tuple[str, ...], is_directory: bool) -> bool:
    match_path = tuple(fsencode(part).decode("latin-1") for part in parts)
    for directory in reversed(stack):
        relative = match_path[len(directory.parts) :]
        for rule in reversed(directory.rules):
            if rule.matches(relative, is_directory):
                return rule.exclude
    return False
