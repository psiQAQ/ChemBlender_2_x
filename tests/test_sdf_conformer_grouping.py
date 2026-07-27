from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy


def _molecule(smiles, *, atom_maps=False, order=None, aromatic=False):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    molecule = Chem.MolFromSmiles(smiles)
    if aromatic:
        Chem.Kekulize(molecule, clearAromaticFlags=True)
    AllChem.EmbedMolecule(molecule, randomSeed=0xC0DE)
    if atom_maps:
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + 1)
    if order is not None:
        molecule = Chem.RenumberAtoms(molecule, order)
    return molecule


def _batch(*entries):
    from rdkit import Chem
    from ChemBlender.core.formats.sdf import parse_sdf

    records = []
    for molecule, properties in entries:
        fields = b"".join(
            b"> <" + name.encode("utf-8") + b">\n" + value.encode("utf-8") + b"\n\n"
            for name, value in properties
        )
        records.append(
            Chem.MolToMolBlock(
                molecule,
                kekulize=not any(atom.GetIsAromatic() for atom in molecule.GetAtoms()),
            ).encode("utf-8")
            + fields
        )
    with TemporaryDirectory() as directory:
        source = Path(directory) / "conformers.sdf"
        source.write_bytes(b"$$$$\n".join(records) + b"$$$$\n")
        return parse_sdf(source)


