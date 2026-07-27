import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

from ChemBlender import reader_api
from ChemBlender.core import (
    ArrayData,
    AtomicIdentityData,
    CategoricalData,
    ConformerSet,
    DatasetStatus,
    ImportBatch,
    MolecularRecord,
    QCProject,
    RawRecordProperty,
    RecordPropertyColumn,
    SourceRecord,
    SourceRevision,
    Structure,
    TopologyRecord,
    TopologySource,
    QualityStatus,
    save_project,
    open_project,
    close_project,
    SidecarIntegrityError,
)
from tests.test_sidecar_storage import write_manifest


def array(values, dims, unit="dimensionless"):
    return ArrayData(numpy.asarray(values), dims, unit)


def categorical(values, categories=("", "R"), missing_code=-1):
    return CategoricalData(
        array(values, ("atom",)), categories, missing_code
    )


def structure(identity=None):
    return Structure(
        id=uuid4(),
        revision="structure-r1",
        atomic_numbers=(6, 1),
        coordinates=array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]], ("atom", "xyz"), "angstrom"),
        atomic_identity=identity,
    )


def identity():
    return AtomicIdentityData(
        isotopes=array([0, 13], ("atom",)),
        formal_charges=array([0, -1], ("atom",)),
        atom_map_numbers=array([0, 2], ("atom",)),
        atom_names=categorical([0, -1], ("C",)),
        stereo_labels=categorical([-1, 0], ("R",)),
    )


def record(structure_id, topology_id=None):
    return MolecularRecord(
        id=uuid4(),
        revision="record-r1",
        source_revision_id=uuid4(),
        record_key="record-0001",
        structure_id=structure_id,
        topology_id=topology_id,
        raw_block=b"title\r\nM  END\r\n",
        title="",
        source_record_index=0,
        block_version="V2000",
        writer_name=None,
        writer_version=None,
        ordered_raw_properties=(
            RawRecordProperty("dup", ""),
            RawRecordProperty("dup", "same-name"),
        ),
        provenance_ids=(),
    )


def source_revision(created_entity_ids):
    source = SourceRecord(uuid4(), "record.sdf", "file", "2026-07-27T00:00:00Z")
    revision = SourceRevision(
        id=uuid4(), source_id=source.id, content_hash="a" * 64,
        byte_size=1, locator="record.sdf", locator_kind="path",
        original_filename="record.sdf", reader_plugin_id="builtin",
        reader_id="sdf", reader_version="1", reader_api_version="0.1",
        import_parameters_hash="b" * 64, parse_identity="c" * 64,
        created_entity_ids=created_entity_ids, diagnostic_ids=(),
    )
    return source, revision


