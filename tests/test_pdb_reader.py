import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender.core import (
    BiologicalHierarchy,
    CapabilitySupport,
    close_project,
    DatasetStatus,
    FrameSet,
    open_project,
    QCProject,
    QualityStatus,
    ReaderNotFoundError,
    save_project,
    SniffMatch,
    TopologySource,
    unit_cell_parameters,
)
from ChemBlender.core.formats import pdb
from ChemBlender.core.model.project import validate_project_graph
from ChemBlender.core.reader_catalog import (
    builtin_reader_descriptors,
    builtin_reader_registry,
)
from ChemBlender.reader_api import (
    internal_batch_from_public,
    ParseRequest,
    public_batch_document,
    public_batch_from_document,
    public_batch_from_internal,
    builtin_reader_plugin_registry,
)
from ChemBlender.reader_api.conformance import (
    ReaderConformanceCase,
    run_reader_conformance,
)


FIXTURES = Path(__file__).parent / "fixtures" / "pdb"


def atom_line(
    serial,
    atom_name_field,
    *,
    record_name=b"ATOM  ",
    residue_name=b"GLY",
    chain=b"A",
    residue_number=1,
    insertion_code=b" ",
    altloc=b" ",
    x=0.0,
    occupancy=1.0,
    b_factor=10.0,
    element=b"C",
):
    line = bytearray(b" " * 80)
    line[0:6] = record_name
    line[6:11] = f"{serial:5d}".encode()
    line[12:16] = atom_name_field
    line[16:17] = altloc
    line[17:20] = residue_name
    line[21:22] = chain
    line[22:26] = f"{residue_number:4d}".encode()
    line[26:27] = insertion_code
    line[30:38] = f"{x:8.3f}".encode()
    line[38:46] = b"   2.000"
    line[46:54] = b"   3.000"
    if occupancy is not None:
        line[54:60] = f"{occupancy:6.2f}".encode()
    if b_factor is not None:
        line[60:66] = f"{b_factor:6.2f}".encode()
    line[76:78] = element.rjust(2)
    return bytes(line)


def model_line(number):
    line = bytearray(b" " * 14)
    line[0:6] = b"MODEL "
    line[10:14] = f"{number:4d}".encode()
    return bytes(line)


def conect_line(source_serial, *target_serials):
    return b"CONECT" + b"".join(
        f"{serial:5d}".encode()
        for serial in (source_serial, *target_serials)
    )


def parse_bytes(raw, name="fixture.pdb"):
    with TemporaryDirectory() as directory:
        source = Path(directory) / name
        source.write_bytes(raw)
        return pdb.parse_pdb(source)


def categorical_values(data):
    return tuple(
        "" if int(code) == data.missing_code else data.categories[int(code)]
        for code in numpy.asarray(data.codes.values)
    )


def identity_keys(structure, hierarchy):
    names = categorical_values(structure.atomic_identity.atom_names)
    altlocs = categorical_values(hierarchy.atom_sites.alternate_locations)
    kinds = categorical_values(hierarchy.atom_sites.record_kinds)
    residue_indices = numpy.asarray(hierarchy.atom_sites.residue_indices.values)
    keys = []
    for atom_index, residue_index in enumerate(residue_indices):
        residue = hierarchy.residues[int(residue_index)]
        chain = hierarchy.chains[residue.chain_index]
        keys.append(
            (
                kinds[atom_index],
                chain.chain_id,
                residue.sequence_number,
                residue.insertion_code,
                residue.residue_name,
                names[atom_index],
                altlocs[atom_index],
            )
        )
    return tuple(keys)


