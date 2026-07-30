from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from uuid import uuid5


PLUGIN_ID = "org.chemblender.example.simplecoords"
PLUGIN_VERSION = "1.0.0"
READER_ID = "simplecoords"
READER_VERSION = "1.0"
READER_MANIFEST_TOML = """\
schema_version = "1"
plugin_id = "org.chemblender.example.simplecoords"
plugin_version = "1.0.0"
chemblender_api = ">=1.0,<2.0"
execution_mode = "extension"
license = ["SPDX:MIT"]

[[readers]]
reader_id = "simplecoords"
reader_version = "1.0"
extensions = [".cbsimple"]
capabilities = ["structure"]
"""

_ELEMENTS = {"H": 1, "C": 6, "N": 7, "O": 8}


def _parameters(request):
    return tuple(
        sorted(
            (
                ("source_content_state", "verified"),
                ("validation_mode", request.validation_mode),
                *request.canonical_parameters.items(),
            )
        )
    )


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _parse_identity(request, parameters):
    return _digest(
        {
            "content_hash": request.source_content_hash,
            "parameters": parameters,
            "plugin_id": PLUGIN_ID,
            "reader_id": READER_ID,
            "reader_version": READER_VERSION,
        }
    )


def _cancelled(api):
    return api.PublicImportBatch(
        report=api.ParserReport(
            READER_ID,
            READER_VERSION,
            (),
            (),
            (
                api.ParserIssue(
                    api.IssueKind.WARNING,
                    "reader.parse",
                    "reader parse cancelled",
                ),
            ),
        )
    )


def _is_cancelled(request):
    result = request.is_cancelled()
    if type(result) is not bool:
        raise TypeError("is_cancelled must return bool")
    return result


def _parse(api, request):
    if _is_cancelled(request):
        return _cancelled(api)
    try:
        lines = request.source_path.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("CBSIMPLE source must be UTF-8") from error
    if len(lines) < 3 or lines[0] != "CBSIMPLE 1":
        raise ValueError("CBSIMPLE 1 header is required")
    if lines[1].split() != ["units", "angstrom"]:
        raise ValueError("CBSIMPLE 1 requires units angstrom")
    atom_header = lines[2].split()
    if len(atom_header) != 2 or atom_header[0] != "atoms":
        raise ValueError("CBSIMPLE 1 atoms count is required")
    try:
        atom_count = int(atom_header[1])
    except ValueError as error:
        raise ValueError("atom count must be an integer") from error
    if atom_count <= 0 or len(lines) != atom_count + 3:
        raise ValueError("atom count must match the coordinate rows")

    atomic_numbers = []
    coordinates = []
    request.progress(api.ProgressEvent("atoms", 0, atom_count))
    for index, line in enumerate(lines[3:]):
        if _is_cancelled(request):
            return _cancelled(api)
        fields = line.split()
        if len(fields) != 4 or fields[0] not in _ELEMENTS:
            raise ValueError(f"invalid atom row {index + 1}")
        try:
            xyz = tuple(float(value) for value in fields[1:])
        except ValueError as error:
            raise ValueError(f"invalid atom row {index + 1}") from error
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError(f"invalid atom row {index + 1}")
        atomic_numbers.append(_ELEMENTS[fields[0]])
        coordinates.extend(xyz)
        request.progress(api.ProgressEvent("atoms", index + 1, atom_count))

    source_id = uuid5(request.source_revision_id, "simplecoords:source")
    structure_id = uuid5(request.source_revision_id, "simplecoords:structure")
    provenance_id = uuid5(request.source_revision_id, "simplecoords:provenance")
    created_ids = (structure_id, provenance_id)
    parameters = _parameters(request)
    coordinate_values = memoryview(array("d", coordinates)).cast("B").cast(
        "d", shape=[atom_count, 3]
    )
    structure = api.Structure(
        id=structure_id,
        revision=request.source_content_hash,
        atomic_numbers=tuple(atomic_numbers),
        coordinates=api.ArrayData(
            coordinate_values,
            ("atom", "xyz"),
            "angstrom",
        ),
    )
    provenance = api.ProvenanceRecord(
        id=provenance_id,
        revision=request.source_content_hash,
        producer="ChemBlender SimpleCoords example reader",
        producer_version=READER_VERSION,
        source=str(request.source_path),
        source_hash=request.source_content_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", "cbsimple"),),
    )
    source = api.SourceRecord(
        id=source_id,
        display_name=request.source_path.name,
        source_kind="local_file",
        created_at_utc=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    )
    revision = api.SourceRevision(
        id=request.source_revision_id,
        source_id=source_id,
        content_hash=request.source_content_hash,
        byte_size=request.source_path.stat().st_size,
        locator=str(request.source_path),
        locator_kind="absolute_path",
        original_filename=request.source_path.name,
        reader_plugin_id=PLUGIN_ID,
        reader_id=READER_ID,
        reader_version=READER_VERSION,
        reader_api_version=api.READER_API_VERSION,
        import_parameters_hash=_digest(parameters),
        parse_identity=_parse_identity(request, parameters),
        created_entity_ids=created_ids,
        diagnostic_ids=(),
    )
    report = api.ParserReport(
        reader_id=READER_ID,
        reader_version=READER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=("structure",),
        issues=(),
    )
    return api.PublicImportBatch(
        sources=(source,),
        source_revisions=(revision,),
        structures=(structure,),
        provenance=(provenance,),
        report=report,
    )


class _SimpleCoordsReader:
    def __init__(self, api):
        self._api = api
        self.manifest = api.ReaderPluginManifest.from_toml(
            READER_MANIFEST_TOML
        )
        self.descriptor = api.PublicReaderDescriptor(
            plugin_id=PLUGIN_ID,
            plugin_version=PLUGIN_VERSION,
            reader_id=READER_ID,
            reader_version=READER_VERSION,
            execution_mode=api.ExecutionMode.EXTENSION,
            extensions=(".cbsimple",),
            capabilities={
                "structure": api.CapabilitySupport.SUPPORTED,
            },
            availability=api.ReaderAvailability(
                True,
                "extension",
                "available",
                "",
            ),
        )
        self.priority = 0

    def sniff(self, request):
        header = request.prefix.splitlines()[:1]
        match = (
            self._api.SniffMatch.EXACT
            if header == [b"CBSIMPLE 1"]
            else self._api.SniffMatch.NONE
        )
        return self._api.SniffResult(match, "CBSIMPLE 1 header")

    def parse(self, request):
        return _parse(self._api, request)


def create_plugin(api):
    return _SimpleCoordsReader(api)
