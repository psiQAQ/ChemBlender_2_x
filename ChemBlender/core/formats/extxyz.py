"""Bounded, dependency-free extXYZ syntax parsing."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import (
    ArrayData,
    AtomFrameProperty,
    CategoricalData,
    CellFrameProperty,
    DatasetStatus,
    FrameProperty,
    FrameSet,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
    ProvenanceRecord,
    Structure,
)
from ..readers import (
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


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
_ATOMIC_NUMBERS = {
    symbol: data[0] for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}
_ATOM_PROPERTIES = {
    "charge": ("atomic_charge", "elementary_charge"),
    "force": ("atomic_force", "electron_volt_per_angstrom"),
    "forces": ("atomic_force", "electron_volt_per_angstrom"),
    "mass": ("atomic_mass", "atomic_mass_unit"),
    "vel": ("atomic_velocity", "angstrom_per_femtosecond"),
    "velocity": ("atomic_velocity", "angstrom_per_femtosecond"),
}
_FRAME_PROPERTIES = {
    "energy": ("energy", "electron_volt"),
    "free_energy": ("free_energy", "electron_volt"),
    "step": ("step", "dimensionless"),
    "temperature": ("temperature", "kelvin"),
    "time": ("time", "femtosecond"),
}


class _LazyNumpy:
    def __getattr__(self, name):
        import numpy as module

        return getattr(module, name)


numpy = _LazyNumpy()


class _ArrayOwner:
    def __init__(self, root):
        self.root = None if root is None else Path(root)
        self.arrays = []
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    def empty(self, shape, dtype):
        if self.root is None:
            return numpy.empty(shape, dtype=dtype)
        path = self.root / f"extxyz-{len(self.arrays):04d}.npy"
        value = numpy.lib.format.open_memmap(
            path,
            mode="w+",
            dtype=dtype,
            shape=shape,
        )
        self.arrays.append((value, path))
        return value

    def zeros(self, shape, dtype):
        value = self.empty(shape, dtype)
        value[...] = 0
        return value

    def full(self, shape, fill_value, dtype):
        value = self.empty(shape, dtype)
        value[...] = fill_value
        return value

    def cleanup(self):
        for value, path in reversed(self.arrays):
            mmap = getattr(value, "_mmap", None)
            if mmap is not None:
                mmap.close()
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.arrays.clear()


class ExtXYZSyntaxError(ValueError):
    """Stable syntax failure for an extXYZ record."""


class ExtXYZCancelled(Exception):
    """Signal cooperative cancellation of a staged extXYZ parse."""


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


def _token(value):
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value or "property"


def _entry_map(frame):
    return {entry.key: entry for entry in frame.comment.entries}


def _field_map(frame):
    return {field.name: field for field in frame.properties}


def _value_map(frame):
    return dict(frame.values)


def _symbol_number(symbol):
    symbol = str(symbol).strip()
    normalized = symbol[:1].upper() + symbol[1:].lower()
    if normalized in {"D", "T"}:
        normalized = "H"
    try:
        return _ATOMIC_NUMBERS[normalized]
    except KeyError as error:
        raise ExtXYZSyntaxError(
            f"unknown extXYZ element symbol: {symbol}"
        ) from error


def _identity(frame):
    fields = _field_map(frame)
    values = _value_map(frame)
    species = fields.get("species")
    if species is None or species.kind != "S" or species.columns != 1:
        raise ExtXYZSyntaxError(
            "extXYZ Properties must contain species:S:1"
        )
    position = fields.get("pos")
    if position is None or position.kind != "R" or position.columns != 3:
        raise ExtXYZSyntaxError("extXYZ Properties must contain pos:R:3")
    return tuple(_symbol_number(value) for value in values["species"])


def _cell_and_pbc(frame):
    entries = _entry_map(frame)
    lattice = entries.get("Lattice")
    pbc_entry = entries.get("pbc")
    if lattice is None:
        if pbc_entry is not None and any(_pbc_tuple(pbc_entry.value)):
            raise ExtXYZSyntaxError("periodic pbc requires Lattice")
        return None, (False, False, False)
    if lattice.diagnostic is not None:
        raise ExtXYZSyntaxError(f"invalid Lattice: {lattice.diagnostic}")
    try:
        values = numpy.asarray(lattice.value, dtype=numpy.float64).reshape(-1)
    except (TypeError, ValueError) as error:
        raise ExtXYZSyntaxError("Lattice must contain nine real values") from error
    if values.shape != (9,) or not numpy.all(numpy.isfinite(values)):
        raise ExtXYZSyntaxError("Lattice must contain nine finite real values")
    cell = values.reshape((3, 3))
    if abs(float(numpy.linalg.det(cell))) < 1.0e-12:
        raise ExtXYZSyntaxError("Lattice must be non-singular")
    return (
        cell,
        (True, True, True)
        if pbc_entry is None
        else _pbc_tuple(pbc_entry.value),
    )


def _pbc_tuple(value):
    if isinstance(value, str):
        values = tuple(value.split())
    elif isinstance(value, tuple):
        values = value
    else:
        values = (value,)
    normalized = []
    for item in values:
        if type(item) is bool:
            normalized.append(item)
        elif str(item) in _LOGICAL:
            normalized.append(_LOGICAL[str(item)])
        else:
            raise ExtXYZSyntaxError("pbc must contain three logical values")
    if len(normalized) != 3:
        raise ExtXYZSyntaxError("pbc must contain three logical values")
    return tuple(normalized)


def _stable_uuid(source_hash, role):
    return uuid5(
        NAMESPACE_URL,
        f"chemblender:extxyz:1:{source_hash}:{role}",
    )


def _source_hash(source, is_cancelled):
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(65536):
            if is_cancelled():
                raise ExtXYZCancelled("extXYZ parse was cancelled")
            digest.update(chunk)
    return digest.hexdigest()


def _revision(source_hash, role, payload):
    document = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        f"{source_hash}:{role}:{document}".encode("utf-8")
    ).hexdigest()


def _dims(field, *, prefix):
    if field.columns == 1:
        return prefix
    if field.columns == 3:
        return prefix + ("xyz",)
    return prefix + ("component",)


def _shape(frame_count, atom_count, field):
    base = (frame_count, atom_count)
    return base if field.columns == 1 else base + (field.columns,)


def _numeric_dtype(kind):
    return {
        "I": numpy.int64,
        "R": numpy.float64,
        "L": numpy.bool_,
    }[kind]


def _categorical(values, present, dims, owner):
    categories = []
    first = next(iter(values.values()))
    suffix = () if not first or isinstance(first[0], str) else (len(first[0]),)
    codes = owner.full(present.shape + suffix, -1, numpy.int64)
    for frame_index, frame_values in values.items():
        for atom_index, value in enumerate(frame_values):
            items = (value,) if isinstance(value, str) else value
            for component, item in enumerate(items):
                if item not in categories:
                    categories.append(item)
                index = (frame_index, atom_index) + (
                    () if suffix == () else (component,)
                )
                codes[index] = categories.index(item)
    return CategoricalData(
        ArrayData(codes, dims, "dimensionless"),
        tuple(categories),
        -1,
    )


def _atom_property(
    *,
    source_hash,
    group_index,
    frame_set_id,
    provenance_id,
    field,
    values,
    frame_count,
    atom_count,
    issues,
    owner,
    declared_unit,
):
    role, unit = _ATOM_PROPERTIES.get(
        field.name,
        (_token(field.name), "unknown"),
    )
    present = numpy.zeros((frame_count, atom_count), dtype=numpy.bool_)
    for frame_index, frame_values in values.items():
        present[frame_index] = True
    if field.kind == "S":
        data = _categorical(
            values,
            present,
            _dims(field, prefix=("frame", "atom")),
            owner,
        )
        mask = None
    else:
        array = owner.zeros(
            _shape(frame_count, atom_count, field),
            _numeric_dtype(field.kind),
        )
        for frame_index, frame_values in values.items():
            array[frame_index] = frame_values
        data = ArrayData(
            array,
            _dims(field, prefix=("frame", "atom")),
            unit,
        )
        mask = (
            None
            if numpy.all(present)
            else ArrayData(
                present,
                ("frame", "atom"),
                "dimensionless",
            )
        )
    if field.name in _ATOM_PROPERTIES:
        if not declared_unit:
            issues.append(
                ParserIssue(
                    IssueKind.AMBIGUOUS,
                    f"atom_properties.{field.name}",
                    f"{unit} was assumed because extXYZ declared no unit",
                )
            )
        status = (
            DatasetStatus.PARTIAL
            if mask is not None
            else DatasetStatus.COMPLETE
        )
    else:
        status = DatasetStatus.AMBIGUOUS
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"atom_properties.{field.name}",
                "extXYZ property has no declared ChemBlender semantic unit",
            )
        )
    identity = f"group:{group_index}:atom_property:{field.name}"
    return AtomFrameProperty(
        id=_stable_uuid(source_hash, identity),
        revision=_revision(
            source_hash,
            identity,
            {
                "kind": field.kind,
                "columns": field.columns,
                "present": present.tolist(),
            },
        ),
        semantic_role=role,
        domain="atom_frame",
        data=data,
        status=status,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        frame_set_id=frame_set_id,
        validity_mask=mask,
    )


def _metadata_property(
    *,
    source_hash,
    group_index,
    frame_set_id,
    provenance_id,
    name,
    values,
    frame_count,
    issues,
    owner,
):
    role, unit = _FRAME_PROPERTIES.get(name, (_token(name), "unknown"))
    present = numpy.asarray(
        [index in values for index in range(frame_count)],
        dtype=numpy.bool_,
    )
    samples = tuple(values.values())
    if not samples:
        return None
    sample = samples[0]
    sample_array = numpy.asarray(sample)
    if isinstance(sample, str) or sample_array.dtype.kind in "SU":
        categories = []
        suffix = (
            ()
            if sample_array.ndim == 0
            else (
                ("component",)
                if sample_array.ndim == 1
                else ("row", "column")
            )
        )
        codes = owner.full(
            (frame_count,) + sample_array.shape,
            -1,
            numpy.int64,
        )
        for index, value in values.items():
            value_array = numpy.asarray(value)
            if value_array.shape != sample_array.shape:
                raise ExtXYZSyntaxError(
                    f"metadata {name} changes shape between frames"
                )
            for offset in numpy.ndindex(value_array.shape or (1,)):
                text = str(value_array.item() if not value_array.shape else value_array[offset])
                if text not in categories:
                    categories.append(text)
                target = (index,) if not value_array.shape else (index,) + offset
                codes[target] = categories.index(text)
        data = CategoricalData(
            ArrayData(codes, ("frame",) + suffix, "dimensionless"),
            tuple(categories),
            -1,
        )
        mask = None
    else:
        if sample_array.ndim > 2 or sample_array.dtype.kind not in "biuf":
            return None
        suffix = (
            ()
            if sample_array.ndim == 0
            else (
                ("tensor_component",)
                if sample_array.ndim == 1
                else ("tensor_row", "tensor_column")
            )
        )
        if name in {"stress", "virial"}:
            size = int(sample_array.size)
            if size not in {6, 9}:
                raise ExtXYZSyntaxError(
                    f"{name} must contain six Voigt or nine matrix values"
                )
            role = f"{name}_{'voigt' if size == 6 else 'matrix'}"
            unit = "unknown"
        array = owner.zeros(
            (frame_count,) + sample_array.shape,
            sample_array.dtype,
        )
        for index, value in values.items():
            value_array = numpy.asarray(value)
            if value_array.shape != sample_array.shape:
                raise ExtXYZSyntaxError(
                    f"metadata {name} changes shape between frames"
                )
            array[index] = value_array
        data = ArrayData(array, ("frame",) + suffix, unit)
        mask = (
            None
            if numpy.all(present)
            else ArrayData(present, ("frame",), "dimensionless")
        )
    if name in _FRAME_PROPERTIES:
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"frame_properties.{name}",
                f"{unit} was assumed because extXYZ declared no unit",
            )
        )
        status = (
            DatasetStatus.PARTIAL
            if mask is not None
            else DatasetStatus.COMPLETE
        )
    else:
        status = DatasetStatus.AMBIGUOUS
    identity = f"group:{group_index}:frame_property:{name}"
    return FrameProperty(
        id=_stable_uuid(source_hash, identity),
        revision=_revision(
            source_hash,
            identity,
            {"present": present.tolist(), "shape": data.shape},
        ),
        semantic_role=role,
        domain="frame",
        data=data,
        status=status,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        frame_set_id=frame_set_id,
        validity_mask=mask,
    )


def _periodic_data(cell, pbc, coordinates, labels):
    fractional = numpy.asarray(coordinates) @ numpy.linalg.inv(cell)
    atom_count = len(labels)
    return PeriodicSiteData(
        fractional_coordinates=ArrayData(
            fractional,
            ("atom", "xyz"),
            "dimensionless",
        ),
        site_labels=tuple(f"{label}{index + 1}" for index, label in enumerate(labels)),
        occupancies=ArrayData(
            numpy.ones(atom_count, dtype=numpy.float64),
            ("atom",),
            "dimensionless",
        ),
        isotropic_displacements=None,
        anisotropic_displacements=None,
        adp_types=("none",) * atom_count,
        disorder_groups=(0,) * atom_count,
        declared_space_group_name=None,
        declared_space_group_number=None,
        symmetry_operations=(),
        cif_envelope_id=None,
        pbc=pbc,
    )


def _build_group(
    source,
    source_hash,
    group_index,
    start,
    end,
    identity,
    issues,
    owner,
    is_cancelled,
):
    frame_count = end - start
    atom_count = len(identity)
    provenance_id = _stable_uuid(source_hash, "provenance")
    structure_id = _stable_uuid(source_hash, f"group:{group_index}:structure")
    frame_set_id = _stable_uuid(source_hash, f"group:{group_index}:frames")
    coordinates = owner.empty(
        (frame_count, atom_count, 3),
        numpy.float64,
    )
    comments = []
    cells = [None] * frame_count
    pbcs = [None] * frame_count
    symbols = None
    atom_specs = {}
    atom_values = {}
    metadata_values = {}
    for source_index, frame in enumerate(iter_extxyz_frames(source)):
        is_cancelled()
        if source_index < start:
            continue
        if source_index >= end:
            break
        frame_index = source_index - start
        fields = _field_map(frame)
        values = _value_map(frame)
        coordinates[frame_index] = values["pos"]
        comments.append(frame.comment.raw)
        cells[frame_index], pbcs[frame_index] = _cell_and_pbc(frame)
        if symbols is None:
            symbols = tuple(str(value) for value in values["species"])
        for field in frame.properties:
            if field.name in {"species", "pos"}:
                continue
            previous = atom_specs.setdefault(field.name, field)
            if previous != field:
                raise ExtXYZSyntaxError(
                    f"Properties field {field.name} changes type or width"
                )
            atom_values.setdefault(field.name, {})[frame_index] = values[field.name]
        for entry in frame.comment.entries:
            if entry.key in _RESERVED_COMMENT_KEYS:
                continue
            if entry.diagnostic is not None:
                issues.append(
                    ParserIssue(
                        IssueKind.AMBIGUOUS,
                        f"metadata.{entry.key}",
                        f"{entry.diagnostic}; raw value retained in comment",
                    )
                )
                continue
            metadata_values.setdefault(entry.key, {})[frame_index] = entry.value

    first_cell = cells[0]
    first_pbc = pbcs[0]
    periodic = (
        None
        if first_cell is None
        else _periodic_data(first_cell, first_pbc, coordinates[0], symbols)
    )
    structure = Structure(
        id=structure_id,
        revision=_revision(
            source_hash,
            f"group:{group_index}:structure",
            {"identity": identity, "first_frame": coordinates[0].tolist()},
        ),
        atomic_numbers=identity,
        coordinates=ArrayData(
            coordinates[0],
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=(
            None
            if first_cell is None
            else ArrayData(first_cell, ("cell_vector", "xyz"), "angstrom")
        ),
        periodic=periodic,
    )
    frame_set = FrameSet(
        id=frame_set_id,
        revision=_revision(
            source_hash,
            f"group:{group_index}:frames",
            {"start": start, "end": end},
        ),
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            coordinates,
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        comments=tuple(comments),
    )
    datasets = [frame_set]
    datasets.extend(
        _atom_property(
            source_hash=source_hash,
            group_index=group_index,
            frame_set_id=frame_set_id,
            provenance_id=provenance_id,
            field=atom_specs[name],
            values=atom_values[name],
            frame_count=frame_count,
            atom_count=atom_count,
            issues=issues,
            owner=owner,
            declared_unit=(
                bool(metadata_values.get(f"{name}_unit"))
                and all(
                    value == _ATOM_PROPERTIES[name][1]
                    for value in metadata_values[f"{name}_unit"].values()
                )
                if name in _ATOM_PROPERTIES
                else False
            ),
        )
        for name in atom_specs
    )
    for name, values in metadata_values.items():
        if name.endswith("_unit") and name[:-5] in _ATOM_PROPERTIES:
            continue
        dataset = _metadata_property(
            source_hash=source_hash,
            group_index=group_index,
            frame_set_id=frame_set_id,
            provenance_id=provenance_id,
            name=name,
            values=values,
            frame_count=frame_count,
            issues=issues,
            owner=owner,
        )
        if dataset is not None:
            datasets.append(dataset)
    if any(cell is not None for cell in cells) and (
        any(cell is None for cell in cells)
        or any(
            not numpy.array_equal(cell, first_cell)
            for cell in cells
            if cell is not None
        )
    ):
        present = numpy.asarray(
            [cell is not None for cell in cells],
            dtype=numpy.bool_,
        )
        values = owner.zeros((frame_count, 3, 3), numpy.float64)
        for index, cell in enumerate(cells):
            if cell is not None:
                values[index] = cell
        mask = (
            None
            if numpy.all(present)
            else ArrayData(present, ("frame",), "dimensionless")
        )
        datasets.append(
            CellFrameProperty(
                id=_stable_uuid(source_hash, f"group:{group_index}:cells"),
                revision=_revision(
                    source_hash,
                    f"group:{group_index}:cells",
                    {"present": present.tolist()},
                ),
                semantic_role="cell",
                domain="cell_frame",
                data=ArrayData(
                    values,
                    ("frame", "cell_vector", "xyz"),
                    "angstrom",
                ),
                status=(
                    DatasetStatus.COMPLETE
                    if mask is None
                    else DatasetStatus.PARTIAL
                ),
                source_calculation=None,
                provenance_ids=(provenance_id,),
                frame_set_id=frame_set_id,
                validity_mask=mask,
            )
        )
    if any(pbc != first_pbc for pbc in pbcs[1:]):
        pbc_values = numpy.asarray(pbcs, dtype=numpy.bool_)
        datasets.append(
            FrameProperty(
                id=_stable_uuid(source_hash, f"group:{group_index}:pbc"),
                revision=_revision(
                    source_hash,
                    f"group:{group_index}:pbc",
                    pbc_values.tolist(),
                ),
                semantic_role="pbc",
                domain="frame",
                data=ArrayData(
                    pbc_values,
                    ("frame", "xyz"),
                    "dimensionless",
                ),
                status=DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(provenance_id,),
                frame_set_id=frame_set_id,
            )
        )
    return structure, tuple(datasets)


def parse_extxyz(source, *, staging_root=None, is_cancelled=None):
    source = Path(source)
    is_cancelled = (lambda: False) if is_cancelled is None else is_cancelled
    if not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable")
    owner = _ArrayOwner(staging_root)
    try:
        source_hash = _source_hash(source, is_cancelled)
        identities = []
        for frame in iter_extxyz_frames(source):
            if is_cancelled():
                raise ExtXYZCancelled("extXYZ parse was cancelled")
            identities.append(_identity(frame))
            _cell_and_pbc(frame)
        if not identities:
            raise ExtXYZSyntaxError("extXYZ source is missing an atom frame")
        ranges = []
        start = 0
        for index in range(1, len(identities)):
            if identities[index] != identities[start]:
                ranges.append((start, index, identities[start]))
                start = index
        ranges.append((start, len(identities), identities[start]))

        issues = []
        if len(ranges) > 1:
            issues.append(
                ParserIssue(
                    IssueKind.AMBIGUOUS,
                    "frames.atomic_identity",
                    "atom identity changed between frames; trajectory was split",
                )
            )
        structures = []
        datasets = []
        for group_index, (start, end, identity) in enumerate(ranges):
            structure, group_datasets = _build_group(
                source,
                source_hash,
                group_index,
                start,
                end,
                identity,
                issues,
                owner,
                is_cancelled,
            )
            structures.append(structure)
            datasets.extend(group_datasets)
        provenance_id = _stable_uuid(source_hash, "provenance")
        provenance = ProvenanceRecord(
            id=provenance_id,
            revision=_revision(source_hash, "provenance", {"format": "extxyz"}),
            producer="ChemBlender extXYZ reader",
            producer_version="1",
            source=str(source.resolve()),
            source_hash=source_hash,
            parent_ids=(),
            operation="parse",
            parameters=(
                ("format", "extxyz"),
                ("lattice_order", "ax ay az bx by bz cx cy cz"),
            ),
        )
        created = tuple(
            [item.id for item in structures]
            + [item.id for item in datasets]
            + [provenance.id]
        )
        return ImportBatch(
            structures=tuple(structures),
            datasets=tuple(datasets),
            provenance=(provenance,),
            report=ParserReport(
                reader_id="extxyz",
                reader_version="1",
                created_entity_ids=created,
                parsed_capabilities=("structure", "trajectory", "properties"),
                issues=tuple(issues),
            ),
        )
    except BaseException:
        owner.cleanup()
        raise


def sniff_extxyz(source, prefix):
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 extXYZ text")
    if len(lines) < 2 or "Properties" not in lines[1]:
        return SniffResult(SniffMatch.NONE, "no extXYZ Properties marker")
    try:
        int(lines[0].strip())
        parse_extxyz_comment(lines[1])
    except (ValueError, ExtXYZSyntaxError):
        return SniffResult(SniffMatch.NONE, "invalid extXYZ Properties marker")
    return SniffResult(SniffMatch.EXACT, "valid extXYZ Properties marker")


def _parse_request(request):
    return parse_extxyz(
        request.source_path,
        staging_root=request.staging_root,
        is_cancelled=request.is_cancelled,
    )


EXTXYZ_READER = ReaderDescriptor(
    reader_id="extxyz",
    reader_version="1",
    extensions=(".xyz", ".extxyz"),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "trajectory": CapabilitySupport.SUPPORTED,
        "properties": CapabilitySupport.SUPPORTED,
    },
    priority=130,
    sniff=sniff_extxyz,
    parse=parse_extxyz,
    parse_request=_parse_request,
)


__all__ = (
    "EXTXYZ_READER",
    "ExtXYZCancelled",
    "ExtXYZComment",
    "ExtXYZFrame",
    "ExtXYZMetadataEntry",
    "ExtXYZPropertyField",
    "ExtXYZSyntaxError",
    "iter_extxyz_frames",
    "parse_extxyz",
    "parse_extxyz_comment",
    "parse_properties_descriptor",
    "sniff_extxyz",
)
