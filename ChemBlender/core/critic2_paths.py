"""Ordered gradient paths from critic2 1.3.15 FLUXPRINT TEXT output.

The format follows src/flux@proc.f90::flx_printpath at the pinned critic2
revision. CP identifiers come from the matching CPJSON, never proximity alone.
"""

from dataclasses import replace
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

from .cache_identity import parser_cache_key, source_hash_bytes
from .critic2_adapter import CRITIC2_REVIEWED_VERSION, _finite, _load, parse_critic2_cpreport
from .grid_cache_service import _ANGSTROM_SCALE
from .model import ArrayData, ImportBatch, ParserReport, ProvenanceRecord, TopologyGraph, TopologyPath


ADAPTER_ID = "critic2-fluxprint-text"
ADAPTER_VERSION = "1"
_COLUMNS = "x y z rho rhox rhoy rhoz rhoxx rhoxy rhoxz rhoyy rhoyz rhozz".split()
_UNIT = {"bohr": "bohr", "ang_": "angstrom"}


def _numbers(line, count):
    import numpy

    fields = line.split()
    if len(fields) != count:
        raise ValueError(f"critic2 path row must contain {count} numbers")
    try:
        # Fortran Ew.d may omit E for a three-digit exponent.
        values = [float(re.sub(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d{3})$",
                               r"\1e\2", field.replace("D", "E").replace("d", "e")))
                  for field in fields]
    except ValueError as error:
        raise ValueError("critic2 path contains an invalid numeric field") from error
    if not numpy.isfinite(values).all():
        raise ValueError("critic2 path contains non-finite samples")
    return numpy.asarray(values)


