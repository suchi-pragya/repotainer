import sys
import tempfile
import tomllib
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest.mock import patch

from repotainer.detection import BUILTIN_RULES, detect
from repotainer.detection.model import (
    DetectionResult,
    Diagnostic,
    EntryKind,
    EntryReader,
    Evidence,
    Rule,
    Selector,
    TomlValue,
    ToolEvidence,
)
from repotainer.detection.readers import FILE_SIZE_LIMIT
from repotainer.scanning.inventory import Inventory, InventoryEntry, scan_inventory


def presence(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    return (("presence", Evidence(entry.relative_path)),)


def text_value(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    value = reader.read_text(entry)
    if value is None:
        return ()
    return (("text", Evidence(entry.relative_path, value=value)),)


def field_presence(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
    return (("presence", Evidence(entry.relative_path, field=("example",))),)


class DetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temp).resolve()

    def write(self, name: str, content: bytes = b"") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def inventory(self) -> Inventory:
        result = scan_inventory(self.root, lambda root, threshold: False)
        assert result is not None
        return result

    def test_selector_matching_and_overlaps(self) -> None:
        self.write("app/pyproject.toml")
        self.write("samples/PYPROJECT.TOML")
        self.write("docs/pyproject.toml/README")
        self.write(".python-version")
        self.write("other/NOTES.toml")
        inventory = self.inventory()

        seen: list[tuple[str, ...]] = []

        def record(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            seen.append(entry.relative_path)
            return presence(entry, reader)

        combined = Rule(
            "combined",
            (
                Selector(filename="pyproject.toml"),
                Selector(path=("app", "pyproject.toml"), kind="file", extension=".toml"),
                Selector(directory_name="pyproject.toml"),
                Selector(filename=".python-version"),
                Selector(extension=".toml"),
                Selector(path=("samples", "PYPROJECT.TOML"), extension=".toml"),
            ),
            record,
        )
        second = Rule("second", (Selector(filename="pyproject.toml"),), field_presence)
        result = detect(inventory, (combined, second))

        self.assertEqual(
            seen,
            [(".python-version",), ("app", "pyproject.toml"), ("docs", "pyproject.toml"), ("other", "NOTES.toml")],
        )
        self.assertEqual(
            result.tools,
            (
                ToolEvidence(
                    "presence",
                    (
                        Evidence((".python-version",)),
                        Evidence(("app", "pyproject.toml")),
                        Evidence(("app", "pyproject.toml"), field=("example",)),
                        Evidence(("docs", "pyproject.toml")),
                        Evidence(("other", "NOTES.toml")),
                    ),
                ),
            ),
        )

    def test_invalid_registrations_fail_before_evaluation(self) -> None:
        self.write("config.toml")
        inventory = self.inventory()
        valid = Rule("valid", (Selector(extension=".toml"),), presence)
        invalid_selectors = (
            Selector(),
            Selector(kind="file"),
            Selector(filename="config.toml", directory_name="config.toml"),
            Selector(filename="config.toml", kind="directory"),
            Selector(directory_name="config.toml", extension=".toml"),
            Selector(path=()),
            Selector(path=("..", "config.toml")),
            Selector(filename="nested/config.toml"),
            Selector(extension="toml"),
            Selector(path=("config.toml",), kind=cast("EntryKind", "other")),
        )
        for selector in invalid_selectors:
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                detect(inventory, (valid, Rule("invalid", (selector,), presence)))
        for rules in ((valid, valid), (Rule("", valid.selectors, presence),), (Rule("empty", (), presence),)):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                detect(inventory, rules)

    def test_rejects_reader_requests_and_evidence_outside_match(self) -> None:
        self.write("config.toml")
        self.write("other.toml")
        (self.root / "assets").mkdir()
        inventory = self.inventory()
        other = InventoryEntry(("other.toml",), "file", ".toml")

        def read_other(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            reader.read_text(other)
            return ()

        def cite_other(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            return presence(other, reader)

        for rule in (
            Rule("reader", (Selector(filename="config.toml"),), read_other),
            Rule("citation", (Selector(filename="config.toml"),), cite_other),
            Rule("directory", (Selector(directory_name="assets"),), text_value),
        ):
            with self.subTest(rule=rule.id), self.assertRaises(ValueError):
                detect(inventory, (rule,))

    def test_shared_read_is_immutable_and_scoped_to_invocation(self) -> None:
        config = self.write("config.toml", b'title = "first"\n[nested]\nitems = [{ name = "x" }]\n')
        self.write("presence.toml")
        inventory = self.inventory()

        def manifest(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            parsed = reader.read_toml(entry)
            assert parsed is not None
            nested = cast("Mapping[str, TomlValue]", parsed["nested"])
            items = cast("tuple[Mapping[str, TomlValue], ...]", nested["items"])
            self.assertIsInstance(items, tuple)
            with self.assertRaises(TypeError):
                cast("dict[str, TomlValue]", items[0])["name"] = "changed"
            with self.assertRaises(TypeError):
                cast("dict[str, TomlValue]", parsed)["title"] = "changed"
            return (("config", Evidence(entry.relative_path, ("title",), cast("str", parsed["title"]))),)

        rules = (
            Rule("first", (Selector(filename="config.toml"),), manifest),
            Rule("second", (Selector(filename="config.toml"),), manifest),
            Rule("text", (Selector(filename="config.toml"),), text_value),
            Rule("presence", (Selector(filename="presence.toml"),), presence),
        )
        opened: list[Path] = []
        open_path = Path.open

        def record_open(path: Path, *args, **kwargs):
            opened.append(path)
            return open_path(path, *args, **kwargs)

        with (
            patch.object(Path, "open", autospec=True, side_effect=record_open),
            patch("repotainer.detection.readers.tomllib.loads", wraps=tomllib.loads) as parse,
        ):
            first = detect(inventory, rules)
        self.assertEqual(opened, [config])
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(first.tools[0].evidence[0].value, "first")
        config.write_bytes(b'title = "second"\n[nested]\nitems = [{ name = "x" }]\n')
        self.assertEqual(detect(inventory, rules).tools[0].evidence[0].value, "second")

    def test_evidence_and_diagnostics_are_independent_of_registration_order(self) -> None:
        self.write("app/manifest.toml")
        self.write("samples/manifest.toml")
        self.write("b.toml", b"\xff")
        self.write("a.toml", b"[")
        inventory = self.inventory()
        selector = (Selector(filename="manifest.toml"),)

        def recorded(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            return (
                ("presence", Evidence(entry.relative_path, ("example",), "same")),
                ("presence", Evidence(entry.relative_path, ("example",))),
                ("another-tool", Evidence(entry.relative_path, ("example",), "same")),
            )

        def malformed(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            self.assertIsNone(reader.read_toml(entry))
            return ()

        rules = (
            Rule("presence-copy", selector, presence),
            Rule("field", selector, recorded),
            Rule("error", (Selector(filename="b.toml"), Selector(filename="a.toml")), malformed),
            Rule("presence", selector, presence),
            Rule("text-error", (Selector(filename="b.toml"),), text_value),
        )
        expected = DetectionResult(
            tools=(
                ToolEvidence(
                    "another-tool",
                    tuple(Evidence((folder, "manifest.toml"), ("example",), "same") for folder in ("app", "samples")),
                ),
                ToolEvidence(
                    "presence",
                    tuple(
                        record
                        for folder in ("app", "samples")
                        for record in (
                            Evidence((folder, "manifest.toml")),
                            Evidence((folder, "manifest.toml"), ("example",)),
                            Evidence((folder, "manifest.toml"), ("example",), "same"),
                        )
                    ),
                ),
            ),
            diagnostics=(
                Diagnostic(("a.toml",), "toml", "invalid-toml"),
                Diagnostic(("b.toml",), "text", "invalid-utf8"),
                Diagnostic(("b.toml",), "toml", "invalid-utf8"),
            ),
        )
        self.assertEqual(detect(inventory, rules), expected)
        self.assertEqual(detect(inventory, tuple(reversed(rules))), expected)

    def test_read_size_limit_preserves_other_results(self) -> None:
        self.write("exact.toml", b" " * FILE_SIZE_LIMIT)
        self.write("over.toml", b"\xff" * (FILE_SIZE_LIMIT + 1))
        self.write("valid.toml", b"title = 'kept'")
        inventory = self.inventory()

        def manifest(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            if reader.read_toml(entry) is None:
                return ()
            return (("config", Evidence(entry.relative_path)),)

        with patch("repotainer.detection.readers.tomllib.loads", wraps=tomllib.loads) as parse:
            result = detect(inventory, (Rule("manifest", (Selector(extension=".toml"),), manifest),))
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(
            result.tools, (ToolEvidence("config", (Evidence(("exact.toml",)), Evidence(("valid.toml",)))),)
        )
        self.assertEqual(result.diagnostics, (Diagnostic(("over.toml",), "toml", "too-large"),))

    def test_reports_disappeared_file_and_unreadable_file(self) -> None:
        missing = self.write("missing.txt")
        unreadable = self.write("unreadable.txt")
        self.write("valid.txt", b"kept")
        inventory = self.inventory()
        missing.unlink()
        open_path = Path.open

        def open_or_deny(path: Path, *args, **kwargs):
            if path == unreadable:
                raise PermissionError("fixture")
            return open_path(path, *args, **kwargs)

        with patch.object(Path, "open", autospec=True, side_effect=open_or_deny):
            result = detect(inventory, (Rule("text", (Selector(extension=".txt"),), text_value),))
        self.assertEqual(result.tools, (ToolEvidence("text", (Evidence(("valid.txt",), value="kept"),)),))
        self.assertEqual(
            result.diagnostics,
            (Diagnostic(("missing.txt",), "text", "missing"), Diagnostic(("unreadable.txt",), "text", "read-error")),
        )

    def test_rejects_replacement_links_without_opening_them(self) -> None:
        excluded = self.write(".venv/excluded.txt", b"excluded")
        replaced_file = self.write("replace.txt", b"original")
        replaced_child = self.write("parent/child.txt", b"original")
        self.write("valid.txt", b"kept")
        outside = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        (outside / "child.txt").write_bytes(b"outside")
        inventory = self.inventory()

        replaced_file.unlink()
        replaced_child.unlink()
        replaced_child.parent.rmdir()
        try:
            replaced_file.symlink_to(excluded)
            replaced_child.parent.symlink_to(outside, target_is_directory=True)
        except OSError, NotImplementedError:
            self.skipTest("symlink creation unavailable")

        result = detect(inventory, (Rule("text", (Selector(extension=".txt"),), text_value),))
        self.assertEqual(result.tools, (ToolEvidence("text", (Evidence(("valid.txt",), value="kept"),)),))
        self.assertEqual(
            result.diagnostics,
            (
                Diagnostic(("parent", "child.txt"), "text", "rejected-path"),
                Diagnostic(("replace.txt",), "text", "rejected-path"),
            ),
        )

    def test_builtins_consume_actual_inventory_and_preserve_all_sources(self) -> None:
        self.write(".gitignore", b"ignored/\n")
        self.write("ignored/pyproject.toml", b"[")
        self.write("app/.python-version", b"\n  3.12  \n")
        manifest = self.write("app/pyproject.toml", b'[project]\nrequires-python = ">=3.13"\n[tool.poetry]\n')
        samples = self.write("samples/pyproject.toml", b'[project]\nrequires-python = ">=3.13"\n')
        version_file = self.root / "app" / ".python-version"
        self.write("app/uv.lock", b"\xff")
        self.write("other.txt", b"unmatched")
        inventory = self.inventory()

        opened: list[Path] = []
        open_path = Path.open

        def record_open(path: Path, *args, **kwargs):
            opened.append(path)
            return open_path(path, *args, **kwargs)

        with (
            patch.object(Path, "open", autospec=True, side_effect=record_open),
            patch("repotainer.detection.readers.tomllib.loads", wraps=tomllib.loads) as parse,
        ):
            result = detect(inventory, BUILTIN_RULES)
        self.assertEqual(opened, [version_file, manifest, samples])
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(
            result,
            DetectionResult(
                tools=(
                    ToolEvidence("poetry", (Evidence(("app", "pyproject.toml"), ("tool", "poetry")),)),
                    ToolEvidence(
                        "python",
                        (
                            Evidence(("app", ".python-version"), value="3.12"),
                            Evidence(("app", "pyproject.toml"), ("project", "requires-python"), ">=3.13"),
                            Evidence(("samples", "pyproject.toml"), ("project", "requires-python"), ">=3.13"),
                        ),
                    ),
                    ToolEvidence("uv", (Evidence(("app", "uv.lock")),)),
                ),
                diagnostics=(),
            ),
        )

    def test_builtins_extract_supported_declarations_and_report_content_failures(self) -> None:
        self.write("blank/.python-version", b" \n\t")
        self.write("multiple/.python-version", b"3.12\n\n3.13\n")
        self.write("blank/pyproject.toml", b'[project]\nrequires-python = "  "\n')
        self.write("missing/pyproject.toml", b"[project]\n[tool]\n")
        self.write("unsupported/pyproject.toml", b"project = false\n[tool]\npoetry = true\n")
        self.write("wrong-type/pyproject.toml", b"[project]\nrequires-python = 313\n")
        self.write("malformed/pyproject.toml", b"[project")
        previous_limit = sys.get_int_max_str_digits()
        self.addCleanup(sys.set_int_max_str_digits, previous_limit)
        sys.set_int_max_str_digits(sys.int_info.default_max_str_digits)
        digits = sys.get_int_max_str_digits() + 1
        self.write("integer-limit/pyproject.toml", b"number = " + b"1" * digits)
        self.write("nesting-limit/pyproject.toml", b"array = " + b"[" * 2000 + b"1" + b"]" * 2000)
        self.write("encoding/.python-version", b"\xff")
        self.write("encoding/pyproject.toml", b"\xff")
        self.write("valid/pyproject.toml", b'[project]\nrequires-python = " >=3.13 "\n')
        result = detect(self.inventory(), BUILTIN_RULES)

        self.assertEqual(
            result,
            DetectionResult(
                tools=(
                    ToolEvidence(
                        "python", (Evidence(("valid", "pyproject.toml"), ("project", "requires-python"), " >=3.13 "),)
                    ),
                ),
                diagnostics=(
                    Diagnostic(("encoding", ".python-version"), "text", "invalid-utf8"),
                    Diagnostic(("encoding", "pyproject.toml"), "toml", "invalid-utf8"),
                    Diagnostic(("integer-limit", "pyproject.toml"), "toml", "invalid-toml"),
                    Diagnostic(("malformed", "pyproject.toml"), "toml", "invalid-toml"),
                    Diagnostic(("nesting-limit", "pyproject.toml"), "toml", "invalid-toml"),
                ),
            ),
        )

    def test_empty_inventory_and_test_only_go_rule(self) -> None:
        self.assertEqual(detect(self.inventory(), BUILTIN_RULES), DetectionResult((), ()))
        self.write("go.mod")
        inventory = self.inventory()

        def go_module(entry: InventoryEntry, reader: EntryReader) -> tuple[tuple[str, Evidence], ...]:
            return (("go", Evidence(entry.relative_path)),)

        go_rule = Rule("go-module", (Selector(filename="go.mod"),), go_module)
        with patch.object(Path, "open", side_effect=AssertionError("presence rule opened the file")):
            result = detect(inventory, (*BUILTIN_RULES, go_rule))
            self.assertEqual(detect(inventory, BUILTIN_RULES), DetectionResult((), ()))
        self.assertEqual(result, DetectionResult((ToolEvidence("go", (Evidence(("go.mod",)),)),), ()))
