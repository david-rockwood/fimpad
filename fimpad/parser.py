"""Utilities for tokenizing and parsing triple-bracket markers."""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

DEFAULT_MARKER_MAX_TOKENS = 100

TRIPLE_RE = re.compile(r"\[\[\[(?P<body>.*?)\]\]\]", re.DOTALL)


class TagParseError(ValueError):
    """Raised when a triple-bracket tag cannot be parsed."""


@dataclass(frozen=True)
class TextToken:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class FIMFunction:
    name: str
    args: tuple[str, ...]
    phase: str | None = None


@dataclass(frozen=True)
class FIMTag:
    max_tokens: int
    functions: tuple[FIMFunction, ...]


@dataclass(frozen=True)
class SequenceTag:
    names: tuple[str, ...]


@dataclass(frozen=True)
class PrefixSuffixTag:
    kind: str  # "prefix" or "suffix"
    hardness: str  # "soft" or "hard"
    is_close: bool = False


@dataclass(frozen=True)
class CommentTag:
    body: str
    position: str | None


TagNode = FIMTag | SequenceTag | PrefixSuffixTag | CommentTag


@dataclass(frozen=True)
class TagToken:
    start: int
    end: int
    raw: str
    body: str
    tag: TagNode | None
    error: str | None = None

    @property
    def kind(self) -> str:
        if self.error:
            return "invalid"
        if self.tag is None:
            return "unknown"
        if isinstance(self.tag, FIMTag):
            return "fim"
        if isinstance(self.tag, SequenceTag):
            return "sequence"
        if isinstance(self.tag, PrefixSuffixTag):
            return self.tag.kind
        if isinstance(self.tag, CommentTag):
            return "comment"
        return "unknown"


Token = TextToken | TagToken


@dataclass(frozen=True)
class FIMRequest:
    """Parsed representation of a FIM marker relative to source text."""

    marker: TagToken
    prefix_token: TagToken | None
    suffix_token: TagToken | None
    before_region: str
    after_region: str
    safe_suffix: str
    max_tokens: int
    keep_tags: bool
    stop_patterns: list[str]
    chop_patterns: list[str]
    post_functions: tuple[FIMFunction, ...]
    config_overrides: dict[str, object]
    use_completion: bool


@dataclass(frozen=True)
class _TokenPiece:
    kind: str
    value: str
    quote: str | None = None


FUNCTION_SPECS: dict[str, dict[str, object]] = {
    "keep": {"args": 0, "default_phase": "meta"},
    "keep_tags": {"args": 0, "default_phase": "meta"},
    "stop": {"args": 1, "default_phase": "init", "require_string": True},
    "chop": {"args": 1, "default_phase": "init", "require_string": True},
    "tail": {"args": 1, "default_phase": "after", "require_string": True},
    "name": {"args": 1, "default_phase": "meta", "allow_any": True},
    "temperature": {"args": 1, "default_phase": "init", "allow_any": True},
    "top_p": {"args": 1, "default_phase": "init", "allow_any": True},
    "append": {"args": 1, "default_phase": "post", "require_string": True},
    "append_nl": {"args": 1, "default_phase": "post", "require_string": True},
}


FUNCTION_RE = re.compile(
    r"(?:(?P<phase>[A-Za-z_][\w-]*)\:)?(?P<name>[A-Za-z_][\w]*)\((?P<args>.*)\)$"
)


def parse_triple_tokens(content: str) -> Iterator[Token]:
    """Yield tokens for ``content`` splitting around ``[[[...]]]`` regions."""

    last_index = 0
    seen_names: set[str] = set()
    tokens: list[Token] = []
    for match in TRIPLE_RE.finditer(content):
        start, end = match.span()
        if start > last_index:
            tokens.append(
                TextToken(start=last_index, end=start, text=content[last_index:start])
            )

        raw = match.group(0)
        inner = match.group("body") or ""
        tag = _parse_tag(inner, seen_names)
        tokens.append(TagToken(start=start, end=end, raw=raw, body=inner, tag=tag))
        last_index = end

    if last_index < len(content):
        tokens.append(
            TextToken(start=last_index, end=len(content), text=content[last_index:])
        )

    _validate_sequence_names(tokens)
    yield from tokens


