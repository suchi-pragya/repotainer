import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from shutil import copy2
from unittest.mock import patch

from repotainer import scaffold
from repotainer.scaffold import (
    ScaffoldConflictError,
    ScaffoldPlan,
    ScaffoldWriteError,
    ToolRequests,
    inspect_scaffold,
    plan_scaffold,
    write_scaffold,
)

DOCKERFILE = Path(".devcontainer/Dockerfile")
SETUP = Path(".devcontainer/setup.sh")
CONFIG = Path(".devcontainer/devcontainer.json")
MISE = Path("mise.toml")


class ScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temporary).resolve()

    def plan(self, requests: ToolRequests = ()) -> ScaffoldPlan:
        return plan_scaffold(inspect_scaffold(self.root), requests)

    def test_creates_the_static_files_and_writes_config_last(self) -> None:
        created = write_scaffold(self.plan()).created
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

    def test_creates_populated_mise_config_in_alphabetical_order(self) -> None:
        created = write_scaffold(self.plan((("uv", "latest"), ("python", "3.13.7")))).created

        self.assertEqual(created, (DOCKERFILE, SETUP, MISE, CONFIG))
        content = (self.root / MISE).read_bytes()
        self.assertEqual(content, b'[tools]\npython = "3.13.7"\nuv = "latest"\n')
        tools = tomllib.loads(content.decode("utf-8"))["tools"]
        self.assertEqual(tools, {"python": "3.13.7", "uv": "latest"})
        self.assertEqual(list(tools), ["python", "uv"])

    def test_preserves_unapproved_root_mise_file(self) -> None:
        original = b"unparsed original bytes"
        (self.root / MISE).write_bytes(original)
        plan = plan_scaffold(inspect_scaffold(self.root), (("python", "3.13"),))

        written = write_scaffold(plan)

        self.assertEqual(written.created, (DOCKERFILE, SETUP, CONFIG))
        self.assertEqual(written.replaced, ())
        self.assertEqual((self.root / MISE).read_bytes(), original)

    def test_alternate_and_nested_configs_are_outside_the_write_plan(self) -> None:
        paths = (
            ".devcontainer.json",
            ".devcontainer/nested/devcontainer.json",
            ".mise.toml",
            "mise.local.toml",
            ".mise/config.toml",
            ".tool-versions",
            "app/mise.toml",
        )
        for name in paths:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"original")
        plan = plan_scaffold(inspect_scaffold(self.root))

        self.assertEqual(write_scaffold(plan).created, (DOCKERFILE, SETUP, MISE, CONFIG))
        for name in paths:
            self.assertEqual((self.root / name).read_bytes(), b"original")

    def test_reports_sorted_conflicts_at_canonical_destinations(self) -> None:
        (self.root / CONFIG.parent).mkdir()
        (self.root / DOCKERFILE).mkdir()
        (self.root / MISE).mkdir()
        with self.assertRaises(ScaffoldConflictError) as raised:
            inspect_scaffold(self.root)
        self.assertEqual(raised.exception.paths, (DOCKERFILE, MISE))
        self.assertFalse((self.root / SETUP).exists())

    def test_reports_a_broken_link_at_an_output_path(self) -> None:
        (self.root / CONFIG.parent).mkdir()
        try:
            (self.root / CONFIG).symlink_to(self.root / "missing.json")
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.plan())
        self.assertEqual(raised.exception.paths, (CONFIG,))
        self.assertTrue((self.root / CONFIG).is_symlink())

    def test_blocked_parent_still_reports_root_conflicts_and_mise_preservation(self) -> None:
        (self.root / CONFIG.parent).touch()
        (self.root / MISE).write_text("[tools]\n", encoding="utf-8")
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.plan())
        self.assertEqual(raised.exception.paths, (CONFIG.parent,))
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
            write_scaffold(self.plan())
        self.assertEqual(raised.exception.paths, (CONFIG.parent,))
        self.assertEqual(list(other.iterdir()), [])

    def test_directory_at_mise_destination_is_unusable(self) -> None:
        (self.root / MISE).mkdir()
        with self.assertRaises(ScaffoldConflictError) as raised:
            write_scaffold(self.plan())
        self.assertEqual(raised.exception.paths, (MISE,))
        self.assertFalse((self.root / CONFIG.parent).exists())

    def test_rejects_invalid_requests_before_writes(self) -> None:
        cases: tuple[ToolRequests, ...] = (
            (("go", "latest"),),
            (("uv", "0.9.1"),),
            (("python", "3.13."),),
            (("python", "3.13"), ("python", "latest")),
        )
        for requests in cases:
            with self.subTest(requests=requests), self.assertRaises(ValueError):
                self.plan(requests)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_backs_up_only_approved_existing_files_before_writing(self) -> None:
        directory = self.root / CONFIG.parent
        directory.mkdir()
        (self.root / CONFIG).write_bytes(b"old config")
        (self.root / MISE).write_bytes(b"old mise")
        unrelated = directory / "notes.txt"
        unrelated.write_bytes(b"keep me")
        plan = self.plan((("python", "3.13"),))
        backup = self.root / "private-backup"
        backup.mkdir()

        replace_file = scaffold._replace_file

        def replace_after_backup(path: Path, content: bytes) -> None:
            self.assertEqual((backup / CONFIG).read_bytes(), b"old config")
            self.assertFalse((backup / MISE).exists())
            replace_file(path, content)

        with (
            patch("repotainer.scaffold.mkdtemp", return_value=str(backup)),
            patch("repotainer.scaffold.copy2", wraps=copy2) as copy,
            patch("repotainer.scaffold._replace_file", side_effect=replace_after_backup),
        ):
            written = write_scaffold(plan, replace_devcontainer=True)

        copy.assert_called_once_with(self.root / CONFIG, backup / CONFIG)
        self.assertEqual(written.created, (DOCKERFILE, SETUP))
        self.assertEqual(written.replaced, (CONFIG,))
        self.assertEqual((self.root / MISE).read_bytes(), b"old mise")
        self.assertEqual(unrelated.read_bytes(), b"keep me")
        self.assertFalse(backup.exists())

    def test_backup_failure_leaves_all_scaffold_files_untouched(self) -> None:
        (self.root / MISE).write_bytes(b"old mise")
        backup = self.root / "private-backup"
        backup.mkdir()
        plan = self.plan()
        with (
            patch("repotainer.scaffold.mkdtemp", return_value=str(backup)),
            patch("repotainer.scaffold.copy2", side_effect=PermissionError("cannot copy")),
            self.assertRaises(ScaffoldWriteError) as raised,
        ):
            write_scaffold(plan, replace_mise=True)
        self.assertEqual(raised.exception.path, self.root / MISE)
        self.assertEqual(list(self.root.iterdir()), [self.root / MISE])
        self.assertEqual((self.root / MISE).read_bytes(), b"old mise")

    def test_replacement_failure_rolls_back_both_groups_and_new_files(self) -> None:
        directory = self.root / CONFIG.parent
        directory.mkdir()
        originals = {DOCKERFILE: b"old Dockerfile", MISE: b"old mise", CONFIG: b"old config"}
        for path, content in originals.items():
            (self.root / path).write_bytes(content)
        plan = self.plan((("python", "3.13"),))
        replace_file = scaffold._replace_file
        backup = self.root / "private-backup"
        backup.mkdir()

        def fail_on_config(path: Path, content: bytes, *, original: Path | None = None) -> None:
            if path == self.root / CONFIG:
                self.assertEqual({key: (backup / key).read_bytes() for key in originals}, originals)
                self.assertTrue((self.root / SETUP).exists())
                self.assertNotEqual((self.root / MISE).read_bytes(), originals[MISE])
                raise OSError("disk full")
            replace_file(path, content, original=original)

        with (
            patch("repotainer.scaffold.mkdtemp", return_value=str(backup)),
            patch("repotainer.scaffold._replace_file", side_effect=fail_on_config),
            self.assertRaises(ScaffoldWriteError) as raised,
        ):
            write_scaffold(plan, replace_devcontainer=True, replace_mise=True)

        self.assertEqual(raised.exception.restored, (MISE, DOCKERFILE))
        self.assertEqual(raised.exception.cleanup_problems, ())
        self.assertEqual({key: (self.root / key).read_bytes() for key in originals}, originals)
        self.assertFalse((self.root / SETUP).exists())
        self.assertFalse(backup.exists())

    def test_restoration_failure_keeps_the_backup(self) -> None:
        directory = self.root / CONFIG.parent
        directory.mkdir()
        (self.root / DOCKERFILE).write_bytes(b"old Dockerfile")
        (self.root / CONFIG).write_bytes(b"old config")
        plan = self.plan()
        replace_file = scaffold._replace_file
        backup = self.root / "private-backup"
        backup.mkdir()

        def fail_on_config_and_restore(path: Path, content: bytes, *, original: Path | None = None) -> None:
            if original is not None or path == self.root / CONFIG:
                raise PermissionError("cannot write")
            replace_file(path, content)

        with (
            patch("repotainer.scaffold.mkdtemp", return_value=str(backup)),
            patch("repotainer.scaffold._replace_file", side_effect=fail_on_config_and_restore),
            self.assertRaises(ScaffoldWriteError) as raised,
        ):
            write_scaffold(plan, replace_devcontainer=True)

        self.assertEqual(raised.exception.backup, backup)
        self.assertEqual(raised.exception.cleanup_problems, ((self.root / DOCKERFILE, "cannot write"),))
        self.assertEqual((backup / DOCKERFILE).read_bytes(), b"old Dockerfile")
        self.assertEqual((self.root / CONFIG).read_bytes(), b"old config")
        self.assertFalse((self.root / SETUP).exists())
        self.assertFalse((self.root / MISE).exists())

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
                write_scaffold(self.plan())
            self.assertEqual(raised.exception.path, "bundled template setup.sh")
            self.assertEqual(list(self.root.iterdir()), [])

        with (
            patch.object(Path, "lstat", side_effect=PermissionError("metadata denied")),
            self.assertRaises(ScaffoldWriteError) as raised,
        ):
            write_scaffold(self.plan())
        self.assertEqual(raised.exception.path, self.root / CONFIG.parent)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_late_directory_collision_preserves_the_new_directory(self) -> None:
        mkdir = Path.mkdir

        def create_other_directory(path: Path) -> None:
            mkdir(path)
            (path / "owner.txt").write_bytes(b"another writer")
            mkdir(path)

        with patch.object(Path, "mkdir", create_other_directory), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.plan())
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
            write_scaffold(self.plan())
        self.assertEqual(raised.exception.path, self.root / CONFIG)
        self.assertEqual((self.root / CONFIG).read_bytes(), b"another writer")
        self.assertFalse((self.root / SETUP).exists())
        self.assertFalse((self.root / DOCKERFILE).exists())
        self.assertFalse((self.root / MISE).exists())
        self.assertEqual([path for path, _ in raised.exception.cleanup_problems], [self.root / CONFIG.parent])

    def test_cleanup_preserves_a_file_if_its_identity_could_not_be_recorded(self) -> None:
        cause = OSError("could not read identity")
        with patch("repotainer.scaffold.os.fstat", side_effect=cause), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.plan())
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
                self.assertEqual((self.root / MISE).read_bytes(), b'[tools]\npython = "latest"\n')
                return fail_after_partial_write(path, mode, buffering)
            return original_open(path, mode, buffering)

        with patch.object(Path, "open", open_until_config), self.assertRaises(ScaffoldWriteError) as raised:
            write_scaffold(self.plan((("python", "latest"),)))
        self.assertIs(raised.exception.cause, cause)
        self.assertEqual(raised.exception.cleanup_problems, ())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(write_scaffold(self.plan((("python", "latest"),))).created, (DOCKERFILE, SETUP, MISE, CONFIG))
        self.assertEqual((self.root / MISE).read_bytes(), b'[tools]\npython = "latest"\n')

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
            write_scaffold(self.plan())
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
            write_scaffold(self.plan())
        self.assertEqual(list(directory.iterdir()), [])
        self.assertTrue((self.root / "original" / DOCKERFILE.name).is_file())
        self.assertIn(directory, dict(raised.exception.cleanup_problems))
