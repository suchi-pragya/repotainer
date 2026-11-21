from repotainer.detection.model import EntryReader, Evidence, Rule, Selector
from repotainer.scanning.inventory import InventoryEntry


def _uv_workflow(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    return (("uv", Evidence(entry.relative_path)),)


UV_RULE = Rule("uv-workflow", (Selector(filename="uv.lock"),), _uv_workflow)
