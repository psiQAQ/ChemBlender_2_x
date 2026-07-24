import base64
import hashlib
import json
import math
import os
import re
from dataclasses import fields
from enum import Enum
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from . import public_model as _model


__all__ = (
    "CanonicalDocumentError",
    "CanonicalDocumentCompatibilityError",
    "CanonicalDocumentIntegrityError",
    "public_batch_document",
    "public_batch_from_document",
    "write_public_batch_bundle",
    "read_public_batch_bundle",
)


_FORMAT = "chemblender.reader-import"
_SCHEMA_VERSION = "0.1"
_DOCUMENT_NAME = "import-batch.json"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TYPE_NAMES = (
    "PublicImportBatch",
    "ArrayData",
    "SourceRecord",
    "SourceRevision",
    "CIFEnvelope",
    "QCSchemaEnvelope",
    "CJSONEnvelope",
    "PeriodicSiteData",
    "MolecularTopology",
    "Structure",
    "SymmetryResult",
    "CalculationMetadata",
    "CalculationRecord",
    "PropertyDataset",
    "AtomicProperty",
    "FrameSet",
    "Grid3D",
    "VibrationalModeSet",
    "ExcitationContribution",
    "ExcitedStateReferences",
    "ExcitedStateSet",
    "Spectrum",
    "BandPathBranch",
    "BandStructure",
    "DensityOfStates",
    "PhononModeSet",
    "SurfaceProperty",
    "FermiSurfaceMesh",
    "TopologyConnection",
    "TopologyPath",
    "TopologyGraph",
    "BasisShell",
    "BasisConvention",
    "BasisSet",
    "OrbitalChannel",
    "OrbitalSet",
    "DensityMatrix",
    "ProvenanceRecord",
    "ParserIssue",
    "ParserReport",
    "DiagnosticValue",
    "ImportDiagnostic",
)
_ENUM_NAMES = (
    "CalculationStatus",
    "DatasetStatus",
    "IssueKind",
    "BasisFunctionKind",
    "OrbitalKind",
    "DensityMatrixLevel",
    "DensityMatrixSpin",
    "SpectrumKind",
    "SpectrumProfile",
    "SpinChannel",
    "EnergyReference",
    "CriticalPointKind",
    "QualityStatus",
    "DiagnosticSeverity",
)
_MODEL_TYPES = {name: getattr(_model, name) for name in _TYPE_NAMES}
_MODEL_ENUMS = {name: getattr(_model, name) for name in _ENUM_NAMES}
_TYPE_TAGS = {value: name for name, value in _MODEL_TYPES.items()}
_ENUM_TAGS = {value: name for name, value in _MODEL_ENUMS.items()}
_VALUE_TAGS = {
    "$uuid",
    "$enum",
    "$bytes",
    "$tuple",
    "$list",
    "$dict",
    "$type",
    "$array",
}


class CanonicalDocumentError(RuntimeError):
    pass


class CanonicalDocumentCompatibilityError(CanonicalDocumentError):
    pass


class CanonicalDocumentIntegrityError(CanonicalDocumentError):
    pass


def _numpy():
    import numpy

    return numpy


