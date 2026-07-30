"""Route legacy import controls through the shared import request model."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from ..core.import_pipeline import ImportRequest, ImportSource, ValidationMode
from ..core.session import ProjectSession


_PUBCHEM_ROOT = "legacy-pubchem"
_PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/SDF"
_PUBCHEM_LOOKUP_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/cids/JSON"
_PUBCHEM_SOURCE_PATTERN = re.compile(
    r"^pubchem-([1-9][0-9]*)-([0-9a-f]{32})\.sdf$"
)
_SESSION_OWNER_MARKER = ".chemblender-session-owner"


@dataclass(frozen=True, slots=True)
class LegacyRouteDiagnostic:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PubChemImportStage:
    request: ImportRequest | None
    source_url: str | None
    content_hash: str | None
    owner_id: UUID
    diagnostics: tuple[LegacyRouteDiagnostic, ...]
    metadata_path: Path | None


def file_import_request(path, validation_mode):
    return ImportRequest(
        sources=(ImportSource(Path(path)),),
        validation_mode=validation_mode,
    )


def smiles_import_request(text, validation_mode):
    return ImportRequest(
        sources=(ImportSource.smiles_text(text),),
        validation_mode=validation_mode,
    )


def _response_bytes(response):
    if getattr(response, "status_code", None) != 200:
        raise OSError(f"PubChem returned HTTP {getattr(response, 'status_code', 'unknown')}")
    content = getattr(response, "content", None)
    if not isinstance(content, bytes) or not content:
        raise OSError("PubChem returned an empty SDF response")
    return content


def _resolve_cid(query, fetch):
    query = query.strip()
    if query.isdigit():
        return _canonical_cid(query)
    response = fetch(
        _PUBCHEM_LOOKUP_URL.format(name=quote(query, safe="")),
        timeout=30,
    )
    if getattr(response, "status_code", None) != 200:
        raise OSError(f"PubChem returned HTTP {getattr(response, 'status_code', 'unknown')}")
    try:
        document = response.json()
        return _canonical_cid(str(document["IdentifierList"]["CID"][0]))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
        raise OSError(f"PubChem could not resolve {query!r}") from error


def _canonical_cid(value):
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("PubChem CID must be a positive integer")
    return str(int(value))


def _is_link_like(path):
    return path.is_symlink() or path.is_junction()


def _untrusted_pubchem_source(reason):
    raise ValueError(f"legacy.pubchem_untrusted: {reason}")


def _owned_session_root(session):
    root = Path(session.temporary_root)
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        _untrusted_pubchem_source("session root is unavailable")
    if _is_link_like(root) or resolved != session._owned_temporary_root:
        _untrusted_pubchem_source("session root is not owned by this session")
    marker = resolved / _SESSION_OWNER_MARKER
    try:
        marker_value = marker.read_bytes()
    except OSError as error:
        _untrusted_pubchem_source("session ownership marker is unavailable")
    if _is_link_like(marker) or marker_value != f"{session.id}\n".encode("utf-8"):
        _untrusted_pubchem_source("session ownership marker does not match")
    return resolved


def _owned_pubchem_root(session, *, create=False):
    session_root = _owned_session_root(session)
    root = session_root / _PUBCHEM_ROOT
    if create:
        root.mkdir(exist_ok=True)
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        _untrusted_pubchem_source("staging root is unavailable")
    if (
        _is_link_like(root)
        or not resolved.is_dir()
        or resolved.parent != session_root
    ):
        _untrusted_pubchem_source("staging root is not owned by this session")
    return resolved


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_pubchem_parameters(path, session):
    """Return PubChem provenance only after validating session-owned staging."""
    if type(session) is not ProjectSession:
        raise TypeError("session must be a ProjectSession")
    source = Path(path)
    if _is_link_like(source):
        _untrusted_pubchem_source("source file is linked")
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        _untrusted_pubchem_source("source file is unavailable")
    root_candidate = Path(session.temporary_root) / _PUBCHEM_ROOT
    try:
        candidate_root = root_candidate.resolve(strict=True)
    except OSError:
        return None
    if source.parent != candidate_root:
        return None
    root = _owned_pubchem_root(session)
    if not source.is_file():
        _untrusted_pubchem_source("source file is unavailable")
    match = _PUBCHEM_SOURCE_PATTERN.fullmatch(source.name)
    if match is None:
        _untrusted_pubchem_source("source name is not a staged PubChem CID file")
    cid, token = match.groups()
    metadata_path = root / f"pubchem-{cid}-{token}.json"
    if _is_link_like(metadata_path):
        _untrusted_pubchem_source("metadata file is linked")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _untrusted_pubchem_source("metadata cannot be read")
    if type(metadata) is not dict or set(metadata) != {
        "content_hash",
        "owner_session_id",
        "source_url",
    }:
        _untrusted_pubchem_source("metadata has an invalid schema")
    expected_url = _PUBCHEM_URL.format(cid=cid)
    declared_hash = metadata["content_hash"]
    if (
        metadata["owner_session_id"] != str(session.id)
        or metadata["source_url"] != expected_url
        or type(declared_hash) is not str
        or re.fullmatch(r"[0-9a-f]{64}", declared_hash) is None
    ):
        _untrusted_pubchem_source("metadata does not match the PubChem source")
    if _hash_file(source) != declared_hash:
        _untrusted_pubchem_source("source content hash does not match metadata")
    return {
        "legacy_source_url": expected_url,
        "legacy_source_sha256": declared_hash,
    }


def stage_pubchem_import(
    query,
    session,
    *,
    validation_mode=ValidationMode.BALANCED,
    fetch=None,
):
    if type(session) is not ProjectSession:
        raise TypeError("session must be a ProjectSession")
    if type(query) is not str or not query.strip():
        raise ValueError("PubChem query must be non-empty text")
    if type(validation_mode) is not ValidationMode:
        raise TypeError("validation_mode must be a ValidationMode")
    if fetch is None:
        import requests

        fetch = requests.get
    if not callable(fetch):
        raise TypeError("fetch must be callable")
    try:
        cid = _resolve_cid(query, fetch)
        source_url = _PUBCHEM_URL.format(cid=cid)
        payload = _response_bytes(fetch(source_url, timeout=30))
    except (KeyboardInterrupt, SystemExit, MemoryError):
        raise
    except (OSError, ValueError) as error:
        return PubChemImportStage(
            request=None,
            source_url=None,
            content_hash=None,
            owner_id=session.id,
            diagnostics=(
                LegacyRouteDiagnostic("legacy.pubchem_network", str(error)),
            ),
            metadata_path=None,
        )

    root = _owned_pubchem_root(session, create=True)
    token = uuid4().hex
    source_path = root / f"pubchem-{cid}-{token}.sdf"
    content_hash = hashlib.sha256(payload).hexdigest()
    metadata_path = root / f"pubchem-{cid}-{token}.json"
    with source_path.open("xb") as stream:
        stream.write(payload)
    document = {
        "content_hash": content_hash,
        "owner_session_id": str(session.id),
        "source_url": source_url,
    }
    try:
        with metadata_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
    except BaseException:
        source_path.unlink(missing_ok=True)
        raise
    request = file_import_request(source_path, validation_mode)
    return PubChemImportStage(
        request=request,
        source_url=source_url,
        content_hash=content_hash,
        owner_id=session.id,
        diagnostics=(),
        metadata_path=metadata_path,
    )
