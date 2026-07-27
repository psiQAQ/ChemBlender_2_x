"""Bounded, dependency-free extXYZ syntax parsing."""

from dataclasses import dataclass
import math
from pathlib import Path
import re


_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_REAL = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[dDeE][+-]?[0-9]+)?\Z"
)
_LOGICAL = {
    "T": True,
    "TRUE": True,
    "True": True,
    "true": True,
    "F": False,
    "FALSE": False,
    "False": False,
    "false": False,
}
_DEFAULT_PROPERTIES = "species:S:1:pos:R:3"
_RESERVED_COMMENT_KEYS = frozenset({"Lattice", "Properties", "pbc"})


class ExtXYZSyntaxError(ValueError):
    """Stable syntax failure for an extXYZ record."""


class _PlainComment(ExtXYZSyntaxError):
    """Signal that a comment mixes free text instead of only key/value pairs."""

    def __init__(self, message, offset):
        super().__init__(message)
        self.offset = offset


@dataclass(frozen=True, slots=True)
class ExtXYZPropertyField:
    name: str
    kind: str
    columns: int


@dataclass(frozen=True, slots=True)
class ExtXYZMetadataEntry:
    key: str
    value: object
    raw_lexeme: str
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class ExtXYZComment:
    raw: str
    entries: tuple[ExtXYZMetadataEntry, ...]
    properties: tuple[ExtXYZPropertyField, ...]


@dataclass(frozen=True, slots=True)
class ExtXYZFrame:
    atom_count: int
    comment: ExtXYZComment
    properties: tuple[ExtXYZPropertyField, ...]
    values: tuple[tuple[str, tuple[object, ...]], ...]


def parse_properties_descriptor(value):
    if not isinstance(value, str):
        raise TypeError("Properties descriptor must be a string")
    parts = value.split(":")
    if not parts or len(parts) % 3:
        raise ExtXYZSyntaxError("Properties descriptor must contain triplets")
    fields = []
    names = set()
    for offset in range(0, len(parts), 3):
        name, kind, raw_columns = parts[offset : offset + 3]
        if not name:
            raise ExtXYZSyntaxError("Properties field name must be non-empty")
        if name in names:
            raise ExtXYZSyntaxError(f"duplicate Properties field: {name}")
        if kind not in {"S", "I", "R", "L"}:
            raise ExtXYZSyntaxError(f"invalid Properties type: {kind}")
        if not _INTEGER.fullmatch(raw_columns):
            raise ExtXYZSyntaxError(
                "Properties columns must be a positive integer"
            )
        columns = int(raw_columns)
        if columns <= 0:
            raise ExtXYZSyntaxError(
                "Properties columns must be a positive integer"
            )
        names.add(name)
        fields.append(ExtXYZPropertyField(name, kind, columns))
    return tuple(fields)


def _quoted(text, start, quote='"'):
    result = []
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == quote:
            return index + 1, "".join(result)
        if character == "\\":
            index += 1
            if index >= len(text):
                break
            escaped = text[index]
            result.append("\n" if escaped == "n" else escaped)
        else:
            result.append(character)
        index += 1
    raise ExtXYZSyntaxError("unclosed quoted string in extXYZ comment")


def _container_end(text, start):
    pairs = {"[": "]", "{": "}"}
    stack = []
    index = start
    while index < len(text):
        character = text[index]
        if character in "\"'":
            index, _value = _quoted(text, index, character)
            continue
        if character in pairs:
            stack.append(character)
        elif character in "]}":
            if not stack or pairs[stack.pop()] != character:
                raise ExtXYZSyntaxError("mismatched array in extXYZ comment")
            if not stack:
                return index + 1
        index += 1
    raise ExtXYZSyntaxError("unclosed array in extXYZ comment")


