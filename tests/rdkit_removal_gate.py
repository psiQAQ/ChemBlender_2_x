"""Repeatable pre-removal RDKit equivalence and cold-process timing gate."""

import argparse
import json
import os
from pathlib import Path
import platform
from statistics import median
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

import numpy

from cbq_core.model import QCProject
from cbq_core.session import ProjectSession
from cbq_core.sidecar import close_project
from ChemBlender.ui.processor import ProcessorState
from ChemBlender.ui.processor_operations import (
    molecule_inputs, publish_operation, start_molecule_operation,
)
from tests.test_worker_molecule_operations import smiles_batch


ROOT = Path(__file__).resolve().parents[1]
PROCESSOR = ROOT / ".venv" / "Scripts" / "chemblender-prepare.exe"
SMILES = "CC(=O)OC1=CC=CC=C1C(=O)O"  # Aspirin, 21 atoms with explicit H.
PARAMETERS = {
    "add_hydrogens": True,
    "force_field": "MMFF94",
    "random_seed": 0xC0FFEE,
    "num_threads": 1,
    "max_iterations": 200,
}


def _session(root):
    batch = smiles_batch(SMILES)
    project = QCProject(uuid4(), "1.1")
    project.commit(batch)
    return ProjectSession(uuid4(), project, root), (
        batch.structures[0].id, batch.topologies[0].id,
        batch.molecular_records[0].id,
    )


def _wait(operation, timeout=120.):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = operation.poll()
        if snapshot.state in {
            ProcessorState.SUCCEEDED,
            ProcessorState.CANCELLED,
            ProcessorState.FAILED,
        }:
            return snapshot
        time.sleep(.01)
    raise AssertionError("molecular operation timed out")


def _external_round(root):
    root.mkdir()
    session, identities = _session(root)
    operation = energy_operation = None
    try:
        started = time.perf_counter()
        operation = start_molecule_operation(
            PROCESSOR, root, session.project, "molecule.smiles_to_3d",
            molecule_inputs(session.project, "molecule.smiles_to_3d", *identities[:2]),
            PARAMETERS,
        )
        snapshot = _wait(operation)
        elapsed = time.perf_counter() - started
        assert snapshot.state is ProcessorState.SUCCEEDED, snapshot.error
        primary = publish_operation(operation, session)
        structure = session.project.structures[primary]
        topology = session.project.topologies[structure.topology_ids[0]]
        coordinates = numpy.asarray(structure.coordinates.values).copy()
        assert len(structure.atomic_numbers) == 21
        assert numpy.isfinite(coordinates).all()

        energy_operation = start_molecule_operation(
            PROCESSOR, root, session.project, "molecule.energy",
            molecule_inputs(
                session.project, "molecule.energy", structure.id, topology.id
            ),
            {"force_field": "MMFF94"},
        )
        energy_snapshot = _wait(energy_operation)
        assert energy_snapshot.state is ProcessorState.SUCCEEDED, energy_snapshot.error
        energy_id = publish_operation(energy_operation, session)
        external_energy = numpy.asarray(
            session.project.datasets[energy_id].data.values
        ).item()

        from chemblender_prepare.worker.molecule_operations import _force_field
        from chemblender_prepare.worker.molecule_operations import _rdkit_molecule

        # Mirrors 78c2d8d mesh.py::calc_energy; its display tolerance was 0.01 kcal/mol.
        molecule = _rdkit_molecule(structure, topology)
        legacy_energy = float(_force_field(molecule, "MMFF94").CalcEnergy())
        assert round(external_energy, 2) == round(legacy_energy, 2)
        return elapsed, coordinates, external_energy
    finally:
        close_project(session.project)
        for prepared in (operation, energy_operation):
            if prepared is not None:
                prepared.cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    assert PROCESSOR.is_file(), PROCESSOR
    with TemporaryDirectory(prefix="rdkit-removal-gate-") as temporary:
        root = Path(temporary)
        rounds = [_external_round(root / f"round-{index}") for index in range(3)]
    timings = [item[0] for item in rounds]
    for _elapsed, coordinates, _energy in rounds[1:]:
        numpy.testing.assert_allclose(coordinates, rounds[0][1], rtol=0., atol=1.e-7)
    cold_extra = timings[0] - median(timings[1:])
    assert cold_extra < 2., cold_extra

    from rdkit import rdBase

    report = {
        "schema": "chemblender_rdkit_removal_gate@1",
        "baseline_commit": "78c2d8d",
        "clock": "time.perf_counter",
        "interval": "start_molecule_operation returned through terminal worker result",
        "cache_state": "new worker process each round; first process cold, filesystem cache uncontrolled",
        "input": {"smiles": SMILES, "atom_count_with_hydrogens": 21},
        "limits_seconds": {"cold_start_extra": 2.0},
        "timings_seconds": {
            "cold": timings[0],
            "warm": timings[1:],
            "warm_median": median(timings[1:]),
            "cold_extra": cold_extra,
        },
        "versions": {
            "rdkit": rdBase.rdkitVersion,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
            "logical_processors": os.environ.get("NUMBER_OF_PROCESSORS", "unknown"),
        },
        "legacy_energy_tolerance_kcal_per_mol": 0.01,
        "external_energy_kcal_per_mol": rounds[0][2],
        "status": "passed",
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")


if __name__ == "__main__":
    main()
