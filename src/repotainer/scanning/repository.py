from dataclasses import dataclass
from pathlib import Path

from repotainer.scanning.paths import PathKind, describe_path


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    target: Path
    kind: PathKind
    scan_root: Path
    git_root: Path | None


def inspect_repository(path: Path) -> RepositoryContext:
    """Resolve a target and find the closest Git worktree containing it."""
    target, kind = describe_path(path)
    scan_root = target if kind == "directory" else target.parent

    return RepositoryContext(target=target, kind=kind, scan_root=scan_root, git_root=_find_git_root(scan_root))


def _find_git_root(scan_root: Path) -> Path | None:
    """Find the nearest ancestor with a Git directory or worktree file."""

    for directory in (scan_root, *scan_root.parents):
        marker = directory / ".git"
        if marker.is_dir() or marker.is_file():
            return directory

    return None
