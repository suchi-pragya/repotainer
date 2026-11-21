import stat
from dataclasses import dataclass
from pathlib import Path

from repotainer.scanning.paths import resolve_scan_root


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    scan_root: Path
    has_git_directory: bool


def inspect_repository(path: Path) -> RepositoryContext:
    """Resolve the target and check for a .git directory at that root."""
    scan_root = resolve_scan_root(path)
    marker = scan_root / ".git"
    try:
        metadata = marker.lstat()
    except FileNotFoundError:
        return RepositoryContext(scan_root, False)

    return RepositoryContext(scan_root, stat.S_ISDIR(metadata.st_mode) and not marker.is_junction())