def parse_fim_request(
    content: str,
    cursor_offset: int,
    default_n: int = DEFAULT_MARKER_MAX_TOKENS,
    *,
    tokens: list[Token] | None = None,
    marker_token: TagToken | None = None,
) -> FIMRequest | None:
    """Parse FIM instructions around ``cursor_offset``.

    Returns ``None`` when the cursor is not inside a FIM marker.
    """

    try:
        tokens = tokens or list(parse_triple_tokens(content))
    except TagParseError:
        return None

    if marker_token is None:
        marker_token = _find_fim_token(tokens, cursor_offset)
    if marker_token is None or not isinstance(marker_token.tag, FIMTag):
        return None

    fim_tag = marker_token.tag
    prefix_token, suffix_token = _find_prefix_suffix(tokens, marker_token)
    before_region, after_region = _extract_regions_clean(
        content, tokens, marker_token, prefix_token, suffix_token
    )
    safe_suffix = _strip_triple_tags(after_region)
    use_completion = after_region.strip() == ""

    max_tokens = _clamp_tokens(fim_tag.max_tokens or default_n, default_n)
    keep_tags = any(fn.name in {"keep", "keep_tags"} for fn in fim_tag.functions)

    stop_patterns: list[str] = []
    chop_patterns: list[str] = []
    post_functions: list[FIMFunction] = []
    config_overrides: dict[str, object] = {}

    for fn in fim_tag.functions:
        if fn.name in {"keep", "keep_tags", "name"}:
            continue
        if fn.name == "temperature" and fn.args:
            try:
                config_overrides["temperature"] = float(fn.args[0])
            except Exception:
                continue
        elif fn.name == "top_p" and fn.args:
            try:
                config_overrides["top_p"] = float(fn.args[0])
            except Exception:
                continue
        elif fn.name in {"append", "append_nl"}:
            post_functions.append(fn)
        elif fn.name in {"chop", "tail"} and fn.args:
            chop_patterns.append(fn.args[0])
        elif fn.name == "stop" and fn.args:
            target = stop_patterns if (fn.phase or "init") != "after" else chop_patterns
            target.append(fn.args[0])

    chop_patterns = _dedupe_preserve(chop_patterns)
    stop_patterns = _dedupe_preserve([p for p in stop_patterns if p not in chop_patterns])

    return FIMRequest(
        marker=marker_token,
        prefix_token=prefix_token,
        suffix_token=suffix_token,
        before_region=before_region,
        after_region=after_region,
        safe_suffix=safe_suffix,
        max_tokens=max_tokens,
        keep_tags=keep_tags,
        stop_patterns=stop_patterns,
        chop_patterns=chop_patterns,
        post_functions=tuple(post_functions),
        config_overrides=config_overrides,
        use_completion=use_completion,
    )


def _parse_tag(body: str, seen_names: set[str]) -> TagNode | None:
    stripped = body.strip()
    if not stripped:
        return None

    tokens = _scan_tokens(stripped)
    if not tokens:
        return None

    first = tokens[0]
    if first.kind == "comment":
        position = None
        if len(tokens) > 1 and tokens[1].kind == "word":
            position = tokens[1].value
        return CommentTag(body=first.value, position=position)

    if first.kind == "word":
        base_word = first.value
        is_close = base_word.startswith("/")
        normalized = base_word[1:] if is_close else base_word
        hardness = "hard" if normalized.endswith("!") else "soft"
        normalized = normalized.rstrip("!")
        name_key = normalized.casefold()
        if name_key in {"prefix", "suffix"}:
            if len(tokens) > 1 and tokens[1].kind == "word":
                nxt = tokens[1].value.casefold()
                if nxt in {"hard", "soft"}:
                    hardness = nxt
            return PrefixSuffixTag(
                kind=name_key, hardness=hardness, is_close=is_close
            )

        fim_match = re.fullmatch(r"(?P<num>\d+)(?P<keep>!)?", base_word)
        if fim_match:
            n_val = int(fim_match.group("num"))
            functions: list[FIMFunction] = []
            if fim_match.group("keep"):
                functions.append(FIMFunction(name="keep_tags", args=(), phase="meta"))
            for tok in tokens[1:]:
                functions.append(_token_to_function(tok, seen_names))
            return FIMTag(max_tokens=n_val, functions=tuple(functions))

    if first.kind == "string":
        names: list[str] = []
        for tok in tokens:
            if tok.kind != "string":
                raise TagParseError("Sequence tags must contain only string literals")
            names.append(tok.value)
        return SequenceTag(names=tuple(names))

    raise TagParseError(f"Unrecognized tag: {body}")


