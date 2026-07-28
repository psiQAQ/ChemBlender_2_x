"""Bounded, dependency-free extXYZ syntax parsing."""

from dataclasses import dataclass, field
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import tempfile
from uuid import NAMESPACE_URL, uuid4, uuid5

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
from ..storage.atomic_paths import short_sibling_temporary_path
from ..storage.hashing import sha256_bytes, sha256_file


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
_DEFERRED_PREVIEW_BYTES = 256 * 1024
_PREVIEW_SNAPSHOT_NAME = "extxyz-preview-source.extxyz"
_MATERIALIZED_MARKER_NAME = ".extxyz-materialized"


class _LazyNumpy:
    def __getattr__(self, name):
        import numpy as module

        return getattr(module, name)


numpy = _LazyNumpy()


def _raise_cleanup_failures(failures):
    if not failures:
        return
    first, *remaining = failures
    for error in remaining:
        first.add_note(
            "additional extXYZ staging cleanup failure: "
            f"{type(error).__name__}: {error}"
        )
    raise first


class _ArrayOwner:
    def __init__(self, root):
        self.root = None
        self.arrays = []
        self._snapshot_path = None
        self._snapshot_root = None
        self._snapshot_root_owned = False
        if root is not None:
            parent = Path(root)
            parent.mkdir(parents=True, exist_ok=True)
            self.root = parent / f"extxyz-{uuid4().hex}"
            self.root.mkdir()
            self._snapshot_root = self.root

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

    def snapshot(self, source, is_cancelled):
        if self._snapshot_root is None:
            self._snapshot_root = Path(
                tempfile.mkdtemp(prefix="chemblender-extxyz-")
            )
            self._snapshot_root_owned = True
        destination = self._snapshot_root / "source.extxyz"
        temporary = short_sibling_temporary_path(destination)
        try:
            with source.open("rb") as input_stream, temporary.open("xb") as output:
                while chunk := input_stream.read(65536):
                    _check_cancelled(is_cancelled)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
                _check_cancelled(is_cancelled)
            os.replace(temporary, destination)
        except BaseException as error:
            try:
                temporary.unlink(missing_ok=True)
            except BaseException as cleanup_error:
                error.add_note(
                    "extXYZ snapshot temporary cleanup failed: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
            raise
        self._snapshot_path = destination
        return destination

    def release_snapshot(self):
        failures = []
        if self._snapshot_path is not None:
            try:
                self._snapshot_path.unlink()
            except FileNotFoundError:
                pass
            except BaseException as error:
                failures.append(error)
            else:
                self._snapshot_path = None
        if self._snapshot_root_owned and self._snapshot_root is not None:
            try:
                self._snapshot_root.rmdir()
            except FileNotFoundError:
                pass
            except BaseException as error:
                failures.append(error)
            else:
                self._snapshot_root = None
                self._snapshot_root_owned = False
        _raise_cleanup_failures(failures)

    def cleanup(self):
        failures = []
        for value, path in reversed(self.arrays):
            mmap = getattr(value, "_mmap", None)
            if mmap is not None:
                try:
                    mmap.close()
                except BaseException as error:
                    failures.append(error)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except BaseException as error:
                failures.append(error)
        self.arrays.clear()
        if self._snapshot_path is not None:
            try:
                self._snapshot_path.unlink()
            except FileNotFoundError:
                pass
            except BaseException as error:
                failures.append(error)
            else:
                self._snapshot_path = None
        if self.root is not None:
            try:
                self.root.rmdir()
            except FileNotFoundError:
                pass
            except BaseException as error:
                failures.append(error)
        if (
            self._snapshot_root_owned
            and self._snapshot_root is not None
            and self._snapshot_root != self.root
        ):
            try:
                self._snapshot_root.rmdir()
            except FileNotFoundError:
                pass
            except BaseException as error:
                failures.append(error)
        _raise_cleanup_failures(failures)


class _PreviewArrayOwner:
    @staticmethod
    def _constant(shape, value, dtype):
        return numpy.broadcast_to(
            numpy.asarray(value, dtype=dtype),
            shape,
        )

    def empty(self, shape, dtype):
        return self._constant(shape, 0, dtype)

    def zeros(self, shape, dtype):
        return self._constant(shape, 0, dtype)

    def full(self, shape, fill_value, dtype):
        return self._constant(shape, fill_value, dtype)


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
        if len(parts) > 1 and all(type(value) is not str for value in values):
            return _promote(values)
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
            try:
                columns = shlex.split(row, comments=False, posix=True)
            except ValueError as error:
                raise ExtXYZSyntaxError(
                    f"extXYZ frame {frame_index} atom {atom_index} "
                    "has invalid quoted columns"
                ) from error
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
            _check_cancelled(is_cancelled)
            digest.update(chunk)
    return digest.hexdigest()


def _check_cancelled(is_cancelled):
    result = is_cancelled()
    if type(result) is not bool:
        raise TypeError("is_cancelled must return bool")
    if result:
        raise ExtXYZCancelled("extXYZ parse was cancelled")


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


@dataclass(slots=True)
class _ValuePlan:
    sample: object
    present: int = 0
    unit_missing: int = 0
    unit_values: set = field(default_factory=set)
    schema: ExtXYZPropertyField | None = None


@dataclass(slots=True)
class _GroupPlan:
    index: int
    start: int
    end: int
    identity: tuple[int, ...]
    first_cell: object
    first_pbc: tuple[bool, bool, bool]
    atom: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    cell_changed: bool = False
    cell_missing: bool = False
    pbc_changed: bool = False

    @property
    def frame_count(self):
        return self.end - self.start


def _metadata_signature(value):
    array = numpy.asarray(value)
    if array.ndim > 2:
        return None
    if array.dtype.kind in "SU":
        kind = "categorical"
    elif array.dtype.kind in "biuf":
        kind = array.dtype.str
    else:
        return None
    return kind, array.shape


def _record_unit(plan, expected, entry):
    if entry is None:
        plan.unit_missing += 1
    else:
        value = None if entry.diagnostic is not None else str(entry.value)
        plan.unit_values.add(expected if value == expected else "<invalid>")


def _unit_mode(plan, expected):
    if expected is None:
        return "unknown", "unknown"
    if plan.unit_missing == plan.present and not plan.unit_values:
        return expected, "assumed"
    if plan.unit_missing == 0 and plan.unit_values == {expected}:
        return expected, "declared"
    return "unknown", "invalid"


def _accumulate_frame_plan(current, frame_index, frame, cell, pbc, issues):
    current.end = frame_index + 1
    current.cell_missing |= cell is None
    current.cell_changed |= (
        (cell is None) != (current.first_cell is None)
        or (
            cell is not None
            and current.first_cell is not None
            and not numpy.array_equal(cell, current.first_cell)
        )
    )
    current.pbc_changed |= pbc != current.first_pbc
    entries = _entry_map(frame)
    values = _value_map(frame)
    for property_field in frame.properties:
        if property_field.name in {"species", "pos"}:
            continue
        plan = current.atom.get(property_field.name)
        if plan is None:
            plan = _ValuePlan(
                values[property_field.name][0],
                schema=property_field,
            )
            current.atom[property_field.name] = plan
        elif plan.schema != property_field:
            raise ExtXYZSyntaxError(
                f"Properties field {property_field.name} changes type or width"
            )
        plan.present += 1
        if property_field.name in _ATOM_PROPERTIES:
            _record_unit(
                plan,
                _ATOM_PROPERTIES[property_field.name][1],
                entries.get(f"{property_field.name}_unit"),
            )
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
        signature = _metadata_signature(entry.value)
        if signature is None:
            issues.append(
                ParserIssue(
                    IssueKind.AMBIGUOUS,
                    f"metadata.{entry.key}",
                    "metadata value cannot be represented as a typed "
                    "property; raw value retained in comment",
                )
            )
            continue
        plan = current.metadata.get(entry.key)
        if plan is None:
            plan = _ValuePlan(entry.value)
            current.metadata[entry.key] = plan
        elif _metadata_signature(plan.sample) != signature:
            raise ExtXYZSyntaxError(
                f"metadata {entry.key} changes shape or type between frames"
            )
        plan.present += 1
    for name, (_role, expected) in _FRAME_PROPERTIES.items():
        plan = current.metadata.get(name)
        if plan is not None and name in entries:
            _record_unit(
                plan,
                expected,
                entries.get(f"{name}_unit"),
            )


def _plan_source(source, is_cancelled, issues):
    groups = []
    current = None
    for frame_index, frame in enumerate(iter_extxyz_frames(source)):
        _check_cancelled(is_cancelled)
        identity = _identity(frame)
        cell, pbc = _cell_and_pbc(frame)
        if current is None or identity != current.identity:
            current = _GroupPlan(
                len(groups),
                frame_index,
                frame_index,
                identity,
                None if cell is None else cell.copy(),
                pbc,
                cell_missing=cell is None,
            )
            groups.append(current)
        _accumulate_frame_plan(
            current,
            frame_index,
            frame,
            cell,
            pbc,
            issues,
        )
    if not groups:
        raise ExtXYZSyntaxError("extXYZ source is missing an atom frame")
    return groups


def _categorical_state(owner, shape, dims, present_shape):
    return {
        "values": owner.full(shape, -1, numpy.int64),
        "dims": dims,
        "categories": [],
        "category_index": {},
        "present": (
            None
            if present_shape is None
            else owner.zeros(present_shape, numpy.bool_)
        ),
        "categorical": True,
    }


def _numeric_state(owner, shape, dims, dtype, unit, present_shape):
    return {
        "values": owner.zeros(shape, dtype),
        "dims": dims,
        "unit": unit,
        "present": (
            None
            if present_shape is None
            else owner.zeros(present_shape, numpy.bool_)
        ),
        "categorical": False,
    }


def _prepare_atom_state(plan, group, owner, issues):
    schema = plan.schema
    role, expected = _ATOM_PROPERTIES.get(
        schema.name,
        (_token(schema.name), None),
    )
    unit, mode = _unit_mode(plan, expected)
    if mode == "assumed":
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"atom_properties.{schema.name}",
                f"{unit} was assumed because extXYZ declared no unit",
            )
        )
    elif mode == "invalid":
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"atom_properties.{schema.name}",
                "explicit extXYZ unit is unknown or inconsistent",
            )
        )
    elif mode == "unknown":
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"atom_properties.{schema.name}",
                "extXYZ property has no declared ChemBlender semantic unit",
            )
        )
    shape = _shape(group.frame_count, len(group.identity), schema)
    dims = _dims(schema, prefix=("frame", "atom"))
    present_shape = (
        None
        if plan.present == group.frame_count
        else (group.frame_count, len(group.identity))
    )
    state = (
        _categorical_state(owner, shape, dims, present_shape)
        if schema.kind == "S"
        else _numeric_state(
            owner,
            shape,
            dims,
            _numeric_dtype(schema.kind),
            unit,
            present_shape,
        )
    )
    state.update(
        {
            "name": schema.name,
            "role": role,
            "mode": mode,
            "plan": plan,
        }
    )
    return state


