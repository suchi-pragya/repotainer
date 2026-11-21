import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

from repotainer.scanning.inventory import Inventory, InventoryEntry, scan_inventory


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temp).resolve()

    def files(self, *names: str) -> None:
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def rules(self, rules: str, directory: str = ".") -> None:
        scope = self.root / directory
        scope.mkdir(parents=True, exist_ok=True)
        (scope / ".gitignore").write_text(rules, encoding="utf-8")

    def inventory(self) -> Inventory:
        confirmation = Mock(return_value=True)
        result = scan_inventory(self.root, confirmation)
        confirmation.assert_not_called()
        assert result is not None
        return result

    def names(self) -> set[str]:
        return {"/".join(entry.relative_path) for entry in self.inventory().entries}

    def test_catalog_metadata_and_order(self) -> None:
        self.files("app/package.json", "package.json", "Dockerfile", ".config.json", ".python-version", "A.tar.GZ")
        (self.root / "sample.txt").mkdir()
        entries = self.inventory().entries
        self.assertEqual(
            entries,
            (
                InventoryEntry((".config.json",), "file", ".json"),
                InventoryEntry((".python-version",), "file", None),
                InventoryEntry(("A.tar.GZ",), "file", ".GZ"),
                InventoryEntry(("Dockerfile",), "file", None),
                InventoryEntry(("app",), "directory", None),
                InventoryEntry(("app", "package.json"), "file", ".json"),
                InventoryEntry(("package.json",), "file", ".json"),
                InventoryEntry(("sample.txt",), "directory", None),
            ),
        )

    def test_rule_scopes_anchoring_and_pruning(self) -> None:
        self.rules("*.log\ncache/\n!cache/keep.txt\n")
        self.rules("!keep.log\n/generated/\n", "app")
        self.files(
            "app/keep.log",
            "app/drop.log",
            "app/cache/keep.txt",
            "app/generated/a.txt",
            "app/nested/generated/a.txt",
            "other/keep.log",
            "other/generated/a.txt",
            "other/cache.txt",
        )
        names = self.names()
        self.assertTrue(
            {"app/keep.log", "app/nested/generated/a.txt", "other/generated/a.txt", "other/cache.txt"} <= names
        )
        self.assertTrue(
            {"app/drop.log", "app/cache", "app/cache/keep.txt", "app/generated", "other/keep.log"}.isdisjoint(names)
        )

    def test_directory_only_rules_and_globstar_regressions(self) -> None:
        self.files("generated/keep.txt", "generated/drop.txt", "sample/config.json", "sample/notes.txt", "cache")
        self.rules("*\n!*/\n!*.json\n!cache\n/cache/\ngenerated/**\n!generated/keep.txt\n")
        self.assertEqual(self.names(), {"generated", "generated/keep.txt", "sample", "sample/config.json", "cache"})

    def test_root_globstar_and_byte_matching(self) -> None:
        self.files("app/notes.txt", "app/config.json", "a.log", "é.log")
        self.rules("/**\n!*/\n!*.json\n!?.log\n")
        self.assertEqual(self.names(), {"app", "app/config.json", "a.log"})

    @unittest.skipIf(os.name == "nt", "fixture uses filenames that are invalid on Windows")
    def test_documented_pattern_syntax(self) -> None:
        ignored = (
            "nested/preview.pyc",
            "lower/a.txt",
            "n9.out",
            "a/b",
            "a/x/y/b",
            "nested/skip/entry",
            "#notes",
            "!important",
            "literal*.txt",
            "trailing ",
            "ordinary",
            "bracket].txt",
            "dash-.txt",
        )
        retained = ("preview.PYC", "lower/uppercase.txt", "n77.out", "literal1.txt", "trailing", "ordinary ")
        self.files(*ignored, *retained)
        self.rules(
            "\ufeff# comment\n\n*.py[codz]\nlower/[a-z].txt\nn?.out\na/**/b\n**/skip/\n"
            "\\#notes\n\\!important\nliteral\\*.txt\ntrailing\\ \nordinary  \nbracket[\\]].txt\ndash[\\-].txt\n"
        )
        names = self.names()
        self.assertTrue(set(ignored).isdisjoint(names))
        self.assertTrue(set(retained) <= names)

    def test_builtin_exclusions_and_nested_repositories(self) -> None:
        self.rules("!.git/\n!.venv/\n!node_modules/\n")
        self.files(
            ".git/config",
            "app/.venv/config",
            "app/node_modules/package.json",
            "repo/.git/config",
            "repo/package.json",
            "submodule/.git",
            "submodule/package.json",
            "node_modules",
        )
        result = self.inventory()
        self.assertEqual(result.pruned_directories, 4)
        self.assertEqual(
            {"/".join(entry.relative_path) for entry in result.entries},
            {".gitignore", "app", "node_modules", "repo", "repo/package.json", "submodule", "submodule/package.json"},
        )

    def test_symlinks_and_manifest_contents_are_skipped(self) -> None:
        self.files("source/keep.txt", "package.json")
        (self.root / "package.json").write_bytes(b"\xffnot JSON")
        try:
            (self.root / "source" / "loop").symlink_to(self.root, target_is_directory=True)
            (self.root / "broken").symlink_to(self.root / "missing")
            (self.root / ".gitignore").symlink_to(self.root / "package.json")
        except OSError as error:
            self.skipTest(str(error))
        with patch.object(Path, "open", side_effect=AssertionError("file opened")):
            self.assertEqual(self.names(), {"package.json", "source", "source/keep.txt"})

    def test_ignore_errors_and_invalid_patterns(self) -> None:
        self.rules("# comment\nthing[[:digit:]].txt\n")
        with self.assertRaisesRegex(ValueError, r"\.gitignore:2: unsupported"):
            self.inventory()
        (self.root / ".gitignore").write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, r"\.gitignore: invalid UTF-8"):
            self.inventory()
        self.rules("bad[\nname\\\n")
        self.files("bad[", "name")
        self.assertEqual(self.names(), {".gitignore", "bad[", "name"})

    def test_ignored_control_file_still_supplies_rules(self) -> None:
        self.rules(".gitignore\n*.log\n")
        self.files("debug.log", "project.toml")
        self.assertEqual(self.names(), {"project.toml"})

    def test_unreadable_directory_and_ignore_file_report_the_path(self) -> None:
        self.files("ignored/child", "blocked/child")
        self.rules("ignored/\n")
        real_scandir = os.scandir

        def scandir(path: Path):
            if path.name in {"blocked", "ignored"}:
                raise PermissionError("permission denied")
            return real_scandir(path)

        with patch("repotainer.scanning.inventory.scandir", side_effect=scandir) as walk:
            with self.assertRaisesRegex(OSError, r"blocked: permission denied"):
                self.inventory()
            self.assertNotIn(call(self.root / "ignored"), walk.call_args_list)
        with (
            patch.object(Path, "open", side_effect=PermissionError("permission denied")),
            self.assertRaisesRegex(OSError, r"\.gitignore: permission denied"),
        ):
            self.inventory()

    def test_metadata_and_iteration_errors_close_the_active_directory(self) -> None:
        child = Mock(path=str(self.root / "child"))
        child.name = "child"
        child.stat.side_effect = PermissionError("classification failed")
        for operation, error_path in (("classification", self.root / "child"), ("iteration", self.root)):
            with self.subTest(operation=operation):
                children = MagicMock()
                if operation == "classification":
                    children.__next__.return_value = child
                else:
                    children.__next__.side_effect = PermissionError("iteration failed")
                with (
                    patch("repotainer.scanning.inventory.scandir", return_value=children),
                    self.assertRaises(OSError) as failure,
                ):
                    self.inventory()
                self.assertIn(f"{error_path}: {operation} failed", str(failure.exception))
                children.close.assert_called_once_with()

    def test_large_scan_confirms_once_and_closes_on_decline(self) -> None:
        self.files(*(f"entry{i:04}" for i in range(1_000)))
        self.assertEqual(len(self.inventory().entries), 1_000)
        self.files("extra", "last")
        children = os.scandir(self.root)
        confirm = Mock(return_value=False)
        with patch("repotainer.scanning.inventory.scandir", return_value=children) as walk:
            self.assertIsNone(scan_inventory(self.root, confirm))
            walk.assert_called_once_with(self.root)
        self.assertIsNone(next(children, None))
        confirm.assert_called_once_with(self.root, 1_000)

        confirm = Mock(return_value=True)
        with patch("repotainer.scanning.inventory.scandir", wraps=os.scandir) as walk:
            result = scan_inventory(self.root, confirm)
            walk.assert_called_once_with(self.root)
        assert result is not None
        self.assertEqual(len(result.entries), 1_002)
        confirm.assert_called_once_with(self.root, 1_000)

    @unittest.skipUnless(shutil.which("git"), "Git is optional for matcher comparison")
    def test_compare_scoped_matcher_with_git(self) -> None:
        self.rules("generated/**\n!generated/keep.txt\n*.log\ncache/\n!cache/keep.txt\n")
        self.rules("!keep.log\n/generated/\n", "app")
        self.rules("*\n!*/\n!*.json\n", "format")
        self.rules("/**\n!*/\n!*.json\n!?.log\n", "anchored")
        files = (
            "generated/keep.txt",
            "generated/drop.txt",
            "app/keep.log",
            "app/drop.log",
            "app/generated/file.txt",
            "app/nested/generated/file.txt",
            "sibling/keep.log",
            "format/nested/notes.txt",
            "format/nested/config.json",
            "cache/keep.txt",
            "anchored/app/notes.txt",
            "anchored/app/config.json",
            "anchored/a.log",
            "anchored/é.log",
        )
        self.files(*files)
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        git = ["git", "-C", str(self.root), "-c", "core.ignoreCase=false", "-c", f"core.excludesFile={os.devnull}"]
        subprocess.run([*git, "init", "-q", "--template="], env=env, check=True)
        subprocess.run([*git, "add", "-f", "app/drop.log"], env=env, check=True)
        included = self.names()
        for name in (*files, "generated", "format/nested", "cache"):
            with self.subTest(name=name):
                check = subprocess.run([*git, "check-ignore", "-q", "--no-index", "--", name], env=env, check=False)
                self.assertIn(check.returncode, (0, 1))
                self.assertEqual(name in included, check.returncode == 1)