def _canonical_json(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CanonicalDocumentIntegrityError(
            "document contains a non-canonical JSON value"
        ) from error


def _file_hash(path):
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError as error:
        raise CanonicalDocumentIntegrityError(
            "cannot hash canonical artifact"
        ) from error


def _remove_temporary(path):
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise CanonicalDocumentIntegrityError(
            "cannot clean canonical temporary file"
        ) from error


def _array_content_hash(value):
    array = _numpy().array(value, copy=True, order="C", subok=False)
    if array.dtype.hasobject:
        raise CanonicalDocumentIntegrityError("object arrays are not supported")
    if array.dtype.fields is not None or array.dtype.subdtype is not None:
        raise CanonicalDocumentIntegrityError(
            "structured or subarray dtype is not supported"
        )
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": array.shape},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256(header)
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest(), array


def _safe_artifacts(root, *, create):
    root = Path(root)
    try:
        if create:
            root.mkdir(parents=True, exist_ok=True)
        resolved_root = root.resolve()
        artifacts = root / "artifacts"
        if create:
            artifacts.mkdir(exist_ok=True)
        resolved_artifacts = artifacts.resolve()
        resolved_artifacts.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise CanonicalDocumentIntegrityError(
            "artifact directory must stay inside the bundle"
        ) from error
    if not resolved_artifacts.is_dir():
        raise CanonicalDocumentIntegrityError("artifact directory is missing")
    return resolved_root, resolved_artifacts


class _Encoder:
    def __init__(self, root):
        self.root, self.artifacts = _safe_artifacts(root, create=True)

    def encode(self, value):
        value_type = type(value)
        if isinstance(value, Enum):
            tag = _ENUM_TAGS.get(value_type)
            if tag is None:
                raise CanonicalDocumentCompatibilityError(
                    f"unregistered enum type: {value_type.__name__}"
                )
            return {"$enum": tag, "value": self.encode(value.value)}
        if value is None or value_type in (str, bool, int):
            return value
        if value_type is float:
            if not math.isfinite(value):
                raise CanonicalDocumentIntegrityError(
                    "non-finite values are not supported"
                )
            return value
        if value_type is UUID:
            return {"$uuid": str(value)}
        if value_type is bytes:
            return {"$bytes": base64.b64encode(value).decode("ascii")}
        if value_type is tuple:
            return {"$tuple": [self.encode(item) for item in value]}
        if value_type is list:
            return {"$list": [self.encode(item) for item in value]}
        if value_type is dict:
            pairs = [
                [self.encode(key), self.encode(item)]
                for key, item in value.items()
            ]
            pairs.sort(key=lambda pair: _canonical_json(pair[0]))
            return {"$dict": pairs}
        if value_type is _model.ArrayData:
            return {
                "$type": "ArrayData",
                "values": self.array(value.values),
                "dims": self.encode(value.dims),
                "unit": value.unit,
            }
        tag = _TYPE_TAGS.get(value_type)
        if tag is None:
            raise CanonicalDocumentCompatibilityError(
                f"unregistered public model type: {value_type.__name__}"
            )
        encoded = {"$type": tag}
        for item in fields(value):
            if item.init:
                encoded[item.name] = self.encode(getattr(value, item.name))
        return encoded

    def array(self, value):
        content_hash, array = _array_content_hash(value)
        destination = self.artifacts / f"{content_hash}.npy"
        try:
            destination.resolve().relative_to(self.root)
        except ValueError as error:
            raise CanonicalDocumentIntegrityError(
                "artifact path must stay inside the bundle"
            ) from error
        temporary = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp"
        )
        write_error = None
        try:
            with temporary.open("xb") as stream:
                _numpy().save(stream, array, allow_pickle=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except OSError as error:
            write_error = error
        finally:
            try:
                _remove_temporary(temporary)
            except CanonicalDocumentIntegrityError:
                if write_error is None:
                    raise
        if write_error is not None:
            raise CanonicalDocumentIntegrityError(
                "cannot write array artifact"
            ) from write_error
        return {
            "$array": "npy",
            "path": f"artifacts/{destination.name}",
            "content_sha256": content_hash,
            "file_sha256": _file_hash(destination),
            "shape": list(array.shape),
            "dtype": array.dtype.str,
        }


def _reject_constant(value):
    raise CanonicalDocumentIntegrityError(f"non-finite JSON value: {value}")


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CanonicalDocumentIntegrityError(
                f"duplicate JSON object field: {key}"
            )
        value[key] = item
    return value


class _Decoder:
    def __init__(self, root):
        self.root, self.artifacts = _safe_artifacts(root, create=False)

    def decode(self, value):
        value_type = type(value)
        if value is None or value_type in (str, bool, int):
            return value
        if value_type is float:
            if not math.isfinite(value):
                raise CanonicalDocumentIntegrityError(
                    "non-finite values are not supported"
                )
            return value
        if value_type is not dict:
            raise CanonicalDocumentIntegrityError(
                "canonical values must use tagged objects"
            )
        tags = set(value).intersection(_VALUE_TAGS)
        if len(tags) > 1:
            raise CanonicalDocumentIntegrityError(
                "canonical object has multiple tags"
            )
        if not tags:
            if any(isinstance(key, str) and key.startswith("$") for key in value):
                raise CanonicalDocumentCompatibilityError(
                    "unknown canonical value tag"
                )
            raise CanonicalDocumentCompatibilityError(
                "canonical object is missing a registered type tag"
            )
        tag = next(iter(tags))
        if tag == "$uuid":
            self._exact_fields(value, {"$uuid"}, "UUID")
            try:
                return UUID(value["$uuid"])
            except (TypeError, ValueError) as error:
                raise CanonicalDocumentIntegrityError("invalid UUID") from error
        if tag == "$enum":
            self._exact_fields(value, {"$enum", "value"}, "enum")
            enum_name = value["$enum"]
            enum_type = (
                _MODEL_ENUMS.get(enum_name)
                if type(enum_name) is str
                else None
            )
            if enum_type is None:
                raise CanonicalDocumentCompatibilityError(
                    f"unknown public enum type: {enum_name!r}"
                )
            try:
                return enum_type(self.decode(value["value"]))
            except (TypeError, ValueError) as error:
                raise CanonicalDocumentIntegrityError(
                    f"invalid {enum_name} value"
                ) from error
        if tag == "$bytes":
            self._exact_fields(value, {"$bytes"}, "bytes")
            try:
                return base64.b64decode(value["$bytes"], validate=True)
            except (TypeError, ValueError) as error:
                raise CanonicalDocumentIntegrityError("invalid bytes") from error
        if tag == "$tuple":
            self._sequence_tag(value, "$tuple")
            return tuple(self.decode(item) for item in value["$tuple"])
        if tag == "$list":
            self._sequence_tag(value, "$list")
            return [self.decode(item) for item in value["$list"]]
        if tag == "$dict":
            self._exact_fields(value, {"$dict"}, "mapping")
            if type(value["$dict"]) is not list:
                raise CanonicalDocumentIntegrityError(
                    "mapping payload must be a list"
                )
            decoded = {}
            try:
                for pair in value["$dict"]:
                    if type(pair) is not list or len(pair) != 2:
                        raise CanonicalDocumentIntegrityError(
                            "mapping entries must be key-value pairs"
                        )
                    key = self.decode(pair[0])
                    if key in decoded:
                        raise CanonicalDocumentIntegrityError(
                            "duplicate mapping key"
                        )
                    decoded[key] = self.decode(pair[1])
            except TypeError as error:
                raise CanonicalDocumentIntegrityError(
                    "mapping keys must be hashable"
                ) from error
            return decoded
        if tag == "$array":
            return self.array(value)
        return self.model(value)

    @staticmethod
    def _exact_fields(value, expected, name):
        if set(value) != expected:
            raise CanonicalDocumentIntegrityError(
                f"invalid fields for {name}"
            )

    def _sequence_tag(self, value, tag):
        self._exact_fields(value, {tag}, tag[1:])
        if type(value[tag]) is not list:
            raise CanonicalDocumentIntegrityError(
                f"{tag[1:]} payload must be a list"
            )

    def model(self, value):
        type_name = value.get("$type")
        class_type = (
            _MODEL_TYPES.get(type_name)
            if type(type_name) is str
            else None
        )
        if class_type is None:
            raise CanonicalDocumentCompatibilityError(
                f"unknown public model type: {type_name!r}"
            )
        expected = {"$type"} | {
            item.name for item in fields(class_type) if item.init
        }
        self._exact_fields(value, expected, type_name)
        try:
            decoded = {
                name: self.decode(value[name])
                for name in expected
                if name != "$type"
            }
            if class_type is _model.DiagnosticValue:
                return class_type._from_canonical(decoded["value"])
            return class_type(**decoded)
        except CanonicalDocumentError:
            raise
        except Exception as error:
            raise CanonicalDocumentIntegrityError(
                f"invalid {type_name}"
            ) from error

    def array(self, descriptor):
        expected = {
            "$array",
            "path",
            "content_sha256",
            "file_sha256",
            "shape",
            "dtype",
        }
        self._exact_fields(descriptor, expected, "array descriptor")
        if descriptor["$array"] != "npy":
            raise CanonicalDocumentCompatibilityError(
                "unsupported array artifact type"
            )
        relative = descriptor["path"]
        pure = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            pure is None
            or pure.is_absolute()
            or ".." in pure.parts
            or len(pure.parts) != 2
            or pure.parts[0] != "artifacts"
        ):
            raise CanonicalDocumentIntegrityError(
                "array path must stay inside artifacts"
            )
        file_hash = descriptor["file_sha256"]
        content_hash = descriptor["content_sha256"]
        if not isinstance(file_hash, str) or not _SHA256.fullmatch(file_hash):
            raise CanonicalDocumentIntegrityError("invalid array file hash")
        if (
            not isinstance(content_hash, str)
            or not _SHA256.fullmatch(content_hash)
        ):
            raise CanonicalDocumentIntegrityError("invalid array content hash")
        if pure.name != f"{content_hash}.npy":
            raise CanonicalDocumentIntegrityError(
                "array filename must match content hash"
            )
        path = self.root.joinpath(*pure.parts).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise CanonicalDocumentIntegrityError(
                "array path must stay inside the bundle"
            ) from error
        if not path.is_file():
            raise CanonicalDocumentIntegrityError(
                f"missing array artifact: {relative}"
            )
        if _file_hash(path) != file_hash:
            raise CanonicalDocumentIntegrityError(
                f"array file hash mismatch: {relative}"
            )
        shape = descriptor["shape"]
        if type(shape) is not list or any(
            type(size) is not int or size < 0 for size in shape
        ):
            raise CanonicalDocumentIntegrityError("invalid array shape")
        try:
            if type(descriptor["dtype"]) is not str:
                raise TypeError
            dtype = _numpy().dtype(descriptor["dtype"])
        except (TypeError, ValueError) as error:
            raise CanonicalDocumentIntegrityError("invalid array dtype") from error
        if dtype.hasobject:
            raise CanonicalDocumentIntegrityError("object arrays are not supported")
        if dtype.fields is not None or dtype.subdtype is not None:
            raise CanonicalDocumentIntegrityError(
                "structured or subarray dtype is not supported"
            )
        try:
            array = _numpy().load(path, allow_pickle=False)
        except Exception as error:
            raise CanonicalDocumentIntegrityError(
                f"cannot load array artifact: {relative}"
            ) from error
        if (
            type(array) is not _numpy().ndarray
            or tuple(array.shape) != tuple(shape)
            or array.dtype != dtype
        ):
            raise CanonicalDocumentIntegrityError(
                f"array metadata mismatch: {relative}"
            )
        if array.dtype.hasobject or _array_content_hash(array)[0] != content_hash:
            raise CanonicalDocumentIntegrityError(
                f"array content hash mismatch: {relative}"
            )
        return array


