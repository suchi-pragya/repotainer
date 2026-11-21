import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from functools import cached_property
from pathlib import Path
from types import MappingProxyType

from repotainer.detection.model import Diagnostic, TomlValue, is_path_component
from repotainer.scanning.inventory import InventoryEntry

FILE_SIZE_LIMIT = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _Failure:
    reason: str


class MatchedEntryReader:
    """Read content on demand and share the outcome for one inventory entry."""

    def __init__(self, root: Path, entry: InventoryEntry) -> None:
        self._root = root
        self._entry = entry
        self.diagnostics: list[Diagnostic] = []

    def read_text(self, entry: InventoryEntry) -> str | None:
        self._check_entry(entry)
        return self._text

    def read_toml(self, entry: InventoryEntry) -> Mapping[str, TomlValue] | None:
        self._check_entry(entry)
        return self._toml

    def _check_entry(self, entry: InventoryEntry) -> None:
        if entry != self._entry or entry.kind != "file":
            raise ValueError("readers require the matched regular-file entry")

    @cached_property
    def _text(self) -> str | None:
        content = self._decoded
        if isinstance(content, _Failure):
            self._diagnose("text", content)
            return None
        return content

    @cached_property
    def _toml(self) -> Mapping[str, TomlValue] | None:
        content = self._decoded
        if isinstance(content, _Failure):
            self._diagnose("toml", content)
            return None
        try:
            parsed = tomllib.loads(content)
            return MappingProxyType({key: _freeze_toml(value) for key, value in parsed.items()})
        except ValueError, RecursionError:
            self._diagnose("toml", _Failure("invalid-toml"))
            return None

    def _diagnose(self, reader: str, failure: _Failure) -> None:
        self.diagnostics.append(Diagnostic(self._entry.relative_path, reader, failure.reason))

    @cached_property
    def _decoded(self) -> str | _Failure:
        content = self._read_bytes()
        if isinstance(content, _Failure):
            return content
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return _Failure("invalid-utf8")

    def _read_bytes(self) -> bytes | _Failure:
        try:
            path = self._checked_path()
            if isinstance(path, _Failure):
                return path
            with path.open("rb") as stream:
                content = stream.read(FILE_SIZE_LIMIT + 1)
        except FileNotFoundError:
            return _Failure("missing")
        except OSError:
            return _Failure("read-error")
        if len(content) > FILE_SIZE_LIMIT:
            return _Failure("too-large")
        return content

    def _checked_path(self) -> Path | _Failure:
        parts = self._entry.relative_path
        if not parts or not all(map(is_path_component, parts)):
            return _Failure("rejected-path")

        path = self._root
        for position, part in enumerate(parts, start=1):
            path /= part
            metadata = path.lstat()
            if getattr(metadata, "st_reparse_tag", 0) == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1):
                return _Failure("rejected-path")
            is_expected_type = stat.S_ISREG if position == len(parts) else stat.S_ISDIR
            if not is_expected_type(metadata.st_mode):
                return _Failure("rejected-path")

        if not path.resolve(strict=True).is_relative_to(self._root):
            return _Failure("rejected-path")
        return path


def _freeze_toml(value: object) -> TomlValue:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_toml(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(map(_freeze_toml, value))
    if isinstance(value, (str, int, float, date, time)):
        return value
    raise TypeError("unexpected TOML value")