def _metadata_dims(sample):
    array = numpy.asarray(sample)
    if array.ndim == 0:
        return ()
    if array.ndim == 1:
        return ("tensor_component",)
    return ("tensor_row", "tensor_column")


def _prepare_metadata_state(name, plan, group, owner, issues):
    role, expected = _FRAME_PROPERTIES.get(name, (_token(name), None))
    unit, mode = _unit_mode(plan, expected)
    sample = numpy.asarray(plan.sample)
    if name in {"stress", "virial"}:
        if sample.ndim != 1 or sample.size not in {6, 9}:
            raise ExtXYZSyntaxError(
                f"{name} must contain six Voigt or nine matrix values"
            )
        role = f"{name}_{'voigt' if sample.size == 6 else 'matrix'}"
        unit, mode = "unknown", "unknown"
    if mode == "assumed":
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"frame_properties.{name}",
                f"{unit} was assumed because extXYZ declared no unit",
            )
        )
    elif mode == "invalid":
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"frame_properties.{name}",
                "explicit extXYZ unit is unknown or inconsistent",
            )
        )
    present_shape = (
        None if plan.present == group.frame_count else (group.frame_count,)
    )
    dims = ("frame",) + _metadata_dims(plan.sample)
    shape = (group.frame_count,) + sample.shape
    state = (
        _categorical_state(owner, shape, dims, present_shape)
        if sample.dtype.kind in "SU"
        else _numeric_state(
            owner,
            shape,
            dims,
            sample.dtype,
            unit,
            present_shape,
        )
    )
    state.update(
        {
            "name": name,
            "role": role,
            "mode": mode,
            "plan": plan,
        }
    )
    return state


