import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from repotainer.cli import app
from repotainer.scanning.repository import inspect_repository


class RepositoryContextTests(unittest.TestCase):
    def test_nested_file_uses_nearest_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            nested = root / "src"
            nested.mkdir()
            target = nested / "main.py"
            target.touch()

            context = inspect_repository(target)

            self.assertEqual(context.target, target)
            self.assertEqual(context.kind, "file")
            self.assertEqual(context.scan_root, nested)
            self.assertEqual(context.git_root, root)

    def test_git_file_marks_a_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").write_text("gitdir: elsewhere\n")

            context = inspect_repository(root)

            self.assertEqual(context.git_root, root)

    def test_no_git_requires_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runner = CliRunner()

            with patch("repotainer.scanning.repository._find_git_root", return_value=None):
                blocked = runner.invoke(app, ["detect", temporary_directory])
                allowed = runner.invoke(app, ["detect", temporary_directory, "--allow-no-git"])

            self.assertEqual(blocked.exit_code, 2)
            self.assertIn("Warning: no Git integration detected", blocked.output)
            self.assertEqual(allowed.exit_code, 0)
            self.assertIn("Git root: none", allowed.output)
