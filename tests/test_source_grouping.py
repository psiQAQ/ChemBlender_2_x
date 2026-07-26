import dataclasses
import tempfile
import unittest
from inspect import signature
from pathlib import Path
from uuid import uuid4

import numpy

from ChemBlender.core.import_pipeline import grouping as grouping_module
from ChemBlender.core.import_pipeline import (
    CalculationGroup,
    GroupingEvidence,
    ImportPreview,
    SourceGroupSuggestion,
    SourcePreview,
    StagedImportSession,
    suggest_source_groups,
)
from ChemBlender.core.model import (
    ArrayData,
    CIFEnvelope,
    CalculationMetadata,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    ImportBatch,
    MolecularTopology,
    PeriodicSiteData,
    PropertyDataset,
    QCSchemaEnvelope,
    SourceRecord,
    SourceRevision,
    Structure,
)


class SourceGroupingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sessions = []

    def tearDown(self):
        for session in reversed(self.sessions):
            if session.root.exists():
                session.discard()
        self.temporary.cleanup()

    def session(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.sessions.append(session)
        return session

    @staticmethod
    def molecular_structure(
        coordinates,
        *,
        atomic_numbers=(8, 1, 1),
        topology=None,
    ):
        coordinates = numpy.asarray(coordinates, dtype=float).reshape(
            (len(atomic_numbers), 3)
        )
        return Structure(
            id=uuid4(),
            revision="r1",
            atomic_numbers=atomic_numbers,
            coordinates=ArrayData(
                coordinates,
                ("atom", "xyz"),
                "angstrom",
            ),
            topology=topology,
        )

    @staticmethod
    def topology(bonds, orders):
        return MolecularTopology(
            bond_indices=ArrayData(
                numpy.asarray(bonds, dtype=int),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=ArrayData(
                numpy.asarray(orders, dtype=float),
                ("bond",),
                "dimensionless",
            ),
        )

    @staticmethod
    def periodic_structure(
        cell,
        fractional,
        atomic_numbers,
        *,
        pbc=(True, True, True),
        cif_envelope_id=None,
    ):
        atom_count = len(atomic_numbers)
        cell = numpy.asarray(cell, dtype=float)
        fractional = numpy.asarray(fractional, dtype=float)
        return Structure(
            id=uuid4(),
            revision="r1",
            atomic_numbers=atomic_numbers,
            coordinates=ArrayData(
                fractional @ cell,
                ("atom", "xyz"),
                "angstrom",
            ),
            cell=ArrayData(
                cell,
                ("cell_vector", "xyz"),
                "angstrom",
            ),
            periodic=PeriodicSiteData(
                fractional_coordinates=ArrayData(
                    fractional,
                    ("atom", "xyz"),
                    "dimensionless",
                ),
                site_labels=tuple(
                    f"site-{index}" for index in range(atom_count)
                ),
                occupancies=ArrayData(
                    numpy.ones(atom_count),
                    ("atom",),
                    "dimensionless",
                ),
                isotropic_displacements=None,
                anisotropic_displacements=None,
                adp_types=("none",) * atom_count,
                disorder_groups=(0,) * atom_count,
                declared_space_group_name=None,
                declared_space_group_number=None,
                symmetry_operations=(),
                cif_envelope_id=cif_envelope_id,
                pbc=pbc,
            ),
        )

    @staticmethod
    def calculation(*, structure_ids=(), metadata=None):
        return CalculationRecord(
            id=uuid4(),
            revision="r1",
            status=CalculationStatus.SUCCESS,
            input_structure_ids=structure_ids,
            result_structure_ids=(),
            dataset_ids=(),
            provenance_ids=(),
            metadata=metadata,
        )

    @staticmethod
    def dataset(*, source_calculation=None):
        return PropertyDataset(
            id=uuid4(),
            revision="r1",
            semantic_role="energy",
            domain="sample",
            data=ArrayData(
                numpy.asarray([1.0]),
                ("sample",),
                "electron_volt",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=source_calculation,
            provenance_ids=(),
        )

    @staticmethod
    def metadata():
        return CalculationMetadata(
            driver="energy",
            method="b3lyp",
            basis="def2-svp",
            molecular_charge=0,
            molecular_multiplicity=1,
            program="orca",
            program_version="6",
        )

    def staged_preview(self, specs, *, session=None):
        session = session or self.session()
        rows = []
        batch_ids = []
        revisions = []
        batches = []
        for index, spec in enumerate(specs):
            source_id = spec.get("source_id", uuid4())
            source = SourceRecord(
                id=source_id,
                display_name=spec["filename"],
                source_kind="local_file",
                created_at_utc=spec.get(
                    "created_at_utc", "2026-07-24T00:00:00Z"
                ),
            )
            structures = tuple(spec.get("structures", ()))
            cif_envelopes = tuple(spec.get("cif_envelopes", ()))
            qcschema_envelopes = tuple(spec.get("qcschema_envelopes", ()))
            calculations = tuple(spec.get("calculations", ()))
            datasets = tuple(spec.get("datasets", ()))
            created_entity_ids = tuple(
                entity.id
                for entity in (
                    structures
                    + cif_envelopes
                    + qcschema_envelopes
                    + calculations
                    + datasets
                )
            )
            revision = SourceRevision(
                id=spec.get("revision_id", uuid4()),
                source_id=spec.get("revision_source_id", source_id),
                content_hash=f"{index + 1:064x}",
                byte_size=index + 1,
                locator=str(self.root / spec.get("directory", f"d{index}") / spec["filename"]),
                locator_kind="absolute_path",
                original_filename=spec["filename"],
                reader_plugin_id="chemblender.builtin",
                reader_id="fixture",
                reader_version="1",
                reader_api_version="0.1",
                import_parameters_hash="a" * 64,
                parse_identity=f"{index + 11:064x}",
                created_entity_ids=spec.get(
                    "created_entity_ids", created_entity_ids
                ),
                diagnostic_ids=(),
            )
            batch = ImportBatch(
                sources=(source,),
                source_revisions=(revision,),
                structures=structures,
                cif_envelopes=cif_envelopes,
                qcschema_envelopes=qcschema_envelopes,
                calculations=calculations,
                datasets=datasets,
            )
            batch_id = uuid4()
            session.register_result(batch_id, batch)
            row = SourcePreview(
                source_id=source.id,
                source_path=Path(revision.locator),
                selected_reader_id=revision.reader_id,
                content_hash=revision.content_hash,
                byte_size=revision.byte_size,
                capabilities=("structure",),
                staged_batch_ids=(batch_id,),
            )
            rows.append(row)
            batch_ids.append(batch_id)
            revisions.append(revision)
            batches.append(batch)
        return (
            session,
            ImportPreview(
                session_id=session.id,
                source_previews=tuple(rows),
                staged_batch_ids=tuple(batch_ids),
            ),
            tuple(revisions),
            tuple(batches),
        )

    @staticmethod
    def evidence_of_kind(suggestions, kind):
        return tuple(
            evidence
            for suggestion in suggestions
            for evidence in suggestion.evidence
            if evidence.kind == kind
        )

    def test_evidence_ranking_is_exact(self):
        revision_ids = (uuid4(), uuid4())
        kinds = (
            "explicit_internal_reference",
            "exact_mapped_structure",
            "kabsch_rmsd",
            "metadata",
            "filename_directory",
        )
        evidence = tuple(
            GroupingEvidence(
                kind=kind,
                source_revision_ids=revision_ids,
                summary=kind,
            )
            for kind in kinds
        )

        self.assertEqual(tuple(item.rank for item in evidence), (5, 4, 3, 2, 1))
        self.assertEqual(
            tuple(item.confidence for item in evidence),
            ("high", "high", "medium", "low", "low"),
        )

    def test_ids_are_derived_from_normalized_content_and_cannot_be_forged(self):
        revision_ids = (uuid4(), uuid4())
        forged_id = uuid4()
        with self.assertRaises(TypeError):
            GroupingEvidence(
                id=forged_id,
                kind="metadata",
                source_revision_ids=revision_ids,
                summary="metadata",
            )

        high = GroupingEvidence(
            kind="exact_mapped_structure",
            source_revision_ids=revision_ids,
            summary="same structure",
        )
        low = GroupingEvidence(
            kind="filename_directory",
            source_revision_ids=tuple(reversed(revision_ids)),
            summary="same filename",
        )
        changed_summary = GroupingEvidence(
            kind="exact_mapped_structure",
            source_revision_ids=tuple(reversed(revision_ids)),
            summary="different summary",
        )
        self.assertNotIn("id", signature(GroupingEvidence).parameters)
        self.assertNotEqual(high.id, low.id)
        self.assertNotEqual(high.id, changed_summary.id)
        self.assertEqual(
            high.id,
            GroupingEvidence(
                kind=high.kind,
                source_revision_ids=tuple(reversed(revision_ids)),
                summary=high.summary,
            ).id,
        )

        suggestion = SourceGroupSuggestion(
            source_revision_ids=revision_ids,
            evidence=(low, high),
        )
        with self.assertRaises(TypeError):
            SourceGroupSuggestion(
                id=forged_id,
                source_revision_ids=revision_ids,
                evidence=(high,),
            )
        reversed_suggestion = SourceGroupSuggestion(
            source_revision_ids=tuple(reversed(revision_ids)),
            evidence=(high, low),
        )
        self.assertNotIn("id", signature(SourceGroupSuggestion).parameters)
        self.assertEqual(suggestion.id, reversed_suggestion.id)
        self.assertNotEqual(
            suggestion.id,
            SourceGroupSuggestion(
                source_revision_ids=revision_ids,
                evidence=(low, changed_summary),
            ).id,
        )
        self.assertNotEqual(
            suggestion.confirm((high.id,)).id,
            suggestion.confirm((low.id,)).id,
        )
        self.assertNotIn("id", signature(CalculationGroup).parameters)
        with self.assertRaises(TypeError):
            CalculationGroup(
                id=forged_id,
                suggestion_id=suggestion.id,
                source_revision_ids=revision_ids,
                evidence_ids=(high.id,),
            )

    def test_explicit_calculation_reference_has_highest_priority(self):
        structure = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-1, 0, 0))
        )
        calculation = self.calculation(structure_ids=(structure.id,))
        session, preview, revisions, _ = self.staged_preview(
            (
                {
                    "filename": "structure.xyz",
                    "directory": "left",
                    "structures": (structure,),
                },
                {
                    "filename": "result.out",
                    "directory": "right",
                    "calculations": (calculation,),
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)

        evidence = self.evidence_of_kind(
            suggestions, "explicit_internal_reference"
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(
            evidence[0].source_revision_ids,
            tuple(sorted((item.id for item in revisions), key=str)),
        )
        self.assertEqual(evidence[0].rank, 5)
        self.assertIn(structure.id, evidence[0].entity_ids)
        self.assertIn(calculation.id, evidence[0].entity_ids)

    def test_typed_reference_validation_rejects_wrong_and_dangling_refs(self):
        dataset = self.dataset()
        wrong_type = self.calculation(structure_ids=(dataset.id,))
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "dataset.dat",
                    "directory": "a",
                    "datasets": (dataset,),
                },
                {
                    "filename": "wrong.out",
                    "directory": "b",
                    "calculations": (wrong_type,),
                },
            )
        )
        with self.assertRaises(ValueError):
            suggest_source_groups(preview, session)

        dangling = self.calculation(structure_ids=(uuid4(),))
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "dangling.out",
                    "directory": "a",
                    "calculations": (dangling,),
                },
                {
                    "filename": "other.xyz",
                    "directory": "b",
                },
            )
        )
        with self.assertRaises(ValueError):
            suggest_source_groups(preview, session)

    def test_dataset_source_calculation_creates_explicit_evidence(self):
        calculation = self.calculation()
        dataset = self.dataset(source_calculation=calculation.id)
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "calculation.out",
                    "directory": "a",
                    "calculations": (calculation,),
                },
                {
                    "filename": "property.dat",
                    "directory": "b",
                    "datasets": (dataset,),
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)

        evidence = self.evidence_of_kind(
            suggestions, "explicit_internal_reference"
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].rank, 5)
        self.assertEqual(
            set(evidence[0].entity_ids),
            {calculation.id, dataset.id},
        )

    def test_nested_calculation_metadata_reference_creates_explicit_evidence(
        self,
    ):
        envelope = QCSchemaEnvelope(
            id=uuid4(),
            revision="r1",
            schema_name="qcschema_output",
            schema_version=1,
            source_bytes=b"{}",
            provenance_ids=(),
        )
        metadata = dataclasses.replace(
            self.metadata(),
            qcschema_envelope_id=envelope.id,
        )
        calculation = self.calculation(metadata=metadata)
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "schema.json",
                    "directory": "a",
                    "qcschema_envelopes": (envelope,),
                },
                {
                    "filename": "calculation.out",
                    "directory": "b",
                    "calculations": (calculation,),
                },
            )
        )

        evidence = self.evidence_of_kind(
            suggest_source_groups(preview, session),
            "explicit_internal_reference",
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].rank, 5)
        self.assertEqual(
            set(evidence[0].entity_ids),
            {calculation.id, envelope.id},
        )

    def test_nested_reference_uses_installed_extension_model_namespace(self):
        model_types = (
            ImportBatch,
            QCSchemaEnvelope,
            CalculationRecord,
            CalculationMetadata,
        )
        original_modules = {
            model_type: model_type.__module__ for model_type in model_types
        }
        try:
            for model_type in model_types:
                model_type.__module__ = (
                    "bl_ext.user_default.chemblender.core.model."
                    f"{original_modules[model_type].rsplit('.', 1)[-1]}"
                )
            envelope = QCSchemaEnvelope(
                id=uuid4(),
                revision="r1",
                schema_name="qcschema_output",
                schema_version=1,
                source_bytes=b"{}",
                provenance_ids=(),
            )
            calculation = self.calculation(
                metadata=dataclasses.replace(
                    self.metadata(),
                    qcschema_envelope_id=envelope.id,
                )
            )
            session, preview, _, _ = self.staged_preview(
                (
                    {
                        "filename": "schema.json",
                        "directory": "a",
                        "qcschema_envelopes": (envelope,),
                    },
                    {
                        "filename": "calculation.out",
                        "directory": "b",
                        "calculations": (calculation,),
                    },
                )
            )
            evidence = self.evidence_of_kind(
                suggest_source_groups(preview, session),
                "explicit_internal_reference",
            )
        finally:
            for model_type, module in original_modules.items():
                model_type.__module__ = module

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].rank, 5)
        self.assertEqual(
            set(evidence[0].entity_ids),
            {calculation.id, envelope.id},
        )

    def test_nested_periodic_cif_reference_creates_explicit_evidence(self):
        envelope = CIFEnvelope(
            id=uuid4(),
            revision="r1",
            block_name="fixture",
            source_bytes=b"data_fixture",
            tag_names=("_cell_length_a",),
            provenance_ids=(),
        )
        structure = self.periodic_structure(
            numpy.eye(3),
            ((0.0, 0.0, 0.0),),
            (6,),
            cif_envelope_id=envelope.id,
        )
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "structure.cif",
                    "directory": "a",
                    "cif_envelopes": (envelope,),
                },
                {
                    "filename": "structure.dat",
                    "directory": "b",
                    "structures": (structure,),
                },
            )
        )

        evidence = self.evidence_of_kind(
            suggest_source_groups(preview, session),
            "explicit_internal_reference",
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].rank, 5)
        self.assertEqual(
            set(evidence[0].entity_ids),
            {structure.id, envelope.id},
        )

    def test_exact_molecular_mapping_uses_atomic_numbers_and_topology(self):
        topology = self.topology(((0, 1), (0, 2)), (1.0, 1.0))
        first = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-0.2, 0.9, 0)),
            topology=topology,
        )
        permuted_topology = self.topology(((1, 0), (1, 2)), (1.0, 1.0))
        second = self.molecular_structure(
            ((6, 2, 1), (5, 2, 1), (4.8, 2.9, 1)),
            atomic_numbers=(1, 8, 1),
            topology=permuted_topology,
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "a.xyz", "directory": "a", "structures": (first,)},
                {"filename": "b.xyz", "directory": "b", "structures": (second,)},
            )
        )
        before = (
            first.coordinates.values.copy(),
            second.coordinates.values.copy(),
        )

        suggestions = suggest_source_groups(preview, session)

        self.assertEqual(
            len(self.evidence_of_kind(suggestions, "exact_mapped_structure")),
            1,
        )
        numpy.testing.assert_array_equal(first.coordinates.values, before[0])
        numpy.testing.assert_array_equal(second.coordinates.values, before[1])

    def test_complete_mapped_topology_rejects_cycle_vs_disconnected_triangles(self):
        coordinates = tuple(
            (
                numpy.cos(index * numpy.pi / 3),
                numpy.sin(index * numpy.pi / 3),
                0.0,
            )
            for index in range(6)
        )
        cycle = self.topology(
            tuple((index, (index + 1) % 6) for index in range(6)),
            (1.0,) * 6,
        )
        triangles = self.topology(
            ((0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3)),
            (1.0,) * 6,
        )
        first = self.molecular_structure(
            coordinates,
            atomic_numbers=(6,) * 6,
            topology=cycle,
        )
        second = self.molecular_structure(
            coordinates,
            atomic_numbers=(6,) * 6,
            topology=triangles,
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "cycle.xyz", "directory": "a", "structures": (first,)},
                {
                    "filename": "triangles.xyz",
                    "directory": "b",
                    "structures": (second,),
                },
            )
        )

        self.assertEqual(suggest_source_groups(preview, session), ())

    def test_one_sided_topology_is_conservatively_not_structure_evidence(self):
        topology = self.topology(((0, 1), (0, 2)), (1.0, 1.0))
        coordinates = ((0, 0, 0), (1, 0, 0), (-0.2, 0.9, 0))
        first = self.molecular_structure(coordinates, topology=topology)
        second = self.molecular_structure(coordinates)
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "with.xyz",
                    "directory": "a",
                    "structures": (first,),
                },
                {
                    "filename": "without.xyz",
                    "directory": "b",
                    "structures": (second,),
                },
            )
        )

        self.assertEqual(suggest_source_groups(preview, session), ())

    def test_rigid_rotation_and_translation_produce_kabsch_evidence(self):
        first = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-0.2, 0.9, 0))
        )
        rotation = numpy.asarray(((0, -1, 0), (1, 0, 0), (0, 0, 1)))
        transformed = numpy.asarray(first.coordinates.values) @ rotation
        transformed += numpy.asarray((5.0, -3.0, 2.0))
        second = self.molecular_structure(transformed)
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "a.xyz", "directory": "a", "structures": (first,)},
                {"filename": "b.xyz", "directory": "b", "structures": (second,)},
            )
        )

        suggestions = suggest_source_groups(preview, session)

        evidence = self.evidence_of_kind(suggestions, "kabsch_rmsd")
        self.assertEqual(len(evidence), 1)
        self.assertLess(evidence[0].metric, 1e-12)
        self.assertEqual(evidence[0].metric_unit, "angstrom")

    def test_kabsch_threshold_is_inclusive_at_point_one_five_angstrom(self):
        threshold = grouping_module._KABSCH_TOLERANCE_ANGSTROM
        self.assertEqual(threshold, 0.15)

        def suggestions_at_rmsd(rmsd):
            first = self.molecular_structure(
                ((-0.5, 0, 0), (0.5, 0, 0)),
                atomic_numbers=(6, 8),
            )
            second = self.molecular_structure(
                ((-0.5 - rmsd, 0, 0), (0.5 + rmsd, 0, 0)),
                atomic_numbers=(6, 8),
            )
            session, preview, _, _ = self.staged_preview(
                (
                    {
                        "filename": "first.xyz",
                        "directory": f"first-{rmsd}",
                        "structures": (first,),
                    },
                    {
                        "filename": "second.xyz",
                        "directory": f"second-{rmsd}",
                        "structures": (second,),
                    },
                )
            )
            return suggest_source_groups(preview, session)

        inside = self.evidence_of_kind(
            suggestions_at_rmsd(0.149),
            "kabsch_rmsd",
        )
        self.assertEqual(len(inside), 1)
        self.assertAlmostEqual(inside[0].metric, 0.149)
        boundary = self.evidence_of_kind(
            suggestions_at_rmsd(0.150),
            "kabsch_rmsd",
        )
        self.assertEqual(len(boundary), 1)
        self.assertAlmostEqual(boundary[0].metric, threshold)
        self.assertEqual(suggestions_at_rmsd(0.151), ())

    def test_nonmatching_composition_produces_no_structure_evidence(self):
        first = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-1, 0, 0))
        )
        second = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-1, 0, 0)),
            atomic_numbers=(6, 1, 1),
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "a.xyz", "directory": "a", "structures": (first,)},
                {"filename": "b.xyz", "directory": "b", "structures": (second,)},
            )
        )

        suggestions = suggest_source_groups(preview, session)

        self.assertEqual(suggestions, ())

    def test_empty_structures_fail_closed_without_false_evidence(self):
        first = self.molecular_structure((), atomic_numbers=())
        second = self.molecular_structure((), atomic_numbers=())
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "a.xyz", "directory": "a", "structures": (first,)},
                {"filename": "b.xyz", "directory": "b", "structures": (second,)},
            )
        )

        self.assertEqual(suggest_source_groups(preview, session), ())

    def test_matching_metadata_is_low_confidence(self):
        first = self.calculation(metadata=self.metadata())
        second = self.calculation(metadata=self.metadata())
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "a.out",
                    "directory": "a",
                    "calculations": (first,),
                },
                {
                    "filename": "b.out",
                    "directory": "b",
                    "calculations": (second,),
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)

        evidence = self.evidence_of_kind(suggestions, "metadata")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].confidence, "low")

    def test_filename_only_is_low_confidence_and_never_reads_source(self):
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "water.xyz", "directory": "a"},
                {"filename": "water.log", "directory": "b"},
            )
        )

        suggestions = suggest_source_groups(preview, session)

        evidence = self.evidence_of_kind(suggestions, "filename_directory")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].rank, 1)
        self.assertEqual(evidence[0].confidence, "low")

    def test_time_proximity_alone_creates_no_suggestion_or_high_fact(self):
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "alpha.xyz",
                    "directory": "a",
                    "created_at_utc": "2026-07-24T00:00:00Z",
                },
                {
                    "filename": "beta.out",
                    "directory": "b",
                    "created_at_utc": "2026-07-24T00:00:01Z",
                },
            )
        )

        self.assertEqual(suggest_source_groups(preview, session), ())

    def test_periodic_exact_uses_metric_composition_and_modulo_coordinates(self):
        first = self.periodic_structure(
            numpy.diag((3.0, 4.0, 5.0)),
            ((0.1, 0.2, 0.3), (0.6, 0.7, 0.8)),
            (14, 8),
        )
        second = self.periodic_structure(
            numpy.diag((3.0, 4.0, 5.0)),
            ((1.6, -0.3, 0.8), (-0.9, 1.2, 0.3)),
            (8, 14),
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "a.cif", "directory": "a", "structures": (first,)},
                {"filename": "b.cif", "directory": "b", "structures": (second,)},
            )
        )

        suggestions = suggest_source_groups(preview, session)

        self.assertEqual(
            len(self.evidence_of_kind(suggestions, "exact_mapped_structure")),
            1,
        )

    def test_periodic_exact_allows_one_global_origin_shift_and_atom_reorder(self):
        cell = numpy.diag((3.0, 4.0, 5.0))
        first_fractional = numpy.asarray(
            ((0.1, 0.2, 0.3), (0.4, 0.6, 0.8), (0.75, 0.1, 0.55))
        )
        shift = numpy.asarray((0.25, -0.4, 0.6))
        order = (2, 0, 1)
        second_fractional = (
            first_fractional[list(order)] + shift
        ) % 1.0
        first = self.periodic_structure(
            cell,
            first_fractional,
            (14, 8, 1),
        )
        second = self.periodic_structure(
            cell,
            second_fractional,
            (1, 14, 8),
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "first.cif", "directory": "a", "structures": (first,)},
                {
                    "filename": "second.cif",
                    "directory": "b",
                    "structures": (second,),
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)

        self.assertEqual(
            len(self.evidence_of_kind(suggestions, "exact_mapped_structure")),
            1,
        )

    def test_periodic_origin_shift_respects_partial_pbc_axes(self):
        cell = numpy.diag((3.0, 4.0, 5.0))
        first = self.periodic_structure(
            cell,
            ((0.1, 0.2, 0.3), (0.6, 0.7, 0.8)),
            (14, 8),
            pbc=(True, True, False),
        )
        periodic_shift = self.periodic_structure(
            cell,
            ((0.35, 0.8, 0.3), (0.85, 0.3, 0.8)),
            (14, 8),
            pbc=(True, True, False),
        )
        nonperiodic_shift = self.periodic_structure(
            cell,
            ((0.1, 0.2, 0.4), (0.6, 0.7, 0.9)),
            (14, 8),
            pbc=(True, True, False),
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "first.cif", "directory": "a", "structures": (first,)},
                {
                    "filename": "periodic.cif",
                    "directory": "b",
                    "structures": (periodic_shift,),
                },
                {
                    "filename": "nonperiodic.cif",
                    "directory": "c",
                    "structures": (nonperiodic_shift,),
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)
        exact_pairs = {
            item.source_revision_ids
            for item in self.evidence_of_kind(
                suggestions, "exact_mapped_structure"
            )
        }
        revisions = tuple(
            session.result(row.staged_batch_ids[0]).source_revisions[0].id
            for row in preview.source_previews
        )

        self.assertIn(
            tuple(sorted((revisions[0], revisions[1]), key=str)),
            exact_pairs,
        )
        self.assertNotIn(
            tuple(sorted((revisions[0], revisions[2]), key=str)),
            exact_pairs,
        )

    def test_periodic_primitive_conventional_candidate_requires_review(self):
        primitive = self.periodic_structure(
            numpy.eye(3),
            ((0.0, 0.0, 0.0),),
            (14,),
        )
        conventional = self.periodic_structure(
            numpy.diag((2.0, 1.0, 1.0)),
            ((0.0, 0.0, 0.0), (0.5, 0.0, 0.0)),
            (14, 14),
        )
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "primitive.cif",
                    "directory": "a",
                    "structures": (primitive,),
                },
                {
                    "filename": "conventional.cif",
                    "directory": "b",
                    "structures": (conventional,),
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)

        conflicts = self.evidence_of_kind(
            suggestions, "periodic_equivalence_conflict"
        )
        self.assertEqual(len(conflicts), 1)
        self.assertTrue(conflicts[0].is_conflict)
        self.assertTrue(conflicts[0].requires_review)
        self.assertEqual(conflicts[0].confidence, "review")
        self.assertTrue(suggestions[0].requires_review)
        self.assertNotIn(
            "exact_mapped_structure",
            {item.kind for item in suggestions[0].evidence},
        )

    def test_input_order_does_not_change_output_or_ids(self):
        first = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-1, 0, 0))
        )
        second = self.molecular_structure(
            ((3, 4, 5), (4, 4, 5), (2, 4, 5))
        )
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "same.xyz", "directory": "a", "structures": (first,)},
                {"filename": "same.log", "directory": "b", "structures": (second,)},
            )
        )
        reversed_preview = dataclasses.replace(
            preview,
            source_previews=tuple(reversed(preview.source_previews)),
            staged_batch_ids=tuple(reversed(preview.staged_batch_ids)),
        )

        forward = suggest_source_groups(preview, session)
        backward = suggest_source_groups(reversed_preview, session)

        self.assertEqual(forward, backward)
        self.assertEqual(
            tuple(item.id for item in forward),
            tuple(item.id for item in backward),
        )

    def test_multisource_confidence_and_confirmation_require_connected_evidence(self):
        first = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-0.2, 0.9, 0))
        )
        second = self.molecular_structure(
            ((4, 3, 2), (5, 3, 2), (3.8, 3.9, 2))
        )
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "alpha.xyz",
                    "directory": "a",
                    "structures": (first,),
                },
                {
                    "filename": "bridge.log",
                    "directory": "b",
                    "structures": (second,),
                },
                {
                    "filename": "bridge.out",
                    "directory": "c",
                },
            )
        )

        suggestions = suggest_source_groups(preview, session)

        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        exact = next(
            item
            for item in suggestion.evidence
            if item.kind == "exact_mapped_structure"
        )
        filename = next(
            item
            for item in suggestion.evidence
            if item.kind == "filename_directory"
        )
        self.assertEqual(suggestion.confidence, "low")
        with self.assertRaises(ValueError):
            suggestion.confirm((exact.id,))
        group = suggestion.confirm((exact.id, filename.id))
        self.assertEqual(
            set(group.source_revision_ids),
            set(suggestion.source_revision_ids),
        )

    def test_irrelevant_low_edge_does_not_reduce_all_high_connectivity(self):
        first_structure = self.molecular_structure(
            ((0, 0, 0),), atomic_numbers=(1,)
        )
        second_structure = self.molecular_structure(
            ((0, 0, 0),), atomic_numbers=(6,)
        )
        second_calculation = self.calculation(
            structure_ids=(first_structure.id,)
        )
        third_calculation = self.calculation(
            structure_ids=(second_structure.id,)
        )
        session, preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "extra.out",
                    "directory": "a",
                    "structures": (first_structure,),
                },
                {
                    "filename": "middle.out",
                    "directory": "b",
                    "structures": (second_structure,),
                    "calculations": (second_calculation,),
                },
                {
                    "filename": "extra.log",
                    "directory": "c",
                    "calculations": (third_calculation,),
                },
            )
        )

        suggestion = suggest_source_groups(preview, session)[0]

        self.assertEqual(suggestion.confidence, "high")
        self.assertEqual(
            sum(
                item.kind == "explicit_internal_reference"
                for item in suggestion.evidence
            ),
            2,
        )
        self.assertEqual(
            sum(
                item.kind == "filename_directory"
                for item in suggestion.evidence
            ),
            1,
        )

    def test_invalid_preview_session_and_batch_associations_fail_closed(self):
        session, preview, _, _ = self.staged_preview(
            (
                {"filename": "a.xyz"},
                {"filename": "b.xyz"},
            )
        )
        other_session = self.session()
        unknown_batch = uuid4()
        unknown_row = dataclasses.replace(
            preview.source_previews[0],
            staged_batch_ids=(unknown_batch,),
        )
        unknown_preview = dataclasses.replace(
            preview,
            source_previews=(unknown_row, preview.source_previews[1]),
            staged_batch_ids=(unknown_batch, preview.staged_batch_ids[1]),
        )

        with self.assertRaises(TypeError):
            suggest_source_groups(object(), session)
        with self.assertRaises(TypeError):
            suggest_source_groups(preview, object())
        with self.assertRaises(ValueError):
            suggest_source_groups(preview, other_session)
        with self.assertRaises(ValueError):
            suggest_source_groups(unknown_preview, session)

        bad_session, bad_preview, _, _ = self.staged_preview(
            (
                {"filename": "a.xyz", "revision_source_id": uuid4()},
                {"filename": "b.xyz"},
            )
        )
        with self.assertRaises(ValueError):
            suggest_source_groups(bad_preview, bad_session)

        duplicate = self.molecular_structure(
            ((0, 0, 0),), atomic_numbers=(1,)
        )
        bad_session, bad_preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "duplicate.xyz",
                    "structures": (duplicate, duplicate),
                    "created_entity_ids": (duplicate.id,),
                },
            )
        )
        with self.assertRaises(ValueError):
            suggest_source_groups(bad_preview, bad_session)

        structure = self.molecular_structure(
            ((0, 0, 0),), atomic_numbers=(1,)
        )
        bad_session, bad_preview, _, _ = self.staged_preview(
            (
                {
                    "filename": "a.xyz",
                    "structures": (structure,),
                    "created_entity_ids": (),
                },
                {"filename": "b.xyz"},
            )
        )
        with self.assertRaises(ValueError):
            suggest_source_groups(bad_preview, bad_session)

    def test_contracts_are_frozen_and_confirmation_validates_evidence(self):
        revision_ids = tuple(sorted((uuid4(), uuid4()), key=str))
        evidence = GroupingEvidence(
            kind="metadata",
            source_revision_ids=revision_ids,
            summary="matching calculation metadata",
        )
        suggestion = SourceGroupSuggestion(
            source_revision_ids=revision_ids,
            evidence=(evidence,),
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.kind = "filename_directory"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            suggestion.evidence = ()
        with self.assertRaises(TypeError):
            suggestion.confirm([evidence.id])
        with self.assertRaises(ValueError):
            suggestion.confirm(())
        with self.assertRaises(ValueError):
            suggestion.confirm((uuid4(),))

        group = suggestion.confirm((evidence.id,))

        self.assertIsInstance(group, CalculationGroup)
        self.assertEqual(group.suggestion_id, suggestion.id)
        self.assertEqual(group.source_revision_ids, suggestion.source_revision_ids)
        self.assertEqual(group.evidence_ids, (evidence.id,))
        self.assertEqual(group.confirmed_by, "user")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            group.confirmed_by = "system"

    def test_suggestion_requires_two_revisions_and_matching_evidence(self):
        revision_id = uuid4()
        evidence = GroupingEvidence(
            kind="metadata",
            source_revision_ids=(revision_id, uuid4()),
            summary="metadata",
        )
        with self.assertRaises(ValueError):
            SourceGroupSuggestion(
                source_revision_ids=(revision_id,),
                evidence=(evidence,),
            )
        with self.assertRaises(ValueError):
            SourceGroupSuggestion(
                source_revision_ids=tuple(
                    sorted((revision_id, uuid4()), key=str)
                ),
                evidence=(evidence,),
            )

    def test_suggestion_does_not_mutate_preview_session_or_batches(self):
        first = self.molecular_structure(
            ((0, 0, 0), (1, 0, 0), (-1, 0, 0))
        )
        second = self.molecular_structure(
            ((2, 2, 2), (3, 2, 2), (1, 2, 2))
        )
        session, preview, _, batches = self.staged_preview(
            (
                {"filename": "same.xyz", "structures": (first,)},
                {"filename": "same.log", "structures": (second,)},
            )
        )
        before_preview = preview
        before_result_ids = session.result_ids
        before_batches = tuple(
            session.result(batch_id) for batch_id in preview.staged_batch_ids
        )

        suggestions = suggest_source_groups(preview, session)

        self.assertTrue(suggestions)
        self.assertIs(preview, before_preview)
        self.assertEqual(preview.grouping_suggestion_ids, ())
        self.assertEqual(session.result_ids, before_result_ids)
        self.assertEqual(before_batches, batches)
        self.assertEqual(
            tuple(session.result(batch_id) for batch_id in preview.staged_batch_ids),
            before_batches,
        )


if __name__ == "__main__":
    unittest.main()
