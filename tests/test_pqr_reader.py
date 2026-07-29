import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy

from ChemBlender.core import (
    CapabilitySupport,
    close_project,
    DatasetStatus,
    open_project,
    QCProject,
    save_project,
    SniffMatch,
)
from ChemBlender.core.formats import pqr
from ChemBlender.core.model.project import validate_project_graph
from ChemBlender.core.reader_catalog import (
    builtin_reader_descriptors,
    builtin_reader_registry,
)
from ChemBlender.reader_api import (
    builtin_reader_plugin_registry,
    internal_batch_from_public,
    ParseRequest,
    public_batch_document,
    public_batch_from_document,
    public_batch_from_internal,
)
from ChemBlender.reader_api.conformance import (
    ReaderConformanceCase,
    run_reader_conformance,
)


FIXTURES = Path(__file__).parent / "fixtures" / "pqr"


class PQRReaderTests(unittest.TestCase):
    def test_validated_with_chain_and_no_chain_dialects(self):
        with_chain = pqr.parse_pqr_records(
            (FIXTURES / "with-chain.pqr").read_bytes()
        )
        no_chain = pqr.parse_pqr_records(
            (FIXTURES / "no-chain.pqr").read_bytes()
        )

        self.assertEqual(
            tuple(
                (
                    atom.record_kind,
                    atom.serial,
                    atom.atom_name,
                    atom.residue_name,
                    atom.chain_id,
                    atom.residue_number,
                    atom.insertion_code,
                    atom.coordinates,
                    atom.charge,
                    atom.radius,
                )
                for atom in with_chain.atoms
            ),
            (
                (
                    "atom",
                    1,
                    "N",
                    "ARG",
                    "A",
                    1,
                    "A",
                    (1.0, 2.0, 3.0),
                    -0.3,
                    1.55,
                ),
                (
                    "hetatm",
                    2,
                    "O",
                    "HOH",
                    "W",
                    2,
                    "",
                    (4.0, 5.0, 6.0),
                    -0.55,
                    1.4,
                ),
            ),
        )
        self.assertEqual(
            tuple(atom.chain_id for atom in no_chain.atoms),
            ("", ""),
        )
        self.assertEqual(with_chain.raw_source, (FIXTURES / "with-chain.pqr").read_bytes())
        self.assertTrue(
            all(issue.path.endswith(".element") for issue in with_chain.issues)
        )

    def test_source_dialect_is_exact_persisted_and_mixed_input_is_isolated(self):
        for filename, dialect in (
            ("with-chain.pqr", "with_chain"),
            ("no-chain.pqr", "no_chain"),
        ):
            with self.subTest(filename=filename):
                source = FIXTURES / filename
                batch = pqr.parse_pqr(source)
                self.assertEqual(
                    dict(batch.provenance[0].parameters)["dialect"],
                    dialect,
                )
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    project = QCProject(batch.sources[0].id, "1.0")
                    project.commit(batch)
                    restored = open_project(
                        save_project(root / f"{dialect}.cbq", project)
                    )
                    try:
                        self.assertEqual(
                            dict(
                                next(iter(restored.provenance.values())).parameters
                            )["dialect"],
                            dialect,
                        )
                    finally:
                        close_project(restored)

                    canonical_root = root / "canonical"
                    canonical_root.mkdir()
                    document = public_batch_document(
                        public_batch_from_internal(batch),
                        canonical_root,
                    )
                    canonical = internal_batch_from_public(
                        public_batch_from_document(document, canonical_root)
                    )
                    self.assertEqual(
                        dict(canonical.provenance[0].parameters)["dialect"],
                        dialect,
                    )

        mixed = b"\n".join(
            (
                b"ATOM 1 N ARG 1 1.000 2.000 3.000 -0.3000 1.5500",
                b"HETATM 2 O HOH W 2 4.000 5.000 6.000 -0.5500 1.4000",
                b"",
            )
        )
        parsed = pqr.parse_pqr_records(mixed)
        self.assertEqual(tuple(atom.serial for atom in parsed.atoms), (1,))
        self.assertIn(
            ("invalid", "record[1].dialect"),
            tuple((issue.kind.value, issue.path) for issue in parsed.issues),
        )
        with self.assertRaisesRegex(pqr.PQRSyntaxError, "invalid records"):
            pqr.parse_pqr_records(mixed, validation_mode="strict")

    def test_padded_pqr_parser_and_suffix_handoff_keep_explicit_route_available(self):
        padded = FIXTURES / "padded.pqr"
        registry = builtin_reader_registry()

        self.assertEqual(len(pqr.parse_pqr_records(padded.read_bytes()).atoms), 1)
        self.assertEqual(registry.select(padded).reader_id, "pqr")
        with TemporaryDirectory() as directory:
            padded_pdb = Path(directory) / "padded.pdb"
            padded_pdb.write_bytes(padded.read_bytes())
            self.assertEqual(registry.select(padded_pdb).reader_id, "pdb")
            explicit = registry.parse(padded_pdb, reader_id="pqr")
            self.assertEqual(explicit.structures[0].atomic_numbers, (7,))
            self.assertEqual(
                numpy.asarray(
                    next(
                        value
                        for value in explicit.datasets
                        if value.semantic_role == "partial_charge"
                    ).data.values
                ).tolist(),
                [-0.3],
            )

    def test_element_inference_uses_pqr_token_and_explicit_context(self):
        raw = b"\n".join(
            (
                b"ATOM 1 CA ALA A 1 0 0 0 0 1.7",
                b"ATOM 2 CD GLU A 2 1 0 0 0 1.7",
                b"HETATM 3 CA CA A 3 2 0 0 0 1.8",
                b"HETATM 4 FE LIG A 4 3 0 0 0 1.8",
                b"HETATM 5 CL LIG A 5 4 0 0 0 1.8",
                b"HETATM 6 BR LIG A 6 5 0 0 0 1.8",
                b"ATOM 7 1HG1 ALA A 7 6 0 0 0 1.2",
                b"HETATM 8 CA LIG A 8 7 0 0 0 1.8",
                b"ATOM 9 QX UNK A 9 8 0 0 0 1.8",
                b"",
            )
        )
        parsed = pqr.parse_pqr_records(raw)

        self.assertEqual(
            tuple((atom.atom_name, atom.element) for atom in parsed.atoms),
            (
                ("CA", "C"),
                ("CD", "C"),
                ("CA", "Ca"),
                ("FE", "Fe"),
                ("CL", "Cl"),
                ("BR", "Br"),
                ("1HG1", "H"),
            ),
        )
        invalid = tuple(
            issue
            for issue in parsed.issues
            if issue.kind.value == "invalid"
        )
        self.assertEqual(
            tuple(issue.path for issue in invalid),
            ("record[7].element", "record[8].element"),
        )
        self.assertIn("CA", invalid[0].message)
        self.assertEqual(
            sum(issue.kind.value == "warning" for issue in parsed.issues),
            7,
        )

        with TemporaryDirectory() as directory:
            source = Path(directory) / "elements.pqr"
            source.write_bytes(raw)
            batch = pqr.parse_pqr(source)
        self.assertEqual(
            batch.structures[0].atomic_numbers,
            (6, 6, 20, 26, 17, 35, 1),
        )
        self.assertEqual(
            batch.structures[0].atomic_identity.atom_names.categories,
            ("CA", "CD", "FE", "CL", "BR", "1HG1"),
        )

    def test_element_policy_matrix_keeps_polymer_and_ion_context_separate(self):
        cases = (
            ("ATOM", "CA", "ALA", "C"),
            ("ATOM", "CD", "GLU", "C"),
            ("ATOM", "FE", "ALA", None),
            ("ATOM", "BR", "ALA", None),
            ("ATOM", "FA", "ALA", None),
            ("ATOM", "SE", "SEC", "Se"),
            ("HETATM", "CA", "CA", "Ca"),
            ("HETATM", "FE", "LIG", "Fe"),
            ("HETATM", "CL", "LIG", "Cl"),
            ("HETATM", "BR", "LIG", "Br"),
            ("HETATM", "CA", "LIG", None),
            ("ATOM", "1HG1", "ALA", "H"),
        )
        for record_name, atom_name, residue_name, expected in cases:
            with self.subTest(
                record_name=record_name,
                atom_name=atom_name,
                residue_name=residue_name,
            ):
                raw = (
                    f"{record_name} 1 {atom_name} {residue_name} A 1 "
                    "0 0 0 0 1.5\n"
                ).encode("ascii")
                parsed = pqr.parse_pqr_records(raw)
                if expected is None:
                    self.assertEqual(parsed.atoms, ())
                    self.assertEqual(parsed.issues[0].path, "record[0].element")
                    self.assertIn(atom_name, parsed.issues[0].message)
                else:
                    self.assertEqual(
                        tuple(atom.element for atom in parsed.atoms),
                        (expected,),
                    )

    def test_balanced_isolates_invalid_rows_and_strict_rejects_them(self):
        raw = (FIXTURES / "malformed.pqr").read_bytes()
        parsed = pqr.parse_pqr_records(raw)

        self.assertEqual(tuple(atom.serial for atom in parsed.atoms), (1,))
        self.assertEqual(
            tuple(issue.path for issue in parsed.issues if issue.kind.value == "invalid"),
            (
                "record[1].charge",
                "record[2].residue_number",
                "record[3].element",
                "record[4].residue_number",
            ),
        )
        with self.assertRaisesRegex(pqr.PQRSyntaxError, "invalid records"):
            pqr.parse_pqr_records(raw, validation_mode="strict")

    def test_residue_conflict_isolated_in_balanced_and_maximum_but_rejected_strict(self):
        raw = b"\n".join(
            (
                b"ATOM 1 N ALA A 1 0 0 0 0 1.5",
                b"ATOM 2 C GLY A 1 1 0 0 0 1.7",
                b"ATOM 3 O ALA A 2 2 0 0 0 1.4",
                b"",
            )
        )
        for mode in ("balanced", "maximum"):
            with self.subTest(mode=mode):
                parsed = pqr.parse_pqr_records(raw, validation_mode=mode)
                self.assertEqual(
                    tuple(atom.serial for atom in parsed.atoms),
                    (1, 3),
                )
                self.assertIn(
                    ("invalid", "record[1].residue_name"),
                    tuple(
                        (issue.kind.value, issue.path)
                        for issue in parsed.issues
                    ),
                )
        with self.assertRaisesRegex(pqr.PQRSyntaxError, "invalid records"):
            pqr.parse_pqr_records(raw, validation_mode="strict")

        with TemporaryDirectory() as directory:
            source = Path(directory) / "conflict.pqr"
            source.write_bytes(raw)
            batch = pqr.parse_pqr(source)
        self.assertEqual(batch.structures[0].atomic_numbers, (7, 8))
        self.assertEqual(
            numpy.asarray(
                next(
                    value
                    for value in batch.datasets
                    if value.semantic_role == "partial_charge"
                ).data.values
            ).tolist(),
            [0.0, 0.0],
        )
        self.assertEqual(
            tuple(
                (residue.residue_name, residue.sequence_number)
                for residue in batch.biological_hierarchies[0].residues
            ),
            (("ALA", 1), ("ALA", 2)),
        )

    def test_residue_range_zero_charge_ignored_records_and_truncated_prefix(self):
        raw = b"\n".join(
            (
                b"REMARK source metadata",
                b"ATOM 1 N ARG -12A 0 0 0 0 1.5",
                b"TER",
                b"ATOM 2 O ARG 123456789 1 0 0 0 1.4",
                b"",
            )
        )
        parsed = pqr.parse_pqr_records(raw, validation_mode="maximum")
        self.assertEqual(
            tuple(
                (
                    atom.residue_number,
                    atom.insertion_code,
                    atom.charge,
                )
                for atom in parsed.atoms
            ),
            ((-12, "A", 0.0), (123456789, "", 0.0)),
        )

        with TemporaryDirectory() as directory:
            source = Path(directory) / "truncated.pqr"
            source.write_bytes(raw)
            first_atom = raw.splitlines(keepends=True)[1]
            self.assertIs(
                pqr.sniff_pqr(source, first_atom).match,
                SniffMatch.PROBABLE,
            )

    def test_maps_identity_hierarchy_charge_radius_without_topology(self):
        batch = pqr.parse_pqr(FIXTURES / "with-chain.pqr")

        self.assertEqual(len(batch.structures), 1)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (7, 8))
        self.assertEqual(structure.atomic_identity.atom_names.categories, ("N", "O"))
        self.assertEqual(structure.topology_ids, ())
        self.assertEqual(batch.topologies, ())
        hierarchy = batch.biological_hierarchies[0]
        self.assertEqual(
            tuple((chain.chain_id, chain.segment_index) for chain in hierarchy.chains),
            (("A", 0), ("W", 0)),
        )
        self.assertEqual(
            tuple(
                (
                    residue.residue_name,
                    residue.sequence_number,
                    residue.insertion_code,
                    residue.hetero,
                )
                for residue in hierarchy.residues
            ),
            (("ARG", 1, "A", False), ("HOH", 2, "", True)),
        )
        datasets = {value.semantic_role: value for value in batch.datasets}
        self.assertEqual(set(datasets), {"partial_charge", "radius"})
        self.assertEqual(
            numpy.asarray(datasets["partial_charge"].data.values).tolist(),
            [-0.3, -0.55],
        )
        self.assertEqual(datasets["partial_charge"].data.unit, "elementary_charge")
        self.assertEqual(numpy.asarray(datasets["radius"].data.values).tolist(), [1.55, 1.4])
        self.assertEqual(datasets["radius"].data.unit, "angstrom")
        self.assertTrue(
            all(value.status is DatasetStatus.COMPLETE for value in datasets.values())
        )
        self.assertEqual(
            batch.report.parsed_capabilities,
            ("atomic_identity", "atomic_property", "hierarchy", "structure"),
        )
        self.assertEqual(
            batch.report.created_entity_ids,
            batch.source_revisions[0].created_entity_ids,
        )

    def test_sniff_catalog_and_strict_request_contract(self):
        with_chain = FIXTURES / "with-chain.pqr"
        pdb_source = Path(__file__).parent / "fixtures" / "pdb" / "atom-hetatm.pdb"
        self.assertIs(
            pqr.sniff_pqr(with_chain, with_chain.read_bytes()).match,
            SniffMatch.EXACT,
        )
        self.assertIs(
            pqr.sniff_pqr(pdb_source, pdb_source.read_bytes()).match,
            SniffMatch.NONE,
        )
        self.assertIs(
            pqr.sniff_pqr(Path("notes.pqr"), b"ordinary text\n").match,
            SniffMatch.NONE,
        )
        self.assertEqual(
            builtin_reader_registry().select(with_chain).reader_id,
            "pqr",
        )
        descriptors = {
            descriptor.reader_id: descriptor
            for descriptor in builtin_reader_descriptors()
        }
        self.assertEqual(descriptors["pqr"].extensions, (".pqr",))
        self.assertEqual(
            dict(descriptors["pqr"].capabilities),
            {
                "atomic_identity": CapabilitySupport.SUPPORTED,
                "atomic_property": CapabilitySupport.SUPPORTED,
                "hierarchy": CapabilitySupport.SUPPORTED,
                "structure": CapabilitySupport.SUPPORTED,
            },
        )

        raw = (FIXTURES / "malformed.pqr").read_bytes()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "strict.pqr"
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
            with self.assertRaisesRegex(pqr.PQRSyntaxError, "invalid records"):
                pqr.parse_pqr_request(request)

    def test_zero_valid_atoms_fail_closed_and_fatal_exceptions_propagate(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "empty.pqr"
            source.write_bytes(b"ordinary text\n")
            with self.assertRaisesRegex(ValueError, "no valid atoms"):
                pqr.parse_pqr(source)

        oversized = b"ATOM " + b"X" * 4096 + b"\n"
        parsed = pqr.parse_pqr_records(oversized)
        self.assertEqual(parsed.atoms, ())
        self.assertEqual(parsed.issues[0].path, "record[0].length")

        for exception_type in (
            KeyboardInterrupt,
            SystemExit,
            GeneratorExit,
            MemoryError,
        ):
            with self.subTest(exception=exception_type.__name__):
                class FatalBytes(bytes):
                    def splitlines(self, *args, **kwargs):
                        raise exception_type

                raw = FatalBytes(b"ATOM")
                with self.assertRaises(exception_type):
                    pqr.parse_pqr_records(raw)
                with self.assertRaises(exception_type):
                    pqr.sniff_pqr(Path("fatal.pqr"), raw)

    def test_reader_conformance_determinism_and_project_round_trips(self):
        source = FIXTURES / "no-chain.pqr"
        batch = pqr.parse_pqr(source)
        repeated = pqr.parse_pqr(source)
        self.assertEqual(
            tuple(value.id for value in batch.structures + batch.datasets),
            tuple(value.id for value in repeated.structures + repeated.datasets),
        )
        self.assertEqual(batch.source_revisions[0].reader_id, "pqr")
        self.assertEqual(
            batch.source_revisions[0].content_hash,
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        self.assertEqual(batch.provenance[0].producer, "ChemBlender PQR reader")

        result = run_reader_conformance(
            ReaderConformanceCase(
                "pqr-no-chain",
                builtin_reader_plugin_registry(),
                "pqr",
                source,
                ("atomic_identity", "atomic_property", "hierarchy", "structure"),
            )
        )
        self.assertTrue(result.passed, result.as_dict())

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = QCProject(batch.sources[0].id, "1.0")
            project.commit(batch)
            validate_project_graph(project)
            restored = open_project(save_project(root / "pqr.cbq", project))
            try:
                validate_project_graph(restored)
                self.assertEqual(len(restored.structures), 1)
                self.assertEqual(len(restored.biological_hierarchies), 1)
                self.assertEqual(len(restored.datasets), 2)
                self.assertEqual(len(restored.topologies), 0)
                restored_datasets = {
                    value.semantic_role: value
                    for value in restored.datasets.values()
                }
                self.assertEqual(
                    numpy.asarray(
                        restored_datasets["partial_charge"].data.values
                    ).tolist(),
                    [-0.3, -0.55],
                )
                self.assertEqual(
                    numpy.asarray(
                        restored_datasets["radius"].data.values
                    ).tolist(),
                    [1.55, 1.4],
                )
            finally:
                close_project(restored)

            canonical_root = root / "canonical"
            canonical_root.mkdir()
            document = public_batch_document(
                public_batch_from_internal(batch),
                canonical_root,
            )
            restored_batch = internal_batch_from_public(
                public_batch_from_document(document, canonical_root)
            )
            canonical_project = QCProject(batch.sources[0].id, "1.0")
            canonical_project.commit(restored_batch)
            validate_project_graph(canonical_project)
            self.assertEqual(
                restored_batch.report.created_entity_ids,
                batch.report.created_entity_ids,
            )
            self.assertEqual(restored_batch.topologies, ())
            canonical_datasets = {
                value.semantic_role: value
                for value in restored_batch.datasets
            }
            self.assertEqual(
                numpy.asarray(
                    canonical_datasets["partial_charge"].data.values
                ).tolist(),
                [-0.3, -0.55],
            )
            self.assertEqual(
                numpy.asarray(canonical_datasets["radius"].data.values).tolist(),
                [1.55, 1.4],
            )


if __name__ == "__main__":
    unittest.main()
