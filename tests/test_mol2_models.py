import unittest
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender import reader_api
from ChemBlender.core import (
    ArrayData,
    AtomicIdentityData,
    AtomicProperty,
    CategoricalData,
    ChemicalAnnotation,
    DatasetStatus,
    ImportBatch,
    IssueKind,
    MolecularRecord,
    ParserIssue,
    ParserReport,
    QCProject,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Structure,
    TopologyRecord,
    TopologySource,
    close_project,
    open_project,
    save_project,
)


def array(values, dims, unit="dimensionless"):
    return ArrayData(numpy.asarray(values), dims, unit)


def categorical(values, categories):
    return CategoricalData(array(values, ("atom",)), categories, -1)


def mol2_fixture():
    atom_names = categorical((0, -1), ("C1",))
    structure = Structure(
        id=uuid4(),
        revision="mol2-structure-r1",
        atomic_numbers=(6, 1),
        coordinates=array(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), ("atom", "xyz"), "angstrom"),
        atomic_identity=AtomicIdentityData(
            isotopes=array((0, 0), ("atom",)),
            formal_charges=array((0, 0), ("atom",)),
            atom_map_numbers=array((0, 0), ("atom",)),
            atom_names=atom_names,
            stereo_labels=categorical((-1, -1), ()),
        ),
    )
    topology = TopologyRecord(
        id=uuid4(),
        revision="mol2-topology-r1",
        structure_id=structure.id,
        bond_indices=array(((0, 1),), ("bond", "endpoint")),
        bond_orders=array((1.0,), ("bond",)),
        aromatic_flags=None,
        stereo_labels=("",),
        source_kind=TopologySource.EXPLICIT_FILE,
        quality_status=QualityStatus.COMPLETE,
        inference_parameters=(),
        provenance_ids=(),
    )
    atom_types = AtomicProperty(
        id=uuid4(),
        revision="mol2-atom-types-r1",
        semantic_role="atom_type",
        domain="atom",
        data=categorical((0, -1), ("C.3",)),
        status=DatasetStatus.PARTIAL,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure.id,
    )
    substructure_ids = AtomicProperty(
        id=uuid4(),
        revision="mol2-substructure-ids-r1",
        semantic_role="substructure_id",
        domain="atom",
        data=array((1, 1), ("atom",)),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure.id,
    )
    partial_charges = AtomicProperty(
        id=uuid4(),
        revision="mol2-partial-charges-r1",
        semantic_role="partial_charge",
        domain="atom",
        data=array((-0.12, 0.12), ("atom",)),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure.id,
    )
    annotations = tuple(
        ChemicalAnnotation(
            id=uuid4(),
            revision="mol2-annotation-r1",
            target_entity_id=structure.id,
            namespace="tripos",
            key=key,
            value=value,
            source="mol2",
            confidence=None,
            provenance_ids=(),
        )
        for key, value in (
            ("molecule_type", "SMALL"),
            ("charge_type", "USER_CHARGES"),
            ("status_bits", "INVALID_CHARGES"),
        )
    )
    raw_block = (
        b"@<TRIPOS>MOLECULE\r\n"
        b"methane\r\n"
        b"2 1 1 0 0\r\n"
        b"SMALL\r\n"
        b"USER_CHARGES\r\n"
    )
    record = MolecularRecord(
        id=uuid4(),
        revision="mol2-record-r1",
        source_revision_id=uuid4(),
        record_key="molecule-0001",
        structure_id=structure.id,
        topology_id=topology.id,
        raw_block=raw_block,
        title="methane",
        source_record_index=0,
        block_version=None,
        writer_name=None,
        writer_version=None,
        ordered_raw_properties=(),
        provenance_ids=(),
    )
    source = SourceRecord(uuid4(), "methane.mol2", "file", "2026-07-29T00:00:00Z")
    created_ids = (
        structure.id,
        topology.id,
        record.id,
        *(annotation.id for annotation in annotations),
        atom_types.id,
        substructure_ids.id,
        partial_charges.id,
    )
    revision = SourceRevision(
        id=record.source_revision_id,
        source_id=source.id,
        content_hash="a" * 64,
        byte_size=len(raw_block),
        locator="methane.mol2",
        locator_kind="path",
        original_filename="methane.mol2",
        reader_plugin_id="chemblender.builtin",
        reader_id="mol2",
        reader_version="1",
        reader_api_version="1.0-rc1",
        import_parameters_hash="b" * 64,
        parse_identity="c" * 64,
        created_entity_ids=created_ids,
        diagnostic_ids=(),
    )
    report = ParserReport(
        "mol2",
        "1",
        created_ids,
        (
            "structure",
            "topology",
            "molecular_record",
            "atomic_property",
            "chemical_annotation",
        ),
        (
            ParserIssue(
                IssueKind.UNSUPPORTED,
                "set",
                "MOL2 SET sections are not represented",
            ),
        ),
    )
    return ImportBatch(
        sources=(source,),
        source_revisions=(revision,),
        structures=(structure,),
        topologies=(topology,),
        molecular_records=(record,),
        annotations=annotations,
        datasets=(atom_types, substructure_ids, partial_charges),
        report=report,
    )


