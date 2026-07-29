import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    AtomicProperty,
    DatasetStatus,
    IssueKind,
    PropertyDataset,
)
from ChemBlender.core.reader_catalog import (
    builtin_reader_registry,
    reader_capability_document,
)
from ChemBlender.reader_api import ParseRequest
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


FIXTURES = Path(__file__).parent / "fixtures" / "poscar"


class PoscarReaderTests(unittest.TestCase):
    def test_maps_periodic_structure_and_selective_dynamics(self):
        from ChemBlender.core.formats.poscar import parse_poscar

        batch = parse_poscar(FIXTURES / "cscl-selective.vasp")
        structure, = batch.structures
        self.assertEqual(structure.atomic_numbers, (55, 17))
        self.assertEqual(structure.periodic.site_labels, ("Cs1", "Cl1"))
        self.assertEqual(structure.periodic.pbc, (True, True, True))
        numpy.testing.assert_allclose(
            structure.coordinates.values,
            numpy.asarray(structure.periodic.fractional_coordinates.values)
            @ numpy.asarray(structure.cell.values),
        )
        selective = next(
            value
            for value in batch.datasets
            if value.semantic_role == "selective_dynamics"
        )
        self.assertIsInstance(selective, AtomicProperty)
        self.assertEqual(selective.data.dims, ("atom", "xyz"))
        self.assertEqual(selective.data.unit, "dimensionless")
        self.assertEqual(selective.data.dtype, "bool")
        self.assertEqual(selective.status, DatasetStatus.COMPLETE)
        self.assertEqual(selective.structure_id, structure.id)
        self.assertEqual(
            tuple(map(tuple, selective.data.values)),
            ((False, False, False), (True, False, True)),
        )

    def test_preserves_velocity_and_source_convention_metadata(self):
        from ChemBlender.core.formats.poscar import parse_poscar

        batch = parse_poscar(FIXTURES / "velocities.CONTCAR")
        structure, = batch.structures
        velocity = next(
            value
            for value in batch.datasets
            if value.semantic_role == "atomic_velocity"
        )
        lattice_velocity = next(
            value
            for value in batch.datasets
            if value.semantic_role == "lattice_velocity"
        )
        self.assertIsInstance(velocity, AtomicProperty)
        self.assertIsInstance(lattice_velocity, PropertyDataset)
        self.assertEqual(velocity.status, DatasetStatus.AMBIGUOUS)
        self.assertEqual(velocity.data.unit, "unknown")
        self.assertEqual(lattice_velocity.data.shape, (3, 3))
        parameters = dict(batch.provenance[0].parameters)
        self.assertEqual(parameters["comment"], "velocity block")
        self.assertEqual(parameters["scale"], 1.0)
        self.assertEqual(parameters["coordinate_mode"], "cartesian")
        self.assertEqual(parameters["species_order"], ("Na", "Cl"))
        self.assertEqual(parameters["counts"], (1, 1))
        self.assertEqual(parameters["velocity_mode"], "cartesian")
        self.assertEqual(parameters["lattice_velocity_initialization_state"], 1.0)
        self.assertEqual(structure.periodic.cif_envelope_id, None)

    def test_vasp4_requires_explicit_species_assignment(self):
        from ChemBlender.core.formats.poscar import parse_poscar

        source = FIXTURES / "vasp4-counts.POSCAR"
        preview = parse_poscar(source)
        self.assertEqual(preview.structures, ())
        self.assertTrue(
            any(
                issue.kind is IssueKind.AMBIGUOUS
                and issue.path == "poscar.species"
                for issue in preview.report.issues
            )
        )
        self.assertEqual(dict(preview.provenance[0].parameters)["counts"], (2, 1))

        batch = parse_poscar(source, species=("Na", "Cl"))
        structure, = batch.structures
        self.assertEqual(structure.atomic_numbers, (11, 11, 17))
        self.assertEqual(
            structure.periodic.site_labels,
            ("Na1", "Na2", "Cl1"),
        )
        self.assertEqual(
            dict(batch.provenance[0].parameters)["species_assignment"],
            ("Na", "Cl"),
        )

    def test_invalid_scale_never_creates_a_structure(self):
        from ChemBlender.core.formats.poscar import parse_poscar

        with TemporaryDirectory() as directory:
            source = Path(directory) / "POSCAR"
            source.write_text(
                "invalid\n"
                "0\n"
                "1 0 0\n0 1 0\n0 0 1\n"
                "H\n1\nDirect\n0 0 0\n",
                encoding="utf-8",
            )
            batch = parse_poscar(source)

        self.assertEqual(batch.structures, ())
        self.assertTrue(
            any(issue.kind is IssueKind.INVALID for issue in batch.report.issues)
        )

    def test_parse_request_uses_species_parameter_and_checks_hash(self):
        from ChemBlender.core.formats.poscar import POSCAR_READER

        source = FIXTURES / "vasp4-counts.POSCAR"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with TemporaryDirectory() as directory:
            request = ParseRequest(
                source,
                digest,
                "balanced",
                {"species": "Na,Cl"},
                Path(directory),
                lambda _event: None,
                lambda: False,
                uuid4(),
            )
            batch = POSCAR_READER.parse_request(request)
            self.assertEqual(batch.structures[0].atomic_numbers, (11, 11, 17))
            bad = ParseRequest(
                source,
                "0" * 64,
                "balanced",
                {"species": "Na,Cl"},
                Path(directory),
                lambda _event: None,
                lambda: False,
                uuid4(),
            )
            with self.assertRaisesRegex(ValueError, "hash"):
                POSCAR_READER.parse_request(bad)

    def test_builtin_registry_selects_suffixless_poscar(self):
        registry = builtin_reader_registry()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "POSCAR"
            shutil.copyfile(FIXTURES / "cscl.vasp", source)
            self.assertEqual(registry.select(source).reader_id, "poscar")
            self.assertEqual(
                registry.parse(source).structures[0].atomic_numbers,
                (55, 17),
            )

    def test_public_reader_registry_returns_a_conforming_batch(self):
        source = FIXTURES / "cscl.vasp"
        with TemporaryDirectory() as directory:
            request = ParseRequest(
                source,
                hashlib.sha256(source.read_bytes()).hexdigest(),
                "balanced",
                {},
                Path(directory),
                lambda _event: None,
                lambda: False,
                uuid4(),
            )
            batch = builtin_reader_plugin_registry().parse("poscar", request)

        self.assertEqual(batch.report.reader_id, "poscar")
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(
            set(batch.report.created_entity_ids),
            {
                *(value.id for value in batch.structures),
                *(value.id for value in batch.datasets),
                *(value.id for value in batch.provenance),
            },
        )

    def test_capability_matrix_matches_catalog(self):
        document = reader_capability_document()
        entry = next(
            value
            for value in document["readers"]
            if value["reader_id"] == "poscar"
        )
        self.assertEqual(entry["availability_contract"], {"kind": "always"})
        self.assertEqual(entry["extensions"], [".vasp", ".poscar", ".contcar"])
        self.assertEqual(
            entry["capabilities"],
            {
                "atomic_property": "supported",
                "crystal": "supported",
                "structure": "supported",
            },
        )
        production = json.loads(
            (
                Path(__file__).parents[1]
                / "docs/quantum-visualization/reader-capability-matrix.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            next(
                value
                for value in production["readers"]
                if value["reader_id"] == "poscar"
            ),
            entry,
        )


if __name__ == "__main__":
    unittest.main()
