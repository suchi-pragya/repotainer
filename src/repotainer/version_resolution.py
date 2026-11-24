"""Resolve tool requests using the version declarations in a completed scan."""

import re
from dataclasses import dataclass

from repotainer.detection.model import Evidence, ToolEvidence

SUPPORTED_TOOLS = ("python", "uv")
type Version = tuple[int, int, int]

_FIRST = (0, 0, 0)
_COMPONENT = r"(?:0|[1-9][0-9]*)"
_PYTHON_REQUEST = re.compile(rf"{_COMPONENT}\.{_COMPONENT}(?:\.{_COMPONENT})?")
_SPECIFIER = re.compile(r"(~=|==|!=|<=|>=|<|>)\s*([0-9]+(?:\.[0-9]+){0,2})(\.\*)?")


@dataclass(frozen=True, slots=True)
class VersionDiagnostic:
    message: str
    evidence: tuple[Evidence, ...]
    ignored: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class VersionChoice:
    request: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class VersionResolution:
    tool: str
    request: str | None
    diagnostics: tuple[VersionDiagnostic, ...] = ()
    conflict: tuple[Evidence, ...] = ()
    choices: tuple[VersionChoice, ...] = ()


@dataclass(frozen=True, slots=True)
class _Interval:
    """A half-open interval of numeric release triples."""

    start: Version = _FIRST
    end: Version | None = None


@dataclass(frozen=True, slots=True)
class _Constraint:
    intervals: tuple[_Interval, ...]
    anchored: bool


@dataclass(frozen=True, slots=True)
class _Declaration:
    evidence: Evidence
    priority: int
    constraint: _Constraint | None


def is_python_request(value: str) -> bool:
    return _PYTHON_REQUEST.fullmatch(value) is not None


def _version(parts: tuple[int, ...]) -> Version:
    return parts[0], parts[1] if len(parts) > 1 else 0, parts[2] if len(parts) > 2 else 0


def _next_patch(version: Version) -> Version:
    return version[0], version[1], version[2] + 1


def _prefix(parts: tuple[int, ...]) -> _Interval:
    end = (parts[0] + 1, 0, 0) if len(parts) == 1 else (parts[0], parts[1] + 1, 0)
    return _Interval(_version(parts), end)


def _intersect(left: tuple[_Interval, ...], right: tuple[_Interval, ...]) -> tuple[_Interval, ...]:
    """Intersect sorted, disjoint intervals without walking the covered releases."""
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        first, second = left[i], right[j]
        start = max(first.start, second.start)
        ends = [end for end in (first.end, second.end) if end is not None]
        end = min(ends) if ends else None
        if end is None or start < end:
            result.append(_Interval(start, end))
        if first.end == end:
            i += 1
        if second.end == end:
            j += 1
    return tuple(result)


def _specifier(operator: str, parts: tuple[int, ...], wildcard: bool) -> _Constraint | None:
    version = _version(parts)
    exact = _Interval(version, _next_patch(version))
    if wildcard:
        if operator not in ("==", "!=") or len(parts) > 2:
            return None
        exact = _prefix(parts)
    match operator:
        case "!=":
            before = (_Interval(end=exact.start),) if exact.start > _FIRST else ()
            assert exact.end is not None
            return _Constraint((*before, _Interval(exact.end)), False)
        case "==":
            return _Constraint((exact,), True)
        case "~=" if len(parts) >= 2:
            return _Constraint((_Interval(version, _prefix(parts[:-1]).end),), True)
        case ">=":
            return _Constraint((_Interval(version),), True)
        case ">":
            return _Constraint((_Interval(_next_patch(version)),), True)
        case "<=":
            return _Constraint((_Interval(end=_next_patch(version)),), False)
        case "<":
            return _Constraint((_Interval(end=version),) if version > _FIRST else (), False)
        case _:
            return None


def _combine(constraints: tuple[_Constraint, ...]) -> _Constraint:
    intervals = (_Interval(),)
    for constraint in constraints:
        intervals = _intersect(intervals, constraint.intervals)
        if not intervals:
            break
    return _Constraint(intervals, any(constraint.anchored for constraint in constraints))


