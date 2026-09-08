"""Build reproducible molecular .cbq examples with existing optional backends.

Run with the reviewed IOData/GBasis environment. This script never installs
packages or downloads inputs. All generated files stay in its owned cache.
"""

import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from math import isfinite
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
OUTPUT = ROOT / ".agents/cache/scientific-corpus/molecular"
INPUTS = {
    "water": BASE / "inputs/wavefunction/water_sto3g_hf_g03.fchk",
    "ch3": BASE / "inputs/wavefunction/ch3_hf_sto3g.fchk",
    "nitrogen": BASE / "inputs/wavefunction/nitrogen-mp2.fchk",
    "water-molden": BASE / "inputs/wavefunction/h2o.molden.input",
    "pqr": ROOT / "examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr",
    "rmd17": ROOT / "examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz",
}


def source_record(name):
    source = INPUTS[name]
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if name in ("pqr", "rmd17"):
        expected = {
            "pqr": "44f78c804e4f006f74a9f2b439094063e1046735106e2c8436543ba7e7578a68",
            "rmd17": "95ad7342776441a9ce2d524a65351dad8b8e29ab40857b4ed858d17ab71a409a",
        }[name]
        upstream = {
            "pqr": "Electrostatics/apbs@4613d0d547c3c71df8815dcb85e9e19abf61822c:examples/protein-rna/model_outNB.pqr",
            "rmd17": "10.6084/m9.figshare.12672038.v3; rmd17_aspirin.npz rows 0..3100 stride100",
        }[name]
        record = {"upstream": upstream, "license": "BSD-3-Clause" if name == "pqr" else "CC0-1.0"}
    else:
        manifest = json.loads((BASE / "input-manifest.json").read_text(encoding="utf-8"))
        item = next(item for item in manifest["files"] if item["path"] == source.relative_to(BASE).as_posix())
        expected = item["sha256"]
        record = {key: item[key] for key in ("url", "commit", "upstream_path")}
        record["license"] = manifest["sources"]["iodata"]["license"]
    if digest != expected:
        raise ValueError(f"reviewed input hash mismatch: {source}")
    record.update(path=str(source), sha256=digest, bytes=len(data))
    if source.suffix == ".fchk":
        lines = data.decode("ascii").splitlines()
        header = lines[1].split()
        record.update(method=header[1], basis=header[2], method_evidence=lines[1],
            calculation_program="not_reported_in_fchk", calculation_program_version="not_reported")
        for label, key in (("Charge", "charge"), ("Multiplicity", "multiplicity"), ("Number of electrons", "electron_count")):
            record[key] = int(next(line for line in lines if line[:40].strip() == label).split()[-1])
    elif name == "water-molden":
        record.update(method="not_reported", basis="stored_explicit_shells",
            calculation_program="ORCA orca_2mkl (declared in title)", calculation_program_version="not_reported",
            method_evidence="Molden title identifies converter; no SCF/post-SCF method is declared")
    elif name == "rmd17":
        record.update(coordinate_unit="angstrom", force_unit="electron_volt_per_angstrom",
            source_npz_sha256="6efe3d2454c1a9215efe2bf271c58084ae556afa188a740ae06955bf43456ee8",
            conversion="source kcal/mol and kcal/mol/angstrom divided by 23.060547830619",
            sampling="32 configurations; original rows 0,100,...,3100; no physical time step declared")
    else:
        record["header_evidence"] = [line for line in data.decode("ascii").splitlines() if line.startswith("REMARK")][:30]
    return record


def publish_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".molecular-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write((json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def statistics(dataset):
    import numpy as np
    from ChemBlender.core import Grid3D

    values = np.asarray(dataset.data.values)
    finite = np.isfinite(values)
    record = {"id": str(dataset.id), "revision": dataset.revision,
        "type": type(dataset).__name__, "semantic_role": dataset.semantic_role,
        "shape": list(values.shape), "unit": dataset.data.unit,
        "finite_count": int(finite.sum()), "value_count": values.size,
        "minimum": float(values[finite].min()) if finite.any() else None,
        "maximum": float(values[finite].max()) if finite.any() else None,
        "structure_id": str(getattr(dataset, "structure_id", "")),
        "provenance_ids": [str(value) for value in dataset.provenance_ids]}
    if isinstance(dataset, Grid3D):
        volume = abs(float(np.linalg.det(np.asarray(dataset.step_vectors))))
        record.update(point_count=values.size, coordinate_unit=dataset.coordinate_unit,
            origin=dataset.origin, step_vectors=dataset.step_vectors, voxel_volume_bohr3=volume)
        if dataset.semantic_role in ("electron_density", "spin_density", "difference_density"):
            record["finite_box_rectangle_integral_electrons"] = float(values.sum() * volume)
            record["integral_convergence"] = "not established; no electron-count acceptance criterion"
        elif dataset.semantic_role == "molecular_orbital":
            record["finite_box_rectangle_integral_abs_psi_squared"] = float(np.sum(values ** 2) * volume)
    return record


