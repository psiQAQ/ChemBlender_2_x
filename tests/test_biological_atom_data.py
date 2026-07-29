import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender import reader_api
from ChemBlender.core import (
    AtomicIdentityData,
    AtomicProperty,
    BiologicalAtomSiteData,
    BiologicalChain,
    BiologicalHierarchy,
    BiologicalModel,
    BiologicalResidue,
    DatasetStatus,
    FrameSet,
    ImportBatch,
    QCProject,
    Structure,
    close_project,
    open_project,
    save_project,
)
from tests.test_mol2_models import array, categorical


def atomic_identity(atom_names):
    atom_count = len(atom_names)
    zeros = numpy.zeros(atom_count, dtype=numpy.int64)
    return AtomicIdentityData(
        isotopes=array(zeros, ("atom",)),
        formal_charges=array(zeros, ("atom",)),
        atom_map_numbers=array(zeros, ("atom",)),
        atom_names=categorical(
            tuple(range(atom_count)),
            tuple(atom_names),
        ),
        stereo_labels=categorical((-1,) * atom_count, ()),
    )


def biological_mapping_fixture():
    pdb_structure = Structure(
        id=uuid4(),
        revision="pdb-reference-r1",
        atomic_numbers=(6, 7),
        coordinates=array(
            ((1.0, 2.0, 3.0), (2.0, 3.0, 4.0)),
            ("atom", "xyz"),
            "angstrom",
        ),
        atomic_identity=atomic_identity(("CA", "N")),
    )
    pdb_hierarchy = BiologicalHierarchy(
        id=uuid4(),
        revision="pdb-hierarchy-r1",
        structure_id=pdb_structure.id,
        model=BiologicalModel(1),
        chains=(BiologicalChain("A", 0),),
        residues=(BiologicalResidue(0, "GLY", 7, "A", False),),
        atom_sites=BiologicalAtomSiteData(
            serial_numbers=array(
                numpy.asarray((10, 20), dtype=numpy.int64),
                ("atom",),
            ),
            residue_indices=array(
                numpy.asarray((0, 0), dtype=numpy.int64),
                ("atom",),
            ),
            alternate_locations=categorical((0, -1), ("A",)),
            record_kinds=categorical((0, 0), ("atom",)),
        ),
        provenance_ids=(),
    )
    pdb_frames = FrameSet(
        id=uuid4(),
        revision="pdb-models-r1",
        semantic_role="coordinates",
        domain="frame",
        data=array(
            (
                ((1.0, 2.0, 3.0), (2.0, 3.0, 4.0)),
                ((1.1, 2.1, 3.1), (2.1, 3.1, 4.1)),
            ),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=pdb_structure.id,
        comments=("MODEL 1", "MODEL 2"),
    )
    occupancy = AtomicProperty(
        id=uuid4(),
        revision="pdb-occupancy-r1",
        semantic_role="occupancy",
        domain="atom",
        data=array((1.0, numpy.nan), ("atom",)),
        status=DatasetStatus.PARTIAL,
        source_calculation=None,
        provenance_ids=(),
        structure_id=pdb_structure.id,
    )
    b_factor = AtomicProperty(
        id=uuid4(),
        revision="pdb-b-factor-r1",
        semantic_role="b_factor",
        domain="atom",
        data=array((12.5, numpy.nan), ("atom",), "angstrom_squared"),
        status=DatasetStatus.PARTIAL,
        source_calculation=None,
        provenance_ids=(),
        structure_id=pdb_structure.id,
    )

    incompatible_structure = Structure(
        id=uuid4(),
        revision="pdb-incompatible-model-r1",
        atomic_numbers=(8,),
        coordinates=array(((5.0, 6.0, 7.0),), ("atom", "xyz"), "angstrom"),
        atomic_identity=atomic_identity(("O",)),
    )
    incompatible_hierarchy = BiologicalHierarchy(
        id=uuid4(),
        revision="pdb-incompatible-hierarchy-r1",
        structure_id=incompatible_structure.id,
        model=BiologicalModel(3),
        chains=(BiologicalChain("B", 1),),
        residues=(BiologicalResidue(0, "HOH", 7, "", True),),
        atom_sites=BiologicalAtomSiteData(
            serial_numbers=array(
                numpy.asarray((10,), dtype=numpy.int64),
                ("atom",),
            ),
            residue_indices=array(
                numpy.asarray((0,), dtype=numpy.int64),
                ("atom",),
            ),
            alternate_locations=categorical((-1,), ()),
            record_kinds=categorical((0,), ("hetatm",)),
        ),
        provenance_ids=(),
    )

    pqr_structure = Structure(
        id=uuid4(),
        revision="pqr-structure-r1",
        atomic_numbers=(7, 8),
        coordinates=array(
            ((8.0, 9.0, 10.0), (9.0, 10.0, 11.0)),
            ("atom", "xyz"),
            "angstrom",
        ),
        atomic_identity=atomic_identity(("NH1", "O")),
    )
    pqr_hierarchy = BiologicalHierarchy(
        id=uuid4(),
        revision="pqr-hierarchy-r1",
        structure_id=pqr_structure.id,
        model=BiologicalModel(None),
        chains=(BiologicalChain("", 0),),
        residues=(BiologicalResidue(0, "ARG", 1, "", False),),
        atom_sites=BiologicalAtomSiteData(
            serial_numbers=array(
                numpy.asarray((1, 2), dtype=numpy.int64),
                ("atom",),
            ),
            residue_indices=array(
                numpy.asarray((0, 0), dtype=numpy.int64),
                ("atom",),
            ),
            alternate_locations=categorical((-1, -1), ()),
            record_kinds=categorical((0, 0), ("atom",)),
        ),
        provenance_ids=(),
    )
    pqr_charge = AtomicProperty(
        id=uuid4(),
        revision="pqr-charge-r1",
        semantic_role="partial_charge",
        domain="atom",
        data=array((-0.30, -0.55), ("atom",), "elementary_charge"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=pqr_structure.id,
    )
    pqr_radius = AtomicProperty(
        id=uuid4(),
        revision="pqr-radius-r1",
        semantic_role="radius",
        domain="atom",
        data=array((1.55, 1.40), ("atom",), "angstrom"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=pqr_structure.id,
    )

    return ImportBatch(
        structures=(pdb_structure, incompatible_structure, pqr_structure),
        biological_hierarchies=(
            pdb_hierarchy,
            incompatible_hierarchy,
            pqr_hierarchy,
        ),
        datasets=(
            pdb_frames,
            occupancy,
            b_factor,
            pqr_charge,
            pqr_radius,
        ),
    )


def stable_atom_identity_keys(structure, hierarchy):
    def values(data):
        return tuple(
            "" if code == data.missing_code else data.categories[code]
            for code in numpy.asarray(data.codes.values)
        )

    atom_names = values(structure.atomic_identity.atom_names)
    alternate_locations = values(hierarchy.atom_sites.alternate_locations)
    record_kinds = values(hierarchy.atom_sites.record_kinds)
    residue_indices = numpy.asarray(hierarchy.atom_sites.residue_indices.values)
    keys = []
    for atom_index, residue_index in enumerate(residue_indices):
        residue = hierarchy.residues[int(residue_index)]
        chain = hierarchy.chains[residue.chain_index]
        keys.append(
            (
                record_kinds[atom_index],
                chain.chain_id,
                residue.sequence_number,
                residue.insertion_code,
                residue.residue_name,
                atom_names[atom_index],
                alternate_locations[atom_index],
            )
        )
    return tuple(keys)


class BiologicalAtomDataMappingTests(unittest.TestCase):
    def assert_mapping(self, batch):
        structures = {value.revision: value for value in batch.structures}
        hierarchies = {
            value.structure_id: value for value in batch.biological_hierarchies
        }
        datasets = {value.semantic_role: value for value in batch.datasets}
        self.assertEqual(
            set(hierarchies),
            {value.id for value in structures.values()},
        )
        for structure in structures.values():
            self.assertEqual(
                hierarchies[structure.id].atom_count,
                len(structure.atomic_numbers),
            )

        pdb_structure = structures["pdb-reference-r1"]
        pdb_hierarchy = hierarchies[pdb_structure.id]
        self.assertEqual(
            numpy.asarray(pdb_hierarchy.atom_sites.serial_numbers.values).tolist(),
            [10, 20],
        )
        self.assertEqual(
            numpy.asarray(pdb_hierarchy.atom_sites.residue_indices.values).tolist(),
            [0, 0],
        )
        self.assertEqual(pdb_hierarchy.atom_sites.alternate_locations.categories, ("A",))
        self.assertEqual(pdb_hierarchy.atom_sites.record_kinds.categories, ("atom",))
        self.assertEqual(pdb_hierarchy.chains, (BiologicalChain("A", 0),))
        self.assertEqual(
            pdb_hierarchy.residues,
            (BiologicalResidue(0, "GLY", 7, "A", False),),
        )
        self.assertEqual(
            pdb_structure.atomic_identity.atom_names.categories,
            ("CA", "N"),
        )
        self.assertEqual(
            stable_atom_identity_keys(pdb_structure, pdb_hierarchy),
            (
                ("atom", "A", 7, "A", "GLY", "CA", "A"),
                ("atom", "A", 7, "A", "GLY", "N", ""),
            ),
        )

        incompatible = structures["pdb-incompatible-model-r1"]
        incompatible_hierarchy = hierarchies[incompatible.id]
        self.assertNotEqual(incompatible.id, pdb_structure.id)
        self.assertEqual(
            numpy.asarray(
                incompatible_hierarchy.atom_sites.serial_numbers.values
            ).tolist(),
            [10],
        )
        self.assertNotEqual(
            stable_atom_identity_keys(pdb_structure, pdb_hierarchy)[0],
            stable_atom_identity_keys(incompatible, incompatible_hierarchy)[0],
        )

        frames = datasets["coordinates"]
        self.assertIsInstance(frames, FrameSet)
        self.assertEqual(frames.structure_id, pdb_structure.id)
        self.assertEqual(frames.data.shape, (2, 2, 3))

        for role, unit, status, structure_revision in (
            ("occupancy", "dimensionless", DatasetStatus.PARTIAL, "pdb-reference-r1"),
            ("b_factor", "angstrom_squared", DatasetStatus.PARTIAL, "pdb-reference-r1"),
            (
                "partial_charge",
                "elementary_charge",
                DatasetStatus.COMPLETE,
                "pqr-structure-r1",
            ),
            ("radius", "angstrom", DatasetStatus.COMPLETE, "pqr-structure-r1"),
        ):
            with self.subTest(role=role):
                dataset = datasets[role]
                structure = structures[structure_revision]
                self.assertIsInstance(dataset, AtomicProperty)
                self.assertEqual(dataset.data.dims, ("atom",))
                self.assertEqual(dataset.data.shape, (len(structure.atomic_numbers),))
                self.assertEqual(dataset.data.unit, unit)
                self.assertIs(dataset.status, status)
                self.assertEqual(dataset.structure_id, structure.id)
        numpy.testing.assert_equal(
            datasets["occupancy"].data.values,
            numpy.asarray((1.0, numpy.nan)),
        )
        numpy.testing.assert_equal(
            datasets["b_factor"].data.values,
            numpy.asarray((12.5, numpy.nan)),
        )
        self.assertEqual(
            numpy.asarray(datasets["partial_charge"].data.values).tolist(),
            [-0.30, -0.55],
        )
        self.assertEqual(
            numpy.asarray(datasets["radius"].data.values).tolist(),
            [1.55, 1.40],
        )

    def test_fixture_locks_pdb_and_pqr_mapping_without_format_models(self):
        self.assert_mapping(biological_mapping_fixture())

    def test_project_rejects_second_or_misaligned_hierarchy_atomically(self):
        batch = biological_mapping_fixture()
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        first_hierarchy = batch.biological_hierarchies[0]
        snapshot = (
            dict(project.structures),
            dict(project.biological_hierarchies),
            dict(project.datasets),
        )

        with self.assertRaisesRegex(ValueError, "only one biological hierarchy"):
            project.commit(
                ImportBatch(
                    biological_hierarchies=(
                        replace(first_hierarchy, id=uuid4()),
                    ),
                )
            )
        self.assertEqual(
            (
                project.structures,
                project.biological_hierarchies,
                project.datasets,
            ),
            snapshot,
        )

        candidate = Structure(
            id=uuid4(),
            revision="rollback-candidate-r1",
            atomic_numbers=(6,),
            coordinates=array(((0.0, 0.0, 0.0),), ("atom", "xyz"), "angstrom"),
        )
        with self.assertRaisesRegex(ValueError, "atom dimension"):
            project.commit(
                ImportBatch(
                    structures=(candidate,),
                    biological_hierarchies=(
                        replace(
                            first_hierarchy,
                            id=uuid4(),
                            structure_id=candidate.id,
                        ),
                    ),
                )
            )
        self.assertNotIn(candidate.id, project.structures)
        self.assertEqual(
            (
                project.structures,
                project.biological_hierarchies,
                project.datasets,
            ),
            snapshot,
        )

    def test_sidecar_and_canonical_round_trips_preserve_mapping(self):
        batch = biological_mapping_fixture()
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = reader_api.public_batch_document(
                reader_api.public_batch_from_internal(batch),
                root,
            )
            canonical = reader_api.internal_batch_from_public(
                reader_api.public_batch_from_document(document, root)
            )
            self.assert_mapping(canonical)

            reopened = open_project(save_project(root / "pdb-pqr.cbq", project))
            try:
                self.assert_mapping(
                    ImportBatch(
                        structures=tuple(reopened.structures.values()),
                        biological_hierarchies=tuple(
                            reopened.biological_hierarchies.values()
                        ),
                        datasets=tuple(reopened.datasets.values()),
                    )
                )
            finally:
                close_project(reopened)


if __name__ == "__main__":
    unittest.main()
