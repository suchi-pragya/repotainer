from collections.abc import Mapping

from repotainer.detection.model import EntryReader, Evidence, Rule, Selector
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


def _uv_workflow(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    return (("uv", Evidence(entry.relative_path)),)


def _poetry_workflow(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    manifest = reader.read_toml(entry)
    if manifest is None:
        return ()
    tool = manifest.get("tool")
    if isinstance(tool, Mapping) and isinstance(tool.get("poetry"), Mapping):
        return (("poetry", Evidence(entry.relative_path, field=("tool", "poetry"))),)
    return ()


BUILTIN_RULES = (
    Rule(
        "python-runtime", (Selector(filename=".python-version"), Selector(filename="pyproject.toml")), _python_runtime
    ),
    Rule("uv-workflow", (Selector(filename="uv.lock"),), _uv_workflow),
    Rule("poetry-workflow", (Selector(filename="pyproject.toml"),), _poetry_workflow),
)