def add_source_evidence(batch, source):
    # Add exact reviewed header evidence to the parser record; retain identities,
    # raw source hashes and both original RDM levels, without guessing a solver.
    return replace(batch, provenance=tuple(replace(record,
        parameters=record.parameters + (("scientific_example_source", source),))
        for record in batch.provenance))


def wavefunction_project(name, source, *, spacing, padding, chunk_size):
    import numpy as np
    from ChemBlender.core import QCProject, DensityMatrixLevel, DensityMatrixSpin
    from ChemBlender.core.grid_difference import derive_grid_difference
    from ChemBlender.core.iodata_adapter import parse_iodata_wavefunction
    from ChemBlender.core.orbital_browser import orbital_rows, suggest_grid
    from ChemBlender.core.wavefunction_grid import evaluate_molecular_orbital_grid, evaluate_electron_density_grid
    from ChemBlender.core.wavefunction_observables import evaluate_density_matrix_grid, evaluate_electrostatic_potential_grid

    batch = add_source_evidence(parse_iodata_wavefunction(INPUTS[name]), source)
    project = QCProject(id=uuid4(), schema_version="0.2")
    project.commit(batch)
    structure, basis, orbitals = batch.structures[0], batch.basis_sets[0], batch.orbital_sets[0]
    grid = suggest_grid(structure, spacing=spacing, padding=padding)
    # A documented fractional-cell offset avoids sampling nuclear singularities.
    grid["origin"] = tuple(float(a + spacing * b) for a, b in zip(grid["origin"], (.37, .29, .19)))
    parameters = dict(grid, chunk_size=chunk_size)
    outputs = []

    def commit(label, produced, **selection):
        project.commit(produced)
        for dataset in produced.datasets:
            outputs.append(dict(statistics(dataset), label=label, **selection))
        print(f"{name}: {label} ({int(np.prod(grid['shape']))} points)", flush=True)
        return produced.datasets[0]

    for channel in orbitals.channels:
        rows = orbital_rows(project, orbitals, channel.label)
        for frontier in (("HOMO", "LUMO") if channel.label == "restricted" else ("HOMO",)):
            selected = next((row for row in rows if frontier in row.labels), None)
            if selected is None:
                raise ValueError(f"{name}: no verified {channel.label} {frontier} selection")
            commit(f"mo_{channel.label}_{frontier.lower()}",
                evaluate_molecular_orbital_grid(structure, basis, orbitals,
                    channel=channel.label, orbital_index=selected.index, **parameters),
                channel=channel.label, orbital_number=selected.index + 1, orbital_index=selected.index,
                frontier=frontier, energy_hartree=selected.energy, occupation=selected.occupation)
    density_grids = {}
    for matrix in batch.density_matrices:
        label = f"rho_{matrix.level.value}_{matrix.spin_role.value}"
        density_grids[(matrix.level, matrix.spin_role)] = commit(label,
            evaluate_density_matrix_grid(structure, basis, matrix, **parameters),
            density_matrix_id=str(matrix.id), density_level=matrix.level.value,
            spin_role=matrix.spin_role.value, density_source="original_stored_ao_density_matrix")
    if not batch.density_matrices:
        commit("rho_orbital_occupations", evaluate_electron_density_grid(structure, basis, orbitals,
            source_provenance=project.provenance.values(), **parameters),
            density_source="orbital_occupations", density_level="not_reported")
    total = [matrix for matrix in batch.density_matrices if matrix.spin_role is DensityMatrixSpin.TOTAL]
    if total:
        matrix = next((matrix for matrix in total if matrix.level is DensityMatrixLevel.POST_SCF), total[0])
        charges = next(dataset for dataset in batch.datasets if dataset.semantic_role == "nuclear_charge")
        commit(f"esp_{matrix.level.value}", evaluate_electrostatic_potential_grid(
            structure, basis, matrix, charges, nuclear_exclusion_radius=1e-8, **parameters),
            density_matrix_id=str(matrix.id), nuclear_charge_dataset_id=str(charges.id),
            density_level=matrix.level.value, nuclear_exclusion_radius_bohr=1e-8)
    if name == "nitrogen":
        left = density_grids[(DensityMatrixLevel.POST_SCF, DensityMatrixSpin.TOTAL)]
        right = density_grids[(DensityMatrixLevel.SCF, DensityMatrixSpin.TOTAL)]
        commit("difference_mp2_minus_scf", derive_grid_difference(left, right, chunk_size=chunk_size),
            left_dataset_id=str(left.id), right_dataset_id=str(right.id),
            definition="original stored UMP2-FC total density minus original stored SCF total density")
    record = {"source": source, "structure_id": str(structure.id),
        "atom_count": len(structure.atomic_numbers), "atomic_numbers": list(structure.atomic_numbers),
        "basis_set_id": str(basis.id), "basis_function_count": basis.basis_function_count,
        "orbital_set_id": str(orbitals.id), "grid": grid, "chunk_size": chunk_size,
        "grid_origin_offset_fraction": [.37, .29, .19], "outputs": outputs,
        "input_datasets": [statistics(dataset) for dataset in batch.datasets],
        "parser_issues": [{"kind": issue.kind.value, "path": issue.path, "message": issue.message} for issue in batch.report.issues]}
    if name == "water-molden":
        record["limits"] = ["No method/SCF level declared: ESP matrix reconstruction intentionally not requested"]
    if name == "nitrogen":
        record["limits"] = ["This input is a single nitrogen atom, not N2", "Original UMP2-FC and SCF matrices share one structure and affine grid"]
    return project, record