def _consumed_unit_names(group):
    names = set()
    for name, plan in group.atom.items():
        expected = _ATOM_PROPERTIES.get(name, (None, None))[1]
        if _unit_mode(plan, expected)[1] == "declared":
            names.add(f"{name}_unit")
    for name, plan in group.metadata.items():
        expected = _FRAME_PROPERTIES.get(name, (None, None))[1]
        if expected is not None and _unit_mode(plan, expected)[1] == "declared":
            names.add(f"{name}_unit")
    return names


def _prepare_group_state(group, owner, issues):
    cell_values = cell_present = pbc_values = None
    if group.cell_changed or (group.first_cell is not None and group.cell_missing):
        cell_values = owner.zeros(
            (group.frame_count, 3, 3),
            numpy.float64,
        )
        if group.cell_missing:
            cell_present = owner.zeros((group.frame_count,), numpy.bool_)
    if group.pbc_changed:
        pbc_values = owner.empty((group.frame_count, 3), numpy.bool_)
    consumed = _consumed_unit_names(group)
    return {
        "plan": group,
        "coordinates": owner.empty(
            (group.frame_count, len(group.identity), 3),
            numpy.float64,
        ),
        "comments": [None] * group.frame_count,
        "symbols": None,
        "cells": cell_values,
        "cell_present": cell_present,
        "pbcs": pbc_values,
        "atom": {
            name: _prepare_atom_state(plan, group, owner, issues)
            for name, plan in group.atom.items()
        },
        "metadata": {
            name: _prepare_metadata_state(name, plan, group, owner, issues)
            for name, plan in group.metadata.items()
            if name not in consumed
        },
    }


