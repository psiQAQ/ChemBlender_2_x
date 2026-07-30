"""Route legacy import controls through the shared import request model."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from ..core.import_pipeline import ImportRequest, ImportSource, ValidationMode
from ..core.session import ProjectSession


_PUBCHEM_ROOT = "legacy-pubchem"
_PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/SDF"
_PUBCHEM_LOOKUP_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/cids/JSON"


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
    canonical_parameters: dict[UUID, dict[str, str]]
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
        return query
    response = fetch(
        _PUBCHEM_LOOKUP_URL.format(name=quote(query, safe="")),
        timeout=30,
    )
    if getattr(response, "status_code", None) != 200:
        raise OSError(f"PubChem returned HTTP {getattr(response, 'status_code', 'unknown')}")
    try:
        document = response.json()
        return str(document["IdentifierList"]["CID"][0])
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
        raise OSError(f"PubChem could not resolve {query!r}") from error


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
            canonical_parameters={},
            metadata_path=None,
        )

    root = session.temporary_root / _PUBCHEM_ROOT
    root.mkdir(exist_ok=True)
    if root.is_symlink() or root.resolve(strict=True).parent != session.temporary_root.resolve(strict=True):
        raise RuntimeError("PubChem staging root must stay inside the session")
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
    parameters = {
        request.sources[0].id: {
            "legacy_source_sha256": content_hash,
            "legacy_source_url": source_url,
        }
    }
    return PubChemImportStage(
        request=request,
        source_url=source_url,
        content_hash=content_hash,
        owner_id=session.id,
        diagnostics=(),
        canonical_parameters=parameters,
        metadata_path=metadata_path,
    )
