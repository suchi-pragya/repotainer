"""Plan and write the scaffold files at the selected project root."""

import os
import stat
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from shutil import copy2, copymode, rmtree
from tempfile import NamedTemporaryFile, mkdtemp

from repotainer.detection.readers import FILE_SIZE_LIMIT
from repotainer.version_resolution import is_python_request

_DEVCONTAINER = Path(".devcontainer")
_DOCKERFILE = _DEVCONTAINER / "Dockerfile"
_SETUP = _DEVCONTAINER / "setup.sh"
_CONFIG = _DEVCONTAINER / "devcontainer.json"
_MISE = Path("mise.toml")
_CONTAINER_FILES = (_DOCKERFILE, _SETUP, _CONFIG)

type _FileIdentity = tuple[int, int]
type ToolRequests = tuple[tuple[str, str], ...]


class ScaffoldConflictError(Exception):
    def __init__(self, paths: tuple[Path, ...], preserves_root_mise: bool) -> None:
        super().__init__(", ".join(path.as_posix() for path in paths))
        self.paths = paths
        self.preserves_root_mise = preserves_root_mise


class ScaffoldWriteError(Exception):
    def __init__(
        self,
        path: Path | str,
        cause: OSError,
        cleanup_problems: tuple[tuple[Path, str], ...] = (),
        *,
        backup: Path | None = None,
        restored: tuple[Path, ...] = (),
        rolled_back: bool = False,
    ) -> None:
        super().__init__(f"{path}: {cause.strerror or cause}")
        self.path = path
        self.cause = cause
        self.cleanup_problems = cleanup_problems
        self.backup = backup
        self.restored = restored
        self.rolled_back = rolled_back


@dataclass(frozen=True, slots=True)
class ScaffoldDestinations:
    root: Path
    existing: frozenset[Path]
    directory_identity: _FileIdentity | None


@dataclass(frozen=True, slots=True)
class ScaffoldPlan:
    destinations: ScaffoldDestinations
    contents: tuple[tuple[Path, bytes], ...]


@dataclass(frozen=True, slots=True)
class ScaffoldWrites:
    created: tuple[Path, ...]
    replaced: tuple[Path, ...]
    leftover_backup: Path | None


def inspect_scaffold(root: Path) -> ScaffoldDestinations:
    """Inspect only the paths used by the generated scaffold."""
    directory = root / _DEVCONTAINER
    directory_stat = _metadata(directory)
    blocked = []
    if directory_stat is None:
        paths = (_MISE,)
    elif _is_directory(directory, directory_stat):
        paths = (*_CONTAINER_FILES, _MISE)
    else:
        blocked.append(_DEVCONTAINER)
        paths = (_MISE,)

    existing = set()
    for relative in paths:
        metadata = _metadata(root / relative)
        if metadata is None:
            continue
        if stat.S_ISREG(metadata.st_mode):
            existing.add(relative)
        else:
            blocked.append(relative)

    if blocked:
        raise ScaffoldConflictError(tuple(sorted(blocked)), _MISE in existing)
    return ScaffoldDestinations(root, frozenset(existing), _identity(directory_stat) if directory_stat else None)


def existing_mise_tools(destinations: ScaffoldDestinations) -> tuple[tuple[str, str | None], ...] | None:
    """Read the tool table for the preview, without loading Mise configuration."""
    try:
        with (destinations.root / _MISE).open("rb") as stream:
            contents = stream.read(FILE_SIZE_LIMIT + 1)
        if len(contents) > FILE_SIZE_LIMIT:
            return None
        tools = tomllib.loads(contents.decode()).get("tools", {})
    except OSError, UnicodeError, tomllib.TOMLDecodeError:
        return None
    if not isinstance(tools, dict):
        return None
    return tuple(
        (name, value if isinstance(value, str) and (value == "latest" or is_python_request(value)) else None)
        for name, value in sorted(tools.items())
    )


def _valid_request(tool: str, request: str) -> bool:
    if tool == "python":
        return request == "latest" or is_python_request(request)
    return tool == "uv" and request == "latest"


def plan_scaffold(destinations: ScaffoldDestinations, tool_requests: ToolRequests = ()) -> ScaffoldPlan:
    seen: set[str] = set()
    for tool, request in tool_requests:
        if tool in seen or not _valid_request(tool, request):
            raise ValueError(f"invalid or duplicate Mise request for {tool!r}")
        seen.add(tool)

    bundled = files("repotainer").joinpath("scaffold_templates")
    payloads = []
    for path in (_DOCKERFILE, _SETUP, _MISE, _CONFIG):
        if path == _MISE:
            tool_lines = "".join(f'{tool} = "{request}"\n' for tool, request in sorted(tool_requests))
            payloads.append((path, f"[tools]\n{tool_lines}".encode()))
            continue
        try:
            payloads.append((path, bundled.joinpath(path.name).read_bytes()))
        except OSError as exc:
            raise ScaffoldWriteError(f"bundled template {path.name}", exc) from exc
    return ScaffoldPlan(destinations, tuple(payloads))