def _write_categorical(state, target, value):
    value = numpy.asarray(value)
    for offset in numpy.ndindex(value.shape or (1,)):
        text = str(value.item() if not value.shape else value[offset])
        if text not in state["category_index"]:
            state["category_index"][text] = len(state["categories"])
            state["categories"].append(text)
        destination = target if not value.shape else target + offset
        state["values"][destination] = state["category_index"][text]


def _fill_states(source, states, is_cancelled):
    group_index = 0
    for frame_index, frame in enumerate(iter_extxyz_frames(source)):
        _check_cancelled(is_cancelled)
        while frame_index >= states[group_index]["plan"].end:
            group_index += 1
        state = states[group_index]
        group = state["plan"]
        local = frame_index - group.start
        values = _value_map(frame)
        if _identity(frame) != group.identity:
            raise ExtXYZSyntaxError("atom identity changed during extXYZ fill")
        state["coordinates"][local] = values["pos"]
        state["comments"][local] = frame.comment.raw
        if state["symbols"] is None:
            state["symbols"] = tuple(str(value) for value in values["species"])
        cell, pbc = _cell_and_pbc(frame)
        if state["cells"] is not None and cell is not None:
            state["cells"][local] = cell
            if state["cell_present"] is not None:
                state["cell_present"][local] = True
        if state["pbcs"] is not None:
            state["pbcs"][local] = pbc
        fields = _field_map(frame)
        for name, property_state in state["atom"].items():
            if name not in fields:
                continue
            if property_state["categorical"]:
                for atom_index, value in enumerate(values[name]):
                    _write_categorical(
                        property_state,
                        (local, atom_index),
                        value,
                    )
            else:
                property_state["values"][local] = values[name]
            if property_state["present"] is not None:
                property_state["present"][local] = True
        entries = _entry_map(frame)
        for name, property_state in state["metadata"].items():
            entry = entries.get(name)
            if entry is None or entry.diagnostic is not None:
                continue
            if property_state["categorical"]:
                _write_categorical(property_state, (local,), entry.value)
            else:
                property_state["values"][local] = entry.value
            if property_state["present"] is not None:
                property_state["present"][local] = True


