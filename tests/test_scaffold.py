import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from repotainer.scaffold import ScaffoldConflictError, ScaffoldWriteError, write_scaffold

DOCKERFILE = Path(".devcontainer/Dockerfile")
SETUP = Path(".devcontainer/setup.sh")
CONFIG = Path(".devcontainer/devcontainer.json")
MISE = Path("mise.toml")


class ScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temporary).resolve()

    def test_creates_the_static_files_and_writes_config_last(self) -> None:
        created = write_scaffold(self.root)
        self.assertEqual(created, (DOCKERFILE, SETUP, MISE, CONFIG))
        config = json.loads((self.root / CONFIG).read_bytes())
        self.assertEqual(
            config,
            {"build": {"context": ".", "dockerfile": "Dockerfile"}, "postCreateCommand": "bash .devcontainer/setup.sh"},
        )
        self.assertEqual(tomllib.loads((self.root / MISE).read_text(encoding="utf-8")), {"tools": {}})
        dockerfile = (self.root / DOCKERFILE).read_text(encoding="utf-8")
        self.assertIn("FROM mcr.microsoft.com/devcontainers/base:ubuntu26.04", dockerfile)
        self.assertIn("COPY --from=jdxcode/mise", dockerfile)
        for shell in ("bash", "zsh"):
            self.assertIn(f"mise activate {shell}", dockerfile)
        for excluded in ("uv", "python3", "tmux", "apt-get"):
            self.assertNotIn(excluded, dockerfile)

    def test_preserves_each_supported_project_mise_location(self) -> None:
        locations = (
            "mise.toml",
            ".mise.toml",
            "mise.local.toml",
            ".mise.local.toml",
            "mise.ci.toml",
            "mise.ci.local.toml",
            ".mise.ci.local.toml",
            ".tool-versions",
            ".miserc.toml",
            ".miserc.local.toml",
            ".config/miserc.toml",
            ".config/mise.toml",
            ".config/mise.ci.local.toml",
            ".config/mise/mise.toml",
            ".config/mise/mise.ci.toml",
            ".config/mise/config.local.toml",
            ".mise/config.ci.toml",
            "mise/config.toml",
            "mise/config.ci.local.toml",
            "mise/conf.d/tool.toml",
            ".mise/conf.d/tools.ci.local.toml",
            ".config/mise/conf.d/tools/mise.ci.toml",
        )
        for index, location in enumerate(locations):
            with self.subTest(location=location):
                root = self.root / str(index)
                config = root / location
                config.parent.mkdir(parents=True)
                config.write_bytes(b"unparsed original bytes")
                self.assertEqual(write_scaffold(root), (DOCKERFILE, SETUP, CONFIG))
                self.assertEqual(config.read_bytes(), b"unparsed original bytes")
                self.assertEqual((root / MISE).exists(), location == MISE.as_posix())

    def test_ignores_nested_projects_ancestor_configs_and_hidden_fragments(self) -> None:
        target = self.root / "project"
        for relative in (".mise/conf.d/.hidden/mise.toml", ".mise/conf.d/.hidden.toml", "backend/.mise/config.toml"):
            config = target / relative
            config.parent.mkdir(parents=True, exist_ok=True)
            config.touch()
        (self.root / MISE).touch()
        self.assertIn(MISE, write_scaffold(target))

    def test_project_mise_link_and_outside_directory_link(self) -> None:
        project = self.root / "project"
        outside = self.root / "outside"
        project.mkdir()
        outside.mkdir()
        (outside / "config.toml").touch()
        try:
            (project / ".mise.toml").symlink_to(outside / "missing")
            (project / ".mise").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))

        self.assertNotIn(MISE, write_scaffold(project))
        (project / ".mise.toml").unlink()
        for relative in (DOCKERFILE, SETUP, CONFIG):
            (project / relative).unlink()
        self.assertIn(MISE, write_scaffold(project))

    def test_reports_sorted_conflicts_including_alternate_configurations(self) -> None:
        child_config = self.root / ".devcontainer/python/devcontainer.json"
        child_config.parent.mkdir(parents=True)
        child_config.touch()
        (self.root / DOCKERFILE).mkdir()
        (self.root / ".devcontainer.json").touch()
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.root)
        self.assertEqual(
            raised.exception.paths, (Path(".devcontainer.json"), DOCKERFILE, child_config.relative_to(self.root))
        )
        self.assertFalse((self.root / MISE).exists())
        self.assertFalse((self.root / SETUP).exists())

    def test_reports_a_broken_link_at_an_output_path(self) -> None:
        (self.root / CONFIG.parent).mkdir()
        try:
            (self.root / CONFIG).symlink_to(self.root / "missing.json")
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.root)
        self.assertEqual(raised.exception.paths, (CONFIG,))
        self.assertTrue((self.root / CONFIG).is_symlink())

    def test_blocked_parent_still_reports_root_conflicts_and_mise_preservation(self) -> None:
        (self.root / CONFIG.parent).touch()
        (self.root / ".devcontainer.json").touch()
        (self.root / MISE).write_text("[tools]\n", encoding="utf-8")
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.root)
        self.assertEqual(raised.exception.paths, (CONFIG.parent, Path(".devcontainer.json")))
        self.assertTrue(raised.exception.preserves_root_mise)

    @unittest.skipUnless(sys.platform == "win32", "Windows junctions require Windows")
    def test_windows_junction_is_a_blocked_parent(self) -> None:
        other = self.root / "other"
        other.mkdir()
        junction = self.root / CONFIG.parent
        result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(other)], capture_output=True)
        if result.returncode:
            self.skipTest(result.stderr.decode(errors="replace"))
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.root)
        self.assertEqual(raised.exception.paths, (CONFIG.parent,))
        self.assertEqual(list(other.iterdir()), [])

    def test_directory_at_mise_destination_is_unusable(self) -> None:
        (self.root / MISE).mkdir()
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.root)
        self.assertEqual(raised.exception.paths, (MISE,))
        self.assertFalse((self.root / CONFIG.parent).exists())

    def test_resource_and_metadata_failures_leave_the_target_untouched(self) -> None:
        with (
            tempfile.TemporaryDirectory() as resources,
            patch("repotainer.scaffold.files", return_value=Path(resources)),
        ):
            template_dir = Path(resources) / "scaffold_templates"
            template_dir.mkdir()
            (template_dir / DOCKERFILE.name).write_bytes(
                files("repotainer").joinpath("scaffold_templates", DOCKERFILE.name).read_bytes()
            )
            with self.assertRaises(ScaffoldWriteError) as raised:
                write_scaffold(self.root)
            self.assertEqual(raised.exception.path, "bundled template setup.sh")
            self.assertEqual(list(self.root.iterdir()), [])

        with (
            patch.object(Path, "lstat", side_effect=PermissionError("metadata denied")),
            self.assertRaises(ScaffoldWriteError) as raised,
        ):
            write_scaffold(self.root)
        self.assertEqual(raised.exception.path, self.root / CONFIG.parent)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_late_directory_collision_preserves_the_new_directory(self) -> None:
        mkdir = Path.mkdir

        def create_other_directory(path: Path) -> None:
            mkdir(path)
            (path / "owner.txt").write_bytes(b"another writer")
            mkdir(path)

        with patch.object(Path, "mkdir", create_other_directory), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.root)
        self.assertEqual(raised.exception.path, self.root / CONFIG.parent)
        self.assertEqual(list((self.root / CONFIG.parent).iterdir()), [self.root / CONFIG.parent / "owner.txt"])

    def test_late_file_collision_preserves_the_new_file_and_cleans_up(self) -> None:
        original_open = Path.open

        def open_after_late_creation(path: Path, mode: str, buffering: int = -1):
            if path == self.root / CONFIG:
                with original_open(path, "wb") as stream:
                    stream.write(b"another writer")
            return original_open(path, mode, buffering)

        with patch.object(Path, "open", open_after_late_creation), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.root)
        self.assertEqual(raised.exception.path, self.root / CONFIG)
        self.assertEqual((self.root / CONFIG).read_bytes(), b"another writer")
        self.assertFalse((self.root / SETUP).exists())
        self.assertFalse((self.root / DOCKERFILE).exists())
        self.assertFalse((self.root / MISE).exists())
        self.assertEqual([path for path, _ in raised.exception.cleanup_problems], [self.root / CONFIG.parent])

    def test_cleanup_preserves_a_file_if_its_identity_could_not_be_recorded(self) -> None:
        cause = OSError("could not read identity")
        with patch("repotainer.scaffold.os.fstat", side_effect=cause), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.root)
        self.assertIs(raised.exception.cause, cause)
        self.assertTrue((self.root / DOCKERFILE).exists())
        self.assertIn("could not verify ownership", str(raised.exception.cleanup_problems))

    def test_failed_write_removes_owned_files_and_allows_retry(self) -> None:
        cause = OSError("disk full")
        original_open = Path.open

        @contextmanager
        def fail_after_partial_write(path: Path, mode: str, buffering: int):
            with original_open(path, mode, buffering) as stream:
                write = stream.write

                def write_partial(data: bytes) -> None:
                    write(data[:1])
                    raise cause

                with patch.object(stream, "write", side_effect=write_partial):
                    yield stream

        def open_until_config(path: Path, mode: str, buffering: int = -1):
            if path == self.root / CONFIG:
                return fail_after_partial_write(path, mode, buffering)
            return original_open(path, mode, buffering)

        with patch.object(Path, "open", open_until_config), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.root)
        self.assertIs(raised.exception.cause, cause)
        self.assertEqual(raised.exception.cleanup_problems, ())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(write_scaffold(self.root), (DOCKERFILE, SETUP, MISE, CONFIG))

    def test_cleanup_preserves_an_observed_replacement_file(self) -> None:
        original_open = Path.open
        dockerfile = self.root / DOCKERFILE

        def replace_before_failure(path: Path, mode: str, buffering: int = -1):
            if path == self.root / SETUP:
                dockerfile.rename(self.root / "original")
                with original_open(dockerfile, "xb") as stream:
                    stream.write(b"replacement")
                raise OSError("setup failed")
            return original_open(path, mode, buffering)

        with patch.object(Path, "open", replace_before_failure), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.root)
        self.assertEqual(dockerfile.read_bytes(), b"replacement")
        self.assertIn(dockerfile, dict(raised.exception.cleanup_problems))

    def test_cleanup_stops_accessing_an_observed_replacement_parent(self) -> None:
        original_open = Path.open
        directory = self.root / CONFIG.parent

        def replace_parent(path: Path, mode: str, buffering: int = -1):
            if path == self.root / SETUP:
                directory.rename(self.root / "original")
                directory.mkdir()
                raise OSError("setup failed")
            return original_open(path, mode, buffering)

        with patch.object(Path, "open", replace_parent), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.root)
        self.assertEqual(list(directory.iterdir()), [])
        self.assertTrue((self.root / "original" / DOCKERFILE.name).is_file())
        self.assertIn(directory, dict(raised.exception.cleanup_problems))