def _validate_sequence_names(tokens: list[Token]):
    registry: set[str] = set()
    sequence_names: list[tuple[int, tuple[str, ...]]] = []

    for token in tokens:
        if not isinstance(token, TagToken):
            continue
        if isinstance(token.tag, FIMTag):
            for fn in token.tag.functions:
                if fn.name == "name" and fn.args:
                    registry.add(fn.args[0])
        elif isinstance(token.tag, SequenceTag):
            sequence_names.append((token.start, token.tag.names))

    for _, names in sequence_names:
        missing = [nm for nm in names if nm not in registry]
        if missing:
            missing_list = ", ".join(missing)
            raise TagParseError(f"Sequence references missing tags: {missing_list}")


def _token_to_function(token: _TokenPiece, seen_names: set[str]) -> FIMFunction:
    if token.kind == "string":
        phase = "before" if token.quote == '"' else "after"
        return FIMFunction(name="stop", args=(token.value,), phase=phase)
    if token.kind != "word":
        raise TagParseError(f"Invalid token in FIM tag: {token.value}")
    return _parse_function(token.value, seen_names)


def _parse_function(func_text: str, seen_names: set[str]) -> FIMFunction:
    match = FUNCTION_RE.fullmatch(func_text)
    if not match:
        raise TagParseError(f"Malformed function: {func_text}")

    phase = match.group("phase")
    name = match.group("name")
    args_text = match.group("args").strip()

    spec = FUNCTION_SPECS.get(name)
    if spec is None:
        raise TagParseError(f"Unknown function: {name}")

    args: list[str] = []
    if args_text:
        pieces = [piece.strip() for piece in args_text.split(",") if piece.strip()]
        for piece in pieces:
            args.append(_parse_arg(piece))

    expected_args = int(spec.get("args", 0))
    if len(args) != expected_args:
        raise TagParseError(
            f"{name}() expects {expected_args} arg(s) but got {len(args)}"
        )

    if spec.get("require_string") and args and not isinstance(args[0], str):
        raise TagParseError(f"{name}() requires a string argument")

    if name == "name":
        ident = str(args[0])
        if ident in seen_names:
            raise TagParseError(f"Duplicate name() id: {ident}")
        seen_names.add(ident)

    phase_value = phase or spec.get("default_phase")
    return FIMFunction(name=name, args=tuple(str(a) for a in args), phase=phase_value)  # type: ignore[arg-type]


def _parse_arg(piece: str) -> str:
    if not piece:
        return ""
    if piece[0] in {'"', "'"}:
        value, index = _parse_string_literal(piece, 0)
        if index != len(piece):
            raise TagParseError("Unexpected trailing characters in string argument")
        return value
    return piece


def _scan_tokens(body: str) -> list[_TokenPiece]:
    tokens: list[_TokenPiece] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch.isspace() or ch == ";":
            i += 1
            continue
        if ch in {'"', "'"}:
            value, new_i = _parse_string_literal(body, i)
            tokens.append(_TokenPiece(kind="string", value=value, quote=ch))
            i = new_i
            continue
        if ch == "(":
            value, new_i = _parse_parenthetical(body, i)
            tokens.append(_TokenPiece(kind="comment", value=value))
            i = new_i
            continue
        j = i + 1
        while j < len(body) and not body[j].isspace() and body[j] != ";":
            j += 1
        tokens.append(_TokenPiece(kind="word", value=body[i:j]))
        i = j
    return tokens


