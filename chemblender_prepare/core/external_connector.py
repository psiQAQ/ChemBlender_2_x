"""Provider-neutral contracts for optional external record connectors."""

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
_AUTH_REF = re.compile(r"env:[A-Z][A-Z0-9_]*")


class ExternalConnectorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalConnectorDescriptor:
    provider: str
    version: str
    locator_fields: tuple[str, ...]
    capabilities: tuple[str, ...]
    authentication_reference: str | None
    envelope_types: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.provider, str) or not _TOKEN.fullmatch(self.provider):
            raise ExternalConnectorError("provider must be a lower token")
        if not isinstance(self.version, str) or not self.version:
            raise ExternalConnectorError("connector version must be non-empty")
        for values, name in (
            (self.locator_fields, "locator fields"),
            (self.capabilities, "capabilities"),
            (self.envelope_types, "envelope types"),
        ):
            values = tuple(values)
            if not values or any(not isinstance(value, str) or not _TOKEN.fullmatch(value) for value in values):
                raise ExternalConnectorError(f"{name} must contain lower tokens")
            if len(set(values)) != len(values):
                raise ExternalConnectorError(f"{name} must not contain duplicates")
            object.__setattr__(self, name.replace(" ", "_"), values)
        if self.authentication_reference is not None and not _AUTH_REF.fullmatch(
            self.authentication_reference
        ):
            raise ExternalConnectorError("authentication reference must name an environment variable")


def builtin_external_connectors():
    values = (
        ExternalConnectorDescriptor(
            "qcarchive", "1", ("server_url", "record_id"),
            ("record", "qcschema_result"),
            "env:CHEMBLENDER_QCARCHIVE_TOKEN", ("qcschema",),
        ),
        ExternalConnectorDescriptor(
            "aiida", "1", ("profile", "node_uuid"),
            ("record", "provenance"), None, ("qcschema", "cjson"),
        ),
        ExternalConnectorDescriptor(
            "nomad", "1", ("base_url", "entry_id"),
            ("record", "archive"),
            "env:CHEMBLENDER_NOMAD_TOKEN", ("qcschema", "cjson"),
        ),
    )
    return {value.provider: value for value in values}


def _safe_url(value, name):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ExternalConnectorError(f"{name} must be an HTTP URL without credentials or query")


@dataclass(frozen=True, slots=True)
class ExternalRecordRequest:
    provider: str
    connector_version: str
    locator: tuple[tuple[str, str], ...]
    envelope_type: str
    authentication_ref: str | None

    def __post_init__(self):
        try:
            descriptor = builtin_external_connectors()[self.provider]
        except (KeyError, TypeError) as error:
            raise ExternalConnectorError("unsupported external record provider") from error
        if self.connector_version != descriptor.version:
            raise ExternalConnectorError("unsupported connector version")
        try:
            locator = dict(self.locator)
        except (TypeError, ValueError) as error:
            raise ExternalConnectorError("locator must contain name/value pairs") from error
        if len(locator) != len(tuple(self.locator)) or set(locator) != set(descriptor.locator_fields):
            raise ExternalConnectorError("locator fields do not match connector descriptor")
        for name, value in locator.items():
            if not isinstance(value, str) or not value:
                raise ExternalConnectorError("locator values must be non-empty strings")
            if any(token in name for token in ("token", "password", "secret", "credential")):
                raise ExternalConnectorError("locator must not contain credentials")
            if name.endswith("url"):
                _safe_url(value, name)
        if self.envelope_type not in descriptor.envelope_types:
            raise ExternalConnectorError("connector does not support the requested envelope")
        if self.authentication_ref is not None and not _AUTH_REF.fullmatch(
            self.authentication_ref
        ):
            raise ExternalConnectorError("authentication_ref must be an env reference")
        object.__setattr__(
            self,
            "locator",
            tuple((name, locator[name]) for name in descriptor.locator_fields),
        )


def external_record_request_document(request):
    if not isinstance(request, ExternalRecordRequest):
        raise TypeError("request must be an ExternalRecordRequest")
    return {
        "schema_name": "chemblender_external_record_request",
        "schema_version": 1,
        "provider": request.provider,
        "connector_version": request.connector_version,
        "locator": dict(request.locator),
        "envelope_type": request.envelope_type,
        "authentication_ref": request.authentication_ref,
    }


def external_record_request_from_document(document):
    fields = {
        "schema_name", "schema_version", "provider", "connector_version",
        "locator", "envelope_type", "authentication_ref",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise ExternalConnectorError("invalid external record request fields")
    if document["schema_name"] != "chemblender_external_record_request" or document["schema_version"] != 1:
        raise ExternalConnectorError("unsupported external record request schema")
    if not isinstance(document["locator"], dict):
        raise ExternalConnectorError("locator must be an object")
    return ExternalRecordRequest(
        document["provider"], document["connector_version"],
        tuple(document["locator"].items()), document["envelope_type"],
        document["authentication_ref"],
    )


def external_record_source_uri(request):
    if not isinstance(request, ExternalRecordRequest):
        raise TypeError("request must be an ExternalRecordRequest")
    locator = dict(request.locator)
    identity_field = {
        "qcarchive": ("record", "record_id"),
        "aiida": ("node", "node_uuid"),
        "nomad": ("entry", "entry_id"),
    }[request.provider]
    identity = (identity_field[0], locator[identity_field[1]])
    return f"{request.provider}://{identity[0]}/{quote(identity[1], safe='')}"