def _split_items(text):
    items = []
    start = 0
    pairs = {"[": "]", "{": "}"}
    stack = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in "\"'":
            index, _value = _quoted(text, index, character)
            continue
        if character in pairs:
            stack.append(character)
        elif character in "]}":
            if not stack or pairs[stack.pop()] != character:
                raise ValueError("array delimiters must match")
        elif character == "," and not stack:
            items.append(text[start:index].strip())
            start = index + 1
        index += 1
    items.append(text[start:].strip())
    if any(not item for item in items):
        raise ValueError("array contains an empty item")
    return items


def _scalar(text):
    if _INTEGER.fullmatch(text):
        return int(text)
    if _REAL.fullmatch(text):
        value = float(text.replace("D", "E").replace("d", "e"))
        if not math.isfinite(value):
            raise ValueError("real value must be finite")
        return value
    if text in _LOGICAL:
        return _LOGICAL[text]
    return text


def _promote(values):
    flat_types = {type(value) for value in values}
    if flat_types <= {int, float}:
        return (
            tuple(float(value) for value in values)
            if float in flat_types
            else tuple(values)
        )
    if len(flat_types) == 1:
        return tuple(values)
    return tuple(str(value) for value in values)


def _array_value(raw):
    try:
        end = _container_end(raw, 0)
    except ExtXYZSyntaxError as error:
        raise ValueError(str(error)) from error
    if end != len(raw):
        raise ValueError("array value has trailing characters")
    if raw.startswith("["):
        items = _split_items(raw[1:-1])
        values = tuple(_typed_value(item) for item in items)
        nested = [value for value in values if isinstance(value, tuple)]
        if nested:
            if len(nested) != len(values):
                raise ValueError("array dimensions must be consistent")
            if any(
                isinstance(item, tuple)
                for value in nested
                for item in value
            ):
                raise ValueError("metadata arrays may have at most two dimensions")
            widths = {len(value) for value in nested}
            if len(widths) != 1:
                raise ValueError("matrix must be rectangular")
            width, = widths
            promoted = _promote(
                tuple(item for value in nested for item in value)
            )
            return tuple(
                promoted[offset : offset + width]
                for offset in range(0, len(promoted), width)
            )
        return _promote(values)
    if raw.startswith("{"):
        content = raw[1:-1].strip()
        if not content:
            raise ValueError("array must contain at least one item")
        items = _split_items(content) if "," in content else content.split()
        return _promote(tuple(_typed_value(item) for item in items))
    raise ValueError("unsupported array")


def _decode_bare_value(raw):
    decoded = []
    index = 0
    while index < len(raw):
        character = raw[index]
        if character == "\\":
            index += 1
            if index == len(raw):
                raise ValueError("bare value has a trailing escape")
            decoded.append(raw[index])
        elif character.isspace() or character in ",[]{}=":
            raise ValueError(
                "bare value containing whitespace or special characters "
                "must be quoted or escaped"
            )
        else:
            decoded.append(character)
        index += 1
    return "".join(decoded)


def _typed_value(raw):
    if raw.startswith("[") or raw.startswith("{"):
        return _array_value(raw)
    if raw[:1] in "\"'":
        end, decoded = _quoted(raw, 0, raw[0])
        if end != len(raw):
            raise ValueError("quoted value has trailing characters")
        parts = decoded.split()
        values = tuple(_scalar(part) for part in parts)
        if parts and all(type(value) is not str for value in values):
            return _promote(values)[0] if len(values) == 1 else _promote(values)
        return decoded
    decoded = _decode_bare_value(raw)
    return _scalar(decoded)


def _comment_token(text, index):
    if text[index] == '"':
        end, value = _quoted(text, index)
        return end, value, False
    start = index
    escaped = []
    requires_quoting = False
    while index < len(text) and not text[index].isspace() and text[index] != "=":
        if text[index] == "\\":
            index += 1
            if index >= len(text):
                raise ExtXYZSyntaxError("trailing escape in extXYZ comment")
        elif text[index] in ",[]{}":
            requires_quoting = True
        escaped.append(text[index])
        index += 1
    if index == start:
        raise ExtXYZSyntaxError("empty key in extXYZ comment")
    return index, "".join(escaped), requires_quoting


