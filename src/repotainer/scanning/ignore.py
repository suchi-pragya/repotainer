import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

type _Token = tuple[str, bool]
type _Component = str | re.Pattern[str] | None


@dataclass(frozen=True, slots=True)
class IgnoreRule:
    line: int
    exclude: bool
    directory_only: bool
    components: tuple[_Component, ...]

    def matches(self, path: tuple[str, ...], is_directory: bool) -> bool:
        if self.directory_only and not is_directory:
            return False

        positions: set[int] | range = {0}
        for component in self.components:
            if component is None:
                positions = range(min(positions), len(path) + 1)
            else:
                positions = {
                    index + 1 for index in positions if index < len(path) and _matches_component(component, path[index])
                }
            if not positions:
                return False
        return len(path) in positions


def read_ignore_rules(directory: Path) -> tuple[IgnoreRule, ...]:
    path = directory / ".gitignore"
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return ()
    except OSError as error:
        raise OSError(error.errno, error.strerror or str(error), str(path)) from error
    if not stat.S_ISREG(mode):
        return ()

    rules = []
    try:
        with path.open(encoding="utf-8-sig", newline="\n") as lines:
            for number, line in enumerate(lines, start=1):
                rule = _parse_rule(path, number, line.removesuffix("\n").removesuffix("\r"))
                if rule is not None:
                    rules.append(rule)
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: invalid UTF-8") from error
    except OSError as error:
        raise OSError(error.errno, error.strerror or str(error), str(path)) from error
    return tuple(rules)


def _parse_rule(source: Path, number: int, line: str) -> IgnoreRule | None:
    if line.startswith("#"):
        return None

    # Git counts filename bytes for ? and bracket expressions. Map each byte to one character.
    line = line.encode("utf-8").decode("latin-1")
    raw_tokens = re.findall(r"\\[\s\S]?|[^\\]", line)
    # A trailing space is significant only when escaped.
    while raw_tokens and raw_tokens[-1] == " ":
        raw_tokens.pop()
    if raw_tokens and raw_tokens[-1] == "\\":
        return None
    tokens = [(raw[-1], raw.startswith("\\")) for raw in raw_tokens]
    exclude = tokens[:1] != [("!", False)]
    if not exclude:
        tokens = tokens[1:]

    directory_only = bool(tokens and tokens[-1] == ("/", False))
    if directory_only:
        tokens.pop()
    anchored = bool(tokens and tokens[0][0] == "/")
    if anchored:
        tokens = tokens[1:]
    if not tokens:
        return None

    segments: list[list[_Token]] = [[]]
    for token in tokens:
        if token[0] == "/":
            segments.append([])
        else:
            segments[-1].append(token)
    if not all(segments):
        return None

    components: list[_Component] = []
    if not anchored and len(segments) == 1:
        components.append(None)
    for index, segment in enumerate(segments):
        if (anchored or len(segments) > 1) and len(segment) >= 2 and all(token == ("*", False) for token in segment):
            components.append(None)
            if index == len(segments) - 1:
                # A terminal /** needs at least one descendant component.
                components.append("*")
        else:
            try:
                component = _compile_component(segment)
            except _UnsupportedPatternError as error:
                raise ValueError(f"{source}:{number}: {error}") from error
            except re.PatternError:
                return None
            components.append(component)
    return IgnoreRule(number, exclude, directory_only, tuple(components))


class _UnsupportedPatternError(ValueError):
    pass


def _compile_component(tokens: list[_Token]) -> str | re.Pattern[str]:
    if ("[", False) not in tokens:
        return "".join(
            f"[{character}]" if escaped and character in "*?[" else character for character, escaped in tokens
        )

    # Use a component regex for classes so escaped closing brackets and range separators
    # keep their literal meaning. Match whole components to keep classes inside a path segment.
    fragments = []
    index = 0
    while index < len(tokens):
        character, escaped = tokens[index]
        index += 1
        if not escaped and character == "[":
            character_class, index = _character_class(tokens, index)
            fragments.append(character_class)
        elif not escaped and character in "*?":
            fragments.append(".*" if character == "*" else ".")
        else:
            fragments.append(re.escape(character))
    return re.compile("".join(fragments), re.DOTALL)


def _character_class(tokens: list[_Token], index: int) -> tuple[str, int]:
    negate = index < len(tokens) and tokens[index] in (("!", False), ("^", False))
    if negate:
        index += 1
    members = []
    if index < len(tokens) and tokens[index] == ("]", False):
        members.append(r"\]")
        index += 1
    while index < len(tokens) and tokens[index] != ("]", False):
        if tokens[index : index + 2] == [("[", False), (":", False)]:
            raise _UnsupportedPatternError("unsupported POSIX character class")
        character, escaped = tokens[index]
        members.append("-" if character == "-" and not escaped else re.escape(character))
        index += 1
    if index == len(tokens):
        raise re.PatternError("unclosed character class")
    prefix = "[^" if negate else "["
    return prefix + "".join(members) + "]", index + 1


def _matches_component(pattern: str | re.Pattern[str], name: str) -> bool:
    if isinstance(pattern, str):
        return PurePosixPath(name).full_match(pattern, case_sensitive=True)
    return pattern.fullmatch(name) is not None