def _one(pattern, block, name):
    matches = list(re.finditer(pattern, block, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"critic2 path requires exactly one {name}")
    return matches[0]


def _matrix(block, name):
    import numpy

    lines = block.splitlines()
    locations = [index for index, line in enumerate(lines) if line.strip() == f"# {name} :"]
    if not locations:
        return None
    if len(locations) != 1:
        raise ValueError(f"duplicate {name} matrix")
    index = locations[0]
    rows = lines[index + 1:index + 5]
    if len(rows) != 4 or any(not row.lstrip().startswith("#") for row in rows):
        raise ValueError(f"truncated {name} matrix")
    matrix = numpy.asarray([_numbers(row.lstrip()[1:], 4) for row in rows])
    if not numpy.allclose(matrix[3], [0., 0., 0., 1.], atol=1e-12, rtol=0.):
        raise ValueError(f"invalid homogeneous {name} matrix")
    if numpy.linalg.det(matrix[:3, :3]) == 0. or numpy.any(matrix[:3, 3] != 0.):
        raise ValueError(f"invalid {name} linear coordinate transform")
    return matrix


def _block(block):
    import numpy

    count = int(_one(r"^\s*# number of points:\s*(\d+)\s*$", block, "point count")[1])
    if count < 2:
        raise ValueError("critic2 path needs at least two ordered samples")
    endpoints = list(re.finditer(r"^\s*# name:\s*(.*?)\s+\((.*?)\)\s+ncp:\s*(\d+)\s+ncpcel:\s*(\d+)\s*$",
                                block, re.MULTILINE))
    if len(endpoints) != 2 or any(int(value[4]) <= 0 for value in endpoints):
        raise ValueError("critic2 paths require two explicit critical point endpoints")
    origin = _one(r"^\s*# ---- origin of the path ----\s*$", block, "origin section")
    end = _one(r"^\s*# ---- end of the path ----\s*$", block, "end section")
    if not origin.start() < endpoints[0].start() < end.start() < endpoints[1].start():
        raise ValueError("critic2 endpoint sections are out of order")
    positions, fractions, units = [], [], []
    for title in ("starting", "end"):
        position = _one(r"^\s*# " + title + r" position \((bohr|ang_)\):\s*(.*?)\s*$", block, title + " coordinates")
        positions.append(_numbers(position[2], 3))
        units.append(_UNIT[position[1]])
        fractional = _one(r"^\s*# " + title + r" position \(cryst\.\):\s*(.*?)\s*$", block, title + " fractional coordinates")
        fractions.append(_numbers(fractional[1], 3))
    if units[0] != units[1]:
        raise ValueError("critic2 path endpoint units disagree")
    gap = _numbers(_one(r"^\s*# distance between nucleus and end of path \(bohr\):\s*(.*?)\s*$",
                        block, "endpoint distance")[1], 1)[0]
    if gap < 0.:
        raise ValueError("critic2 path endpoint distance must be non-negative")
    lines = block.splitlines()
    headers = [index for index, line in enumerate(lines)
               if line.lstrip().startswith("#") and line.lstrip()[1:].split() == _COLUMNS]
    if len(headers) != 1:
        raise ValueError("critic2 path requires the exact 13-column sample header")
    rows = [line.strip() for line in lines[headers[0] + 1:] if line.strip()]
    if len(rows) != count:
        raise ValueError("critic2 path sample count does not match declared count")
    values = numpy.asarray([_numbers(row, 13) for row in rows])
    return dict(values=values, cells=tuple(int(value[4]) for value in endpoints),
                nonequivalent=tuple(int(value[3]) for value in endpoints),
                positions=numpy.asarray(positions), fractions=numpy.asarray(fractions),
                coordinate_unit=units[0], endpoint_gap_bohr=float(gap),
                matrix=_matrix(block, "Crys2Car"), inverse=_matrix(block, "Car2Crys"))


def _image(position, target, matrix, tolerance, label):
    import numpy

    delta = position - target
    translation = numpy.zeros(3, dtype=int)
    if matrix is not None:
        translation = numpy.rint(numpy.linalg.solve(matrix, delta)).astype(int)
        delta = delta - matrix @ translation
    gap = float(numpy.linalg.norm(delta))
    if gap > tolerance:
        raise ValueError(f"critic2 path {label} does not match its declared critical point")
    return tuple(int(value) for value in translation), gap


def parse_critic2_paths(path, *, graph, cpreport_path, endpoint_tolerance=0.02):
    """Attach ordered CP-to-CP paths as a new graph, preserving the input graph.

    endpoint_tolerance is in bohr. A sampled endpoint may approach a nucleus
    without landing on it; its coordinates remain untouched. For periodic data,
    image translations are recorded per path and CP endpoint in provenance.
    """
    import numpy

    if not isinstance(graph, TopologyGraph):
        raise TypeError("graph must be a TopologyGraph")
    endpoint_tolerance = _finite(endpoint_tolerance, "endpoint_tolerance")
    if endpoint_tolerance <= 0.:
        raise ValueError("endpoint_tolerance must be positive")
    cpreport_path, cp_source, document = _load(cpreport_path)
    matching = parse_critic2_cpreport(cpreport_path, structure_id=graph.structure_id,
        source_grid_id=graph.source_grid_id, source_calculation=graph.source_calculation,
        coordinate_unit=graph.data.unit, field_semantic_role=graph.field_semantic_role,
        field_unit=graph.field_values.unit, laplacian_unit=graph.laplacians.unit).datasets[0]
    if (graph.critical_point_ids != matching.critical_point_ids
            or not numpy.array_equal(graph.data.values, matching.data.values)):
        raise ValueError("cpreport and TopologyGraph critical point identities or coordinates disagree")
    section = document.get("structure", {})
    if not isinstance(section.get("is_molecule"), bool):
        raise ValueError("path binding requires CPJSON structure.is_molecule")
    periodic = not section["is_molecule"]
    source_unit = document.get("units", "bohr")
    factor = _ANGSTROM_SCALE["bohr"] / _ANGSTROM_SCALE[graph.data.unit]
    tolerance = endpoint_tolerance * factor
    expected_matrix = None
    if periodic:
        values = section.get("crys_to_cart_matrix")
        if not isinstance(values, list) or len(values) != 9:
            raise ValueError("periodic CPJSON requires a crys_to_cart_matrix")
        expected_matrix = numpy.asarray([_finite(value, "crys_to_cart_matrix") for value in values]).reshape(3, 3, order="F")
        expected_matrix *= _ANGSTROM_SCALE[source_unit] / _ANGSTROM_SCALE["bohr"]
    cells = document["critical_points"]["cell_cps"]
    id_map = {cell["id"]: (index, cell) for index, cell in enumerate(cells)}
    path = Path(path)
    try:
        source = path.read_bytes()
        text = source.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError("cannot read critic2 FLUXPRINT TEXT") from error
    blocks = re.split(r"^\s*# End gradient path\s*$", text, flags=re.MULTILINE)
    if len(blocks) < 2 or blocks[-1].strip():
        raise ValueError("critic2 path file is missing an End gradient path marker")
    records = [_block(block) for block in blocks[:-1]]
    options = {"parent_graph_id": str(graph.id), "parent_revision": graph.revision,
               "cpreport_source_hash": source_hash_bytes(cp_source),
               "endpoint_tolerance_bohr": endpoint_tolerance, "coordinate_unit": graph.data.unit}
    source_hash = source_hash_bytes(source)
    revision = parser_cache_key(source_hash, ADAPTER_ID, ADAPTER_VERSION, options)
    graph_id = uuid5(NAMESPACE_URL, f"chemblender:{ADAPTER_ID}:{revision}")
    paths, path_metadata = [], []
    for index, record in enumerate(records):
        point_indices = []
        for cell_id, nonequivalent in zip(record["cells"], record["nonequivalent"]):
            if cell_id not in id_map or id_map[cell_id][1]["nonequivalent_id"] != nonequivalent:
                raise ValueError("critic2 path has an unknown or mismatched CP cell identifier")
            point_indices.append(id_map[cell_id][0])
        start_id, end_id = (graph.critical_point_ids[item] for item in point_indices)
        if start_id == end_id:
            raise ValueError("same-CP periodic paths require a richer topology model")
        header_scale = _ANGSTROM_SCALE[record["coordinate_unit"]] / _ANGSTROM_SCALE[graph.data.unit]
        headers = record["positions"] * header_scale
        matrix = record["matrix"]
        if periodic:
            if matrix is None or record["inverse"] is None:
                raise ValueError("periodic critic2 paths require Crys2Car and Car2Crys matrices")
            if (not numpy.allclose(matrix[:3, :3], expected_matrix, atol=1e-8, rtol=1e-8)
                    or not numpy.allclose(matrix @ record["inverse"], numpy.eye(4), atol=1e-8, rtol=1e-8)):
                raise ValueError("critic2 path coordinate matrices disagree with CPJSON")
            matrix = matrix[:3, :3] * factor
            samples = record["values"][:, :3] @ matrix.T
            if not numpy.allclose(record["fractions"] @ matrix.T, headers, atol=tolerance, rtol=0.):
                raise ValueError("critic2 path fractional and Cartesian endpoint headers disagree")
        else:
            if matrix is not None or record["inverse"] is not None:
                raise ValueError("molecular critic2 paths must contain Cartesian samples")
            samples = record["values"][:, :3] * header_scale
        endpoint_images = []
        for side, cp_index in enumerate(point_indices):
            _image(headers[side], graph.data.values[cp_index], matrix, tolerance, "header")
            image, gap = _image(samples[0 if side == 0 else -1], graph.data.values[cp_index],
                                matrix, tolerance, "sample endpoint")
            endpoint_images.append(image)
            if side == 1 and abs(gap - record["endpoint_gap_bohr"] * factor) > tolerance:
                raise ValueError("critic2 sampled endpoint gap disagrees with its header")
        if numpy.linalg.norm(samples[0] - headers[0]) > tolerance:
            raise ValueError("critic2 first sample disagrees with the declared path origin")
        path_id = uuid5(graph_id, f"path:{index}")
        paths.append(TopologyPath(id=path_id, start_id=start_id, end_id=end_id,
                                  samples=ArrayData(samples, ("sample", "xyz"), graph.data.unit)))
        path_metadata.append({"path_id": str(path_id), "start_id": str(start_id), "end_id": str(end_id),
                              "cell_ids": record["cells"], "start_lattice_vector": endpoint_images[0],
                              "end_lattice_vector": endpoint_images[1],
                              "coordinate_source": "fractional_crys2car_bohr" if periodic else record["coordinate_unit"],
                              "declared_endpoint_gap_bohr": record["endpoint_gap_bohr"],
                              "sample_count": len(samples)})
    provenance_id = uuid5(graph_id, "provenance")
    provenance = ProvenanceRecord(id=provenance_id, revision=revision, producer="critic2",
        producer_version=CRITIC2_REVIEWED_VERSION, source=str(path), source_hash=source_hash,
        parent_ids=(graph.id,), operation="parse_fluxprint_text",
        parameters=tuple(options.items()) + (("paths", path_metadata),))
    result = replace(graph, id=graph_id, revision=revision,
                     paths=graph.paths + tuple(paths), provenance_ids=graph.provenance_ids + (provenance_id,))
    return ImportBatch(datasets=(result,), provenance=(provenance,), report=ParserReport(
        reader_id=ADAPTER_ID, reader_version=ADAPTER_VERSION,
        parsed_capabilities=("topology", "ordered_gradient_paths"),
        created_entity_ids=(graph_id, provenance_id), issues=()))
