import hashlib
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4

from .model import (
    ArrayData,
    BandStructure,
    DatasetStatus,
    FermiSurfaceMesh,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    SurfaceProperty,
)


ADAPTER_VERSION = "1"
_POINT_PROPERTIES = {
    "fermi_velocity": ("fermi_velocity", "meter_per_second"),
    "fermi_speed": ("fermi_speed", "meter_per_second"),
    "spin": ("spin_texture", "dimensionless"),
    "scalars": ("orbital_contribution", "dimensionless"),
}


def _faces(values):
    import numpy

    flattened = numpy.asarray(values)
    if flattened.ndim != 1 or not numpy.issubdtype(flattened.dtype, numpy.integer):
        raise ValueError("PyProcar surface faces must use flattened integer connectivity")
    faces = []
    offset = 0
    while offset < len(flattened):
        corner_count = int(flattened[offset])
        if corner_count != 3 or offset + 4 > len(flattened):
            raise ValueError("PyProcar surface must be triangulated")
        faces.append(flattened[offset + 1 : offset + 4])
        offset += 4
    if offset != len(flattened) or not faces:
        raise ValueError("PyProcar surface must contain complete triangles")
    return numpy.asarray(faces, dtype=numpy.int64)


def _package_version():
    try:
        return version("PyProcar")
    except PackageNotFoundError:
        return "unavailable"


def adapt_pyprocar_fermi_surface(
    surface,
    band_structure,
    *,
    spin_index,
    fermi_energy,
    source="",
):
    import numpy

    if not isinstance(band_structure, BandStructure):
        raise TypeError("band_structure must be a normalized BandStructure")
    for attribute in ("points", "faces", "point_data", "cell_data"):
        if not hasattr(surface, attribute):
            raise TypeError("surface must expose PyVista-compatible mesh data")
    vertices = numpy.asarray(surface.points, dtype=float)
    faces = _faces(surface.faces)
    if "band_index" not in surface.cell_data:
        raise ValueError("PyProcar surface cell_data must contain band_index")
    local_bands = numpy.asarray(surface.cell_data["band_index"])
    if local_bands.shape != (len(faces),) or not numpy.issubdtype(
        local_bands.dtype, numpy.integer
    ):
        raise ValueError("PyProcar band_index must contain one integer per face")
    original_to_local = getattr(surface, "band_isosurface_index_map", None)
    if not isinstance(original_to_local, dict):
        raise ValueError("PyProcar surface must expose band_isosurface_index_map")
    local_to_original = {int(local): int(original) for original, local in original_to_local.items()}
    try:
        band_indices = numpy.asarray(
            [local_to_original[int(index)] for index in local_bands],
            dtype=numpy.int64,
        )
    except KeyError as error:
        raise ValueError("PyProcar band index mapping is incomplete") from error

    properties = []
    issues = []
    for name in surface.point_data:
        if name not in _POINT_PROPERTIES:
            issues.append(
                ParserIssue(
                    IssueKind.UNSUPPORTED,
                    f"pyprocar.point_data.{name}",
                    "point array is outside the explicit Fermi-surface property contract",
                )
            )
            continue
        semantic_role, unit = _POINT_PROPERTIES[name]
        values = numpy.asarray(surface.point_data[name])
        dims = ("vertex",) if values.ndim == 1 else ("vertex", "xyz")
        if values.shape[0] != len(vertices) or values.ndim not in {1, 2} or (
            values.ndim == 2 and values.shape[1] != 3
        ):
            raise ValueError(f"PyProcar point_data {name} has an invalid shape")
        properties.append(
            SurfaceProperty(
                semantic_role=semantic_role,
                domain="vertex",
                data=ArrayData(values.copy(), dims, unit),
            )
        )
    for name in surface.cell_data:
        if name != "band_index":
            issues.append(
                ParserIssue(
                    IssueKind.UNSUPPORTED,
                    f"pyprocar.cell_data.{name}",
                    "cell array is outside the explicit Fermi-surface property contract",
                )
            )

    digest = hashlib.sha256()
    digest.update(band_structure.revision.encode("utf-8"))
    for values in (vertices, faces, band_indices):
        digest.update(numpy.ascontiguousarray(values).tobytes())
    digest.update(repr((spin_index, fermi_energy)).encode("ascii"))
    revision = digest.hexdigest()
    provenance_id = uuid4()
    dataset = FermiSurfaceMesh(
        id=uuid4(),
        revision=revision,
        semantic_role="fermi_surface",
        domain="surface_vertex",
        data=ArrayData(vertices, ("vertex", "xyz"), "inverse_angstrom"),
        status=DatasetStatus.COMPLETE,
        source_calculation=band_structure.source_calculation,
        provenance_ids=(provenance_id,),
        structure_id=band_structure.structure_id,
        band_structure_id=band_structure.id,
        faces=ArrayData(faces, ("face", "corner"), "dimensionless"),
        band_indices=ArrayData(band_indices, ("face",), "dimensionless"),
        spin_index=spin_index,
        fermi_energy=fermi_energy,
        coordinate_convention="cartesian_reciprocal_2pi",
        properties=tuple(properties),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="PyProcar Fermi-surface adapter",
        producer_version=f"{ADAPTER_VERSION}/PyProcar-{_package_version()}",
        source=str(source),
        source_hash=revision,
        parent_ids=(band_structure.id, band_structure.structure_id),
        operation="normalize_fermi_surface_mesh",
        parameters=(
            ("coordinate_convention", dataset.coordinate_convention),
            ("spin_index", spin_index),
            ("fermi_energy", fermi_energy),
        ),
    )
    return ImportBatch(
        datasets=(dataset,),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="pyprocar-fermi-surface",
            reader_version=ADAPTER_VERSION,
            created_entity_ids=(dataset.id, provenance.id),
            parsed_capabilities=("fermi_surface", "projection"),
            issues=tuple(issues),
        ),
    )