def _python_constraint(value: str, *, manifest: bool) -> _Constraint | None:
    if not manifest:
        if not is_python_request(value):
            return None
        parts = tuple(map(int, value.split(".")))
        return _Constraint((_prefix(parts),), True) if len(parts) == 2 else _specifier("==", parts, False)

    constraints = []
    for clause in value.split(","):
        match = _SPECIFIER.fullmatch(clause.strip())
        if match is None:
            return None
        operator, release, wildcard = match.groups()
        constraint = _specifier(operator, tuple(map(int, release.split("."))), wildcard is not None)
        if constraint is None:
            return None
        constraints.append(constraint)
    return _combine(tuple(constraints))


def _python_declarations(evidence: tuple[Evidence, ...]) -> tuple[_Declaration, ...]:
    declarations = []
    for item in evidence:
        if item.value is None:
            continue
        manifest = item.path[-1] == "pyproject.toml" and item.field == ("project", "requires-python")
        if not manifest and (item.path[-1] != ".python-version" or item.field is not None):
            continue
        try:
            constraint = _python_constraint(item.value, manifest=manifest)
        except ValueError:
            constraint = None
        declarations.append(_Declaration(item, 2 if manifest else 1, constraint))
    return tuple(
        sorted(declarations, key=lambda declaration: (declaration.evidence.path, declaration.evidence.field or ()))
    )


def _request(constraint: _Constraint) -> str | None:
    if not constraint.intervals:
        return None
    if constraint.anchored:
        major, minor, _ = constraint.intervals[0].start
    else:
        cap = constraint.intervals[-1].end
        if cap is None:
            return None
        major, minor, patch = cap
        if patch == 0:
            if minor == 0:
                return None
            minor -= 1

    series = _prefix((major, minor))
    patches = _intersect(constraint.intervals, (series,))
    assert patches
    end = patches[-1].end
    if end == series.end:
        if len(patches) != 1:
            return None
        release = (major, minor)
    else:
        assert end is not None
        release = (major, minor, end[2] - 1)
    try:
        return ".".join(map(str, release))
    except ValueError:
        return None


def _intersection(declarations: tuple[_Declaration, ...]) -> _Constraint:
    return _combine(tuple(item.constraint for item in declarations if item.constraint is not None))


def resolve_tool(tool: ToolEvidence) -> VersionResolution:
    """Resolve a supported tool or return the conflict for the CLI to present."""
    declarations = _python_declarations(tool.evidence) if tool.tool == "python" else ()
    if not declarations:
        return VersionResolution(tool.tool, "latest")

    highest = max(item.priority for item in declarations)
    unsupported = tuple(item for item in declarations if item.constraint is None)
    diagnostics = [VersionDiagnostic("cannot interpret version declaration", (item.evidence,)) for item in unsupported]
    if any(item.priority == highest for item in unsupported):
        diagnostics.append(
            VersionDiagnostic(
                'using "latest" because compatibility with the highest-priority declaration could not be established',
                tuple(item.evidence for item in unsupported if item.priority == highest),
            )
        )
        return VersionResolution(tool.tool, "latest", tuple(diagnostics))

    retained = tuple(item for item in declarations if item.constraint is not None)
    shared = _intersection(retained)
    if not shared.intervals:
        retained = tuple(item for item in retained if item.priority == highest)
        ignored = tuple(item.evidence for item in declarations if item.priority < highest)
        if ignored:
            diagnostics.append(
                VersionDiagnostic(
                    "conflicting declarations; using the highest-priority evidence",
                    tuple(item.evidence for item in retained),
                    ignored,
                )
            )
        shared = _intersection(retained)

    sources = tuple(item.evidence for item in retained)
    if not shared.intervals:
        choices: dict[str, list[Evidence]] = {}
        for item in retained:
            assert item.constraint is not None
            if (request := _request(item.constraint)) is not None:
                choices.setdefault(request, []).append(item.evidence)
        return VersionResolution(
            tool.tool,
            None,
            tuple(diagnostics),
            sources,
            tuple(VersionChoice(request, tuple(evidence)) for request, evidence in choices.items()),
        )

    if (request := _request(shared)) is None:
        diagnostics.append(VersionDiagnostic('using "latest" because the constraints yield no usable request', sources))
        request = "latest"
    return VersionResolution(tool.tool, request, tuple(diagnostics))