def _parse_string_literal(text: str, start: int) -> tuple[str, int]:
    quote = text[start]
    assert quote in {'"', "'"}
    i = start + 1
    chars: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 1
            if i >= len(text):
                chars.append("\\")
                break
            esc = text[i]
            if esc == "n":
                chars.append("\n")
            elif esc == "t":
                chars.append("\t")
            elif esc == "r":
                chars.append("\r")
            elif esc == quote:
                chars.append(quote)
            else:
                chars.append(esc)
            i += 1
            continue
        if ch == quote:
            return "".join(chars), i + 1
        chars.append(ch)
        i += 1
    raise TagParseError("Unterminated string literal")


def _parse_parenthetical(text: str, start: int) -> tuple[str, int]:
    depth = 0
    chars: list[str] = []
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 1
            if i < len(text):
                chars.append(text[i])
            i += 1
            continue
        if ch == "(":
            depth += 1
            if depth > 1:
                chars.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                return "".join(chars), i + 1
            chars.append(ch)
            i += 1
            continue
        chars.append(ch)
        i += 1
    raise TagParseError("Unterminated parenthetical in comment tag")


def _strip_triple_tags(text: str) -> str:
    parts: list[str] = []
    last_index = 0
    for match in TRIPLE_RE.finditer(text):
        parts.append(text[last_index : match.start()])
        last_index = match.end()
    parts.append(text[last_index:])
    return "".join(parts)


def _clamp_tokens(n: int, default_n: int) -> int:
    try:
        value = int(n)
    except Exception:
        value = default_n
    return max(1, min(4096, value))


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _find_fim_token(tokens: list[Token], cursor_offset: int) -> TagToken | None:
    marker_token: TagToken | None = None
    for token in tokens:
        if not isinstance(token, TagToken) or token.kind != "fim":
            continue
        if not cursor_within_span(token.start, token.end, cursor_offset):
            continue
        if marker_token is None or token.start >= marker_token.start:
            marker_token = token
    return marker_token


def _find_prefix_suffix(
    tokens: list[Token], marker_token: TagToken
) -> tuple[TagToken | None, TagToken | None]:
    prefix_token: TagToken | None = None
    suffix_token: TagToken | None = None
    for token in tokens:
        if not isinstance(token, TagToken):
            continue
        if (
            token.kind == "prefix"
            and not getattr(token.tag, "is_close", False)
            and token.start < marker_token.start
        ):
            prefix_token = token
        elif (
            token.kind == "suffix"
            and not getattr(token.tag, "is_close", False)
            and token.start >= marker_token.end
        ):
            suffix_token = token
            break
    return prefix_token, suffix_token


def _strip_comment_segments(
    content: str, tokens: list[Token], start: int, end: int
) -> str:
    pieces: list[str] = []
    cursor = start
    for token in tokens:
        if not isinstance(token, TagToken) or token.kind != "comment":
            continue
        if token.start >= end:
            break
        if token.end <= start:
            continue
        if cursor < token.start:
            pieces.append(content[cursor : token.start])
        cursor = max(cursor, token.end)
    if cursor < end:
        pieces.append(content[cursor:end])
    return "".join(pieces)


def _extract_regions_clean(
    content: str,
    tokens: list[Token],
    marker_token: TagToken,
    prefix_token: TagToken | None,
    suffix_token: TagToken | None,
) -> tuple[str, str]:
    if prefix_token is not None:
        before_region = _strip_comment_segments(
            content, tokens, prefix_token.end, marker_token.start
        )
    else:
        before_region = _strip_comment_segments(content, tokens, 0, marker_token.start)

    if suffix_token is not None:
        after_region = _strip_comment_segments(
            content, tokens, marker_token.end, suffix_token.start
        )
    else:
        after_region = _strip_comment_segments(
            content, tokens, marker_token.end, len(content)
        )

    return before_region, after_region


def cursor_within_span(start: int, end: int, cursor_offset: int) -> bool:
    return (start <= cursor_offset <= end) or (
        cursor_offset > 0 and start <= cursor_offset - 1 < end
    )


__all__ = [
    "Token",
    "TextToken",
    "TagToken",
    "FIMTag",
    "SequenceTag",
    "PrefixSuffixTag",
    "CommentTag",
    "FIMFunction",
    "FIMRequest",
    "TagParseError",
    "parse_triple_tokens",
    "parse_fim_request",
    "cursor_within_span",
]