class SDFConformerGroupingTests(unittest.TestCase):
    def test_suggestions_are_immutable_and_never_create_a_conformer_set(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            ConformerGroupSuggestion,
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))

        suggestions = suggest_conformer_groups(batch)

        self.assertEqual(len(suggestions), 1)
        self.assertIsInstance(suggestions[0], ConformerGroupSuggestion)
        self.assertEqual(batch.datasets, ())
        with self.assertRaisesRegex(Exception, "cannot assign|frozen"):
            suggestions[0].record_ids = ()

    def test_complete_unique_atom_maps_take_precedence_for_reordered_records(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))

        suggestion = suggest_conformer_groups(batch)[0]

        self.assertEqual(suggestion.evidence[1].kind, "complete_atom_maps")
        self.assertEqual(suggestion.atom_mappings[0], tuple(range(5)))
        self.assertEqual(suggestion.atom_mappings[1], (4, 3, 2, 1, 0))

    def test_canonical_rank_isomorphism_mapping_is_deterministic(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I")
        second = _molecule("FC(Cl)(Br)I", order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))

        first_result = suggest_conformer_groups(batch)
        second_result = suggest_conformer_groups(batch)
        reversed_result = suggest_conformer_groups(
            replace(batch, molecular_records=tuple(reversed(batch.molecular_records)))
        )

        self.assertEqual(first_result, second_result)
        self.assertEqual(first_result, reversed_result)
        self.assertEqual(first_result[0].evidence[1].kind, "canonical_ranks_isomorphism")
        self.assertEqual(first_result[0].atom_mappings[1], (4, 3, 2, 1, 0))
        self.assertFalse(first_result[0].requires_review)

    def test_charge_bond_aromatic_stereo_and_isotope_differences_do_not_group(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            suggest_conformer_groups,
        )

        cases = (
            ("charge", _molecule("C[NH3+]"), _molecule("CN")),
            ("bond", _molecule("CC"), _molecule("C=C")),
            ("aromatic", _molecule("c1ccccc1"), _molecule("c1ccccc1", aromatic=True)),
            ("stereo", _molecule("F/C=C/F"), _molecule("F/C=C\\F")),
            ("isotope", _molecule("[13CH3]C"), _molecule("CC")),
        )
        for name, first, second in cases:
            with self.subTest(name=name):
                batch = _batch((first, ()), (second, ()))
                self.assertEqual(
                    suggest_conformer_groups(batch), (),
                )

    def test_same_atom_count_alone_does_not_group(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            suggest_conformer_groups,
        )

        batch = _batch((_molecule("CCO"), ()), (_molecule("CCN"), ()))

        self.assertEqual(suggest_conformer_groups(batch), ())

    def test_ambiguous_symmetric_isomorphism_requires_review(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            suggest_conformer_groups,
        )

        batch = _batch((_molecule("CC"), ()), (_molecule("CC", order=(1, 0)), ()))

        suggestion = suggest_conformer_groups(batch)[0]

        self.assertTrue(suggestion.requires_review)
        self.assertEqual(suggestion.evidence[1].kind, "ambiguous_symmetric_isomorphism")

    def test_explicit_acceptance_reorders_coordinates_and_property_columns_with_provenance(self):
        from ChemBlender.core import ArrayData, CategoricalData, RecordPropertyColumn
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            accept_conformer_group,
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch(
            (first, (("Energy", "-1.0"), ("Flag", "true"), ("State", "solid"))),
            (second, (("Energy", "-2.0"), ("Flag", "false"), ("State", "liquid"))),
            (_molecule("CCO"), (("State", "vapor"),)),
        )

        def reverse_column(column):
            if isinstance(column.data, CategoricalData):
                data = CategoricalData(
                    ArrayData(column.data.codes.values[::-1].copy(), ("record",), "dimensionless"),
                    column.data.categories,
                    column.data.missing_code,
                )
            else:
                data = ArrayData(column.data.values[::-1].copy(), ("record",), "dimensionless")
            mask = None if column.validity_mask is None else ArrayData(
                column.validity_mask.values[::-1].copy(), ("record",), "dimensionless"
            )
            return replace(
                column, id=uuid4(), revision=f"reordered-{column.semantic_role}",
                data=data, record_ids=tuple(reversed(column.record_ids)), validity_mask=mask,
            )

        grouped_batch = replace(batch, datasets=tuple(reverse_column(column) for column in batch.datasets))
        suggestion = suggest_conformer_groups(grouped_batch)[0]

        accepted = accept_conformer_group(
            suggestion,
            grouped_batch,
        )

        self.assertEqual(accepted.conformer_set.record_ids, suggestion.record_ids)
        self.assertEqual(accepted.conformer_set.atom_mappings.values.tolist()[1], [4, 3, 2, 1, 0])
        self.assertEqual(
            accepted.conformer_set.data.values[1].tolist(),
            batch.structures[1].coordinates.values[[4, 3, 2, 1, 0]].tolist(),
        )
        columns = {column.semantic_role: column for column in accepted.property_columns}
        self.assertEqual(columns["sdf_energy"].record_ids, suggestion.record_ids)
        self.assertEqual(columns["sdf_energy"].data.values.tolist(), [-1.0, -2.0])
        self.assertIsNone(columns["sdf_energy"].validity_mask)
        self.assertEqual(columns["sdf_flag"].data.values.tolist(), [True, False])
        self.assertIsNone(columns["sdf_flag"].validity_mask)
        self.assertEqual(columns["sdf_state"].data.codes.values.tolist(), [0, 1])
        self.assertEqual(accepted.provenance.operation, "group_conformers")
        self.assertIn(("evidence", "complete_atom_maps"), accepted.provenance.parameters)
        provenance = dict(accepted.provenance.parameters)
        self.assertEqual(provenance["confirmed_by"], "user")
        self.assertEqual(provenance["mapping_direction"], "reference_atom_to_source_atom")
        self.assertEqual(provenance["property_column_lineage"][0][1], grouped_batch.datasets[0].revision)
        self.assertEqual(provenance["topology_lineage"][0][1], batch.topologies[0].revision)

    def test_categorical_snapshot_change_fails_closed(self):
        from ChemBlender.core import ArrayData, CategoricalData
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            accept_conformer_group,
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, (("State", "solid"),)), (second, (("State", "liquid"),)))
        suggestion = suggest_conformer_groups(batch)[0]
        column = batch.datasets[0]
        changed = replace(
            column,
            data=CategoricalData(
                ArrayData(column.data.codes.values.copy(), ("record",), "dimensionless"),
                tuple(reversed(column.data.categories)),
                column.data.missing_code,
            ),
        )

        with self.assertRaisesRegex(ValueError, "stale"):
            accept_conformer_group(suggestion, replace(batch, datasets=(changed,)))

    def test_source_and_provenance_snapshot_changes_fail_closed(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            accept_conformer_group,
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))
        suggestion = suggest_conformer_groups(batch)[0]
        mutations = (
            (
                "record source revision",
                replace(
                    batch,
                    molecular_records=(
                        replace(batch.molecular_records[0], source_revision_id=uuid4()),
                        batch.molecular_records[1],
                    ),
                ),
            ),
            (
                "record provenance",
                replace(
                    batch,
                    molecular_records=(
                        replace(batch.molecular_records[0], provenance_ids=(uuid4(),)),
                        batch.molecular_records[1],
                    ),
                ),
            ),
            (
                "topology provenance",
                replace(
                    batch,
                    topologies=(
                        replace(batch.topologies[0], provenance_ids=(uuid4(),)),
                        batch.topologies[1],
                    ),
                ),
            ),
        )

        for changed_name, changed_batch in mutations:
            with self.subTest(changed=changed_name):
                self.assertEqual(
                    changed_batch.molecular_records[0].revision,
                    batch.molecular_records[0].revision,
                )
                with self.assertRaisesRegex(ValueError, "stale"):
                    accept_conformer_group(suggestion, changed_batch)

    def test_cancellation_is_checked_between_rdkit_records(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            ConformerGroupingCancelled,
            suggest_conformer_groups,
        )

        batch = _batch(
            (_molecule("FC(Cl)(Br)I", atom_maps=True), ()),
            (_molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0)), ()),
        )
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 4

        with self.assertRaises(ConformerGroupingCancelled):
            suggest_conformer_groups(batch, is_cancelled=cancelled)
        self.assertEqual(calls, 4)

    def test_stale_suggestion_and_cancellation_fail_closed(self):
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            ConformerGroupingCancelled,
            accept_conformer_group,
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))
        suggestion = suggest_conformer_groups(batch)[0]
        stale = replace(batch.molecular_records[0], revision="changed-r2")

        with self.assertRaisesRegex(ValueError, "stale"):
            accept_conformer_group(
                suggestion,
                replace(batch, molecular_records=(stale, batch.molecular_records[1])),
            )
        with self.assertRaises(ConformerGroupingCancelled):
            suggest_conformer_groups(
                batch,
                is_cancelled=lambda: True,
            )

    def test_acceptance_converts_bohr_coordinates_to_reference_unit_and_snapshot_tracks_units(self):
        from ChemBlender.core import ArrayData
        from ChemBlender.core.import_pipeline.conformer_grouping import (
            accept_conformer_group,
            suggest_conformer_groups,
        )

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))
        source = batch.structures[1]
        bohr_structure = replace(
            source,
            coordinates=ArrayData(source.coordinates.values / 0.529177210903, ("atom", "xyz"), "bohr"),
        )
        bohr_batch = replace(batch, structures=(batch.structures[0], bohr_structure))
        suggestion = suggest_conformer_groups(bohr_batch)[0]

        accepted = accept_conformer_group(suggestion, bohr_batch)

        self.assertEqual(accepted.conformer_set.data.unit, "angstrom")
        numpy.testing.assert_allclose(
            accepted.conformer_set.data.values[1],
            source.coordinates.values[[4, 3, 2, 1, 0]],
        )
        self.assertNotEqual(suggestion, suggest_conformer_groups(batch)[0])

    def test_invalid_or_non_explicit_topology_is_not_suggested(self):
        from ChemBlender.core import TopologySource
        from ChemBlender.core.model import QualityStatus
        from ChemBlender.core.import_pipeline.conformer_grouping import suggest_conformer_groups

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, ()), (second, ()))
        for fields in (
            {"source_kind": TopologySource.RDKIT_SANITIZED},
            *({"quality_status": status} for status in (
                QualityStatus.PARTIAL,
                QualityStatus.AMBIGUOUS,
                QualityStatus.INCOMPLETE,
                QualityStatus.INVALID,
            )),
        ):
            with self.subTest(fields=fields):
                changed = replace(batch.topologies[1], **fields)
                self.assertEqual(
                    suggest_conformer_groups(replace(batch, topologies=(batch.topologies[0], changed))),
                    (),
                )

    def test_acceptance_is_atomic_when_property_conversion_fails(self):
        from ChemBlender.core.import_pipeline import conformer_grouping

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        batch = _batch((first, (("Energy", "-1.0"),)), (second, (("Energy", "-2.0"),)))
        suggestion = conformer_grouping.suggest_conformer_groups(batch)[0]
        column = batch.datasets[0]
        before = (column.record_ids, column.data.values.copy())

        with patch.object(
            conformer_grouping,
            "_reordered_column",
            side_effect=RuntimeError("synthetic conversion failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic conversion failure"):
                conformer_grouping.accept_conformer_group(
                    suggestion,
                    batch,
                )

        self.assertEqual(column.record_ids, before[0])
        numpy.testing.assert_array_equal(column.data.values, before[1])

    def test_transaction_keeps_live_session_unchanged_on_publication_failure_and_round_trips(self):
        from ChemBlender.core import ImportBatch, SourceRecord, SourceRevision, create_session, close_session
        from ChemBlender.core.import_pipeline import (
            ConformerGroupingDecision,
            ImportCommitDecisions,
            ImportPreview,
            SourcePreview,
            StagedImportSession,
            commit_import_preview,
            suggest_conformer_groups,
        )
        from ChemBlender.core.import_pipeline import transaction

        first = _molecule("FC(Cl)(Br)I", atom_maps=True)
        second = _molecule("FC(Cl)(Br)I", atom_maps=True, order=(4, 3, 2, 1, 0))
        parsed = _batch((first, (("Energy", "-1.0"),)), (second, (("Energy", "-2.0"),)))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "conformers.sdf"
            source_path.write_bytes(b"fixture")
            source = SourceRecord(uuid4(), source_path.name, "local_file", "2026-07-28T00:00:00Z")
            revision_id = parsed.molecular_records[0].source_revision_id
            created = tuple(
                entity.id
                for group in (
                    parsed.structures, parsed.topologies, parsed.molecular_records,
                    parsed.cif_envelopes, parsed.qcschema_envelopes, parsed.cjson_envelopes,
                    parsed.symmetry_results, parsed.calculations, parsed.datasets,
                    parsed.basis_sets, parsed.orbital_sets, parsed.density_matrices,
                    parsed.provenance,
                )
                for entity in group
            )
            revision = SourceRevision(
                id=revision_id, source_id=source.id, content_hash="a" * 64,
                byte_size=source_path.stat().st_size, locator=str(source_path),
                locator_kind="absolute_path", original_filename=source_path.name,
                reader_plugin_id="builtin", reader_id="sdf", reader_version="1",
                reader_api_version="0.1", import_parameters_hash="b" * 64,
                parse_identity="c" * 64, created_entity_ids=created, diagnostic_ids=(),
            )
            batch = ImportBatch(
                sources=(source,), source_revisions=(revision,), structures=parsed.structures,
                topologies=parsed.topologies, molecular_records=parsed.molecular_records,
                datasets=parsed.datasets, provenance=parsed.provenance, report=parsed.report,
            )
            staging = StagedImportSession.create(temp_parent=root)
            session = create_session(temp_parent=root)
            try:
                staged_id = uuid4()
                staging.register_result(staged_id, batch)
                preview = ImportPreview(
                    staging.id,
                    (SourcePreview(source.id, source_path, "sdf", "a" * 64, 7, (), (staged_id,), ()),),
                    (staged_id,),
                )
                suggestion = suggest_conformer_groups(batch)[0]
                decisions = ImportCommitDecisions(
                    conformer_grouping_decisions=(ConformerGroupingDecision(suggestion),),
                )
                previous = session.project
                with patch.object(transaction, "solidify_session", side_effect=OSError("publication failed")):
                    with self.assertRaisesRegex(OSError, "publication failed"):
                        commit_import_preview(session, staging, preview, decisions)
                self.assertIs(session.project, previous)
                self.assertIsNone(session.sidecar_path)

                result = commit_import_preview(session, staging, preview, decisions)
                self.assertTrue(result.sidecar_path.exists())
                self.assertEqual(
                    len([item for item in result.project.datasets.values() if item.domain == "conformer"]),
                    1,
                )
                coordinates = next(iter(result.project.structures.values())).coordinates.values
                self.assertFalse(coordinates.loaded)
                lazy_batch = ImportBatch(
                    structures=tuple(result.project.structures.values()),
                    topologies=tuple(result.project.topologies.values()),
                    molecular_records=tuple(result.project.molecular_records.values()),
                    datasets=tuple(result.project.datasets.values()),
                    provenance=tuple(result.project.provenance.values()),
                )
                suggest_conformer_groups(lazy_batch)
                self.assertFalse(coordinates.loaded)
            finally:
                close_session(session)
                staging.discard()


if __name__ == "__main__":
    unittest.main()