class Mol2ModelMappingTests(unittest.TestCase):
    def test_mol2_mapping_reuses_exchange_and_project_contracts(self):
        batch = mol2_fixture()
        structure = batch.structures[0]
        record = batch.molecular_records[0]
        atom_types, substructure_ids, partial_charges = batch.datasets

        self.assertEqual(
            tuple((value.key, value.value) for value in batch.annotations),
            (
                ("molecule_type", "SMALL"),
                ("charge_type", "USER_CHARGES"),
                ("status_bits", "INVALID_CHARGES"),
            ),
        )
        self.assertIsInstance(structure.atomic_identity.atom_names, CategoricalData)
        self.assertIsInstance(atom_types.data, CategoricalData)
        self.assertIsInstance(substructure_ids, AtomicProperty)
        self.assertEqual(structure.atomic_identity.atom_names.codes.values.tolist(), [0, -1])
        self.assertEqual(atom_types.data.codes.values.tolist(), [0, -1])
        self.assertEqual(atom_types.data.categories, ("C.3",))
        self.assertIn(numpy.dtype(substructure_ids.data.dtype).kind, "iu")
        self.assertEqual(substructure_ids.data.values.tolist(), [1, 1])
        self.assertEqual(partial_charges.data.values.tolist(), [-0.12, 0.12])
        self.assertEqual(record.raw_block, b"@<TRIPOS>MOLECULE\r\nmethane\r\n2 1 1 0 0\r\nSMALL\r\nUSER_CHARGES\r\n")
        self.assertEqual(
            batch.report.issues,
            (ParserIssue(IssueKind.UNSUPPORTED, "set", "MOL2 SET sections are not represented"),),
        )

        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        self.assertIs(project.structures[structure.id], structure)
        self.assertIs(project.topologies[record.topology_id], batch.topologies[0])
        self.assertEqual(project.molecular_records[record.id].raw_block, record.raw_block)

        public = reader_api.public_batch_from_internal(batch)
        with TemporaryDirectory() as temporary:
            document = reader_api.public_batch_document(public, temporary)
            restored = reader_api.internal_batch_from_public(
                reader_api.public_batch_from_document(document, temporary)
            )
            self.assertEqual(restored.molecular_records[0].raw_block, record.raw_block)
            self.assertEqual(restored.datasets[1].data.values.tolist(), [1, 1])

            root = f"{temporary}/mol2.cbq"
            save_project(root, project)
            reopened = open_project(root)
            try:
                self.assertEqual(reopened.molecular_records[record.id].raw_block, record.raw_block)
                self.assertEqual(
                    numpy.asarray(reopened.datasets[substructure_ids.id].data.values).tolist(),
                    [1, 1],
                )
            finally:
                close_project(reopened)


if __name__ == "__main__":
    unittest.main()