def _value_lexeme(text, index):
    if text[index] in "\"'":
        end, _value = _quoted(text, index, text[index])
        return end, text[index:end]
    if text[index] in "[{":
        end = _container_end(text, index)
        if end < len(text) and not text[end].isspace():
            while end < len(text) and not text[end].isspace():
                end += 1
        return end, text[index:end]
    end = index
    while end < len(text):
        if text[end] == "\\":
            end += 2
            if end > len(text):
                raise ExtXYZSyntaxError("trailing escape in extXYZ comment")
            continue
        if text[end].isspace():
            break
        end += 1
    return end, text[index:end]


def _has_unquoted_reserved_assignment(text, start):
    index = start
    while index < len(text):
        character = text[index]
        previous_is_word = index > start and (
            text[index - 1].isalnum() or text[index - 1] == "_"
        )
        if character == '"' or (character == "'" and not previous_is_word):
            try:
                index, _value = _quoted(text, index, character)
            except ExtXYZSyntaxError:
                return False
            continue
        if character == "\\":
            index += 2
            continue
        for key in _RESERVED_COMMENT_KEYS:
            end = index + len(key)
            if (
                text.startswith(key, index)
                and not previous_is_word
                and (end == len(text) or not (text[end].isalnum() or text[end] == "_"))
            ):
                while end < len(text) and text[end].isspace():
                    end += 1
                if end < len(text) and text[end] == "=":
                    return True
        index += 1
    return False


def parse_extxyz_comment(text):
    if not isinstance(text, str):
        raise TypeError("extXYZ comment must be a string")
    entries = []
    seen = set()
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index == len(text):
            break
        token_start = index
        index, key, requires_quoting = _comment_token(text, index)
        while index < len(text) and text[index].isspace():
            index += 1
        if index == len(text) or text[index] != "=":
            if seen.intersection(_RESERVED_COMMENT_KEYS):
                raise ExtXYZSyntaxError(
                    "free text is not allowed after a reserved extXYZ marker"
                )
            raise _PlainComment(
                f"extXYZ comment key {key!r} is missing '='",
                token_start,
            )
        if requires_quoting:
            raise ExtXYZSyntaxError(
                "bare extXYZ comment keys containing special characters "
                "must be quoted or escaped"
            )
        index += 1
        while index < len(text) and text[index].isspace():
            index += 1
        if index == len(text):
            raise ExtXYZSyntaxError(f"extXYZ comment key {key!r} has no value")
        if key in seen:
            raise ExtXYZSyntaxError(f"duplicate extXYZ comment key: {key}")
        seen.add(key)
        try:
            end, raw = _value_lexeme(text, index)
        except ExtXYZSyntaxError as error:
            if text[index] not in "[{":
                raise
            raw = text[index:].rstrip()
            entries.append(ExtXYZMetadataEntry(key, None, raw, str(error)))
            break
        try:
            value = _typed_value(raw)
            diagnostic = None
        except ValueError as error:
            value = None
            diagnostic = str(error)
        entries.append(ExtXYZMetadataEntry(key, value, raw, diagnostic))
        index = end

    properties_entry = next(
        (entry for entry in entries if entry.key == "Properties"),
        None,
    )
    if properties_entry is None:
        properties = parse_properties_descriptor(_DEFAULT_PROPERTIES)
    elif not isinstance(properties_entry.value, str):
        raise ExtXYZSyntaxError("Properties value must be a descriptor string")
    else:
        properties = parse_properties_descriptor(properties_entry.value)
    return ExtXYZComment(text, tuple(entries), properties)


