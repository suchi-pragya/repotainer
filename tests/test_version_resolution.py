import unittest

from repotainer.detection.model import Evidence, ToolEvidence
from repotainer.version_resolution import VersionChoice, resolve_tool


def pin(value: str, *directory: str) -> Evidence:
    return Evidence((*directory, ".python-version"), value=value)


def requirement(value: str, *directory: str) -> Evidence:
    return Evidence((*directory, "pyproject.toml"), ("project", "requires-python"), value)


class VersionResolutionTests(unittest.TestCase):
    def test_resolves_supported_declarations(self) -> None:
        cases = (
            ((pin("3.11.9"), requirement("<3.12")), "3.11.9"),
            ((pin("3.12.8"), requirement(">=3.12.5,<3.13")), "3.12.8"),
            ((pin("3.12"), requirement(">=3.12.5,<3.13")), "3.12"),
            ((pin("3.12"),), "3.12"),
            ((requirement("==3.12"),), "3.12.0"),
            ((requirement("==3.12.*"),), "3.12"),
            ((requirement(">=3.12,!=3.12.*"),), "3.13"),
            ((requirement(">=3.12,!=3.*"),), "4.0"),
            ((requirement("<3.12"),), "3.11"),
            ((requirement("<3.13,!=3.12.*"),), "3.11"),
            ((requirement(">=3.13.4"),), "3.13"),
            ((requirement(">=3.13.4,<3.13.8"),), "3.13.7"),
            ((requirement(">=3.13.4,<3.13.8,!=3.13.7"),), "3.13.6"),
            ((requirement(">3.13.4, <=3.13.5"),), "3.13.5"),
            ((requirement("~=3.12.5"),), "3.12"),
            ((requirement(">=3.12.3,<=3.99999.2"),), "3.12"),
            ((requirement(">=3.12.9,>=3.99999.2"),), "3.99999"),
            ((requirement(">=3.13.4,!=3.13.4"),), "3.13"),
            ((requirement("<=3.13.2"),), "3.13.2"),
        )
        for evidence, expected in cases:
            with self.subTest(evidence=evidence):
                result = resolve_tool(ToolEvidence("python", evidence))
                self.assertEqual(result.request, expected)
                self.assertEqual(result.diagnostics, ())
                self.assertEqual(result.conflict, ())

    def test_uses_latest_without_version_evidence(self) -> None:
        for tool in ("python", "uv"):
            with self.subTest(tool=tool):
                result = resolve_tool(ToolEvidence(tool, (Evidence(("uv.lock",)),)))
                self.assertEqual(result.request, "latest")
                self.assertEqual(result.diagnostics, ())

    def test_uses_latest_when_highest_priority_declaration_is_unsupported(self) -> None:
        cases = (
            (pin("pypy3.11"),),
            (pin("3.13."),),
            (pin("3.13.7"), requirement(" >=3.15.0rc1,<3.16 ")),
            (requirement("~=3"),),
            (requirement(">=3.12.*"),),
            (requirement("===3.12"),),
        )
        for evidence in cases:
            with self.subTest(evidence=evidence):
                result = resolve_tool(ToolEvidence("python", evidence))
                self.assertEqual(result.request, "latest")
                self.assertEqual(result.diagnostics[-1].evidence, (evidence[-1],))
                self.assertIn("highest-priority", result.diagnostics[-1].message)
                self.assertEqual(result.conflict, ())

    def test_ignores_unsupported_lower_priority_declaration(self) -> None:
        unsupported = pin("3.15.0rc1")
        result = resolve_tool(ToolEvidence("python", (unsupported, requirement(">=3.13,<3.14"))))
        self.assertEqual(result.request, "3.13")
        self.assertEqual(result.diagnostics[0].evidence, (unsupported,))

    def test_warns_when_supported_constraints_yield_no_request(self) -> None:
        for value in ("<4.0", "!=3.13.*", ">=3.13.4,!=3.13.7"):
            with self.subTest(value=value):
                evidence = requirement(value)
                result = resolve_tool(ToolEvidence("python", (evidence,)))
                self.assertEqual(result.request, "latest")
                self.assertEqual(result.diagnostics[0].evidence, (evidence,))
                self.assertIn("no usable request", result.diagnostics[0].message)

    def test_conflict_uses_highest_tier_without_lower_pins(self) -> None:
        manifest = requirement(">=3.13,<3.14")
        agreeing_pin = pin("3.13.7")
        conflicting_pin = pin("3.12.8", "examples", "legacy")
        agreed = resolve_tool(ToolEvidence("python", (manifest, agreeing_pin, pin("3.13", "examples"))))
        self.assertEqual(agreed.request, "3.13.7")
        for evidence in ((manifest, conflicting_pin), (manifest, agreeing_pin, conflicting_pin)):
            with self.subTest(evidence=evidence):
                result = resolve_tool(ToolEvidence("python", evidence))
                self.assertEqual(result.request, "3.13")
                self.assertEqual(result.diagnostics[0].evidence, (manifest,))
                self.assertEqual(result.diagnostics[0].ignored, evidence[1:])

    def test_conflict_groups_identical_requests_in_path_order(self) -> None:
        legacy = requirement(">=3.12,<3.13", "examples", "legacy")
        api = requirement(">=3.13,<3.14", "packages", "api")
        worker = requirement(">=3.13,<3.14", "packages", "worker")
        result = resolve_tool(ToolEvidence("python", (worker, legacy, api)))
        self.assertIsNone(result.request)
        self.assertEqual(result.conflict, (legacy, api, worker))
        self.assertEqual(result.choices, (VersionChoice("3.12", (legacy,)), VersionChoice("3.13", (api, worker))))

    def test_reports_conflict_with_no_usable_individual_candidate(self) -> None:
        manifest = requirement(">=3.13.4,<3.13.8,!=3.13.*")
        result = resolve_tool(ToolEvidence("python", (manifest,)))
        self.assertIsNone(result.request)
        self.assertEqual(result.conflict, (manifest,))
        self.assertEqual(result.choices, ())
