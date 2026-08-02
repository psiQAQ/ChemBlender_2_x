import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, CategoricalData, DatasetStatus, FrameSet
from ChemBlender.core.exporters import (
    ExportCancelled,
    export_pqr,
    preview_pqr_export,
)
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.core.exporters.pdb_readiness import (
    PDBPQRExportReadiness,
    PDBPQRExportStatus,
)


FIXTURES = Path(__file__).with_name("fixtures") / "pqr"


class PQRExporterTests(unittest.TestCase):
    def _property(self, batch, role):
        return next(value for value in batch.datasets if value.semantic_role == role)

    def _replace_property(self, batch, property):
        return replace(
            batch,
            datasets=tuple(
                property if value.id == property.id else value
                for value in batch.datasets
            ),
        )

    def _lazy_coordinates(self, batch, directory, name):
        from ChemBlender.core.sidecar import LazyNpyArray, _array_content_hash

        array = numpy.asarray(batch.structures[0].coordinates.values)
        path = Path(directory) / f"{name}.npy"
        numpy.save(path, array)
        lazy = LazyNpyArray(
            path,
            array.shape,
            array.dtype,
            _array_content_hash(array)[0],
        )
        structure = replace(
            batch.structures[0],
            coordinates=ArrayData(lazy, ("atom", "xyz"), "angstrom"),
        )
        return replace(batch, structures=(structure,)), lazy

    def _assert_rejected_without_publication(
        self,
        entities,
        token,
        *,
        confirm_loss=False,
    ):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "rejected.pqr"
            with self.assertRaisesRegex(ValueError, token):
                export_pqr(
                    entities,
                    confirm_loss=confirm_loss,
                    destination=destination,
                )
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def _atom_semantics(self, batch):
        structure = batch.structures[0]
        hierarchy = batch.biological_hierarchies[0]
        names = structure.atomic_identity.atom_names
        kinds = hierarchy.atom_sites.record_kinds
        residue_indices = hierarchy.atom_sites.residue_indices.values
        return tuple(
            (
                names.categories[int(names.codes.values[index])],
                kinds.categories[int(kinds.codes.values[index])],
                hierarchy.chains[hierarchy.residues[int(residue_index)].chain_index].chain_id,
                hierarchy.chains[
                    hierarchy.residues[int(residue_index)].chain_index
                ].segment_index,
                hierarchy.residues[int(residue_index)].residue_name,
                hierarchy.residues[int(residue_index)].sequence_number,
                hierarchy.residues[int(residue_index)].insertion_code,
                hierarchy.residues[int(residue_index)].hetero,
            )
            for index, residue_index in enumerate(residue_indices)
        )

    def test_ready_chain_and_no_chain_exports_are_deterministic_ascii_lf(self):
        cases = (
            ("with-chain.pqr", (11, 11)),
            ("no-chain.pqr", (10, 10)),
        )
        for filename, field_counts in cases:
            with self.subTest(filename=filename):
                batch = parse_pqr(FIXTURES / filename)

                first = export_pqr(batch)
                second = export_pqr(batch)

                self.assertEqual(first.text, second.text)
                self.assertEqual(first.text, (FIXTURES / filename).read_text("ascii"))
                self.assertTrue(first.text.isascii())
                self.assertTrue(first.text.endswith("\n"))
                self.assertEqual(
                    tuple(len(line.split()) for line in first.text.splitlines()),
                    field_counts,
                )

    def test_unsupported_readiness_includes_stable_status_and_token(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")

        with self.assertRaisesRegex(
            ValueError,
            "MissingHierarchy.*hierarchy.missing",
        ):
            preview_pqr_export(replace(batch, biological_hierarchies=()))

    def test_loss_preview_blocks_text_and_destination_until_confirmed(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        structure = replace(batch.structures[0], molecular_charge=1)
        batch = replace(batch, structures=(structure,))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.pqr"

            blocked = export_pqr(batch, destination=destination)

            self.assertEqual(blocked.text, "")
            self.assertTrue(blocked.report.requires_confirmation)
            self.assertFalse(destination.exists())
            self.assertIn(
                "molecular_charge_omitted",
                tuple(entry.code for entry in blocked.report.entries),
            )

            written = export_pqr(
                batch,
                confirm_loss=True,
                destination=destination,
            )
            self.assertTrue(written.report.written)
            self.assertEqual(destination.read_text("ascii"), written.text)

    def test_confirm_loss_requires_exact_bool(self):
        with self.assertRaisesRegex(TypeError, "confirm_loss"):
            export_pqr(parse_pqr(FIXTURES / "with-chain.pqr"), confirm_loss=1)

    def test_cancellation_before_validation_publishes_nothing(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.pqr"

            with self.assertRaises(ExportCancelled):
                export_pqr(
                    batch,
                    destination=destination,
                    is_cancelled=lambda: True,
                )

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_control_label_is_rejected_before_destination_publication(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        identity = batch.structures[0].atomic_identity
        structure = replace(
            batch.structures[0],
            atomic_identity=replace(
                identity,
                atom_names=replace(
                    identity.atom_names,
                    categories=("N\x7f", "O"),
                ),
            ),
        )
        batch = replace(batch, structures=(structure,))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid-label.pqr"

            with self.assertRaisesRegex(ValueError, "PQR atom name is invalid"):
                export_pqr(batch, destination=destination)

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_writer_rechecks_element_identity_after_readiness_bypass(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        batch = replace(
            batch,
            structures=(replace(batch.structures[0], atomic_numbers=(7, 7)),),
        )
        ready = PDBPQRExportReadiness(PDBPQRExportStatus.READY, ())
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "mismatched-element.pqr"
            with patch(
                "ChemBlender.core.exporters.pqr.pqr_export_readiness",
                return_value=ready,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "PQR identity.element.mismatch",
                ):
                    export_pqr(batch, destination=destination)

            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_reversed_entity_container_insertion_order_is_byte_deterministic(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        ordered = SimpleNamespace(
            structures={"structure": batch.structures[0]},
            biological_hierarchies={"hierarchy": batch.biological_hierarchies[0]},
            datasets={value.semantic_role: value for value in batch.datasets},
            topologies={},
        )
        reversed_entities = SimpleNamespace(
            structures=dict(reversed(tuple(ordered.structures.items()))),
            biological_hierarchies=dict(
                reversed(tuple(ordered.biological_hierarchies.items()))
            ),
            datasets=dict(reversed(tuple(ordered.datasets.items()))),
            topologies={},
        )
        reversed_tuple = SimpleNamespace(
            structures=(batch.structures[0],),
            biological_hierarchies=(batch.biological_hierarchies[0],),
            datasets=tuple(reversed(batch.datasets)),
            topologies=(),
        )

        self.assertEqual(
            export_pqr(ordered).text,
            export_pqr(reversed_entities).text,
        )
        self.assertEqual(export_pqr(ordered).text, export_pqr(reversed_tuple).text)

    def test_entity_containers_are_snapshotted_once_before_validation(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        charge = self._property(batch, "partial_charge")

        class FlappingEntities:
            def __init__(self):
                self.values = {
                    "structures": batch.structures,
                    "biological_hierarchies": batch.biological_hierarchies,
                    "datasets": batch.datasets,
                    "topologies": batch.topologies,
                }
                self.accesses = {
                    name: 0 for name in self.values
                }

            def __getattr__(self, name):
                values = self.values[name]
                if name == "datasets" and self.accesses[name]:
                    values = tuple(
                        replace(value, data=replace(value.data, unit="dimensionless"))
                        if value.id == charge.id else value
                        for value in values
                    )
                self.accesses[name] += 1
                return values

        entities = FlappingEntities()

        result = export_pqr(entities)

        self.assertEqual(result.text, (FIXTURES / "with-chain.pqr").read_text("ascii"))
        self.assertEqual(
            entities.accesses,
            {
                "structures": 1,
                "biological_hierarchies": 1,
                "datasets": 1,
                "topologies": 1,
            },
        )

    def test_live_loss_array_mutation_aborts_before_publication(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        isotopes = batch.structures[0].atomic_identity.isotopes.values
        calls = 0

        def mutate_after_preview():
            nonlocal calls
            calls += 1
            if calls == 2:
                isotopes[0] = 1
            return False

        try:
            with TemporaryDirectory() as directory:
                destination = Path(directory) / "mutated.pqr"

                with self.assertRaisesRegex(
                    ValueError,
                    "inputs changed after snapshot",
                ):
                    export_pqr(
                        batch,
                        destination=destination,
                        is_cancelled=mutate_after_preview,
                    )

                self.assertEqual(tuple(Path(directory).iterdir()), ())
        finally:
            isotopes[0] = 0

    def test_lazy_snapshot_arrays_release_exporter_owned_mmaps(self):
        source = parse_pqr(FIXTURES / "with-chain.pqr")
        with TemporaryDirectory() as directory:
            cases = (
                ("preview", lambda batch: preview_pqr_export(batch), None),
                ("export", lambda batch: export_pqr(batch), None),
                (
                    "validation",
                    lambda batch: preview_pqr_export(
                        replace(batch, biological_hierarchies=())
                    ),
                    ValueError,
                ),
                (
                    "cancellation",
                    lambda batch: export_pqr(
                        batch,
                        is_cancelled=iter((False, True)).__next__,
                    ),
                    ExportCancelled,
                ),
            )
            for name, operation, error in cases:
                with self.subTest(name=name):
                    batch, lazy = self._lazy_coordinates(source, directory, name)
                    try:
                        self.assertFalse(lazy.loaded)
                        if error is None:
                            operation(batch)
                        else:
                            with self.assertRaises(error):
                                operation(batch)
                        self.assertFalse(lazy.loaded)
                    finally:
                        lazy.close()

            batch, lazy = self._lazy_coordinates(source, directory, "mutation")
            isotopes = batch.structures[0].atomic_identity.isotopes.values
            calls = 0

            def mutate():
                nonlocal calls
                calls += 1
                if calls == 2:
                    isotopes[0] = 1
                return False

            try:
                with self.assertRaisesRegex(ValueError, "inputs changed"):
                    export_pqr(batch, is_cancelled=mutate)
                self.assertFalse(lazy.loaded)
            finally:
                isotopes[0] = 0
                lazy.close()

    def test_live_coordinate_shape_mutation_keeps_stable_readiness_token(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        coordinates = batch.structures[0].coordinates.values
        coordinates.shape = (coordinates.size,)
        try:
            self._assert_rejected_without_publication(
                batch,
                "PQR export is Invalid: coordinates.shape",
            )
        finally:
            coordinates.shape = (2, 3)

    def test_live_rank_mutations_keep_family_readiness_tokens(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        structure = batch.structures[0]
        hierarchy = batch.biological_hierarchies[0]
        cases = (
            (
                self._property(batch, "partial_charge").data.values,
                "dataset.partial_charge.shape",
            ),
            (
                self._property(batch, "radius").data.values,
                "dataset.radius.shape",
            ),
            (structure.atomic_identity.isotopes.values, "identity.isotopes.invalid"),
            (
                structure.atomic_identity.atom_names.codes.values,
                "identity.atom_name.invalid",
            ),
            (hierarchy.atom_sites.serial_numbers.values, "hierarchy.shape"),
            (hierarchy.atom_sites.residue_indices.values, "hierarchy.shape"),
            (
                hierarchy.atom_sites.alternate_locations.codes.values,
                "identity.altloc.invalid",
            ),
            (
                hierarchy.atom_sites.record_kinds.codes.values,
                "identity.record_kind",
            ),
        )
        for values, token in cases:
            with self.subTest(token=token), TemporaryDirectory() as directory:
                destination = Path(directory) / "invalid.pqr"
                original_shape = values.shape
                values.shape = (1, values.size)
                try:
                    with self.assertRaises(ValueError) as raised:
                        export_pqr(batch, destination=destination)
                    self.assertEqual(
                        str(raised.exception),
                        f"PQR export is Invalid: {token}",
                    )
                    self.assertEqual(tuple(Path(directory).iterdir()), ())
                finally:
                    values.shape = original_shape

    def test_writer_revalidates_property_contract_after_readiness_bypass(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        charge = self._property(batch, "partial_charge")
        ready = PDBPQRExportReadiness(PDBPQRExportStatus.READY, ())
        invalid_properties = (
            (
                replace(
                    charge,
                    data=replace(charge.data, unit="dimensionless"),
                ),
                "partial_charge property is invalid",
            ),
            (
                replace(charge, status=DatasetStatus.PARTIAL),
                "partial_charge property is invalid",
            ),
            (
                replace(
                    charge,
                    data=ArrayData(
                        numpy.asarray(((0.1,), (-0.55,))),
                        ("atom", "component"),
                        "elementary_charge",
                    ),
                ),
                "dataset.partial_charge.shape",
            ),
        )
        for invalid_property, message in invalid_properties:
            with self.subTest(invalid_property=invalid_property), patch(
                "ChemBlender.core.exporters.pqr.pqr_export_readiness",
                return_value=ready,
            ), self.assertRaisesRegex(
                ValueError,
                message,
            ):
                export_pqr(self._replace_property(batch, invalid_property))

    def test_duplicate_and_out_of_range_serials_renumber_in_structure_order(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        hierarchy = batch.biological_hierarchies[0]
        for serials in ((1, 1), (1, 100000)):
            with self.subTest(serials=serials):
                renumbered = replace(
                    hierarchy,
                    atom_sites=replace(
                        hierarchy.atom_sites,
                        serial_numbers=ArrayData(
                            numpy.asarray(serials),
                            ("atom",),
                            "dimensionless",
                        ),
                    ),
                )
                text = export_pqr(
                    replace(batch, biological_hierarchies=(renumbered,)),
                    confirm_loss=True,
                ).text

                self.assertEqual(
                    tuple(line.split()[1] for line in text.splitlines()),
                    ("1", "2"),
                )

    def test_charge_radius_units_finiteness_and_precision_are_enforced(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        charge = self._property(batch, "partial_charge")
        radius = self._property(batch, "radius")
        formatted = self._replace_property(
            self._replace_property(
                batch,
                replace(
                    charge,
                    data=replace(
                        charge.data,
                        values=numpy.asarray((0.123456, -0.0)),
                    ),
                ),
            ),
            replace(
                radius,
                data=replace(
                    radius.data,
                    values=numpy.asarray((1.23456, 1.4)),
                ),
            ),
        )
        self.assertTrue(
            export_pqr(formatted).text.splitlines()[0].endswith("0.1235 1.2346")
        )
        self.assertTrue(
            export_pqr(formatted).text.splitlines()[1].endswith("0.0000 1.4000")
        )
        invalid_cases = (
            (
                replace(charge, data=replace(charge.data, unit="dimensionless")),
                "dataset.partial_charge.unit",
            ),
            (
                replace(
                    radius,
                    data=replace(
                        radius.data,
                        values=numpy.asarray((numpy.inf, 1.4)),
                    ),
                ),
                "dataset.radius.values",
            ),
        )
        for property, token in invalid_cases:
            with self.subTest(token=token), TemporaryDirectory() as directory:
                destination = Path(directory) / "invalid.pqr"
                with self.assertRaisesRegex(ValueError, token):
                    export_pqr(
                        self._replace_property(batch, property),
                        destination=destination,
                    )
                self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_overflow_and_writer_serial_guard_fail_before_publication(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        structure = batch.structures[0]
        hierarchy = batch.biological_hierarchies[0]
        charge = self._property(batch, "partial_charge")
        radius = self._property(batch, "radius")
        coordinates = numpy.asarray(structure.coordinates.values).copy()
        coordinates[0, 0] = 10000.0
        cases = (
            (
                replace(
                    batch,
                    structures=(replace(structure, coordinates=replace(structure.coordinates, values=coordinates)),),
                ),
                "coordinates.overflow",
            ),
            (
                replace(
                    batch,
                    structures=(
                        replace(
                            structure,
                            atomic_identity=replace(
                                structure.atomic_identity,
                                atom_names=replace(
                                    structure.atomic_identity.atom_names,
                                    categories=("LONGER", "O"),
                                ),
                            ),
                        ),
                    ),
                ),
                "identity.atom_name.overflow",
            ),
            (
                replace(
                    batch,
                    biological_hierarchies=(
                        replace(
                            hierarchy,
                            residues=(
                                replace(hierarchy.residues[0], sequence_number=10000),
                                hierarchy.residues[1],
                            ),
                        ),
                    ),
                ),
                "identity.residue_number.overflow",
            ),
            (
                self._replace_property(
                    batch,
                    replace(
                        charge,
                        data=replace(charge.data, values=numpy.asarray((1000.0, -0.55))),
                    ),
                ),
                "dataset.partial_charge.overflow",
            ),
            (
                self._replace_property(
                    batch,
                    replace(
                        radius,
                        data=replace(radius.data, values=numpy.asarray((100.0, 1.4))),
                    ),
                ),
                "dataset.radius.overflow",
            ),
        )
        for invalid, token in cases:
            with self.subTest(token=token), TemporaryDirectory() as directory:
                destination = Path(directory) / "overflow.pqr"
                with self.assertRaisesRegex(ValueError, token):
                    export_pqr(invalid, destination=destination)
                self.assertEqual(tuple(Path(directory).iterdir()), ())

        serials = replace(
            hierarchy,
            atom_sites=replace(
                hierarchy.atom_sites,
                serial_numbers=replace(
                    hierarchy.atom_sites.serial_numbers,
                    values=numpy.asarray((100000, 2)),
                ),
            ),
        )
        ready = PDBPQRExportReadiness(PDBPQRExportStatus.READY, ())
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "serial-overflow.pqr"
            with patch(
                "ChemBlender.core.exporters.pqr.pqr_export_readiness",
                return_value=ready,
            ), self.assertRaisesRegex(ValueError, "PQR atom serial is invalid"):
                export_pqr(
                    replace(batch, biological_hierarchies=(serials,)),
                    destination=destination,
                )
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_frames_and_multiple_structures_remain_unexportable(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        structure = batch.structures[0]
        frames = FrameSet(
            id=uuid4(),
            revision="pqr-export-test",
            semantic_role="coordinates",
            domain="frame",
            data=ArrayData(
                numpy.stack((structure.coordinates.values, structure.coordinates.values)),
                ("frame", "atom", "xyz"),
                "angstrom",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure.id,
            comments=("frame 1", "frame 2"),
        )
        with self.assertRaisesRegex(ValueError, "dataset.coordinates.unsupported"):
            export_pqr(replace(batch, datasets=(*batch.datasets, frames)))
        ambiguous = SimpleNamespace(
            structures=(structure, structure),
            biological_hierarchies=batch.biological_hierarchies,
            datasets=batch.datasets,
            topologies=(),
        )
        with self.assertRaisesRegex(ValueError, "structure.ambiguous"):
            export_pqr(ambiguous)

    def test_mid_write_cancellation_cleans_destination_and_temporary(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls == 5

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "cancelled.pqr"
            with self.assertRaises(ExportCancelled):
                export_pqr(
                    batch,
                    destination=destination,
                    is_cancelled=cancelled,
                )
            self.assertGreaterEqual(calls, 5)
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_loss_codes_are_sorted_and_cover_real_omissions(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        structure = batch.structures[0]
        identity = structure.atomic_identity
        identity = replace(
            identity,
            isotopes=replace(identity.isotopes, values=numpy.asarray((1, 0))),
            formal_charges=replace(
                identity.formal_charges,
                values=numpy.asarray((1, 0)),
            ),
            atom_map_numbers=replace(
                identity.atom_map_numbers,
                values=numpy.asarray((1, 0)),
            ),
            stereo_labels=CategoricalData(
                ArrayData(numpy.asarray((0, -1)), ("atom",), "dimensionless"),
                ("R",),
                -1,
            ),
        )
        omitted = SimpleNamespace(
            structures=(
                replace(
                    structure,
                    atomic_identity=identity,
                    cell=ArrayData(
                        numpy.eye(3),
                        ("cell_vector", "xyz"),
                        "angstrom",
                    ),
                    molecular_charge=1,
                    molecular_multiplicity=2,
                ),
            ),
            biological_hierarchies=batch.biological_hierarchies,
            datasets=batch.datasets,
            topologies=(SimpleNamespace(structure_id=structure.id),),
        )

        codes = tuple(entry.code for entry in preview_pqr_export(omitted).entries)

        self.assertEqual(codes, tuple(sorted(codes)))
        self.assertEqual(
            codes,
            (
                "atom_map_numbers_omitted",
                "atom_stereo_omitted",
                "cell_omitted",
                "formal_charge_omitted",
                "isotopes_omitted",
                "molecular_charge_omitted",
                "molecular_multiplicity_omitted",
                "topology_omitted",
            ),
        )

    def test_model_and_chain_segment_loss_requires_confirmation_and_round_trips_explicitly(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        hierarchy = batch.biological_hierarchies[0]
        hierarchy = replace(
            hierarchy,
            model=replace(hierarchy.model, number=7),
            chains=tuple(
                replace(chain, segment_index=3) for chain in hierarchy.chains
            ),
        )
        batch = replace(batch, biological_hierarchies=(hierarchy,))

        preview = preview_pqr_export(batch)

        self.assertEqual(
            tuple(entry.code for entry in preview.entries),
            ("chain_segment_indices_omitted", "model_number_omitted"),
        )
        self.assertEqual(export_pqr(batch).text, "")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "normalized.pqr"
            written = export_pqr(
                batch,
                confirm_loss=True,
                destination=destination,
            )
            restored = parse_pqr(destination)

        self.assertNotIn("MODEL", written.text)
        self.assertEqual(len(restored.structures[0].atomic_numbers), 2)
        self.assertEqual(restored.biological_hierarchies[0].model.number, None)
        self.assertEqual(
            tuple(
                chain.segment_index
                for chain in restored.biological_hierarchies[0].chains
            ),
            (0, 0),
        )
        self.assertEqual(
            tuple(residue.hetero for residue in hierarchy.residues),
            tuple(
                residue.hetero
                for residue in restored.biological_hierarchies[0].residues
            ),
        )

    def test_hierarchy_hetero_kind_mismatch_fails_before_publication(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        hierarchy = batch.biological_hierarchies[0]
        hierarchy = replace(
            hierarchy,
            residues=(
                replace(hierarchy.residues[0], hetero=True),
                hierarchy.residues[1],
            ),
        )
        self._assert_rejected_without_publication(
            replace(batch, biological_hierarchies=(hierarchy,)),
            "hierarchy.residue_kind.mismatch",
        )

    def test_colliding_native_residue_keys_fail_before_atoms_can_be_dropped(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        hierarchy = batch.biological_hierarchies[0]
        hierarchy = replace(
            hierarchy,
            chains=(
                hierarchy.chains[0],
                replace(hierarchy.chains[1], chain_id="A", segment_index=1),
            ),
            residues=(
                hierarchy.residues[0],
                replace(
                    hierarchy.residues[1],
                    sequence_number=1,
                    insertion_code="A",
                    hetero=False,
                ),
            ),
            atom_sites=replace(
                hierarchy.atom_sites,
                record_kinds=CategoricalData(
                    ArrayData(
                        numpy.asarray((0, 0)),
                        ("atom",),
                        "dimensionless",
                    ),
                    ("atom",),
                    -1,
                ),
            ),
        )
        self._assert_rejected_without_publication(
            replace(batch, biological_hierarchies=(hierarchy,)),
            "hierarchy.residue_key.conflict",
            confirm_loss=True,
        )

    def test_topology_ids_require_loss_confirmation_and_dangling_refs_fail_closed(self):
        batch = parse_pqr(FIXTURES / "with-chain.pqr")
        topology_id = uuid4()
        structure = replace(batch.structures[0], topology_ids=(topology_id,))
        topology = SimpleNamespace(id=topology_id, structure_id=structure.id)
        bound = SimpleNamespace(
            structures=(structure,),
            biological_hierarchies=batch.biological_hierarchies,
            datasets=batch.datasets,
            topologies=(topology,),
        )

        self.assertEqual(
            tuple(entry.code for entry in preview_pqr_export(bound).entries),
            ("topology_omitted",),
        )
        self.assertEqual(export_pqr(bound).text, "")

        dangling = SimpleNamespace(
            structures=bound.structures,
            biological_hierarchies=bound.biological_hierarchies,
            datasets=bound.datasets,
            topologies=(),
        )
        self._assert_rejected_without_publication(
            dangling,
            "topology.reference.invalid",
            confirm_loss=True,
        )

    def test_native_parse_pqr_reimport_preserves_normalized_semantics(self):
        source = parse_pqr(FIXTURES / "with-chain.pqr")
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "round-trip.pqr"
            export_pqr(source, destination=destination)
            restored = parse_pqr(destination)

        self.assertEqual(source.structures[0].atomic_numbers, restored.structures[0].atomic_numbers)
        numpy.testing.assert_allclose(
            source.structures[0].coordinates.values,
            restored.structures[0].coordinates.values,
            atol=0.001,
            rtol=0.0,
        )
        self.assertEqual(self._atom_semantics(source), self._atom_semantics(restored))
        for role, tolerance in (("partial_charge", 0.0001), ("radius", 0.0001)):
            with self.subTest(role=role):
                numpy.testing.assert_allclose(
                    self._property(source, role).data.values,
                    self._property(restored, role).data.values,
                    atol=tolerance,
                    rtol=0.0,
                )


if __name__ == "__main__":
    unittest.main()
