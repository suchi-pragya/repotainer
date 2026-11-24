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
        self.assertEqual(config, {"tools": {"python": "3.13", "uv": "latest"}})
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
        self.assertIn('Recommended Mise request: python = "latest"', result.stderr)
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

    def test_manifest_takes_precedence_over_conflicting_series(self) -> None:
        (self.root / ".python-version").write_text("3.12\n", encoding="utf-8")
        (self.root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.13"\n', encoding="utf-8")

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("value='3.12'", result.stdout)
        self.assertIn("value='>=3.13'", result.stdout)
        config = tomllib.loads((self.root / "mise.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"tools": {"python": "3.13"}})
        self.assertIn("using the highest-priority evidence", result.stderr)
        self.assertIn("Set aside: .python-version", result.stderr)

    def test_nested_manifest_takes_precedence_over_root_exact_pin(self) -> None:
        for selected in (".", "examples/legacy"):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                nested = root / "examples" / "legacy"
                nested.mkdir(parents=True)
                (root / ".python-version").write_bytes(b"3.13.2\n")
                (nested / "pyproject.toml").write_bytes(b'[project]\nrequires-python = ">=3.12,<3.13"\n')
                target = root / selected

                result = self.runner.invoke(app, [str(target)])

                self.assertEqual(result.exit_code, 0, result.output)
                self.assertNotIn("Choose a python version", result.output)
                self.assertEqual(tomllib.loads((target / "mise.toml").read_text()), {"tools": {"python": "3.12"}})
                self.assertTrue((target / ".devcontainer" / "devcontainer.json").is_file())
                if selected == ".":
                    self.assertIn("examples/legacy/pyproject.toml", result.stderr)
                    self.assertIn("Set aside: .python-version = '3.13.2'", result.stderr)
                else:
                    self.assertNotIn(".python-version", result.output)
                    self.assertFalse((root / "mise.toml").exists())

    def test_unsupported_authoritative_evidence_uses_latest_with_warning(self) -> None:
        (self.root / ".python-version").write_bytes(b"3.13.7\n")
        (self.root / "pyproject.toml").write_bytes(b'[project]\nrequires-python = ">=3.15.0rc1,<3.16"\n')

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pyproject.toml 'project.requires-python' = '>=3.15.0rc1,<3.16'", result.stderr)
        self.assertIn("compatibility with the highest-priority declaration", result.stderr)
        self.assertEqual(tomllib.loads((self.root / "mise.toml").read_text()), {"tools": {"python": "latest"}})

    def write_manifest_conflict(self, root: Path) -> None:
        nested = root / "examples" / "legacy"
        nested.mkdir(parents=True)
        (root / "pyproject.toml").write_bytes(b'[project]\nrequires-python = ">=3.13,<3.14"\n')
        (nested / "pyproject.toml").write_bytes(b'[project]\nrequires-python = ">=3.12,<3.13"\n')

    def test_interactive_version_choices_include_latest_and_retry_invalid_input(self) -> None:
        for choice, request in enumerate(("3.12", "3.13", "latest"), 1):
            with self.subTest(choice=choice), patch("repotainer.commands.main._can_prompt", return_value=True):
                root = self.root / str(choice)
                self.write_manifest_conflict(root)
                result = self.runner.invoke(app, [str(root)], input=f"9\n{choice}\n")
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(tomllib.loads((root / "mise.toml").read_text()), {"tools": {"python": request}})
                menu = [
                    line.strip() for line in result.stderr.splitlines() if line.startswith(("  1.", "  2.", "  3."))
                ]
                self.assertEqual(
                    menu,
                    [
                        "1. 3.12 from examples/legacy/pyproject.toml 'project.requires-python' = '>=3.12,<3.13'",
                        "2. 3.13 from pyproject.toml 'project.requires-python' = '>=3.13,<3.14'",
                        "3. latest",
                    ],
                )
                self.assertIn("Choose a number from 1 to 3.", result.stderr)
                self.assertNotIn("Choose a python version", result.stdout)

    def test_prompt_uses_stdin_and_stderr_terminals(self) -> None:
        for stdin_tty, stderr_tty in ((True, True), (False, True), (True, False)):
            with (
                self.subTest(stdin=stdin_tty, stderr=stderr_tty),
                patch("repotainer.commands.main.sys") as streams,
            ):
                root = self.root / f"{stdin_tty}-{stderr_tty}"
                self.write_manifest_conflict(root)
                streams.stdin.isatty.return_value = stdin_tty
                streams.stderr.isatty.return_value = stderr_tty
                streams.stdout.isatty.return_value = False
                interactive = stdin_tty and stderr_tty
                result = self.runner.invoke(app, [str(root)], input="2\n" if interactive else "")
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual("Choose a python version" in result.stderr, interactive)
                if not interactive:
                    self.assertIn('using "latest" (unattended run)', result.stderr)
                    self.assertIn("examples/legacy/pyproject.toml", result.stderr)
                expected = "3.13" if interactive else "latest"
                self.assertEqual(tomllib.loads((root / "mise.toml").read_text()), {"tools": {"python": expected}})

    def test_interrupted_version_prompt_leaves_project_untouched(self) -> None:
        self.write_manifest_conflict(self.root)
        for interruption in (EOFError, KeyboardInterrupt):
            with (
                self.subTest(interruption=interruption),
                patch("repotainer.commands.main._can_prompt", return_value=True),
                patch("repotainer.commands.main.typer.prompt", side_effect=interruption),
                patch("repotainer.commands.main.write_scaffold") as writer,
            ):
                result = self.runner.invoke(app, [str(self.root)])
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn("Scaffold selection cancelled", result.stderr)
                writer.assert_not_called()
        self.assertFalse((self.root / "mise.toml").exists())
        self.assertFalse((self.root / ".devcontainer").exists())

    def test_version_warning_displays_control_characters_as_text(self) -> None:
        unusual = Evidence(("example\npath", ".python-version"), value="3.13.\x1b")
        detection = DetectionResult((ToolEvidence("python", (unusual,)),), ())
        with patch("repotainer.commands.main.detect", return_value=detection):
            result = self.runner.invoke(app, [str(self.root)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(repr(detection), result.stdout)
        self.assertIn(r"example\npath/.python-version", result.stderr)
        self.assertIn(r"3.13.\x1b", result.stderr)
        self.assertNotIn("\x1b", result.stderr)
        self.assertEqual(tomllib.loads((self.root / "mise.toml").read_text()), {"tools": {"python": "latest"}})

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

    def test_preserves_ignored_root_mise_and_reuses_existing_directory(self) -> None:
        (self.root / "uv.lock").touch()
        (self.root / ".gitignore").write_bytes(b"mise.toml\n")
        mise = self.root / "mise.toml"
        mise.write_bytes(b"[tools]\n")
        unrelated = self.root / ".devcontainer" / "notes.txt"
        unrelated.parent.mkdir()
        unrelated.write_bytes(b"keep me")
        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Preserved existing project mise configuration.", result.stdout)
        self.assertEqual(mise.read_bytes(), b"[tools]\n")
        self.assertEqual(unrelated.read_bytes(), b"keep me")
        self.assertTrue((unrelated.parent / "devcontainer.json").is_file())

    def test_reports_blocked_destinations_without_writing(self) -> None:
        (self.root / ".devcontainer").mkdir()
        (self.root / ".devcontainer" / "Dockerfile").mkdir()
        (self.root / ".devcontainer" / "devcontainer.json").mkdir()
        (self.root / "mise.toml").write_bytes(b"[tools]\n")

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("DetectionResult", result.stdout)
        self.assertEqual(
            result.stderr.splitlines(),
            [
                "Error: Scaffold conflicts. No files created.",
                "  .devcontainer/Dockerfile",
                "  .devcontainer/devcontainer.json",
                "Preserved existing mise.toml.",
            ],
        )
        self.assertFalse((self.root / ".devcontainer" / "setup.sh").exists())
        self.assertEqual((self.root / "mise.toml").read_bytes(), b"[tools]\n")

    def test_devcontainer_conflict_reports_recommendations_before_stopping(self) -> None:
        (self.root / "uv.lock").touch()
        (self.root / ".devcontainer").write_bytes(b"blocked")

        result = self.runner.invoke(app, [str(self.root)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("ToolEvidence(tool='uv'", result.stdout)
        self.assertIn('Recommended Mise request: uv = "latest"', result.stderr)
        self.assertIn("  .devcontainer", result.stderr)
        self.assertFalse((self.root / "mise.toml").exists())
        self.assertEqual((self.root / ".devcontainer").read_bytes(), b"blocked")

    def test_replacement_groups_are_approved_independently_after_preview(self) -> None:
        for devcontainer, mise in (("y", "y"), ("n", "y"), ("y", "n"), ("n", "n")):
            with (
                self.subTest(devcontainer=devcontainer, mise=mise),
                patch("repotainer.commands.main._can_prompt", return_value=True),
            ):
                root = self.root / f"{devcontainer}-{mise}"
                config = root / ".devcontainer" / "devcontainer.json"
                config.parent.mkdir(parents=True)
                config.write_bytes(b'{"name": "existing"}\n')
                (root / ".python-version").write_bytes(b"3.13.7\n")
                (root / "mise.toml").write_bytes(b'[tools]\npython = "3.12"\n')

                result = self.runner.invoke(app, [str(root)], input=f"{devcontainer}\n{mise}\n")

                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn('Recommended Mise request: python = "3.13.7"', result.stderr)
                self.assertIn("Current Mise request: 'python' = \"3.12\"", result.stderr)
                self.assertLess(
                    result.output.index("DetectionResult"), result.output.index("Replace existing Dev Container")
                )
                self.assertLess(
                    result.stderr.index("Replace entire file .devcontainer/devcontainer.json"),
                    result.stderr.index("Replace existing Dev Container"),
                )
                self.assertLess(
                    result.stderr.index("Replace existing Dev Container"), result.stderr.index("Replace existing Mise")
                )
                self.assertLess(
                    result.stderr.index("Replace entire file mise.toml"), result.stderr.index("Replace existing Mise")
                )
                self.assertEqual(
                    tomllib.loads((root / "mise.toml").read_text())["tools"]["python"],
                    "3.13.7" if mise == "y" else "3.12",
                )
                self.assertEqual(config.read_bytes() == b'{"name": "existing"}\n', devcontainer == "n")
                self.assertEqual((config.parent / "setup.sh").exists(), devcontainer == "y")

    def test_unattended_run_preserves_both_groups_and_reports_recommendation(self) -> None:
        config = self.root / ".devcontainer" / "devcontainer.json"
        config.parent.mkdir()
        config.write_bytes(b"existing container")
        (self.root / "mise.toml").write_bytes(b'[tools]\npython = "3.12"\n')
        (self.root / ".python-version").write_bytes(b"3.13.7\n")
        with patch("repotainer.commands.main._can_prompt", return_value=False):
            result = self.runner.invoke(app, [str(self.root)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('Recommended Mise request: python = "3.13.7"', result.stderr)
        self.assertNotIn("Replace existing", result.stderr)
        self.assertIn("No scaffold files changed.", result.stdout)
        self.assertEqual(config.read_bytes(), b"existing container")
        self.assertEqual((self.root / "mise.toml").read_bytes(), b'[tools]\npython = "3.12"\n')

    def test_eof_after_first_replacement_approval_creates_no_files(self) -> None:
        config = self.root / ".devcontainer" / "devcontainer.json"
        config.parent.mkdir()
        config.write_bytes(b"old")
        (self.root / "mise.toml").write_bytes(b"[tools]\n")
        with (
            patch("repotainer.commands.main._can_prompt", return_value=True),
            patch("repotainer.commands.main.write_scaffold") as writer,
        ):
            result = self.runner.invoke(app, [str(self.root)], input="y\n")
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Scaffold selection cancelled", result.stderr)
        writer.assert_not_called()
        self.assertEqual(config.read_bytes(), b"old")

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
