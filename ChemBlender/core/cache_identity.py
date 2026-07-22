import hashlib
import json
import math
import re
from enum import Enum
from uuid import UUID


_SHA256 = re.compile(r"[0-9a-f]{64}")


class CacheIdentityError(ValueError):
    pass


def source_hash_bytes(source):
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    return hashlib.sha256(source).hexdigest()


def _canonical(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CacheIdentityError("cache identity values must be finite")
        return value
    if isinstance(value, UUID):
        return {"uuid": str(value)}
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": _canonical(value.value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CacheIdentityError("cache identity mapping keys must be strings")
        return {key: _canonical(value[key]) for key in sorted(value)}
    raise CacheIdentityError(
        f"unsupported cache identity value: {type(value).__name__}"
    )


def _digest(layer, payload):
    document = {"layer": layer, "payload": _canonical(payload)}
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_hash(value, name):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise CacheIdentityError(f"{name} must be SHA-256 hex")


def parser_cache_key(source_hash, reader_id, reader_version, options):
    _require_hash(source_hash, "source_hash")
    return _digest(
        "parser",
        {
            "source_hash": source_hash,
            "reader_id": reader_id,
            "reader_version": reader_version,
            "options": options,
        },
    )


def derivation_cache_key(inputs, operation_id, operation_version, parameters):
    normalized_inputs = []
    for entity_id, revision in inputs:
        if not isinstance(entity_id, UUID) or not isinstance(revision, str) or not revision:
            raise CacheIdentityError("derivation inputs require UUID and revision")
        normalized_inputs.append((entity_id, revision))
    return _digest(
        "derivation",
        {
            "inputs": normalized_inputs,
            "operation_id": operation_id,
            "operation_version": operation_version,
            "parameters": parameters,
        },
    )


def render_cache_key(
    entity_id,
    entity_revision,
    derivation_hash,
    adapter_id,
    adapter_version,
    geometry_settings,
):
    if not isinstance(entity_id, UUID):
        raise CacheIdentityError("entity_id must be a UUID")
    if not isinstance(entity_revision, str) or not entity_revision:
        raise CacheIdentityError("entity_revision must be non-empty")
    _require_hash(derivation_hash, "derivation_hash")
    return _digest(
        "render",
        {
            "entity": (entity_id, entity_revision),
            "derivation_hash": derivation_hash,
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "geometry_settings": geometry_settings,
        },
    )