class ChemicalIdentityAndRecordsTests(unittest.TestCase):
    def test_atomic_identity_contract_and_structure_binding(self):
        value = identity()
        self.assertEqual(value.atom_count, 2)
        self.assertIs(structure().atomic_identity, None)
        self.assertIs(structure(value).atomic_identity, value)
        with self.assertRaisesRegex(ValueError, "atom dimension"):
            AtomicIdentityData(
                array([0, 0], ("atom",)), array([0], ("atom",)),
                array([0], ("atom",)), categorical([0]), categorical([0]),
            )
        with self.assertRaisesRegex(TypeError, "integer"):
            AtomicIdentityData(
                array([1.5, 0], ("atom",)), array([0, 0], ("atom",)),
                array([0, 0], ("atom",)), categorical([0, 0]), categorical([0, 0]),
            )
        for name, values in (
            ("isotopes", array([-1, 0], ("atom",))),
            ("atom_map_numbers", array([0, -1], ("atom",))),
            ("formal_charges", array([True, False], ("atom",))),
        ):
            fields = {
                field: getattr(value, field)
                for field in value.__dataclass_fields__
            }
            fields[name] = values
            with self.subTest(name=name), self.assertRaises(TypeError):
                AtomicIdentityData(**fields)
        with self.assertRaisesRegex(ValueError, "match atomic numbers"):
            Structure(
                id=uuid4(), revision="bad", atomic_numbers=(1,),
                coordinates=array([[0.0, 0.0, 0.0]], ("atom", "xyz"), "angstrom"),
                atomic_identity=value,
            )

    def test_record_preserves_raw_bytes_and_ordered_duplicate_properties(self):
        molecule = structure()
        value = record(molecule.id)
        self.assertEqual(value.raw_block, b"title\r\nM  END\r\n")
        self.assertEqual(
            tuple((item.name, item.value) for item in value.ordered_raw_properties),
            (("dup", ""), ("dup", "same-name")),
        )
        with self.assertRaisesRegex(ValueError, "record_key"):
            MolecularRecord(
                **{name: ("" if name == "record_key" else getattr(value, name))
                   for name in value.__dataclass_fields__}
            )
        with self.assertRaisesRegex(TypeError, "source_record_index"):
            MolecularRecord(
                **{name: (True if name == "source_record_index" else getattr(value, name))
                   for name in value.__dataclass_fields__}
            )
        for name, replacement in (
            ("source_record_index", -1),
            ("writer_name", 1),
            ("writer_version", object()),
        ):
            fields = {field: getattr(value, field) for field in value.__dataclass_fields__}
            fields[name] = replacement
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                MolecularRecord(**fields)

    def test_record_property_column_masks_and_categorical_rules(self):
        record_ids = (uuid4(), uuid4())
        complete = RecordPropertyColumn(
            id=uuid4(), revision="column-r1", semantic_role="energy", domain="record",
            data=array([1.0, 2.0], ("record",), "hartree"),
            status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            record_ids=record_ids,
        )
        self.assertEqual(complete.record_ids, record_ids)
        with self.assertRaisesRegex(ValueError, "unique"):
            RecordPropertyColumn(
                id=uuid4(), revision="duplicate-r1", semantic_role="energy",
                domain="record", data=array([1.0, 2.0], ("record",), "hartree"),
                status=DatasetStatus.COMPLETE, source_calculation=None,
                provenance_ids=(), record_ids=(record_ids[0], record_ids[0]),
            )
        for domain, dims in (("atom", ("record",)), ("record", ("value",))):
            with self.subTest(domain=domain, dims=dims), self.assertRaises(ValueError):
                RecordPropertyColumn(
                    id=uuid4(), revision="invalid-r1", semantic_role="energy",
                    domain=domain, data=array([1.0, 2.0], dims, "hartree"),
                    status=DatasetStatus.COMPLETE, source_calculation=None,
                    provenance_ids=(), record_ids=record_ids,
                )
        partial_fields = {name: getattr(complete, name) for name in complete.__dataclass_fields__}
        partial_fields.update(
            status=DatasetStatus.PARTIAL,
            validity_mask=array([True, False], ("record",)),
        )
        self.assertIsInstance(RecordPropertyColumn(**partial_fields), RecordPropertyColumn)
        with self.assertRaisesRegex(ValueError, "requires a validity mask"):
            RecordPropertyColumn(**{**partial_fields, "validity_mask": None})
        with self.assertRaisesRegex(ValueError, "Complete"):
            RecordPropertyColumn(**{**partial_fields, "status": DatasetStatus.COMPLETE})
        categories = CategoricalData(
            ArrayData(numpy.asarray([0, -1], dtype=numpy.int64), ("record",), "dimensionless"),
            ("ok",), -1,
        )
        with self.assertRaisesRegex(ValueError, "Complete categorical"):
            RecordPropertyColumn(
                id=uuid4(), revision="cat-r1", semantic_role="label", domain="record",
                data=categories, status=DatasetStatus.COMPLETE,
                source_calculation=None, provenance_ids=(), record_ids=record_ids,
            )
        with self.assertRaisesRegex(ValueError, "missing_code"):
            RecordPropertyColumn(
                id=uuid4(), revision="cat-mask-r1", semantic_role="label", domain="record",
                data=categories, status=DatasetStatus.PARTIAL,
                source_calculation=None, provenance_ids=(), record_ids=record_ids,
                validity_mask=array([True, False], ("record",)),
            )
        for values in (
            numpy.asarray(["text", "value"]),
            numpy.asarray([object(), object()], dtype=object),
            numpy.zeros(2, dtype=[("value", numpy.float64)]),
        ):
            with self.subTest(dtype=values.dtype), self.assertRaisesRegex(
                TypeError, "numeric, logical or categorical"
            ):
                RecordPropertyColumn(
                    id=uuid4(), revision="invalid-r1", semantic_role="invalid",
                    domain="record", data=ArrayData(values, ("record",), "dimensionless"),
                    status=DatasetStatus.COMPLETE, source_calculation=None,
                    provenance_ids=(), record_ids=record_ids,
                )
        for record_ids_value, values in (
            (("not-a-uuid",), numpy.asarray([1.0])),
            ((uuid4(),), numpy.asarray([1.0, 2.0])),
        ):
            with self.subTest(record_ids=record_ids_value), self.assertRaises((TypeError, ValueError)):
                RecordPropertyColumn(
                    id=uuid4(), revision="invalid-ids-r1", semantic_role="energy",
                    domain="record", data=ArrayData(values, ("record",), "hartree"),
                    status=DatasetStatus.COMPLETE, source_calculation=None,
                    provenance_ids=(), record_ids=record_ids_value,
                )

    def test_conformer_set_requires_permutation_mapping(self):
        molecule = structure()
        record_ids = (uuid4(), uuid4())
        conformers = ConformerSet(
            id=uuid4(), revision="conformer-r1", semantic_role="coordinates",
            domain="conformer", data=array(
                [[[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]], [[0.0, 0.0, 0.1], [0.0, 0.0, 1.1]]],
                ("conformer", "atom", "xyz"), "angstrom",
            ), status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            reference_structure_id=molecule.id, reference_topology_id=None,
            record_ids=record_ids, record_keys=("one", "two"),
            atom_mappings=array([[0, 1], [1, 0]], ("conformer", "atom")),
        )
        self.assertEqual(conformers.record_ids, record_ids)
        with self.assertRaisesRegex(ValueError, "permutation"):
            ConformerSet(
                **{name: (array([[0, 0], [1, 0]], ("conformer", "atom")) if name == "atom_mappings" else getattr(conformers, name))
                   for name in conformers.__dataclass_fields__}
            )
        for values, unit in (
            (numpy.ones((2, 2, 3), dtype=bool), "angstrom"),
            (numpy.ones((2, 2, 3), dtype=complex), "angstrom"),
            (numpy.asarray([[[object()] * 3] * 2] * 2, dtype=object), "angstrom"),
            (numpy.zeros((2, 2, 3), dtype=[("value", numpy.float64)]), "angstrom"),
            (numpy.ones((2, 2, 3), dtype=float), "electron_volt"),
        ):
            with self.subTest(dtype=values.dtype, unit=unit), self.assertRaises(ValueError):
                ConformerSet(
                    **{
                        name: (
                            ArrayData(values, ("conformer", "atom", "xyz"), unit)
                            if name == "data" else getattr(conformers, name)
                        )
                        for name in conformers.__dataclass_fields__
                    }
                )
        for name, replacement in (
            ("data", array([[[0.0, 0.0, 0.0]]], ("conformer", "atom", "axis"), "angstrom")),
            ("data", array(numpy.empty((1, 0, 3)), ("conformer", "atom", "xyz"), "angstrom")),
            ("atom_mappings", array([[True, False], [False, True]], ("conformer", "atom"))),
            ("record_ids", (record_ids[0], record_ids[0])),
            ("record_keys", ("one", "one")),
            ("record_keys", ("one",)),
        ):
            fields = {field: getattr(conformers, field) for field in conformers.__dataclass_fields__}
            fields[name] = replacement
            with self.subTest(name=name), self.assertRaises(ValueError):
                ConformerSet(**fields)

    def test_atomic_identity_rejects_wrong_dims_categories_and_object_values(self):
        value = identity()
        with self.assertRaisesRegex(ValueError, "represent"):
            CategoricalData(
                ArrayData(numpy.asarray([0, 1], dtype=numpy.int8), ("atom",), "dimensionless"),
                tuple(str(index) for index in range(129)), -1,
            )
        replacements = (
            ("isotopes", ArrayData(numpy.asarray([0, 1]), ("site",), "dimensionless")),
            ("formal_charges", ArrayData(numpy.asarray([object(), object()]), ("atom",), "dimensionless")),
        )
        for name, replacement in replacements:
            fields = {field: getattr(value, field) for field in value.__dataclass_fields__}
            fields[name] = replacement
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                AtomicIdentityData(**fields)

    def test_conformer_set_can_group_records_from_independent_structures(self):
        reference = structure()
        independent = structure()
        value = record(independent.id)
        source, revision = source_revision(
            (reference.id, independent.id, value.id)
        )
        value = MolecularRecord(
            **{
                name: (revision.id if name == "source_revision_id" else getattr(value, name))
                for name in value.__dataclass_fields__
            }
        )
        conformers = ConformerSet(
            id=uuid4(), revision="conformer-r1", semantic_role="coordinates",
            domain="conformer", data=array(
                [[[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]]],
                ("conformer", "atom", "xyz"), "angstrom",
            ), status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            reference_structure_id=reference.id, reference_topology_id=None,
            record_ids=(value.id,), record_keys=(value.record_key,),
            atom_mappings=array([[0, 1]], ("conformer", "atom")),
        )
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(
            sources=(source,), source_revisions=(revision,),
            structures=(reference, independent), molecular_records=(value,),
            datasets=(conformers,),
        ))
        self.assertIs(project.datasets[conformers.id], conformers)

    def test_project_rejects_dangling_conformer_records_without_mutation(self):
        molecule = structure()
        dataset = ConformerSet(
            id=uuid4(), revision="conformer-r1", semantic_role="coordinates",
            domain="conformer", data=array(
                [[[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]]],
                ("conformer", "atom", "xyz"), "angstrom",
            ), status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            reference_structure_id=molecule.id, reference_topology_id=None,
            record_ids=(uuid4(),), record_keys=("missing",),
            atom_mappings=array([[0, 1]], ("conformer", "atom")),
        )
        project = QCProject(uuid4(), "0.2")
        with self.assertRaisesRegex(ValueError, "dangling"):
            project.commit(ImportBatch(structures=(molecule,), datasets=(dataset,)))
        self.assertEqual(project.structures, {})
        self.assertEqual(project.datasets, {})

    def test_project_rejects_cross_registry_and_molecular_dangling_references(self):
        molecule = structure()
        source = SourceRecord(molecule.id, "records.sdf", "file", "2026-07-27T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            QCProject(uuid4(), "0.2").commit(
                ImportBatch(sources=(source,), structures=(molecule,))
            )

        source, revision = source_revision((molecule.id,))
        topology_id = uuid4()
        record_value = record(molecule.id, topology_id)
        record_value = MolecularRecord(
            **{
                name: (revision.id if name == "source_revision_id" else getattr(record_value, name))
                for name in record_value.__dataclass_fields__
            }
        )
        column = RecordPropertyColumn(
            id=uuid4(), revision="column-r1", semantic_role="energy", domain="record",
            data=array([1.0], ("record",), "hartree"), status=DatasetStatus.COMPLETE,
            source_calculation=None, provenance_ids=(), record_ids=(uuid4(),),
        )
        cases = (
            (
                "topology",
                ImportBatch(
                    sources=(source,), source_revisions=(revision,), structures=(molecule,),
                    molecular_records=(record_value,),
                ),
                "topology",
            ),
            (
                "record_property",
                ImportBatch(structures=(molecule,), datasets=(column,)),
                "record property",
            ),
            (
                "revision_created_entity",
                ImportBatch(
                    sources=(source,),
                    source_revisions=(SourceRevision(
                        **{
                            name: ((uuid4(),) if name == "created_entity_ids" else getattr(revision, name))
                            for name in revision.__dataclass_fields__
                        }
                    ),),
                ),
                "created entity",
            ),
        )
        for name, batch, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                QCProject(uuid4(), "0.2").commit(batch)

        provenance_missing = MolecularRecord(
            **{
                name: (
                    (uuid4(),) if name == "provenance_ids"
                    else None if name == "topology_id"
                    else getattr(record_value, name)
                )
                for name in record_value.__dataclass_fields__
            }
        )
        with self.assertRaisesRegex(ValueError, "provenance"):
            QCProject(uuid4(), "0.2").commit(ImportBatch(
                sources=(source,), source_revisions=(revision,), structures=(molecule,),
                molecular_records=(provenance_missing,),
            ))

    def test_project_sidecar_and_reader_api_round_trip(self):
        molecule = structure(identity())
        source_revision_id = uuid4()
        value = record(molecule.id)
        value = MolecularRecord(
            **{name: (source_revision_id if name == "source_revision_id" else getattr(value, name))
               for name in value.__dataclass_fields__}
        )
        source, revision = source_revision((molecule.id, value.id))
        value = MolecularRecord(
            **{name: (revision.id if name == "source_revision_id" else getattr(value, name))
               for name in value.__dataclass_fields__}
        )
        project = QCProject(uuid4(), "0.2")
        # Records are intentionally rejected until their source revision exists.
        with self.assertRaisesRegex(ValueError, "source revision"):
            project.commit(ImportBatch(structures=(molecule,), molecular_records=(value,)))
        batch = ImportBatch(
            sources=(source,), source_revisions=(revision,), structures=(molecule,),
            molecular_records=(value,),
        )
        project.commit(batch)
        self.assertEqual(project.molecular_records[value.id], value)
        public = reader_api.public_batch_from_internal(
            batch
        )
        self.assertEqual(public.molecular_records, (value,))
        self.assertEqual(
            reader_api.internal_batch_from_public(public).molecular_records, (value,)
        )
        with TemporaryDirectory() as temporary:
            document = reader_api.public_batch_document(public, temporary)
            restored = reader_api.public_batch_from_document(document, temporary)
        self.assertEqual(restored.molecular_records, (value,))

        with TemporaryDirectory() as temporary:
            root = f"{temporary}/records.cbq"
            save_project(root, project)
            reopened = open_project(root)
            try:
                self.assertEqual(
                    reopened.structures[molecule.id].atomic_identity.atom_count, 2
                )
                self.assertEqual(reopened.molecular_records[value.id].raw_block, value.raw_block)
                self.assertEqual(
                    reopened.molecular_records[value.id].ordered_raw_properties,
                    value.ordered_raw_properties,
                )
            finally:
                close_project(reopened)

    def test_current_sidecar_and_canonical_documents_accept_only_missing_task1_fields(self):
        molecule = structure()
        source, revision = source_revision((molecule.id,))
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(
            sources=(source,), source_revisions=(revision,), structures=(molecule,),
        ))
        with TemporaryDirectory() as temporary:
            root = f"{temporary}/legacy.cbq"
            save_project(root, project)
            manifest_path = f"{root}/manifest.json"
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            del manifest["project"]["molecular_records"]
            del manifest["project"]["structures"]["$dict"][0][1]["atomic_identity"]
            write_manifest(Path(manifest_path), manifest)
            reopened = open_project(root)
            try:
                self.assertEqual(reopened.molecular_records, {})
                self.assertIsNone(reopened.structures[molecule.id].atomic_identity)
            finally:
                close_project(reopened)

            document = reader_api.public_batch_document(
                reader_api.public_batch_from_internal(
                    ImportBatch(structures=(molecule,))
                ), temporary
            )
            legacy = json.loads(document)
            legacy["batch"].pop("molecular_records", None)
            legacy["batch"]["structures"]["$tuple"][0].pop("atomic_identity", None)
            restored = reader_api.public_batch_from_document(
                json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                temporary,
            )
        self.assertEqual(restored.molecular_records, ())
        self.assertIsNone(restored.structures[0].atomic_identity)

    def test_project_validates_and_persists_record_column_and_conformer_set(self):
        molecule = structure()
        value = record(molecule.id)
        source, revision = source_revision((molecule.id, value.id))
        value = MolecularRecord(
            **{name: (revision.id if name == "source_revision_id" else getattr(value, name))
               for name in value.__dataclass_fields__}
        )
        column = RecordPropertyColumn(
            id=uuid4(), revision="energy-r1", semantic_role="energy", domain="record",
            data=array([-1.0], ("record",), "hartree"), status=DatasetStatus.COMPLETE,
            source_calculation=None, provenance_ids=(), record_ids=(value.id,),
        )
        conformers = ConformerSet(
            id=uuid4(), revision="conformers-r1", semantic_role="coordinates",
            domain="conformer", data=array(
                [[[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]]],
                ("conformer", "atom", "xyz"), "angstrom",
            ), status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            reference_structure_id=molecule.id, reference_topology_id=None,
            record_ids=(value.id,), record_keys=(value.record_key,),
            atom_mappings=array([[0, 1]], ("conformer", "atom")),
        )
        project = QCProject(uuid4(), "0.2")
        batch = ImportBatch(
            sources=(source,), source_revisions=(revision,), structures=(molecule,),
            molecular_records=(value,), datasets=(column, conformers),
        )
        project.commit(batch)
        self.assertIs(project.datasets[column.id], column)
        public = reader_api.public_batch_from_internal(batch)
        self.assertIsInstance(
            reader_api.internal_batch_from_public(public).datasets[1], ConformerSet
        )
        with TemporaryDirectory() as temporary:
            root = f"{temporary}/models.cbq"
            save_project(root, project)
            reopened = open_project(root)
            try:
                self.assertIsInstance(reopened.datasets[column.id], RecordPropertyColumn)
                self.assertIsInstance(reopened.datasets[conformers.id], ConformerSet)
                self.assertEqual(reopened.datasets[conformers.id].atom_mappings.shape, (1, 2))
                column_values = reopened.datasets[column.id].data.values
                values = reopened.datasets[conformers.id].data.values
                self.assertFalse(column_values.loaded)
                self.assertFalse(values.loaded)
                self.assertEqual(values[0, 0, 0], 0.0)
                self.assertTrue(values.loaded)
            finally:
                close_project(reopened)
            self.assertFalse(column_values.loaded)
            self.assertFalse(values.loaded)

    def test_public_batch_rejects_unsafe_ndarray_dtypes(self):
        for values in (
            numpy.asarray([[object(), object(), object()]], dtype=object),
            numpy.zeros((1, 3), dtype=[("value", numpy.float64)]),
        ):
            with self.subTest(dtype=values.dtype), self.assertRaisesRegex(
                TypeError, "object, structured or subarray"
            ):
                reader_api.public_batch_from_internal(ImportBatch(structures=(
                    Structure(
                        id=uuid4(), revision="unsafe-r1", atomic_numbers=(1,),
                        coordinates=ArrayData(values, ("atom", "xyz"), "angstrom"),
                    ),
                )))
        with TemporaryDirectory() as temporary:
            values = numpy.memmap(
                f"{temporary}/unsafe.npy", mode="w+", shape=(1, 3),
                dtype=[("value", numpy.float64)],
            )
            with self.assertRaisesRegex(TypeError, "object, structured or subarray"):
                reader_api.public_batch_from_internal(ImportBatch(structures=(
                    Structure(
                        id=uuid4(), revision="unsafe-memmap-r1", atomic_numbers=(1,),
                        coordinates=ArrayData(values, ("atom", "xyz"), "angstrom"),
                    ),
                )))
            values._mmap.close()

    def test_public_batch_rejects_unsafe_memoryview_dtypes(self):
        for values in (
            memoryview(numpy.empty((1, 3), dtype=object)),
            memoryview(numpy.zeros((1, 3), dtype=[("value", numpy.float64)])),
        ):
            structure_value = Structure(
                id=uuid4(), revision="unsafe-memoryview-r1", atomic_numbers=(1,),
                coordinates=ArrayData(values, ("atom", "xyz"), "angstrom"),
            )
            with self.subTest(format=values.format), self.assertRaisesRegex(
                TypeError, "object, structured or subarray"
            ):
                reader_api.public_batch_from_internal(ImportBatch(structures=(structure_value,)))
            with self.subTest(format=values.format), self.assertRaises(
                reader_api.PublicBatchValidationError
            ):
                reader_api.internal_batch_from_public(
                    reader_api.PublicImportBatch(structures=(structure_value,))
                )

    def test_task1_additive_fields_reject_malformed_and_unknown_values(self):
        molecule = structure(identity())
        value = record(molecule.id)
        source, revision = source_revision((molecule.id, value.id))
        value = MolecularRecord(
            **{
                name: (revision.id if name == "source_revision_id" else getattr(value, name))
                for name in value.__dataclass_fields__
            }
        )
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(
            sources=(source,), source_revisions=(revision,), structures=(molecule,),
            molecular_records=(value,),
        ))
        with TemporaryDirectory() as temporary:
            root = f"{temporary}/malformed.cbq"
            save_project(root, project)
            manifest_path = Path(root) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for field, replacement in (
                ("unknown_task1_field", True),
                ("raw_block", {"$uuid": str(uuid4())}),
            ):
                with self.subTest(field=field):
                    candidate = json.loads(json.dumps(manifest))
                    candidate["project"]["molecular_records"]["$dict"][0][1][field] = replacement
                    write_manifest(manifest_path, candidate)
                    with self.assertRaises(SidecarIntegrityError):
                        open_project(root)


if __name__ == "__main__":
    unittest.main()