def native_project(name, source):
    from ChemBlender.core import QCProject
    from ChemBlender.core.reader_catalog import builtin_reader_registry

    batch = builtin_reader_registry().parse(INPUTS[name], reader_id="pqr" if name == "pqr" else "extxyz")
    batch = add_source_evidence(batch, source)
    project = QCProject(id=uuid4(), schema_version="0.2")
    project.commit(batch)
    return project, {"source": source, "structure_id": str(batch.structures[0].id),
        "atom_count": len(batch.structures[0].atomic_numbers),
        "outputs": [statistics(dataset) for dataset in batch.datasets],
        "parser_issues": [{"kind": issue.kind.value, "path": issue.path, "message": issue.message} for issue in batch.report.issues]}


def main():
    from ChemBlender.core import close_project, open_project, save_project

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=tuple(INPUTS), default=list(INPUTS))
    parser.add_argument("--spacing", type=float, default=.25)
    parser.add_argument("--padding", type=float, default=6.)
    parser.add_argument("--chunk-size", type=int, default=4096)
    args = parser.parse_args()
    if not isfinite(args.spacing) or args.spacing <= 0 or not isfinite(args.padding) or args.padding < 0 or args.chunk_size <= 0:
        parser.error("spacing/chunk-size must be positive; padding must be finite and non-negative")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "schema_version": 1, "generator": str(Path(__file__).resolve()), "cases": {},
        "interpretation": "Finite grids for visualization; integrals are observations, not convergence/electron-count tests"}
    document["runtime"] = {"python": platform.python_version(), "executable": sys.executable}
    for package in ("numpy", "qc-iodata", "qc-gbasis"):
        try:
            document["runtime"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            document["runtime"][package] = "unavailable"
    failures = []
    for name in args.only:
        project = None
        started = time.monotonic()
        try:
            source = source_record(name)
            target = OUTPUT / f"{name}.cbq"
            parameters = {"spacing": args.spacing, "padding": args.padding, "chunk_size": args.chunk_size}
            if target.exists():
                previous = document["cases"].get(name, {})
                if previous.get("source", {}).get("sha256") != source["sha256"] or previous.get("parameters") != parameters:
                    raise ValueError("existing output differs from requested inputs/parameters; preserving it")
                reopened = open_project(target)
                close_project(reopened)
                print(f"{name}: existing validated project reused", flush=True)
                continue
            if name in ("pqr", "rmd17"):
                project, record = native_project(name, source)
            else:
                project, record = wavefunction_project(name, source, **parameters)
            save_project(target, project)
            reopened = open_project(target)
            try:
                assert set(reopened.datasets) == set(project.datasets)
                assert set(reopened.provenance) == set(project.provenance)
            finally:
                close_project(reopened)
            record.update(status="complete", sidecar=str(target), project_id=str(project.id),
                parameters=parameters, elapsed_seconds=time.monotonic() - started)
            document["cases"][name] = record
            print(f"{name}: saved + reopened {target}", flush=True)
        except Exception as error:
            failures.append(name)
            failure = {"status": "failed", "error_type": type(error).__name__, "message": str(error)}
            if document["cases"].get(name, {}).get("status") == "complete":
                document.setdefault("attempt_errors", {})[name] = failure
            else:
                document["cases"][name] = failure
            print(f"{name}: {type(error).__name__}: {error}", flush=True)
        finally:
            if project is not None:
                close_project(project)
            publish_json(manifest_path, document)
    print(str(manifest_path), flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
