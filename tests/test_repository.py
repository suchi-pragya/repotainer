import tempfile
import tomllib
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from repotainer.cli import app
from repotainer.detection import BUILTIN_RULES, detect
from repotainer.detection.model import DetectionResult, Diagnostic, Evidence, ToolEvidence
from repotainer.scaffold import ScaffoldWriteError
from repotainer.scanning.inventory import scan_inventory
from repotainer.scanning.repository import inspect_repository


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        temporary_directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temporary_directory).resolve()

    def test_default_directory_and_help(self) -> None:
        with chdir(self.root):
            root = self.root
            (root / "pyproject.toml").touch()
            inventory = scan_inventory(root, lambda *_: True)
            with patch("repotainer.commands.main.detect", wraps=detect) as detector:
                result = self.runner.invoke(app)
            detector.assert_called_once_with(inventory, BUILTIN_RULES)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(f"Scan root: {root}", result.stdout)
            self.assertIn("Files: 1", result.stdout)
            self.assertTrue((root / ".devcontainer" / "devcontainer.json").is_file())
            self.assertEqual((root / "mise.toml").read_bytes(), b"[tools]\n")
            help_result = self.runner.invoke(app, ["--help"])
            self.assertEqual(help_result.exit_code, 0, help_result.output)
            self.assertIn("Directory to inventory", help_result.stdout)
            self.assertIn("print detected tool evidence", help_result.stdout)
            self.assertIn("dev container scaffold", " ".join(help_result.stdout.split()))
            self.assertNotIn("--allow-no-git", help_result.stdout)

    def test_prints_complete_evidence_after_inventory(self) -> None:
        (self.root / ".python-version").write_text("3.13\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.12"\n[tool.poetry]\n', encoding="utf-8"
        )
        (self.root / "uv.lock").touch()

        result = self.runner.invoke(app, [str(self.root)])

        expected = DetectionResult(
            tools=(
                ToolEvidence("poetry", (Evidence(("pyproject.toml",), ("tool", "poetry")),)),
                ToolEvidence(
                    "python",
                    (
                        Evidence((".python-version",), value="3.13"),
                        Evidence(("pyproject.toml",), ("project", "requires-python"), ">=3.12"),
                        Evidence(("pyproject.toml",), ("tool", "poetry")),
                        Evidence(("uv.lock",)),
                    ),
                ),
                ToolEvidence("uv", (Evidence(("uv.lock",)),)),
            ),
            diagnostics=(),
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Files: 3", result.stdout)
        config = tomllib.loads((self.root / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"tools": {"python": "latest", "uv": "latest"}})
        self.assertEqual(
            result.stdout.splitlines()[4:],
            [
                "Pruned directories: 0",
                repr(expected),
                "Created scaffold files:",
                "  .devcontainer/Dockerfile",
                "  .devcontainer/setup.sh",
                "  mise.toml",
                "  .devcontainer/devcontainer.json",
            ],
        )

    def test_prints_declaration_diagnostics_alongside_evidence(self) -> None:
        (self.root / "pyproject.toml").write_text("[project\n", encoding="utf-8")
        (self.root / "uv.lock").touch()

        result = self.runner.invoke(app, [str(self.root)])

        expected = DetectionResult(
            tools=(ToolEvidence("python", (Evidence(("uv.lock",)),)), ToolEvidence("uv", (Evidence(("uv.lock",)),))),
            diagnostics=(Diagnostic(("pyproject.toml",), "toml", "invalid-toml"),),
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.stdout.splitlines()[5:7], [repr(expected), "Created scaffold files:"])
        self.assertTrue((self.root / ".devcontainer" / "devcontainer.json").is_file())
        self.assertEqual(result.stderr, "")
        config = tomllib.loads((self.root / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"tools": {"python": "latest", "uv": "latest"}})

    def test_nested_uv_evidence_populates_mise_config_at_scan_root(self) -> None:
        nested = self.root / "app"
        nested.mkdir()
        (nested / "uv.lock").touch()

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        config = tomllib.loads((self.root / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"tools": {"python": "latest", "uv": "latest"}})
        self.assertFalse((nested / "mise.toml").exists())

    def test_poetry_evidence_adds_only_python_to_mise_config(self) -> None:
        (self.root / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("ToolEvidence(tool='poetry'", result.stdout)
        config = tomllib.loads((self.root / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"tools": {"python": "latest"}})

    def test_conflicting_python_versions_still_generate_latest(self) -> None:
        (self.root / ".python-version").write_text("3.12\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.13"\n', encoding="utf-8")

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("value='3.12'", result.stdout)
        self.assertIn("value='>=3.13'", result.stdout)
        config = tomllib.loads((self.root / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"tools": {"python": "latest"}})

    def test_detector_error_propagates_without_scan_error_or_success_output(self) -> None:
        error = ValueError("invalid built-in rule")
        with patch("repotainer.commands.main.detect", side_effect=error):
            result = self.runner.invoke(app, [str(self.root)])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIs(result.exception, error)
        self.assertIn("No .git directory found", result.stdout)
        self.assertNotIn("Scan root:", result.stdout)
        self.assertNotIn("DetectionResult", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_subdirectory_is_its_own_scope(self) -> None:
        (self.root / ".git").mkdir()
        (self.root / ".gitignore").write_text("app/parent-only.txt\n", encoding="utf-8")
        target = self.root / "app"
        target.mkdir()
        (target / ".gitignore").write_text("local.txt\n", encoding="utf-8")
        (target / "parent-only.txt").touch()
        (target / "local.txt").touch()
        result = self.runner.invoke(app, [str(target)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(result.stdout.startswith(f"No .git directory found at {target}."))
        self.assertIn("Files: 2", result.stdout)

    def test_git_directory_is_informational_and_pruned(self) -> None:
        marker = self.root / ".git"
        marker.mkdir()
        (marker / "config").touch()
        result = self.runner.invoke(app, [str(self.root)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(result.stdout.startswith(f"Found a .git directory at {self.root}."))
        self.assertIn("Files: 0", result.stdout)
        self.assertIn("Pruned directories: 1", result.stdout)
        self.assertEqual(result.stdout.splitlines()[5:7], [repr(DetectionResult((), ())), "Created scaffold files:"])

    def test_git_file_and_symlink_do_not_count_as_local_git(self) -> None:
        marker = self.root / ".git"
        marker.write_text("gitdir: elsewhere\n", encoding="utf-8")
        self.assertFalse(inspect_repository(self.root).has_git_directory)
        self.assertIn("Files: 0", self.runner.invoke(app, [str(self.root)]).stdout)
        marker.unlink()
        target = self.root / "metadata"
        target.mkdir()
        try:
            marker.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        self.assertFalse(inspect_repository(self.root).has_git_directory)

    def test_invalid_targets_do_not_scan(self) -> None:
        file = self.root / "main.py"
        file.touch()
        git_contents = self.root / ".git" / "objects"
        git_contents.mkdir(parents=True)
        for path in (file, self.root / "missing", git_contents.parent, git_contents):
            with self.subTest(path=path), patch("repotainer.commands.main.detect") as detector:
                result = self.runner.invoke(app, [str(path)])
                detector.assert_not_called()
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn(str(path), result.stderr)
                self.assertNotIn("Scan root:", result.stdout)
                self.assertNotIn("DetectionResult", result.stdout)
        self.assertFalse((self.root / ".devcontainer").exists())
        self.assertFalse((self.root / "mise.toml").exists())

    def test_explicit_symlink_is_rejected(self) -> None:
        link = self.root / "link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        result = self.runner.invoke(app, [str(link)])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("link: expected a directory", result.stderr)

    def test_inventory_errors_identify_path_without_printing_summary(self) -> None:
        (self.root / ".gitignore").write_text("file[[:digit:]]\n", encoding="utf-8")
        with patch("repotainer.commands.main.detect") as detector:
            result = self.runner.invoke(app, [str(self.root)])
        detector.assert_not_called()
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(".gitignore:1:", result.stderr)
        self.assertNotIn("Scan root:", result.stdout)
        self.assertNotIn("DetectionResult", result.stdout)
        self.assertEqual(list(self.root.iterdir()), [self.root / ".gitignore"])

    def test_missing_git_is_distinct_from_metadata_errors(self) -> None:
        marker = self.root / ".git"
        lstat = Path.lstat

        def refuse_marker(path: Path):
            if path == marker:
                raise PermissionError(13, "Permission denied", str(path))
            return lstat(path)

        with patch.object(Path, "lstat", refuse_marker):
            result = self.runner.invoke(app, [str(self.root)])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(str(marker), result.stderr)
        self.assertNotIn("Scan root:", result.stdout)

    def test_confirmation_outcomes(self) -> None:
        for index, (answer, status) in enumerate((("y\n", 0), ("n\n", 1), ("\n", 1), ("", 2))):
            with self.subTest(answer=answer), patch("repotainer.commands.main.detect", wraps=detect) as detector:
                target = self.root / str(index)
                target.mkdir()
                for file_index in range(1_002):
                    (target / str(file_index)).touch()
                inventory = scan_inventory(target, lambda *_: True)
                result = self.runner.invoke(app, [str(target)], input=answer)
                self.assertEqual(result.exit_code, status, result.output)
                self.assertEqual(result.output.count("Continue?"), 1)
                if status == 0:
                    detector.assert_called_once_with(inventory, BUILTIN_RULES)
                    self.assertIn("Files: 1002", result.stdout)
                    self.assertTrue((target / ".devcontainer" / "devcontainer.json").is_file())
                else:
                    detector.assert_not_called()
                    self.assertNotIn("Scan root:", result.stdout)
                    self.assertNotIn("DetectionResult", result.stdout)
                    message = "Inventory cancelled" if status == 1 else "input unavailable"
                    self.assertIn(message, result.stderr)
                    self.assertFalse((target / ".devcontainer").exists())
                    self.assertFalse((target / "mise.toml").exists())

    def test_preserves_ignored_mise_config_and_reuses_existing_directory(self) -> None:
        (self.root / "uv.lock").touch()
        (self.root / ".gitignore").write_text(".mise/\n", encoding="utf-8")
        mise = self.root / ".mise" / "config.toml"
        mise.parent.mkdir()
        mise.write_bytes(b"[tools]\n")
        unrelated = self.root / ".devcontainer" / "notes.txt"
        unrelated.parent.mkdir()
        unrelated.write_bytes(b"keep me")
        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Preserved existing project mise configuration.", result.stdout)
        self.assertFalse((self.root / "mise.toml").exists())
        self.assertEqual(mise.read_bytes(), b"[tools]\n")
        self.assertEqual(unrelated.read_bytes(), b"keep me")
        self.assertTrue((unrelated.parent / "devcontainer.json").is_file())

    def test_reports_all_conflicts_without_writing(self) -> None:
        committed_paths = (".gitignore", ".devcontainer/Dockerfile", ".devcontainer.json", "mise.toml")
        (self.root / ".devcontainer").mkdir()
        for relative in committed_paths:
            (self.root / relative).write_bytes(b".devcontainer/\n")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("DetectionResult", result.stdout)
        self.assertEqual(
            result.stderr.splitlines(),
            [
                "Error: Scaffold conflicts. No files created.",
                "  .devcontainer.json",
                "  .devcontainer/Dockerfile",
                "Preserved existing mise.toml.",
            ],
        )
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, before)

    def test_devcontainer_conflict_blocks_populated_mise_config(self) -> None:
        inputs = {"uv.lock": b"", ".devcontainer.json": b"{}\n"}
        for name, content in inputs.items():
            (self.root / name).write_bytes(content)

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("ToolEvidence(tool='uv'", result.stdout)
        self.assertEqual(
            result.stderr.splitlines(),
            ["Error: Scaffold conflicts. No files created.", "  .devcontainer.json"],
        )
        self.assertCountEqual((path.name for path in self.root.iterdir()), inputs)
        for name, content in inputs.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertFalse((self.root / "mise.toml").exists())
        self.assertFalse((self.root / ".devcontainer").exists())

    def test_reports_generation_error_and_cleanup_details(self) -> None:
        error = ScaffoldWriteError(
            self.root / ".devcontainer" / "setup.sh",
            OSError("disk full"),
            ((self.root / ".devcontainer" / "Dockerfile", "permission denied"),),
        )
        with patch("repotainer.commands.main.write_scaffold", side_effect=error):
            result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("DetectionResult", result.stdout)
        self.assertNotIn("Created scaffold files", result.stdout)
        self.assertIn("setup.sh: disk full", result.stderr)
        self.assertIn("Dockerfile: permission denied", result.stderr)
