from collections.abc import Mapping

from repotainer.detection.model import EntryReader, Evidence, Rule, Selector
from repotainer.scanning.inventory import InventoryEntry


def _poetry_workflow(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    manifest = reader.read_toml(entry)
    if manifest is None:
        return ()
    tool = manifest.get("tool")
    if isinstance(tool, Mapping) and isinstance(tool.get("poetry"), Mapping):
        return (("poetry", Evidence(entry.relative_path, field=("tool", "poetry"))),)
    return ()


POETRY_RULE = Rule("poetry-workflow", (Selector(filename="pyproject.toml"),), _poetry_workflow)