def public_batch_document(batch, bundle_root):
    if type(batch) is not _model.PublicImportBatch:
        raise CanonicalDocumentIntegrityError(
            "batch must be an exact PublicImportBatch"
        )
    try:
        document = {
            "format": _FORMAT,
            "schema_version": _SCHEMA_VERSION,
            "batch": _Encoder(bundle_root).encode(batch),
        }
        return _canonical_json(document)
    except RecursionError as error:
        raise CanonicalDocumentIntegrityError(
            "document nesting exceeds the recursion limit"
        ) from error


def public_batch_from_document(document, bundle_root):
    if type(document) is not bytes:
        raise CanonicalDocumentIntegrityError("document must be UTF-8 bytes")
    try:
        parsed = json.loads(
            document.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_strict_object,
        )
    except CanonicalDocumentError:
        raise
    except RecursionError as error:
        raise CanonicalDocumentIntegrityError(
            "document nesting exceeds the recursion limit"
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalDocumentIntegrityError(
            "document must be valid UTF-8 JSON"
        ) from error
    if type(parsed) is not dict or set(parsed) != {
        "format",
        "schema_version",
        "batch",
    }:
        raise CanonicalDocumentCompatibilityError(
            "document must contain exactly format, schema_version and batch"
        )
    if parsed["format"] != _FORMAT:
        raise CanonicalDocumentCompatibilityError(
            "unsupported canonical document format"
        )
    if parsed["schema_version"] != _SCHEMA_VERSION:
        raise CanonicalDocumentCompatibilityError(
            "unsupported canonical document schema"
        )
    try:
        batch = _Decoder(bundle_root).decode(parsed["batch"])
    except RecursionError as error:
        raise CanonicalDocumentIntegrityError(
            "document nesting exceeds the recursion limit"
        ) from error
    if type(batch) is not _model.PublicImportBatch:
        raise CanonicalDocumentCompatibilityError(
            "document batch must be a PublicImportBatch"
        )
    return batch


def write_public_batch_bundle(root, batch):
    root = Path(root)
    document = public_batch_document(batch, root)
    destination = root / _DOCUMENT_NAME
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    write_error = None
    try:
        with temporary.open("xb") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        write_error = error
    finally:
        try:
            _remove_temporary(temporary)
        except CanonicalDocumentIntegrityError:
            if write_error is None:
                raise
    if write_error is not None:
        raise CanonicalDocumentIntegrityError(
            "cannot write canonical document"
        ) from write_error
    return destination


def read_public_batch_bundle(root):
    root = Path(root)
    try:
        resolved_root = root.resolve()
        document_path = (root / _DOCUMENT_NAME).resolve()
        document_path.relative_to(resolved_root)
        document = document_path.read_bytes()
    except (OSError, ValueError) as error:
        raise CanonicalDocumentIntegrityError(
            "cannot read canonical document"
        ) from error
    return public_batch_from_document(document, resolved_root)