def _atom_value(kind, text, frame_index, atom_index, field):
    try:
        if kind == "S":
            if not text:
                raise ValueError
            return text
        if kind == "I":
            if not _INTEGER.fullmatch(text):
                raise ValueError
            return int(text)
        if kind == "R":
            if not _REAL.fullmatch(text):
                raise ValueError
            value = float(text.replace("D", "E").replace("d", "e"))
            if not math.isfinite(value):
                raise ValueError
            return value
        return _LOGICAL[text]
    except (KeyError, ValueError) as error:
        raise ExtXYZSyntaxError(
            f"extXYZ frame {frame_index} atom {atom_index} "
            f"has invalid {kind} value for {field}"
        ) from error


def _iter_stream(stream):
    lines = iter(stream)
    frame_index = 0
    while True:
        try:
            count_line = next(lines)
        except StopIteration:
            return
        if not count_line.strip():
            if any(line.strip() for line in lines):
                raise ExtXYZSyntaxError("blank lines are allowed only at end of extXYZ")
            return
        try:
            atom_count = int(count_line.strip())
        except ValueError as error:
            raise ExtXYZSyntaxError(
                f"extXYZ frame {frame_index} atom count must be an integer"
            ) from error
        if atom_count <= 0:
            raise ExtXYZSyntaxError(
                f"extXYZ frame {frame_index} atom count must be positive"
            )
        try:
            raw_comment = next(lines).rstrip("\r\n")
        except StopIteration as error:
            raise ExtXYZSyntaxError(
                f"extXYZ frame {frame_index} is missing its comment"
            ) from error
        default_comment = ExtXYZComment(
            raw_comment,
            (),
            parse_properties_descriptor(_DEFAULT_PROPERTIES),
        )
        if "=" not in raw_comment:
            comment = default_comment
        else:
            try:
                comment = parse_extxyz_comment(raw_comment)
            except _PlainComment as error:
                if _has_unquoted_reserved_assignment(raw_comment, error.offset):
                    raise ExtXYZSyntaxError(
                        "free text before a reserved extXYZ marker is not allowed"
                    ) from error
                comment = default_comment
        fields = comment.properties
        explicit_properties = any(
            entry.key == "Properties" for entry in comment.entries
        )
        width = sum(field.columns for field in fields)
        values = {field.name: [] for field in fields}
        for atom_index in range(atom_count):
            try:
                row = next(lines)
            except StopIteration as error:
                raise ExtXYZSyntaxError(
                    f"extXYZ frame {frame_index} does not contain all "
                    "declared atom rows"
                ) from error
            columns = row.split()
            if len(columns) < width or (
                explicit_properties and len(columns) != width
            ):
                raise ExtXYZSyntaxError(
                    f"extXYZ frame {frame_index} atom {atom_index} "
                    + (
                        f"must contain exactly {width} columns"
                        if explicit_properties
                        else f"must contain at least {width} columns"
                    )
                )
            offset = 0
            for field in fields:
                items = tuple(
                    _atom_value(
                        field.kind,
                        text,
                        frame_index,
                        atom_index,
                        field.name,
                    )
                    for text in columns[offset : offset + field.columns]
                )
                values[field.name].append(items[0] if field.columns == 1 else items)
                offset += field.columns
        yield ExtXYZFrame(
            atom_count,
            comment,
            fields,
            tuple((field.name, tuple(values[field.name])) for field in fields),
        )
        frame_index += 1


def iter_extxyz_frames(source):
    if isinstance(source, (str, Path)):
        with Path(source).open(encoding="utf-8-sig", newline="") as stream:
            yield from _iter_stream(stream)
        return
    yield from _iter_stream(source)


__all__ = (
    "ExtXYZComment",
    "ExtXYZFrame",
    "ExtXYZMetadataEntry",
    "ExtXYZPropertyField",
    "ExtXYZSyntaxError",
    "iter_extxyz_frames",
    "parse_extxyz_comment",
    "parse_properties_descriptor",
)
