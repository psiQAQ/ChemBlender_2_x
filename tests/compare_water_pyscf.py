"""Compare the saved water example with an existing PySCF, without Blender.

Run with the existing PySCF environment on PYTHONPATH; no packages are installed.
The report and PySCF scratch files stay under the repository .agents/cache.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FCHK = ROOT / "submodules/iodata/iodata/test/data/water_sto3g_hf_g03.fchk"
FCHK_SHA256 = "aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816"
INDICES = ((14, 17, 19), (18, 26, 22), (22, 13, 23), (25, 28, 20),
           (28, 19, 25), (19, 23, 30), (24, 25, 26), (16, 25, 28),
           (30, 28, 18), (20, 16, 28), (26, 22, 15), (32, 21, 22))
# Fixed before observing results. This is a pointwise regression screen allowing
# printed FCHK coefficients/basis rounding and independent SCF termination;
# it is not an integration accuracy or a grid-convergence criterion.
ATOL = 1.e-6
RTOL = 1.e-5


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scientific_hashes(project_path):
    return {path.relative_to(project_path).as_posix(): sha256(path)
            for path in (project_path / "manifest.json", *sorted((project_path / "arrays").glob("*.npy")))}


def compare(project_path):
    import numpy as np
    import pyscf
    import scipy
    from pyscf import gto, lib, scf
    from cbq_core.model import Grid3D
    from cbq_core.sidecar import close_project
    from cbq_core.sidecar import open_project

    assert sha256(FCHK) == FCHK_SHA256, "the fixed source fixture changed"
    lines = FCHK.read_text(encoding="ascii").splitlines()
    assert lines[1].split() == ["SP", "RHF", "STO-3G"]
    integers = {line[:43].strip(): int(line.split()[-1]) for line in lines
                if len(line) > 43 and line[43:].strip().startswith("I") and "N=" not in line}
    assert (integers["Charge"], integers["Multiplicity"], integers["Number of electrons"]) == (0, 1, 10)
    before = scientific_hashes(project_path)
    project = open_project(project_path)
    try:
        assert len(project.structures) == len(project.orbital_sets) == len(project.basis_sets) == 1
        structure = next(iter(project.structures.values()))
        orbitals = next(iter(project.orbital_sets.values()))
        basis = next(iter(project.basis_sets.values()))
        assert structure.coordinates.unit == "bohr" and basis.name.lower() == "sto-3g"
        assert orbitals.kind.value == "restricted" and structure.atomic_numbers == (8, 1, 1)
        coordinates = np.asarray(structure.coordinates.values)
        fields = {}
        for dataset in project.datasets.values():
            if not isinstance(dataset, Grid3D):
                continue
            if dataset.semantic_role == "molecular_orbital":
                record = project.provenance[dataset.provenance_ids[0]]
                number = dict(record.parameters)["orbital_index"]
                name = {4: "homo", 5: "lumo"}[number]
            else:
                name = {"electron_density": "density", "electrostatic_potential": "esp"}[dataset.semantic_role]
            assert name not in fields, "ambiguous example field selection"
            fields[name] = dataset
        assert set(fields) == {"density", "esp", "homo", "lumo"}
        reference_grid = fields["density"]
        for dataset in fields.values():
            assert dataset.coordinate_unit == "bohr" and dataset.structure_id == structure.id
            assert dataset.data.shape == (45, 45, 45)
            assert (dataset.origin, dataset.step_vectors) == (reference_grid.origin, reference_grid.step_vectors)
        indices = np.asarray(INDICES)
        points = np.asarray(reference_grid.origin) + indices @ np.asarray(reference_grid.step_vectors)
        distances = np.linalg.norm(points[:, None, :] - coordinates[None, :, :], axis=2)
        assert distances.min() > .5, "comparison points must stay away from nuclei"
        charges = next(value for value in project.datasets.values() if value.semantic_role == "nuclear_charge")
        np.testing.assert_array_equal(charges.data.values, structure.atomic_numbers)
        assert any(record.source_hash == FCHK_SHA256 for record in project.provenance.values())

        lib.num_threads(1)
        mol = gto.M(atom=list(zip(structure.atomic_numbers, coordinates)), unit="Bohr",
                    basis="sto-3g", charge=0, spin=0, cart=True, verbose=0)
        assert mol.nao_nr() == basis.basis_function_count == 7 and mol.nelectron == 10
        mean_field = scf.RHF(mol)
        mean_field.chkfile = None
        # PySCF retains the initially allocated NamedTemporaryFile even after
        # disabling checkpoints; release its Windows handle explicitly.
        mean_field._chkfile.close()
        mean_field.conv_tol, mean_field.conv_tol_grad = 1.e-12, 1.e-9
        mean_field.max_cycle = 100
        energy = mean_field.kernel()
        assert mean_field.converged, "independent PySCF RHF did not converge"
        density_matrix = mean_field.make_rdm1()
        ao = mol.eval_gto("GTOval_cart", points)
        independent = {
            "density": np.einsum("pi,ij,pj->p", ao, density_matrix, ao),
            "homo": ao @ mean_field.mo_coeff[:, 4],
            "lumo": ao @ mean_field.mo_coeff[:, 5],
        }
        # Same Coulomb convention as pyscf.tools.cubegen.mep: V_nuc - V_elec.
        # int1e_rinv evaluates the electronic integral directly at each point.
        potential = np.sum(mol.atom_charges()[None, :] / distances, axis=1)
        for index, point in enumerate(points):
            with mol.with_rinv_origin(point):
                potential[index] -= np.einsum("ij,ji", density_matrix, mol.intor("int1e_rinv"))
        independent["esp"] = potential
        comparisons = {}
        for name, dataset in fields.items():
            stored = np.asarray(dataset.data.values[tuple(indices.T)])
            candidate = independent[name]
            phase = -1 if name in {"homo", "lumo"} and np.dot(stored, candidate) < 0 else 1
            candidate = candidate * phase
            error = np.abs(candidate - stored)
            allowance = ATOL + RTOL * np.abs(candidate)
            comparisons[name] = {
                "dataset_id": str(dataset.id), "dataset_revision": dataset.revision,
                "unit": dataset.data.unit, "pyscf_global_phase": phase,
                "stored_gbasis": stored.tolist(), "independent_pyscf": candidate.tolist(),
                "absolute_errors": error.tolist(), "max_absolute_error": float(error.max()),
                "max_error_over_allowance": float(np.max(error / allowance)),
                "passed": bool(np.all(error <= allowance)),
            }
        original_energy = float(next(line.split()[-1] for line in lines if line.startswith("Total Energy")))
        report = {
            "comparison": "saved GBasis fields versus independent PySCF RHF/STO-3G",
            "status": "passed" if all(value["passed"] for value in comparisons.values()) else "failed",
            "project_id": str(project.id), "project_path": str(project_path),
            "source": {"path": str(FCHK), "sha256": FCHK_SHA256, "method_header": lines[1].strip(),
                       "original_program_version": None},
            "software": {"python": sys.version.split()[0], "numpy": np.__version__,
                         "pyscf": pyscf.__version__, "scipy": scipy.__version__,
                         "pyscf_path": pyscf.__file__, "numpy_path": np.__file__},
            "grid": {"coordinate_unit": "bohr", "origin": reference_grid.origin,
                     "step_vectors": reference_grid.step_vectors, "indices": INDICES,
                     "points": points.tolist(), "minimum_nuclear_distance_bohr": float(distances.min())},
            "method": {"charge": 0, "spin": 0, "basis": "PySCF built-in STO-3G", "ao_count": 7,
                       "converged": bool(mean_field.converged), "scf_conv_tol": 1.e-12,
                       "scf_conv_tol_grad": 1.e-9, "energy_hartree": float(energy),
                       "fchk_energy_hartree": original_energy,
                       "energy_absolute_difference_hartree": abs(float(energy) - original_energy),
                       "fchk_orbital_energies_hartree": np.asarray(orbitals.channels[0].energies.values).tolist(),
                       "pyscf_orbital_energies_hartree": mean_field.mo_energy.tolist(),
                       "pyscf_raw_basis": mol._basis},
            "tolerance": {"absolute": ATOL, "relative": RTOL,
                          "rule": "abs(stored - independent) <= absolute + relative * abs(independent)",
                          "scope": "fixed pointwise screen; permits printed FCHK precision and independent SCF termination; no grid integration convergence claim"},
            "fields": comparisons,
            "scientific_files_sha256": before,
        }
    finally:
        close_project(project)
    assert scientific_hashes(project_path) == before, "comparison modified the saved scientific project"
    assert "bpy" not in sys.modules and "gbasis" not in sys.modules and "iodata" not in sys.modules
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=ROOT / "examples/quantum-workbench/output/water-workbench.cbq")
    parser.add_argument("--output", type=Path, default=ROOT / ".agents/cache/water-pyscf-comparison.json")
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / ".agents/cache")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="pyscf-water-", dir=output.parent) as scratch:
        os.environ["PYSCF_TMPDIR"] = scratch
        report = compare(args.project.resolve())
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output),
                      "max_absolute_errors": {name: value["max_absolute_error"] for name, value in report["fields"].items()}}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
