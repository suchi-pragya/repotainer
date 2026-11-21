import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from repotainer.cli import app
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
            result = self.runner.invoke(app)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(f"Scan root: {root}", result.stdout)
            self.assertIn("Files: 1", result.stdout)
            help_result = self.runner.invoke(app, ["--help"])
            self.assertEqual(help_result.exit_code, 0, help_result.output)
            self.assertIn("Directory to inventory", help_result.stdout)
            self.assertNotIn("--allow-no-git", help_result.stdout)

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
            with self.subTest(path=path):
                result = self.runner.invoke(app, [str(path)])
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn(str(path), result.stderr)
                self.assertNotIn("Scan root:", result.stdout)

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
        result = self.runner.invoke(app, [str(self.root)])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(".gitignore:1:", result.stderr)
        self.assertNotIn("Scan root:", result.stdout)

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
        for index in range(1_002):
            (self.root / str(index)).touch()
        for answer, status in (("y\n", 0), ("n\n", 1), ("\n", 1), ("", 2)):
            with self.subTest(answer=answer):
                result = self.runner.invoke(app, [str(self.root)], input=answer)
                self.assertEqual(result.exit_code, status, result.output)
                self.assertEqual(result.output.count("Continue?"), 1)
                if status == 0:
                    self.assertIn("Files: 1002", result.stdout)
                else:
                    self.assertNotIn("Scan root:", result.stdout)
                    message = "Inventory cancelled" if status == 1 else "input unavailable"
                    self.assertIn(message, result.stderr)
