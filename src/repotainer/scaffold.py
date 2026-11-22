"""Write the dev container scaffold and optional mise config into a resolved project root."""

import errno
import os
import stat
from importlib.resources import files
from pathlib import Path

_DEVCONTAINER = Path(".devcontainer")
_DOCKERFILE = _DEVCONTAINER / "Dockerfile"
_SETUP = _DEVCONTAINER / "setup.sh"
_CONFIG = _DEVCONTAINER / "devcontainer.json"
_MISE = Path("mise.toml")

type _FileIdentity = tuple[int, int]


class ScaffoldConflictError(Exception):
    def __init__(self, paths: tuple[Path, ...], preserves_root_mise: bool) -> None:
        super().__init__(", ".join(path.as_posix() for path in paths))
        self.paths = paths
        self.preserves_root_mise = preserves_root_mise


class ScaffoldWriteError(Exception):
    def __init__(self, path: Path | str, cause: OSError, cleanup_problems: tuple[tuple[Path, str], ...] = ()) -> None:
        super().__init__(f"{path}: {cause.strerror or cause}")
        self.path = path
        self.cause = cause
        self.cleanup_problems = cleanup_problems


def write_scaffold(root: Path, *, selected_tools: tuple[str, ...] = ()) -> tuple[Path, ...]:
    """Return the project-relative paths created, in write order."""
    directory = root / _DEVCONTAINER
    directory_stat = _metadata(directory)
    mise_stat = _metadata(root / _MISE)
    preserves_root_mise = _is_config_file(mise_stat)
    conflicts = _devcontainer_conflicts(root, directory_stat)
    if mise_stat is not None and not preserves_root_mise:
        conflicts.add(_MISE)
    if conflicts:
        raise ScaffoldConflictError(tuple(sorted(conflicts, key=Path.as_posix)), preserves_root_mise)

    generate_mise = not preserves_root_mise and not _has_project_mise_config(root)
    payloads = _template_payloads(generate_mise, selected_tools)
    directory_identity = _identity(directory_stat) if directory_stat else None
    created: dict[Path, _FileIdentity | None] = {}
    path = directory
    try:
        if directory_stat is None:
            directory.mkdir()
            created[directory] = None
            metadata = directory.lstat()
            if not _is_directory(directory, metadata):
                raise OSError("scaffold directory changed after creation")
            directory_identity = _identity(metadata)
            created[directory] = directory_identity

        for relative, content in payloads.items():
            path = root / relative
            if relative.parent == _DEVCONTAINER and not _same_directory(directory, directory_identity):
                raise OSError(f"{directory}: directory changed before creation")
            with path.open("xb") as stream:
                created[path] = None
                created[path] = _identity(os.fstat(stream.fileno()))
                stream.write(content)
    except OSError as exc:
        problems = _cleanup(created, directory, directory_identity)
        raise ScaffoldWriteError(path, exc, problems) from exc

    return tuple(payloads)


def _metadata(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ScaffoldWriteError(path, exc) from exc


def _entries(directory: Path) -> list[Path]:
    try:
        return sorted(directory.iterdir())
    except OSError as exc:
        raise ScaffoldWriteError(directory, exc) from exc


def _is_directory(path: Path, metadata: os.stat_result) -> bool:
    return stat.S_ISDIR(metadata.st_mode) and not path.is_junction()


def _is_config_file(metadata: os.stat_result | None) -> bool:
    return metadata is not None and (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode))


def _local_directory(root: Path, path: Path) -> Path | None:
    metadata = _metadata(path)
    if metadata is None:
        return None
    if _is_directory(path, metadata):
        return path
    if not stat.S_ISLNK(metadata.st_mode) and not stat.S_ISDIR(metadata.st_mode):
        return None
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None
        raise ScaffoldWriteError(path, exc) from exc
    if not resolved.is_relative_to(root):
        return None
    resolved_stat = _metadata(resolved)
    return resolved if resolved_stat is not None and _is_directory(resolved, resolved_stat) else None


def _devcontainer_conflicts(root: Path, directory_stat: os.stat_result | None) -> set[Path]:
    conflicts = set()
    alternate = Path(".devcontainer.json")
    if _metadata(root / alternate) is not None:
        conflicts.add(alternate)
    if directory_stat is None:
        return conflicts
    if not _is_directory(root / _DEVCONTAINER, directory_stat):
        conflicts.add(_DEVCONTAINER)
        return conflicts

    for relative in (_DOCKERFILE, _SETUP, _CONFIG):
        if _metadata(root / relative) is not None:
            conflicts.add(relative)
    for child in _entries(root / _DEVCONTAINER):
        directory = _local_directory(root, child)
        if directory is not None and _metadata(directory / _CONFIG.name) is not None:
            conflicts.add(child.relative_to(root) / _CONFIG.name)
    return conflicts


def _has_toml(directory: Path, stems: tuple[str, ...]) -> bool:
    for path in _entries(directory):
        if path.suffix != ".toml":
            continue
        if any(path.stem == stem or path.stem.startswith(stem + ".") for stem in stems) and _is_config_file(
            _metadata(path)
        ):
            return True
    return False


def _has_fragments(root: Path, directory: Path) -> bool:
    fragments = _local_directory(root, directory / "conf.d")
    if fragments is None:
        return False
    for path in _entries(fragments):
        if path.name.startswith("."):
            continue
        if path.suffix == ".toml" and _is_config_file(_metadata(path)):
            return True
        fragment = _local_directory(root, path)
        if fragment is not None and _has_toml(fragment, ("mise",)):
            return True
    return False


def _has_project_mise_config(root: Path) -> bool:
    fixed = (".tool-versions", ".miserc.toml", ".miserc.local.toml")
    if any(_is_config_file(_metadata(root / name)) for name in fixed) or _has_toml(root, ("mise", ".mise")):
        return True

    config = _local_directory(root, root / ".config")
    if config is not None and (
        _is_config_file(_metadata(config / "miserc.toml")) or _has_toml(config, ("mise", ".mise"))
    ):
        return True

    candidates = [root / "mise", root / ".mise"]
    if config is not None:
        candidates.append(config / "mise")
    for path in candidates:
        directory = _local_directory(root, path)
        if directory is None:
            continue
        stems = ("config", "mise", ".mise") if config is not None and path == config / "mise" else ("config",)
        if _has_toml(directory, stems) or _has_fragments(root, directory):
            return True
    return False


def _template_payloads(generate_mise: bool, selected_tools: tuple[str, ...]) -> dict[Path, bytes]:
    bundled = files("repotainer").joinpath("scaffold_templates")
    payloads = {}
    for path in (_DOCKERFILE, _SETUP, _CONFIG):
        if path == _CONFIG and generate_mise:
            tool_lines = "".join(f'{tool} = "latest"\n' for tool in sorted(selected_tools))
            payloads[_MISE] = f"[tools]\n{tool_lines}".encode()
        try:
            payloads[path] = bundled.joinpath(path.name).read_bytes()
        except OSError as exc:
            raise ScaffoldWriteError(f"bundled template {path.name}", exc) from exc
    return payloads


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
