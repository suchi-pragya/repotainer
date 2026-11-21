import stat
from pathlib import Path


def resolve_scan_root(path: Path) -> Path:
    """Resolve an existing directory that can be used as the inventory root."""
    try:
        target = path.expanduser()
    except RuntimeError as error:
        raise ValueError(f"{path}: {error}") from error
    metadata = target.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or target.is_junction():
        raise ValueError(f"{path}: expected a directory, got a file or another unsupported path type")
    root = target.resolve(strict=True)
    if ".git" in root.parts:
        raise ValueError(f"{path}: cannot inventory a .git metadata directory")
    return root