def write_scaffold(
    plan: ScaffoldPlan, *, replace_devcontainer: bool = False, replace_mise: bool = False
) -> ScaffoldWrites:
    """Apply both approved groups, with rollback across the run on a write error."""
    root = plan.destinations.root
    existing = plan.destinations.existing
    write_container = replace_devcontainer or not existing.intersection(_CONTAINER_FILES)
    write_mise = replace_mise or _MISE not in existing
    writes = tuple(
        (path, content) for path, content in plan.contents if (write_mise if path == _MISE else write_container)
    )
    replacements = tuple(path for path, _ in writes if path in existing)
    backup = _back_up(root, replacements) if replacements else None

    directory = root / _DEVCONTAINER
    directory_identity = plan.destinations.directory_identity
    created: dict[Path, _FileIdentity | None] = {}
    replaced: list[Path] = []
    path = directory
    try:
        if write_container and directory_identity is None:
            directory.mkdir()
            created[directory] = None
            metadata = directory.lstat()
            if not _is_directory(directory, metadata):
                raise OSError("scaffold directory changed after creation")
            directory_identity = _identity(metadata)
            created[directory] = directory_identity

        for relative, content in writes:
            path = root / relative
            if relative.parent == _DEVCONTAINER and not _same_directory(directory, directory_identity):
                raise OSError(f"{directory}: scaffold directory changed")
            if relative in existing:
                _replace_file(path, content)
                replaced.append(relative)
            else:
                with path.open("xb") as stream:
                    created[path] = None
                    created[path] = _identity(os.fstat(stream.fileno()))
                    stream.write(content)
    except OSError as exc:
        problems = _cleanup(created, directory, directory_identity)
        restored, restore_problems = _restore(root, backup, replaced, directory_identity)
        leftover_backup, backup_problems = (backup, ()) if restore_problems else _remove_backup(backup)
        raise ScaffoldWriteError(
            path,
            exc,
            problems + restore_problems + backup_problems,
            backup=leftover_backup,
            restored=restored,
            rolled_back=bool(created or replaced) and not (problems or restore_problems),
        ) from exc

    leftover_backup, _ = _remove_backup(backup)
    return ScaffoldWrites(tuple(path for path, _ in writes if path not in existing), tuple(replaced), leftover_backup)


def _back_up(root: Path, replacements: tuple[Path, ...]) -> Path:
    backup = None
    path = root
    try:
        backup = Path(mkdtemp(prefix="repotainer-backup-"))
        for relative in replacements:
            path = root / relative
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy2(path, destination)
    except OSError as exc:
        leftover, problems = _remove_backup(backup)
        raise ScaffoldWriteError(path, exc, problems, backup=leftover) from exc
    return backup


def _replace_file(path: Path, content: bytes, *, original: Path | None = None) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".repotainer-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        copymode(original or path, temporary)
        temporary.replace(path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _restore(
    root: Path, backup: Path | None, replaced: list[Path], directory_identity: _FileIdentity | None
) -> tuple[tuple[Path, ...], tuple[tuple[Path, str], ...]]:
    if backup is None:
        return (), ()
    restored = []
    problems = []
    directory = root / _DEVCONTAINER
    for relative in reversed(replaced):
        path = root / relative
        original = backup / relative
        try:
            if relative.parent == _DEVCONTAINER and not _same_directory(directory, directory_identity):
                raise OSError("scaffold directory changed; skipped restoration")
            _replace_file(path, original.read_bytes(), original=original)
            restored.append(relative)
        except OSError as exc:
            problems.append((path, exc.strerror or str(exc)))
    return tuple(restored), tuple(problems)


def _remove_backup(backup: Path | None) -> tuple[Path | None, tuple[tuple[Path, str], ...]]:
    if backup is not None:
        try:
            rmtree(backup)
        except OSError as exc:
            return backup, ((backup, exc.strerror or str(exc)),)
    return None, ()


def _metadata(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ScaffoldWriteError(path, exc) from exc


def _is_directory(path: Path, metadata: os.stat_result) -> bool:
    return stat.S_ISDIR(metadata.st_mode) and not path.is_junction()


def _identity(metadata: os.stat_result) -> _FileIdentity:
    return metadata.st_dev, metadata.st_ino


def _same_directory(path: Path, identity: _FileIdentity | None) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return _is_directory(path, metadata) and identity is not None and _identity(metadata) == identity


def _cleanup(
    created: dict[Path, _FileIdentity | None], directory: Path, directory_identity: _FileIdentity | None
) -> tuple[tuple[Path, str], ...]:
    problems = []
    for path, identity in reversed(created.items()):
        try:
            if path.parent == directory and not _same_directory(directory, directory_identity):
                problems.append((path, "scaffold directory changed; skipped cleanup"))
                continue
            current_identity = _identity(path.lstat())
            if identity is None or current_identity != identity:
                problems.append((path, "could not verify ownership; skipped cleanup"))
                continue
            if path == directory:
                path.rmdir()
            else:
                path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            problems.append((path, exc.strerror or str(exc)))
    return tuple(sorted(problems, key=lambda problem: problem[0].as_posix()))
