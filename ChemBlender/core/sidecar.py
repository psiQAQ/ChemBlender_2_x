import base64
import hashlib
import json
import os
import re
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from . import model
from .model_registry import MODEL_ENUMS, model_type_from_tag, model_type_tag
from .sidecar_migrations import (
    CURRENT_MANIFEST_VERSION,
    CURRENT_PROJECT_SCHEMA_VERSION,
    migrate_manifest,
)


FORMAT_ID = "chemblender.cbq"
MANIFEST_VERSION = CURRENT_MANIFEST_VERSION
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UTC_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z"
)


def _numpy():
    import numpy

    return numpy


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON value: {value}")


def _canonical_json(document):
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest_hash(manifest):
    payload = {
        key: value
        for key, value in manifest.items()
        if key != "manifest_sha256"
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


class SidecarError(RuntimeError):
    pass


class SidecarNotFoundError(SidecarError):
    pass


class SidecarCompatibilityError(SidecarError):
    pass


class SidecarIntegrityError(SidecarError):
    pass


class LazyNpyArray:
    def __init__(self, path, shape, dtype, content_hash):
        self.path = Path(path)
        self.shape = tuple(shape)
        self.dtype = _numpy().dtype(dtype)
        self.content_hash = content_hash
        self._array = None

    @property
    def loaded(self):
        return self._array is not None

    def _load(self):
        if self._array is None:
            try:
                array = _numpy().load(self.path, mmap_mode="r", allow_pickle=False)
            except Exception as error:
                raise SidecarIntegrityError(
                    f"cannot open sidecar array: {self.path.name}"
                ) from error
            if tuple(array.shape) != self.shape or array.dtype != self.dtype:
                memory_map = getattr(array, "_mmap", None)
                if memory_map is not None:
                    memory_map.close()
                raise SidecarIntegrityError(
                    f"sidecar array metadata mismatch: {self.path.name}"
                )
            if _array_content_hash(array)[0] != self.content_hash:
                memory_map = getattr(array, "_mmap", None)
                if memory_map is not None:
                    memory_map.close()
                raise SidecarIntegrityError(
                    f"sidecar array content mismatch: {self.path.name}"
                )
            self._array = array
        return self._array

    def __array__(self, dtype=None, copy=None):
        array = _numpy().asarray(self._load(), dtype=dtype)
        if copy is True:
            return array.copy()
        return array

    def __getitem__(self, key):
        return self._load()[key]

    def __iter__(self):
        return iter(self._load())

    def __len__(self):
        return self.shape[0]

    def close(self):
        if self._array is not None:
            memory_map = getattr(self._array, "_mmap", None)
            if memory_map is not None:
                memory_map.close()
            self._array = None


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_content_hash(array):
    contiguous = _numpy().array(array, copy=True, order="C", subok=False)
    header = json.dumps(
        {"dtype": contiguous.dtype.str, "shape": contiguous.shape},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    digest = hashlib.sha256(header)
    digest.update(memoryview(contiguous).cast("B"))
    return digest.hexdigest(), contiguous


def _atomic_bytes(path, data):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class _Encoder:
    def __init__(self, root):
        self.root = Path(root)
        self.arrays = self.root / "arrays"

    def encode(self, value):
        if isinstance(value, Enum):
            for tag, enum_type in MODEL_ENUMS.items():
                if enum_type is type(value):
                    return {"$enum": tag, "value": self.encode(value.value)}
            raise SidecarIntegrityError(
                f"unsupported manifest value: {type(value).__name__}"
            )
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if isinstance(value, UUID):
            return {"$uuid": str(value)}
        if isinstance(value, bytes):
            return {"$bytes": base64.b64encode(value).decode("ascii")}
        if isinstance(value, tuple):
            return {"$tuple": [self.encode(item) for item in value]}
        if isinstance(value, list):
            return {"$list": [self.encode(item) for item in value]}
        if isinstance(value, dict):
            return {
                "$dict": [
                    [self.encode(key), self.encode(item)]
                    for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                ]
            }
        if type(value) is model.ArrayData:
            encoded = {"$type": "ArrayData"}
            encoded["values"] = self._array(value.values)
            encoded["dims"] = self.encode(value.dims)
            encoded["unit"] = value.unit
            return encoded
        if is_dataclass(value):
            try:
                type_name = model_type_tag(value)
            except TypeError as error:
                raise SidecarIntegrityError(
                    f"unsupported manifest value: {type(value).__name__}"
                ) from error
            encoded = {"$type": type_name}
            for item in fields(value):
                if item.init:
                    encoded[item.name] = self.encode(getattr(value, item.name))
            return encoded
        raise SidecarIntegrityError(
            f"unsupported manifest value: {type(value).__name__}"
        )

    def _array(self, values):
        array = _numpy().asarray(values)
        if array.dtype.hasobject:
            raise SidecarIntegrityError("object arrays are not supported")
        content_hash, contiguous = _array_content_hash(array)
        destination = self.arrays / f"{content_hash}.npy"
        reusable = False
        if destination.exists():
            existing = None
            try:
                existing = _numpy().load(
                    destination, mmap_mode="r", allow_pickle=False
                )
                reusable = _array_content_hash(existing)[0] == content_hash
            except Exception:
                reusable = False
            finally:
                memory_map = getattr(existing, "_mmap", None)
                if memory_map is not None:
                    memory_map.close()
        if not reusable:
            temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as stream:
                    _numpy().save(stream, contiguous, allow_pickle=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return {
            "$array": "npy",
            "path": f"arrays/{destination.name}",
            "content_sha256": content_hash,
            "file_sha256": _file_hash(destination),
            "shape": list(contiguous.shape),
            "dtype": contiguous.dtype.str,
        }


class _Decoder:
    def __init__(self, root, verify_arrays):
        self.root = Path(root).resolve()
        self.verify_arrays = verify_arrays

    def decode(self, value):
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if not isinstance(value, dict):
            raise SidecarIntegrityError("manifest values must use tagged objects")
        if "$uuid" in value:
            try:
                return UUID(value["$uuid"])
            except (TypeError, ValueError) as error:
                raise SidecarIntegrityError("invalid UUID in manifest") from error
        if "$enum" in value:
            try:
                enum_type = MODEL_ENUMS[value["$enum"]]
                return enum_type(self.decode(value["value"]))
            except (KeyError, TypeError, ValueError) as error:
                raise SidecarIntegrityError("invalid enum in manifest") from error
        if "$bytes" in value:
            try:
                return base64.b64decode(value["$bytes"], validate=True)
            except (TypeError, ValueError) as error:
                raise SidecarIntegrityError("invalid bytes in manifest") from error
        if "$tuple" in value:
            return tuple(self.decode(item) for item in value["$tuple"])
        if "$list" in value:
            return [self.decode(item) for item in value["$list"]]
        if "$dict" in value:
            try:
                return {
                    self.decode(key): self.decode(item) for key, item in value["$dict"]
                }
            except (TypeError, ValueError) as error:
                raise SidecarIntegrityError("invalid mapping in manifest") from error
        type_name = value.get("$type")
        if type_name == "ArrayData":
            return model.ArrayData(
                self._array(value.get("values")),
                self.decode(value.get("dims")),
                value.get("unit"),
            )
        try:
            class_type = model_type_from_tag(type_name)
        except (KeyError, TypeError) as error:
            raise SidecarIntegrityError(f"unknown model type: {type_name!r}") from error
        expected = {item.name for item in fields(class_type) if item.init}
        actual = set(value) - {"$type"}
        if actual != expected:
            raise SidecarIntegrityError(f"invalid fields for model type {type_name}")
        try:
            return class_type(**{name: self.decode(value[name]) for name in expected})
        except SidecarError:
            raise
        except Exception as error:
            raise SidecarIntegrityError(f"invalid {type_name} in manifest") from error

    def _array(self, descriptor):
        if not isinstance(descriptor, dict) or descriptor.get("$array") != "npy":
            raise SidecarIntegrityError("invalid array descriptor")
        relative = descriptor.get("path")
        pure = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            pure is None
            or pure.is_absolute()
            or ".." in pure.parts
            or len(pure.parts) != 2
            or pure.parts[0] != "arrays"
        ):
            raise SidecarIntegrityError("array path must stay inside the sidecar")
        path = self.root.joinpath(*pure.parts).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise SidecarIntegrityError(
                "array path must stay inside the sidecar"
            ) from error
        if not path.is_file():
            raise SidecarIntegrityError(f"missing sidecar array: {relative}")
        file_hash = descriptor.get("file_sha256")
        content_hash = descriptor.get("content_sha256")
        if not isinstance(file_hash, str) or not _SHA256.fullmatch(file_hash):
            raise SidecarIntegrityError("invalid array file hash")
        if not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash):
            raise SidecarIntegrityError("invalid array content hash")
        if pure.stem != content_hash:
            raise SidecarIntegrityError("array filename does not match content hash")
        if self.verify_arrays and _file_hash(path) != file_hash:
            raise SidecarIntegrityError(f"sidecar array checksum mismatch: {relative}")
        try:
            shape = tuple(int(size) for size in descriptor["shape"])
            dtype = _numpy().dtype(descriptor["dtype"])
        except (KeyError, TypeError, ValueError) as error:
            raise SidecarIntegrityError("invalid array metadata") from error
        if any(size < 0 for size in shape) or dtype.hasobject:
            raise SidecarIntegrityError("unsafe array metadata")
        return LazyNpyArray(path, shape, dtype, content_hash)


def save_project(root, project):
    root = Path(root)
    if root.suffix.lower() != ".cbq":
        raise ValueError("sidecar directory must use the .cbq suffix")
    return _write_project_tree(root, project)


def _write_project_tree(root, project):
    if not isinstance(project, model.QCProject):
        raise TypeError("project must be a QCProject")
    if project.schema_version not in ("0.1", CURRENT_PROJECT_SCHEMA_VERSION):
        raise SidecarCompatibilityError("unsupported project schema")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "arrays").mkdir(exist_ok=True)
    encoded = _Encoder(root).encode(project)
    encoded["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
    manifest = {
        "format": FORMAT_ID,
        "manifest_version": MANIFEST_VERSION,
        "generation_id": str(uuid4()),
        "created_at_utc": datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "project_id": str(project.id),
        "project_schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "project": encoded,
    }
    try:
        manifest["manifest_sha256"] = _manifest_hash(manifest)
        document = _canonical_json(manifest) + b"\n"
    except (TypeError, ValueError) as error:
        raise SidecarIntegrityError("manifest is not canonical JSON") from error
    _atomic_bytes(root / "manifest.json", document)
    return root


def open_project(
    root,
    *,
    expected_project_id=None,
    expected_schema_version=None,
    verify_arrays=True,
):
    project, _manifest = _open_project_with_manifest(
        root,
        expected_project_id=expected_project_id,
        expected_schema_version=expected_schema_version,
        verify_arrays=verify_arrays,
    )
    return project


def _open_project_with_manifest(
    root,
    *,
    expected_project_id=None,
    expected_schema_version=None,
    verify_arrays=True,
):
    root = Path(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise SidecarNotFoundError(f"sidecar manifest not found: {manifest_path}")
    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise SidecarIntegrityError("cannot read sidecar manifest") from error
    source_version = (
        manifest.get("manifest_version")
        if isinstance(manifest, dict)
        else None
    )
    manifest = migrate_manifest(manifest)
    if source_version == MANIFEST_VERSION:
        project_id, schema_version = _validate_current_manifest(manifest)
        if manifest["format"] != FORMAT_ID:
            raise SidecarCompatibilityError("unsupported sidecar format")
    else:
        if manifest.get("format") != FORMAT_ID:
            raise SidecarCompatibilityError("unsupported sidecar format")
        project_id = _strict_uuid(manifest.get("project_id"), "project_id")
        schema_version = manifest.get("project_schema_version")
    if expected_project_id is not None and project_id != expected_project_id:
        raise SidecarCompatibilityError("sidecar project UUID does not match")
    if (
        expected_schema_version is not None
        and expected_schema_version != schema_version
        and not (
            expected_schema_version == "0.1"
            and schema_version == CURRENT_PROJECT_SCHEMA_VERSION
        )
    ):
        raise SidecarCompatibilityError("sidecar project schema is incompatible")
    project = _Decoder(root, verify_arrays).decode(manifest.get("project"))
    if not isinstance(project, model.QCProject):
        raise SidecarIntegrityError("manifest project is not a QCProject")
    if project.id != project_id or project.schema_version != schema_version:
        raise SidecarIntegrityError("manifest header and project payload disagree")
    return project, manifest


def _strict_uuid(value, name):
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise SidecarIntegrityError(f"invalid {name} in manifest") from error
    if str(parsed) != value:
        raise SidecarIntegrityError(f"invalid {name} in manifest")
    return parsed


def _validate_current_manifest(manifest):
    expected_fields = {
        "format",
        "manifest_version",
        "generation_id",
        "created_at_utc",
        "manifest_sha256",
        "project_id",
        "project_schema_version",
        "project",
    }
    if set(manifest) != expected_fields:
        raise SidecarIntegrityError(
            "sidecar manifest has invalid top-level fields"
        )
    stored_hash = manifest.get("manifest_sha256")
    if (
        not isinstance(stored_hash, str)
        or not _SHA256.fullmatch(stored_hash)
        or stored_hash != _manifest_hash(manifest)
    ):
        raise SidecarIntegrityError("sidecar manifest hash mismatch")
    _strict_uuid(manifest.get("generation_id"), "generation_id")
    project_id = _strict_uuid(manifest.get("project_id"), "project_id")
    created_at = manifest.get("created_at_utc")
    if (
        not isinstance(created_at, str)
        or not _UTC_TIMESTAMP.fullmatch(created_at)
    ):
        raise SidecarIntegrityError("invalid created_at_utc in manifest")
    try:
        timestamp = datetime.fromisoformat(
            created_at.removesuffix("Z") + "+00:00"
        )
    except ValueError as error:
        raise SidecarIntegrityError(
            "invalid created_at_utc in manifest"
        ) from error
    if timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise SidecarIntegrityError("invalid created_at_utc in manifest")
    return _validate_current_project_header(manifest, project_id)


def _validate_current_project_header(manifest, project_id):
    schema_version = manifest.get("project_schema_version")
    project = manifest.get("project")
    encoded_id = project.get("id") if isinstance(project, dict) else None
    if (
        not isinstance(project, dict)
        or project.get("$type") != "QCProject"
        or not isinstance(encoded_id, dict)
        or set(encoded_id) != {"$uuid"}
        or not isinstance(schema_version, str)
        or not schema_version
        or not isinstance(project.get("schema_version"), str)
    ):
        raise SidecarIntegrityError(
            "manifest header and project payload disagree"
        )
    try:
        payload_id = _strict_uuid(
            encoded_id["$uuid"],
            "project payload id",
        )
    except SidecarIntegrityError as error:
        raise SidecarIntegrityError(
            "manifest header and project payload disagree"
        ) from error
    if (
        payload_id != project_id
        or project["schema_version"] != schema_version
    ):
        raise SidecarIntegrityError(
            "manifest header and project payload disagree"
        )
    if schema_version != CURRENT_PROJECT_SCHEMA_VERSION:
        raise SidecarCompatibilityError("unsupported sidecar manifest version")
    return project_id, schema_version


def close_project(project):
    """Release memory maps held by a project, notably before deleting it on Windows."""
    seen = set()

    def close(value):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        if isinstance(value, LazyNpyArray):
            value.close()
        elif isinstance(value, model.ArrayData):
            close(value.values)
        elif is_dataclass(value):
            for item in fields(value):
                close(getattr(value, item.name))
        elif isinstance(value, dict):
            for key, item in value.items():
                close(key)
                close(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                close(item)

    close(project)
