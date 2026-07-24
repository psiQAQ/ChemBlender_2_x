import copy
import dataclasses
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    ImportBatch,
    OrbitalChannel,
    OrbitalKind,
    OrbitalSet,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    VibrationalModeSet,
    open_project,
    save_project,
)
from ChemBlender.core.sidecar import SidecarIntegrityError
from tests.test_sidecar_storage import DATASET_ID, PROVENANCE_ID, sample_project, write_manifest


def graph_project():
    project = sample_project()
    structure = next(iter(project.structures.values()))
    basis = BasisSet(
        id=uuid4(),
        revision="basis-r1",
        structure_id=structure.id,
        name="minimal",
        shells=(
            BasisShell(
                center_atom=0,
                angular_momenta=(0,),
                kinds=(BasisFunctionKind.CARTESIAN,),
                exponents=ArrayData(
                    numpy.asarray([1.0]), ("primitive",), "inverse_square_bohr"
                ),
                coefficients=ArrayData(
                    numpy.asarray([[1.0]]),
                    ("primitive", "contraction"),
                    "dimensionless",
                ),
            ),
        ),
        conventions=(BasisConvention(0, BasisFunctionKind.CARTESIAN, ("1",)),),
        primitive_normalization="l2",
        provenance_ids=(PROVENANCE_ID,),
    )
    orbitals = OrbitalSet(
        id=uuid4(),
        revision="orbital-r1",
        structure_id=structure.id,
        basis_set_id=basis.id,
        kind=OrbitalKind.RESTRICTED,
        channels=(
            OrbitalChannel(
                label="restricted",
                coefficients=ArrayData(
                    numpy.asarray([[1.0]]),
                    ("orbital", "basis_function"),
                    "dimensionless",
                ),
                energies=None,
                occupations=None,
                irreps=(),
            ),
        ),
        provenance_ids=(PROVENANCE_ID,),
    )
    vibrations = VibrationalModeSet(
        id=uuid4(),
        revision="vibration-r1",
        semantic_role="vibrational_modes",
        domain="mode",
        data=ArrayData(numpy.asarray([1000.0]), ("mode",), "inverse_centimeter"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        structure_id=structure.id,
        displacements=ArrayData(
            numpy.zeros((1, 2, 3)), ("mode", "atom", "xyz"), "angstrom"
        ),
        reduced_masses=None,
        force_constants=None,
        ir_intensities=None,
        raman_activities=None,
        symmetries=None,
        displacement_convention="mass_weighted",
    )
    spectrum = Spectrum(
        id=uuid4(),
        revision="spectrum-r1",
        semantic_role="ir_spectrum",
        domain="frequency",
        data=ArrayData(
            numpy.asarray([1.0]), ("sample",), "kilometer_per_mole"
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        axis=ArrayData(
            numpy.asarray([1000.0]), ("sample",), "inverse_centimeter"
        ),
        kind=SpectrumKind.IR,
        profile=SpectrumProfile.STICK,
        source_dataset_id=vibrations.id,
        fwhm=None,
        selection_policy="all",
    )
    calculation = CalculationRecord(
        id=uuid4(),
        revision="calculation-r1",
        status=CalculationStatus.SUCCESS,
        input_structure_ids=(structure.id,),
        result_structure_ids=(),
        dataset_ids=(DATASET_ID,),
        provenance_ids=(PROVENANCE_ID,),
    )
    project.commit(
        ImportBatch(
            calculations=(calculation,),
            datasets=(vibrations, spectrum),
            basis_sets=(basis,),
            orbital_sets=(orbitals,),
        )
    )
    return project


def typed_object(value, type_name):
    if isinstance(value, dict):
        if value.get("$type") == type_name:
            return value
        for item in value.values():
            found = typed_object(item, type_name)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = typed_object(item, type_name)
            if found is not None:
                return found
    return None


class ProjectGraphIntegrityTests(unittest.TestCase):
    def test_save_rejects_invalid_in_memory_graph_before_publication(self):
        project = graph_project()
        atomic = next(
            value
            for value in project.datasets.values()
            if value.__class__.__name__ == "AtomicProperty"
        )
        project.datasets[atomic.id] = dataclasses.replace(
            atomic, structure_id=uuid4()
        )

        with TemporaryDirectory() as directory:
            root = Path(directory) / "invalid.cbq"
            with self.assertRaises(SidecarIntegrityError):
                save_project(root, project)
            self.assertFalse(root.exists())

    def test_save_rejects_registry_key_mismatch_before_publication(self):
        project = graph_project()
        structure = next(iter(project.structures.values()))
        project.structures = {uuid4(): structure}

        with TemporaryDirectory() as directory:
            root = Path(directory) / "invalid-registry.cbq"
            with self.assertRaises(SidecarIntegrityError):
                save_project(root, project)
            self.assertFalse(root.exists())

    def test_open_rejects_tampered_relationships_with_valid_manifest_hash(self):
        project = graph_project()
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "graph.cbq", project)
            manifest_path = root / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            mutations = {
                "atomic_structure": ("AtomicProperty", "structure_id"),
                "calculation_dataset": ("CalculationRecord", "dataset_ids"),
                "spectrum_source": ("Spectrum", "source_dataset_id"),
                "orbital_basis": ("OrbitalSet", "basis_set_id"),
                "grid_structure": ("Grid3D", "structure_id"),
            }

            for name, (type_name, field) in mutations.items():
                with self.subTest(name=name):
                    manifest = copy.deepcopy(original)
                    target = typed_object(manifest["project"], type_name)
                    if field == "dataset_ids":
                        target[field] = {"$tuple": [{"$uuid": str(uuid4())}]}
                    else:
                        target[field] = {"$uuid": str(uuid4())}
                    write_manifest(manifest_path, manifest)
                    with self.assertRaises(SidecarIntegrityError):
                        open_project(root)

    def test_open_rejects_spectrum_source_with_wrong_dataset_type(self):
        project = graph_project()
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "spectrum.cbq", project)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            spectrum = typed_object(manifest["project"], "Spectrum")
            spectrum["source_dataset_id"] = {"$uuid": str(DATASET_ID)}
            write_manifest(manifest_path, manifest)

            with self.assertRaises(SidecarIntegrityError):
                open_project(root)


if __name__ == "__main__":
    unittest.main()
