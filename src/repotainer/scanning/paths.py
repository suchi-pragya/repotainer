from pathlib import Path
from typing import Literal

PathKind = Literal["file", "directory"]


def describe_path(path: Path) -> tuple[Path, PathKind]:
    """Resolve a path and identify whether it is a regular file or directory."""
    target = path.expanduser().resolve(strict=True)
    if target.is_file():
        return target, "file"
    if target.is_dir():
        return target, "directory"
    raise ValueError(f"Unsupported path type: {target}")