def _state_data(state):
    if state["categorical"]:
        return CategoricalData(
            ArrayData(state["values"], state["dims"], "dimensionless"),
            tuple(state["categories"]),
            -1,
        )
    return ArrayData(state["values"], state["dims"], state["unit"])


def _state_status(state):
    if state["mode"] in {"invalid", "unknown"}:
        return DatasetStatus.AMBIGUOUS
    return (
        DatasetStatus.PARTIAL
        if state["present"] is not None
        else DatasetStatus.COMPLETE
    )


def _state_mask(state, dims):
    if state["categorical"] or state["present"] is None:
        return None
    return ArrayData(state["present"], dims, "dimensionless")


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


def _finalize_group(state, source_hash):
    group = state["plan"]
    group_index = group.index
    provenance_id = _stable_uuid(source_hash, "provenance")
    structure_id = _stable_uuid(source_hash, f"group:{group_index}:structure")
    frame_set_id = _stable_uuid(source_hash, f"group:{group_index}:frames")
    periodic = (
        None
        if group.first_cell is None
        else _periodic_data(
            group.first_cell,
            group.first_pbc,
            state["coordinates"][0],
            state["symbols"],
        )
    )
    structure = Structure(
        id=structure_id,
        revision=_revision(
            source_hash,
            f"group:{group_index}:structure",
            {
                "identity": group.identity,
                "start": group.start,
                "end": group.end,
            },
        ),
        atomic_numbers=group.identity,
        coordinates=ArrayData(
            state["coordinates"][0],
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=(
            None
            if group.first_cell is None
            else ArrayData(
                group.first_cell,
                ("cell_vector", "xyz"),
                "angstrom",
            )
        ),
        periodic=periodic,
    )
    frame_set = FrameSet(
        id=frame_set_id,
        revision=_revision(
            source_hash,
            f"group:{group_index}:frames",
            {"start": group.start, "end": group.end},
        ),
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            state["coordinates"],
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
        comments=tuple(state["comments"]),
    )
    datasets = [frame_set]
    for name, property_state in state["atom"].items():
        identity = f"group:{group_index}:atom_property:{name}"
        datasets.append(
            AtomFrameProperty(
                id=_stable_uuid(source_hash, identity),
                revision=_revision(
                    source_hash,
                    identity,
                    {
                        "kind": property_state["plan"].schema.kind,
                        "columns": property_state["plan"].schema.columns,
                        "present": property_state["plan"].present,
                    },
                ),
                semantic_role=property_state["role"],
                domain="atom_frame",
                data=_state_data(property_state),
                status=_state_status(property_state),
                source_calculation=None,
                provenance_ids=(provenance_id,),
                frame_set_id=frame_set_id,
                validity_mask=_state_mask(
                    property_state,
                    ("frame", "atom"),
                ),
            )
        )
    for name, property_state in state["metadata"].items():
        identity = f"group:{group_index}:frame_property:{name}"
        datasets.append(
            FrameProperty(
                id=_stable_uuid(source_hash, identity),
                revision=_revision(
                    source_hash,
                    identity,
                    {
                        "present": property_state["plan"].present,
                        "shape": property_state["values"].shape,
                    },
                ),
                semantic_role=property_state["role"],
                domain="frame",
                data=_state_data(property_state),
                status=_state_status(property_state),
                source_calculation=None,
                provenance_ids=(provenance_id,),
                frame_set_id=frame_set_id,
                validity_mask=_state_mask(property_state, ("frame",)),
            )
        )
    if state["cells"] is not None:
        mask = (
            None
            if state["cell_present"] is None
            else ArrayData(
                state["cell_present"],
                ("frame",),
                "dimensionless",
            )
        )
        datasets.append(
            CellFrameProperty(
                id=_stable_uuid(source_hash, f"group:{group_index}:cells"),
                revision=_revision(
                    source_hash,
                    f"group:{group_index}:cells",
                    {
                        "present": (
                            group.frame_count
                            if state["cell_present"] is None
                            else int(numpy.count_nonzero(state["cell_present"]))
                        )
                    },
                ),
                semantic_role="cell",
                domain="cell_frame",
                data=ArrayData(
                    state["cells"],
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
    if state["pbcs"] is not None:
        datasets.append(
            FrameProperty(
                id=_stable_uuid(source_hash, f"group:{group_index}:pbc"),
                revision=_revision(
                    source_hash,
                    f"group:{group_index}:pbc",
                    {"frames": group.frame_count},
                ),
                semantic_role="pbc",
                domain="frame",
                data=ArrayData(
                    state["pbcs"],
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


def _finalize_batch(states, source_hash, source, issues):
    finalized = [_finalize_group(state, source_hash) for state in states]
    structures = [item[0] for item in finalized]
    datasets = [
        dataset
        for _structure, group_datasets in finalized
        for dataset in group_datasets
    ]
    provenance_id = _stable_uuid(source_hash, "provenance")
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=_revision(source_hash, "provenance", {"format": "extxyz"}),
        producer="ChemBlender extXYZ reader",
        producer_version="1",
        source=str(Path(source).resolve()),
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


def _parse_snapshot(
    snapshot,
    owner,
    source_hash,
    source,
    is_cancelled,
    *,
    release_snapshot=False,
):
    issues = []
    groups = _plan_source(snapshot, is_cancelled, issues)
    if len(groups) > 1:
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                "frames.atomic_identity",
                "atom identity changed between frames; trajectory was split",
            )
        )
    states = [_prepare_group_state(group, owner, issues) for group in groups]
    _fill_states(snapshot, states, is_cancelled)
    if release_snapshot:
        owner.release_snapshot()
    return _finalize_batch(states, source_hash, source, issues)


def parse_extxyz(source, *, staging_root=None, is_cancelled=None):
    source = Path(source)
    is_cancelled = (lambda: False) if is_cancelled is None else is_cancelled
    if not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable")
    owner = _ArrayOwner(staging_root)
    try:
        snapshot = owner.snapshot(source, is_cancelled)
        return _parse_snapshot(
            snapshot,
            owner,
            _source_hash(snapshot, is_cancelled),
            source,
            is_cancelled,
            release_snapshot=True,
        )
    except BaseException as error:
        try:
            owner.cleanup()
        except BaseException as cleanup_error:
            error.add_note(
                "extXYZ staging cleanup failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
            for note in getattr(cleanup_error, "__notes__", ()):
                error.add_note(note)
        raise


def _properties_schema_state(text):
    assignment = _has_unquoted_reserved_assignment(text, 0)
    try:
        comment = parse_extxyz_comment(text)
    except ExtXYZSyntaxError:
        return assignment, False
    if not any(entry.key == "Properties" for entry in comment.entries):
        return False, False
    fields = {field.name: field for field in comment.properties}
    valid = (
        fields.get("species") == ExtXYZPropertyField("species", "S", 1)
        and fields.get("pos") == ExtXYZPropertyField("pos", "R", 3)
    )
    return True, valid


def has_extxyz_properties_assignment(text):
    return _properties_schema_state(text)[0]


def sniff_extxyz(source, prefix):
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 extXYZ text")
    if len(lines) < 2:
        return SniffResult(SniffMatch.NONE, "no extXYZ Properties marker")
    try:
        atom_count = int(lines[0].strip())
    except ValueError:
        return SniffResult(SniffMatch.NONE, "invalid extXYZ atom count")
    _assignment, valid = _properties_schema_state(lines[1])
    if atom_count <= 0 or not valid:
        return SniffResult(SniffMatch.NONE, "invalid extXYZ Properties marker")
    return SniffResult(SniffMatch.EXACT, "valid extXYZ Properties marker")


class _PreviewFallback(Exception):
    pass


def _preview_records(raw, is_cancelled):
    records = []
    position = 0
    expected_count = None
    expected_properties = None
    first_frame_end = None
    while position < len(raw):
        _check_cancelled(is_cancelled)
        if raw[position] in b"\r\n":
            if raw[position:].strip():
                raise _PreviewFallback
            break
        count_end = raw.find(b"\n", position)
        if count_end < 0:
            raise _PreviewFallback
        count_raw = raw[position:count_end].rstrip(b"\r")
        try:
            count = int(count_raw.decode("utf-8-sig").strip())
        except (UnicodeDecodeError, ValueError) as error:
            raise _PreviewFallback from error
        if count <= 0 or (
            expected_count is not None and count != expected_count
        ):
            raise _PreviewFallback
        expected_count = count
        newline = b"\r\n" if raw[count_end - 1 : count_end] == b"\r" else b"\n"
        comment_start = count_end + 1
        comment_end = raw.find(b"\n", comment_start)
        if comment_end < 0:
            raise _PreviewFallback
        try:
            comment = parse_extxyz_comment(
                raw[comment_start:comment_end].rstrip(b"\r").decode("utf-8")
            )
        except (UnicodeDecodeError, ExtXYZSyntaxError) as error:
            raise _PreviewFallback from error
        if expected_properties is None:
            expected_properties = comment.properties
        elif comment.properties != expected_properties:
            raise _PreviewFallback
        atom_start = comment_end + 1
        marker = newline + str(count).encode("ascii") + newline
        next_marker = raw.find(marker, atom_start)
        if next_marker < 0:
            next_position = len(raw)
            row_region = raw[atom_start:].rstrip(b"\r\n")
            row_lines = row_region.count(b"\n") + bool(row_region)
        else:
            next_position = next_marker + len(newline)
            row_region = raw[atom_start:next_position]
            row_lines = row_region.count(b"\n")
        if row_lines != count:
            raise _PreviewFallback
        if first_frame_end is None:
            first_frame_end = next_position
        cell, pbc = _cell_and_pbc(
            ExtXYZFrame(count, comment, comment.properties, ())
        )
        records.append((comment, cell, pbc))
        position = next_position
    if not records or first_frame_end is None:
        raise _PreviewFallback
    return expected_count, first_frame_end, tuple(records)


def _preview_categories(values):
    return list(dict.fromkeys(str(value) for value in numpy.asarray(values).flat))


def _preview_batch(raw, source_hash, source, is_cancelled):
    atom_count, first_frame_end, records = _preview_records(
        raw,
        is_cancelled,
    )
    try:
        first = next(
            iter_extxyz_frames(
                io.StringIO(raw[:first_frame_end].decode("utf-8-sig"))
            )
        )
    except (StopIteration, UnicodeDecodeError, ExtXYZSyntaxError) as error:
        raise _PreviewFallback from error
    if first.atom_count != atom_count:
        raise _PreviewFallback

    identity = _identity(first)
    first_cell, first_pbc = records[0][1:]
    group = _GroupPlan(
        0,
        0,
        0,
        identity,
        None if first_cell is None else first_cell.copy(),
        first_pbc,
        cell_missing=first_cell is None,
    )
    issues = []
    for frame_index, (comment, cell, pbc) in enumerate(records):
        frame = ExtXYZFrame(
            atom_count,
            comment,
            first.properties,
            first.values,
        )
        _accumulate_frame_plan(
            group,
            frame_index,
            frame,
            cell,
            pbc,
            issues,
        )

    state = _prepare_group_state(group, _PreviewArrayOwner(), issues)
    first_values = _value_map(first)
    coordinates = numpy.asarray(first_values["pos"], dtype=numpy.float64)
    state["coordinates"] = numpy.broadcast_to(
        coordinates,
        (group.frame_count, atom_count, 3),
    )
    state["comments"] = [record[0].raw for record in records]
    state["symbols"] = tuple(str(value) for value in first_values["species"])
    if state["cell_present"] is not None:
        state["cell_present"] = numpy.asarray(
            [cell is not None for _comment, cell, _pbc in records],
            dtype=numpy.bool_,
        )
    if state["cells"] is not None and first_cell is not None:
        state["cells"] = numpy.broadcast_to(
            first_cell,
            (group.frame_count, 3, 3),
        )
    if state["pbcs"] is not None:
        state["pbcs"] = numpy.broadcast_to(
            numpy.asarray(first_pbc, dtype=numpy.bool_),
            (group.frame_count, 3),
        )
    for name, property_state in state["atom"].items():
        if property_state["categorical"]:
            categories = _preview_categories(first_values[name])
            property_state["categories"] = categories
            property_state["category_index"] = {
                value: index for index, value in enumerate(categories)
            }
    for property_state in state["metadata"].values():
        if property_state["categorical"]:
            categories = _preview_categories(property_state["plan"].sample)
            property_state["categories"] = categories
            property_state["category_index"] = {
                value: index for index, value in enumerate(categories)
            }
    return _finalize_batch((state,), source_hash, source, issues)


def _preview_snapshot(request):
    _check_cancelled(request.is_cancelled)
    raw = request.source_path.read_bytes()
    _check_cancelled(request.is_cancelled)
    if sha256_bytes(raw) != request.source_content_hash:
        raise ExtXYZSyntaxError("extXYZ source changed before preview snapshot")
    destination = request.staging_root / _PREVIEW_SNAPSHOT_NAME
    temporary = short_sibling_temporary_path(destination)
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _check_cancelled(request.is_cancelled)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return raw, destination


def _mark_materialized(request):
    (request.staging_root / _MATERIALIZED_MARKER_NAME).write_text(
        f"{request.source_content_hash}\n",
        encoding="ascii",
        newline="\n",
    )


def _preview_request(request):
    if request.source_path.stat().st_size < _DEFERRED_PREVIEW_BYTES:
        batch = _parse_request(request)
        _mark_materialized(request)
        return batch
    raw, snapshot = _preview_snapshot(request)
    try:
        return _preview_batch(
            raw,
            request.source_content_hash,
            request.source_path,
            request.is_cancelled,
        )
    except _PreviewFallback:
        snapshot.unlink(missing_ok=True)
        batch = _parse_request(request)
        _mark_materialized(request)
        return batch
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _materialize_request(request):
    snapshot = request.staging_root / _PREVIEW_SNAPSHOT_NAME
    if not snapshot.is_file():
        marker = request.staging_root / _MATERIALIZED_MARKER_NAME
        if (
            marker.is_file()
            and marker.read_text(encoding="ascii")
            == f"{request.source_content_hash}\n"
        ):
            return None
        raise ExtXYZSyntaxError("extXYZ preview snapshot is missing")
    _check_cancelled(request.is_cancelled)
    if sha256_file(snapshot, request.is_cancelled) != request.source_content_hash:
        raise ExtXYZSyntaxError("extXYZ preview snapshot hash mismatch")
    owner = _ArrayOwner(request.staging_root)
    try:
        batch = _parse_snapshot(
            snapshot,
            owner,
            request.source_content_hash,
            request.source_path,
            request.is_cancelled,
        )
        return batch
    except BaseException as error:
        try:
            owner.cleanup()
        except BaseException as cleanup_error:
            error.add_note(
                "extXYZ materialization cleanup failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise


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
    preview_request=_preview_request,
    materialize_request=_materialize_request,
)


__all__ = (
    "EXTXYZ_READER",
    "ExtXYZCancelled",
    "ExtXYZComment",
    "ExtXYZFrame",
    "ExtXYZMetadataEntry",
    "ExtXYZPropertyField",
    "ExtXYZSyntaxError",
    "has_extxyz_properties_assignment",
    "iter_extxyz_frames",
    "parse_extxyz",
    "parse_extxyz_comment",
    "parse_properties_descriptor",
    "sniff_extxyz",
)