class PDBReaderTests(unittest.TestCase):
    def test_single_model_maps_structure_hierarchy_identity_and_properties(self):
        self.assertTrue(hasattr(pdb, "parse_pdb"))

        batch = pdb.parse_pdb(FIXTURES / "altloc.pdb")

        self.assertEqual(len(batch.structures), 1)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (6, 6))
        self.assertEqual(
            structure.atomic_identity.atom_names.categories,
            ("CA",),
        )
        self.assertEqual(len(batch.biological_hierarchies), 1)
        hierarchy = batch.biological_hierarchies[0]
        self.assertIsInstance(hierarchy, BiologicalHierarchy)
        self.assertEqual(hierarchy.structure_id, structure.id)
        self.assertEqual(hierarchy.atom_sites.alternate_locations.categories, ("A", "B"))
        datasets = {value.semantic_role: value for value in batch.datasets}
        self.assertEqual(set(datasets), {"occupancy", "b_factor"})
        self.assertEqual(
            numpy.asarray(datasets["occupancy"].data.values).tolist(),
            [0.6, 0.4],
        )
        self.assertEqual(datasets["occupancy"].data.unit, "dimensionless")
        self.assertEqual(datasets["b_factor"].data.unit, "angstrom_squared")
        self.assertTrue(
            all(value.status is DatasetStatus.COMPLETE for value in datasets.values())
        )
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        self.assertEqual(
            batch.report.created_entity_ids,
            batch.source_revisions[0].created_entity_ids,
        )
        self.assertEqual(
            batch.source_revisions[0].diagnostic_ids,
            tuple(value.id for value in batch.diagnostics),
        )

    def test_reordered_compatible_models_form_one_deterministic_frame_set(self):
        raw = b"\n".join(
            (
                model_line(1),
                atom_line(1, b" N  ", x=1.0, element=b"N"),
                atom_line(2, b" CA ", x=2.0),
                b"ENDMDL",
                model_line(2),
                atom_line(20, b" CA ", x=20.0),
                atom_line(10, b" N  ", x=10.0, element=b"N"),
                b"ENDMDL",
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.biological_hierarchies), 1)
        self.assertEqual(
            identity_keys(batch.structures[0], batch.biological_hierarchies[0]),
            (
                ("atom", "A", 1, "", "GLY", "N", ""),
                ("atom", "A", 1, "", "GLY", "CA", ""),
            ),
        )
        frames = [value for value in batch.datasets if isinstance(value, FrameSet)]
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].comments, ("MODEL 1", "MODEL 2"))
        self.assertEqual(
            numpy.asarray(frames[0].data.values)[:, :, 0].tolist(),
            [[1.0, 2.0], [10.0, 20.0]],
        )
        repeated = parse_bytes(raw)
        self.assertEqual(
            tuple(value.id for value in batch.structures + batch.datasets),
            tuple(value.id for value in repeated.structures + repeated.datasets),
        )

    def test_repeated_model_numbers_keep_frames_and_topologies_occurrence_scoped(self):
        raw = b"\n".join(
            (
                model_line(1),
                atom_line(1, b" N  ", x=1.0, element=b"N"),
                atom_line(2, b" CA ", x=2.0),
                conect_line(1, 2),
                b"ENDMDL",
                model_line(1),
                atom_line(2, b" CA ", x=20.0),
                atom_line(1, b" N  ", x=10.0, element=b"N"),
                conect_line(1, 2),
                b"ENDMDL",
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertEqual(len(batch.structures), 1)
        frames = [value for value in batch.datasets if isinstance(value, FrameSet)]
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].comments, ("MODEL 1", "MODEL 1"))
        self.assertEqual(
            numpy.asarray(frames[0].data.values)[:, :, 0].tolist(),
            [[1.0, 2.0], [10.0, 20.0]],
        )
        self.assertEqual(len(batch.topologies), 2)
        self.assertEqual(
            tuple(
                (
                    dict(topology.inference_parameters)["model_number"],
                    dict(topology.inference_parameters)["model_occurrence"],
                    numpy.asarray(topology.bond_indices.values).tolist(),
                )
                for topology in batch.topologies
            ),
            ((1, 1, [[0, 1]]), (1, 2, [[0, 1]])),
        )
        self.assertTrue(
            any(
                issue.kind.value == "ambiguous"
                and issue.path == "record[5].model"
                for issue in batch.report.issues
            )
        )

    def test_missing_different_and_duplicate_identity_split_models_with_diagnostics(self):
        raw = b"\n".join(
            (
                model_line(1),
                atom_line(1, b" CA ", altloc=b"A"),
                atom_line(2, b" N  ", element=b"N"),
                b"ENDMDL",
                model_line(2),
                atom_line(3, b" CA ", altloc=b"A"),
                b"ENDMDL",
                model_line(3),
                atom_line(4, b" CA ", altloc=b"B"),
                atom_line(5, b" N  ", element=b"N"),
                b"ENDMDL",
                model_line(4),
                atom_line(6, b" CA ", residue_number=2, altloc=b"A"),
                atom_line(7, b" N  ", element=b"N"),
                b"ENDMDL",
                model_line(5),
                atom_line(8, b" CA ", altloc=b"A"),
                atom_line(9, b" CA ", altloc=b"A"),
                b"ENDMDL",
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertEqual(len(batch.structures), 5)
        self.assertFalse(any(isinstance(value, FrameSet) for value in batch.datasets))
        self.assertEqual(
            tuple(value.model.number for value in batch.biological_hierarchies),
            (1, 2, 3, 4, 5),
        )
        diagnostics = {
            value.field_path: value.message for value in batch.diagnostics
            if value.field_path.startswith("model[")
        }
        for model_number in (2, 3, 4):
            message = diagnostics[f"model[{model_number}].identity"]
            self.assertIn("missing=", message)
            self.assertIn("additional=", message)
        self.assertIn(
            "duplicate seven-field atom identity",
            diagnostics["model[5].identity"],
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "duplicate.pdb"
            source.write_bytes(raw)
            request = ParseRequest(
                source,
                hashlib.sha256(raw).hexdigest(),
                "strict",
                {},
                root,
                lambda _event: None,
                lambda: False,
            )
            with self.assertRaisesRegex(ValueError, "invalid model mapping"):
                pdb.parse_pdb_request(request)

    def test_conect_maps_explicit_topology_and_absence_does_not_infer(self):
        connected = pdb.parse_pdb(FIXTURES / "conect.pdb")

        self.assertEqual(len(connected.topologies), 1)
        topology = connected.topologies[0]
        self.assertIs(topology.source_kind, TopologySource.EXPLICIT_FILE)
        self.assertIs(topology.quality_status, QualityStatus.AMBIGUOUS)
        self.assertEqual(
            numpy.asarray(topology.bond_indices.values).tolist(),
            [[0, 1], [1, 2]],
        )
        self.assertEqual(
            numpy.asarray(topology.bond_orders.values).tolist(),
            [2.0, 0.0],
        )
        self.assertEqual(connected.structures[0].topology_ids, (topology.id,))

        bondless = pdb.parse_pdb(FIXTURES / "altloc.pdb")
        self.assertEqual(bondless.topologies, ())
        self.assertEqual(bondless.structures[0].topology_ids, ())

    def test_compatible_model_topologies_remain_model_scoped(self):
        raw = b"\n".join(
            (
                model_line(1),
                atom_line(1, b" N  ", element=b"N"),
                atom_line(2, b" CA "),
                conect_line(1, 2),
                b"ENDMDL",
                model_line(2),
                atom_line(1, b" CA "),
                atom_line(2, b" N  ", element=b"N"),
                conect_line(1, 2),
                b"ENDMDL",
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.topologies), 2)
        self.assertEqual(
            tuple(
                dict(value.inference_parameters)["model_number"]
                for value in batch.topologies
            ),
            (1, 2),
        )
        self.assertEqual(
            tuple(
                numpy.asarray(value.bond_indices.values).tolist()
                for value in batch.topologies
            ),
            ([[0, 1]], [[0, 1]]),
        )

    def test_duplicate_identity_conect_recovers_by_source_atom_index(self):
        raw = b"\n".join(
            (
                model_line(1),
                atom_line(1, b" N  ", element=b"N"),
                atom_line(2, b" N  ", element=b"N"),
                atom_line(3, b" CA "),
                atom_line(4, b" CA "),
                conect_line(1, 2, 1, 9),
                b"ENDMDL",
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertEqual(len(batch.structures[0].atomic_numbers), 4)
        self.assertEqual(len(batch.topologies), 1)
        self.assertEqual(
            numpy.asarray(batch.topologies[0].bond_indices.values).tolist(),
            [[0, 1]],
        )
        duplicate = next(
            issue
            for issue in batch.report.issues
            if issue.path == "model[1].identity"
        )
        self.assertEqual(
            duplicate.message,
            (
                "duplicate seven-field atom identity prevents MODEL "
                "alignment: duplicates=((('atom', 'A', 1, '', 'GLY', "
                "'CA', ''), 2), (('atom', 'A', 1, '', 'GLY', 'N', ''), "
                "2))"
            ),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "duplicate-conect.pdb"
            source.write_bytes(raw)
            request = ParseRequest(
                source,
                hashlib.sha256(raw).hexdigest(),
                "strict",
                {},
                root,
                lambda _event: None,
                lambda: False,
            )
            with self.assertRaises((pdb.PDBSyntaxError, ValueError)):
                pdb.parse_pdb_request(request)

    def test_missing_occupancy_and_b_factor_are_nan_partial_properties(self):
        raw = b"\n".join(
            (
                atom_line(1, b" C1 ", occupancy=0.75, b_factor=12.0),
                atom_line(2, b" C2 ", occupancy=None, b_factor=None),
                b"",
            )
        )

        batch = parse_bytes(raw)
        datasets = {value.semantic_role: value for value in batch.datasets}

        for role in ("occupancy", "b_factor"):
            values = numpy.asarray(datasets[role].data.values)
            self.assertTrue(numpy.isfinite(values[0]))
            self.assertTrue(numpy.isnan(values[1]))
            self.assertIs(datasets[role].status, DatasetStatus.PARTIAL)

    def test_occupancy_bounds_and_missing_are_partial_with_or_without_cryst1(self):
        zero = parse_bytes(atom_line(1, b" C0 ", occupancy=0.0) + b"\n")
        zero_occupancy = next(
            value
            for value in zero.datasets
            if value.semantic_role == "occupancy"
        )
        self.assertEqual(
            numpy.asarray(zero_occupancy.data.values).tolist(),
            [0.0],
        )
        self.assertIs(zero_occupancy.status, DatasetStatus.COMPLETE)

        atom_records = b"\n".join(
            (
                atom_line(1, b" C1 ", occupancy=-0.1),
                atom_line(2, b" C2 ", occupancy=0.0),
                atom_line(3, b" C3 ", occupancy=1.0),
                atom_line(4, b" C4 ", occupancy=None),
                atom_line(5, b" C5 ", occupancy=1.1),
                b"",
            )
        )

        for with_cryst1 in (False, True):
            with self.subTest(with_cryst1=with_cryst1):
                raw = atom_records
                if with_cryst1:
                    raw = (FIXTURES / "cryst1.pdb").read_bytes() + raw
                batch = parse_bytes(raw)
                occupancy = next(
                    value
                    for value in batch.datasets
                    if value.semantic_role == "occupancy"
                )
                values = numpy.asarray(occupancy.data.values)
                self.assertTrue(numpy.isnan(values[0]))
                self.assertEqual(values[1:3].tolist(), [0.0, 1.0])
                self.assertTrue(numpy.isnan(values[3]))
                self.assertTrue(numpy.isnan(values[4]))
                self.assertIs(occupancy.status, DatasetStatus.PARTIAL)
                self.assertEqual(
                    sum(
                        issue.kind.value == "invalid"
                        and issue.path.endswith(".occupancy")
                        for issue in batch.report.issues
                    ),
                    2,
                )
                if with_cryst1:
                    periodic = numpy.asarray(
                        batch.structures[0].periodic.occupancies.values
                    )
                    numpy.testing.assert_equal(periodic, values)

    def test_nonpositive_atom_serials_are_skipped_balanced_and_rejected_strict(self):
        raw = b"\n".join(
            (
                atom_line(0, b" C0 "),
                atom_line(-1, b" CN "),
                atom_line(1, b" C1 "),
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertEqual(
            numpy.asarray(
                batch.biological_hierarchies[0].atom_sites.serial_numbers.values
            ).tolist(),
            [1],
        )
        self.assertEqual(
            tuple(
                issue.path
                for issue in batch.report.issues
                if issue.path.endswith(".serial")
            ),
            ("record[0].serial", "record[1].serial"),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid-serial.pdb"
            source.write_bytes(raw)
            request = ParseRequest(
                source,
                hashlib.sha256(raw).hexdigest(),
                "strict",
                {},
                root,
                lambda _event: None,
                lambda: False,
            )
            with self.assertRaisesRegex(pdb.PDBSyntaxError, "invalid records"):
                pdb.parse_pdb_request(request)

    def test_cryst1_uses_existing_cell_periodic_and_source_metadata(self):
        raw = (
            (FIXTURES / "cryst1.pdb").read_bytes()
            + atom_line(1, b" C1 ", x=1.0)
            + b"\n"
        )

        batch = parse_bytes(raw)
        structure = batch.structures[0]

        self.assertEqual(structure.cell.dims, ("cell_vector", "xyz"))
        numpy.testing.assert_allclose(
            unit_cell_parameters(structure.cell),
            (42.0, 43.0, 44.0, 90.0, 100.0, 120.0),
        )
        self.assertEqual(
            structure.periodic.declared_space_group_name,
            "P 21 21 21",
        )
        parameters = dict(batch.provenance[0].parameters)
        self.assertEqual(parameters["cryst1_source_record"], "CRYST1")
        self.assertEqual(parameters["cryst1_z"], 4)

    def test_invalid_cryst1_symmetry_stays_raw_not_typed(self):
        cryst1 = bytearray((FIXTURES / "cryst1.pdb").read_bytes().rstrip(b"\r\n"))
        cryst1[55:66] = b"NOT A GROUP"
        raw = bytes(cryst1) + b"\n" + atom_line(1, b" C1 ") + b"\n"

        batch = parse_bytes(raw)

        self.assertIsNone(
            batch.structures[0].periodic.declared_space_group_name
        )
        self.assertEqual(
            dict(batch.provenance[0].parameters)["cryst1_space_group_field"],
            "NOT A GROUP",
        )
        self.assertIn(
            ("invalid", "record[0].space_group"),
            tuple(
                (issue.kind.value, issue.path)
                for issue in batch.report.issues
            ),
        )

    def test_nonpositive_model_number_recovers_without_forging_typed_number(self):
        raw = b"\n".join(
            (
                model_line(0),
                atom_line(1, b" C1 "),
                b"ENDMDL",
                b"",
            )
        )

        batch = parse_bytes(raw)

        self.assertIsNone(batch.biological_hierarchies[0].model.number)
        self.assertIn(
            ("invalid", "model[0].number"),
            tuple(
                (issue.kind.value, issue.path)
                for issue in batch.report.issues
            ),
        )

    def test_balanced_recovers_valid_atoms_strict_rejects_and_zero_atom_fails(self):
        balanced = pdb.parse_pdb(FIXTURES / "malformed.pdb")
        self.assertIn(
            3,
            tuple(
                value.model.number for value in balanced.biological_hierarchies
            ),
        )
        self.assertTrue(
            any(value.quality_status is QualityStatus.INVALID for value in balanced.diagnostics)
        )
        with self.assertRaisesRegex(ValueError, "no valid atoms"):
            pdb.parse_pdb(FIXTURES / "cryst1.pdb")

        raw = (FIXTURES / "malformed.pdb").read_bytes()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "strict.pdb"
            source.write_bytes(raw)
            request = ParseRequest(
                source,
                hashlib.sha256(raw).hexdigest(),
                "strict",
                {},
                root,
                lambda _event: None,
                lambda: False,
            )
            with self.assertRaises(ValueError):
                pdb.parse_pdb_request(request)

    def test_builtin_catalog_registers_pdb_reader(self):
        descriptors = {
            descriptor.reader_id: descriptor
            for descriptor in builtin_reader_descriptors()
        }

        self.assertIn("pdb", descriptors)
        self.assertEqual(descriptors["pdb"].extensions, (".pdb",))
        self.assertEqual(
            dict(descriptors["pdb"].capabilities),
            {
                "atomic_identity": CapabilitySupport.SUPPORTED,
                "atomic_property": CapabilitySupport.SUPPORTED,
                "crystal": CapabilitySupport.PARTIAL,
                "hierarchy": CapabilitySupport.SUPPORTED,
                "multi_model": CapabilitySupport.SUPPORTED,
                "structure": CapabilitySupport.SUPPORTED,
                "topology": CapabilitySupport.PARTIAL,
                "trajectory": CapabilitySupport.SUPPORTED,
            },
        )

    def test_sniff_does_not_claim_ordinary_text_or_pqr(self):
        registry = builtin_reader_registry()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            text = root / "notes.pdb"
            text.write_bytes(b"ordinary text\n")
            pqr_source = root / "charges.pdb"
            pqr_source.write_bytes(
                b"ATOM 1 N ARG A 1 1.000 2.000 3.000 -0.3000 1.5500\n"
            )
            for source in (text, pqr_source):
                with self.subTest(source=source.name):
                    self.assertIs(
                        next(
                            value
                            for value in builtin_reader_descriptors()
                            if value.reader_id == "pdb"
                        ).sniff(source, source.read_bytes()).match,
                        SniffMatch.NONE,
                    )
                    with self.assertRaises(ReaderNotFoundError):
                        registry.select(source)

    def test_reader_api_v1_conformance(self):
        registry = builtin_reader_plugin_registry()
        result = run_reader_conformance(
            ReaderConformanceCase(
                "pdb-altloc",
                registry,
                "pdb",
                FIXTURES / "altloc.pdb",
                (
                    "atomic_identity",
                    "atomic_property",
                    "crystal",
                    "hierarchy",
                    "multi_model",
                    "structure",
                    "topology",
                    "trajectory",
                ),
            )
        )

        self.assertTrue(result.passed, result.as_dict())

    def test_multimodel_periodic_batch_round_trips_sidecar_and_canonical_document(self):
        raw = (FIXTURES / "cryst1.pdb").read_bytes() + b"\n".join(
            (
                model_line(1),
                atom_line(
                    1,
                    b" N  ",
                    x=1.0,
                    occupancy=None,
                    b_factor=None,
                    element=b"N",
                ),
                atom_line(2, b" CA ", x=2.0),
                conect_line(1, 2),
                b"ENDMDL",
                model_line(2),
                atom_line(20, b" CA ", x=20.0),
                atom_line(
                    10,
                    b" N  ",
                    x=10.0,
                    occupancy=None,
                    b_factor=None,
                    element=b"N",
                ),
                conect_line(10, 20),
                b"ENDMDL",
                b"",
            )
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "roundtrip.pdb"
            source.write_bytes(raw)
            batch = pdb.parse_pdb(source)

            project = QCProject(uuid4(), "1.0")
            project.commit(batch)
            validate_project_graph(project)
            restored = open_project(
                save_project(root / "roundtrip.cbq", project)
            )
            try:
                validate_project_graph(restored)
                revision = next(iter(restored.source_revisions.values()))
                self.assertEqual(
                    revision.created_entity_ids,
                    batch.report.created_entity_ids,
                )
                self.assertEqual(len(restored.structures), 1)
                self.assertEqual(len(restored.topologies), 2)
                self.assertEqual(len(restored.biological_hierarchies), 1)
                self.assertEqual(len(restored.datasets), 3)
            finally:
                close_project(restored)

            canonical_root = root / "canonical"
            canonical_root.mkdir()
            public = public_batch_from_internal(batch)
            document = public_batch_document(public, canonical_root)
            restored_batch = internal_batch_from_public(
                public_batch_from_document(document, canonical_root)
            )
            canonical_project = QCProject(uuid4(), "1.0")
            canonical_project.commit(restored_batch)
            validate_project_graph(canonical_project)
            self.assertEqual(
                restored_batch.report.created_entity_ids,
                batch.report.created_entity_ids,
            )


if __name__ == "__main__":
    unittest.main()
