from collections.abc import Mapping

from repotainer.detection.model import EntryReader, Evidence, EvidenceSharing, Rule, Selector
from repotainer.scanning.inventory import InventoryEntry


def _python_runtime(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    if entry.relative_path[-1] == ".python-version":
        content = reader.read_text(entry)
        if content is None:
            return ()
        lines = filter(None, map(str.strip, content.splitlines()))
        version = next(lines, None)
        if version is not None and next(lines, None) is None:
            return (("python", Evidence(entry.relative_path, value=version)),)
        return ()

    manifest = reader.read_toml(entry)
    if manifest is None:
        return ()
    project = manifest.get("project")
    if isinstance(project, Mapping):
        requirement = project.get("requires-python")
        if isinstance(requirement, str) and requirement.strip():
            return (("python", Evidence(entry.relative_path, ("project", "requires-python"), requirement)),)
    return ()


PYTHON_RULE = Rule(
    "python-runtime",
    (Selector(filename=".python-version"), Selector(filename="pyproject.toml")),
    _python_runtime,
    evidence_sharing=EvidenceSharing(receiver="python", sources=("uv", "poetry")),
)
