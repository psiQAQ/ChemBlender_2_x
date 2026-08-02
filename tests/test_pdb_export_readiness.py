import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, FrameSet, ImportBatch
from ChemBlender.core.exporters import (
    pdb_export_readiness,
    pqr_export_readiness,
)
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.core.formats.pqr import parse_pqr
from tests.test_biological_atom_data import biological_mapping_fixture


FIXTURES = Path(__file__).with_name("fixtures")


class PDBPQRExportReadinessTests(unittest.TestCase):
    def setUp(self):
        self.pdb = parse_pdb(FIXTURES / "pdb" / "atom-hetatm.pdb")
        self.pqr = parse_pqr(FIXTURES / "pqr" / "with-chain.pqr")

    def property(self, batch, role):
        return next(value for value in batch.datasets if value.semantic_role == role)

    def test_complete_imported_entities_are_ready(self):
        for report in (
            pdb_export_readiness(self.pdb),
            pqr_export_readiness(self.pqr),
        ):
            with self.subTest(report=report):
                self.assertEqual(report.status.value, "Ready")
                self.assertEqual(report.tokens, ())
                self.assertFalse(hasattr(report, "__dict__"))
                with self.assertRaises(FrozenInstanceError):
                    report.status = None

    def test_pqr_requires_atom_name_to_infer_the_structure_element(self):
        mismatched = replace(
            self.pqr.structures[0],
            atomic_numbers=(7, 7),
        )

        report = pqr_export_readiness(
            replace(self.pqr, structures=(mismatched,))
        )

        self.assertEqual(report.status.value, "Invalid")
        self.assertEqual(report.tokens, ("identity.element.mismatch",))

    def test_generic_structure_reports_missing_hierarchy(self):
        generic = ImportBatch(structures=self.pdb.structures)

        report = pdb_export_readiness(generic)

        self.assertEqual(report.status.value, "MissingHierarchy")
        self.assertEqual(report.tokens, ("hierarchy.missing",))

    def test_pqr_requires_complete_finite_charge_and_radius_with_exact_units(self):
        charge = self.property(self.pqr, "partial_charge")
        radius = self.property(self.pqr, "radius")
        cases = (
            (
                "missing",
                replace(self.pqr, datasets=(charge,)),
                "MissingProperty",
                ("dataset.radius.missing",),
            ),
            (
                "nan",
                replace(
                    self.pqr,
                    datasets=(
                        replace(
                            charge,
                            data=ArrayData(
                                numpy.asarray((numpy.nan, -0.55)),
                                ("atom",),
                                "elementary_charge",
                            ),
                        ),
                        radius,
                    ),
                ),
                "Invalid",
                ("dataset.partial_charge.values",),
            ),
            (
                "infinite",
                replace(
                    self.pqr,
                    datasets=(
                        charge,
                        replace(
                            radius,
                            data=ArrayData(
                                numpy.asarray((numpy.inf, 1.40)),
                                ("atom",),
                                "angstrom",
                            ),
                        ),
                    ),
                ),
                "Invalid",
                ("dataset.radius.values",),
            ),
            (
                "unit",
                replace(
                    self.pqr,
                    datasets=(
                        replace(
                            charge,
                            data=replace(charge.data, unit="dimensionless"),
                        ),
                        radius,
                    ),
                ),
                "Invalid",
                ("dataset.partial_charge.unit",),
            ),
        )
        for name, batch, status, issues in cases:
            with self.subTest(name=name):
                report = pqr_export_readiness(batch)
                self.assertEqual(report.status.value, status)
                self.assertEqual(report.tokens, issues)

    def test_pqr_rejects_frames_and_multiple_structures_without_losing_boundaries(self):
        structure = self.pqr.structures[0]
        coordinates = numpy.asarray(structure.coordinates.values)
        frames = FrameSet(
            id=uuid4(),
            revision="pqr-frames-r1",
            semantic_role="coordinates",
            domain="frame",
            data=ArrayData(
                numpy.stack((coordinates, coordinates + 1.0)),
                ("frame", "atom", "xyz"),
                "angstrom",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure.id,
            comments=("frame 1", "frame 2"),
        )
        report = pqr_export_readiness(
            replace(self.pqr, datasets=(*self.pqr.datasets, frames))
        )
        self.assertEqual(report.status.value, "Invalid")
        self.assertEqual(report.tokens, ("dataset.coordinates.unsupported",))

        hierarchy = self.pqr.biological_hierarchies[0]
        second_structure = replace(
            structure,
            id=uuid4(),
            revision="pqr-second-structure-r1",
        )
        second_hierarchy = replace(
            hierarchy,
            id=uuid4(),
            revision="pqr-second-hierarchy-r1",
            structure_id=second_structure.id,
        )
        second_datasets = tuple(
            replace(
                value,
                id=uuid4(),
                revision=f"pqr-second-{value.semantic_role}-r1",
                structure_id=second_structure.id,
            )
            for value in self.pqr.datasets
        )
        first = replace(
            self.pqr,
            structures=(structure, second_structure),
            biological_hierarchies=(hierarchy, second_hierarchy),
            datasets=(*self.pqr.datasets, *second_datasets),
        )
        last = replace(
            self.pqr,
            structures=(second_structure, structure),
            biological_hierarchies=(second_hierarchy, hierarchy),
            datasets=(*second_datasets, *self.pqr.datasets),
        )

        self.assertEqual(pqr_export_readiness(first), pqr_export_readiness(last))
        self.assertEqual(pqr_export_readiness(first).status.value, "Ambiguous")
        self.assertEqual(
            pqr_export_readiness(first).tokens,
            ("structure.ambiguous",),
        )

    def test_live_hierarchy_and_identity_mutations_fail_closed(self):
        structure = self.pdb.structures[0]
        hierarchy = self.pdb.biological_hierarchies[0]

        def mutate_value(array, index, value, token):
            values = numpy.asarray(array.values)
            original = values[index]
            values[index] = value
            try:
                report = pdb_export_readiness(self.pdb)
            finally:
                values[index] = original
            self.assertEqual(report.status.value, "Invalid")
            self.assertEqual(report.tokens, (token,))

        def mutate_attribute(instance, name, value, token):
            original = getattr(instance, name)
            object.__setattr__(instance, name, value)
            try:
                report = pdb_export_readiness(self.pdb)
            finally:
                object.__setattr__(instance, name, original)
            self.assertEqual(report.status.value, "Invalid")
            self.assertEqual(report.tokens, (token,))

        mutate_value(
            hierarchy.atom_sites.residue_indices,
            0,
            999,
            "hierarchy.shape",
        )
        mutate_value(
            structure.atomic_identity.atom_names.codes,
            0,
            999,
            "identity.atom_name.invalid",
        )
        mutate_value(
            hierarchy.atom_sites.alternate_locations.codes,
            0,
            999,
            "identity.altloc.invalid",
        )
        mutate_value(
            hierarchy.atom_sites.record_kinds.codes,
            0,
            hierarchy.atom_sites.record_kinds.missing_code,
            "identity.record_kind",
        )

        residue = hierarchy.residues[0]
        original_chain_index = residue.chain_index
        object.__setattr__(residue, "chain_index", 999)
        try:
            report = pdb_export_readiness(self.pdb)
        finally:
            object.__setattr__(residue, "chain_index", original_chain_index)
        self.assertEqual(report.status.value, "Invalid")
        self.assertEqual(report.tokens, ("hierarchy.shape",))

        mutate_attribute(
            hierarchy.atom_sites.serial_numbers,
            "values",
            numpy.asarray(((32, 3835, 33),), dtype=numpy.int64),
            "hierarchy.shape",
        )
        mutate_attribute(
            hierarchy.atom_sites.residue_indices,
            "values",
            numpy.asarray((0.0, 1.0, 2.0), dtype=numpy.float64),
            "hierarchy.shape",
        )

        altloc_codes = hierarchy.atom_sites.alternate_locations.codes
        mutate_attribute(
            altloc_codes,
            "values",
            numpy.asarray(altloc_codes.values, dtype=numpy.float64),
            "identity.altloc.invalid",
        )
        mutate_attribute(
            hierarchy.atom_sites.record_kinds.codes,
            "values",
            numpy.asarray(
                (hierarchy.atom_sites.record_kinds.codes.values,),
                dtype=numpy.int64,
            ),
            "identity.record_kind",
        )
        mutate_attribute(
            altloc_codes,
            "dims",
            ("site",),
            "identity.altloc.invalid",
        )
        mutate_attribute(
            altloc_codes,
            "unit",
            "angstrom",
            "identity.altloc.invalid",
        )

    def test_long_identifiers_report_field_overflow(self):
        hierarchy = self.pdb.biological_hierarchies[0]
        chain = replace(hierarchy.chains[0], chain_id="AB")
        overflow = replace(
            self.pdb,
            biological_hierarchies=(
                replace(hierarchy, chains=(chain,)),
            ),
        )

        report = pdb_export_readiness(overflow)

        self.assertEqual(report.status.value, "FieldOverflow")
        self.assertEqual(report.tokens, ("identity.chain_id.overflow",))

    def test_association_uses_explicit_ids_and_never_revision_as_a_tiebreaker(self):
        hierarchy = self.pqr.biological_hierarchies[0]
        charge = self.property(self.pqr, "partial_charge")
        stale_hierarchy = replace(
            hierarchy,
            id=uuid4(),
            revision="stale-revision",
        )
        stale_charge = replace(
            charge,
            id=uuid4(),
            revision="stale-revision",
        )
        stale_first = replace(
            self.pqr,
            biological_hierarchies=(stale_hierarchy, hierarchy),
            datasets=(stale_charge, *self.pqr.datasets),
        )
        stale_last = replace(
            self.pqr,
            biological_hierarchies=(hierarchy, stale_hierarchy),
            datasets=(*self.pqr.datasets, stale_charge),
        )
        self.assertEqual(
            pqr_export_readiness(stale_first),
            pqr_export_readiness(stale_last),
        )
        self.assertEqual(pqr_export_readiness(stale_first).status.value, "Ambiguous")
        self.assertEqual(
            pqr_export_readiness(stale_first).tokens,
            ("dataset.partial_charge.ambiguous", "hierarchy.ambiguous"),
        )

    def test_duplicate_or_out_of_range_source_serials_require_renumbering(self):
        hierarchy = self.pdb.biological_hierarchies[0]
        for serials in ((32, 32, 33), (100000, 3835, 33)):
            with self.subTest(serials=serials):
                sites = replace(
                    hierarchy.atom_sites,
                    serial_numbers=ArrayData(
                        numpy.asarray(serials, dtype=numpy.int64),
                        ("atom",),
                        "dimensionless",
                    ),
                )
                batch = replace(
                    self.pdb,
                    biological_hierarchies=(
                        replace(hierarchy, atom_sites=sites),
                    ),
                )

                report = pdb_export_readiness(batch)

                self.assertEqual(report.status.value, "ReadyWithRenumbering")
                self.assertEqual(report.tokens, ("serial.renumber",))

    def test_identity_coordinates_and_frames_fail_closed(self):
        structure = self.pdb.structures[0]
        missing_identity = replace(
            self.pdb,
            structures=(replace(structure, atomic_identity=None),),
        )
        report = pdb_export_readiness(missing_identity)
        self.assertEqual(report.status.value, "MissingProperty")
        self.assertEqual(report.tokens, ("identity.atom_name.missing",))

        coordinates = numpy.asarray(structure.coordinates.values)
        original = float(coordinates[0, 0])
        coordinates[0, 0] = numpy.nan
        try:
            report = pdb_export_readiness(self.pdb)
        finally:
            coordinates[0, 0] = original
        self.assertEqual(report.status.value, "Invalid")
        self.assertEqual(report.tokens, ("coordinates.values",))

        multimodel = biological_mapping_fixture()
        frames = next(
            value for value in multimodel.datasets if isinstance(value, FrameSet)
        )
        ambiguous = replace(
            multimodel,
            datasets=(*multimodel.datasets, replace(frames, id=uuid4())),
        )
        report = pdb_export_readiness(ambiguous)
        self.assertEqual(report.status.value, "Ambiguous")
        self.assertEqual(report.tokens, ("dataset.coordinates.ambiguous",))

    def test_live_numeric_array_mutations_use_actual_shape_and_dtype(self):
        def mutate(array, values, batch, token):
            original = array.values
            object.__setattr__(array, "values", values)
            try:
                report = (
                    pqr_export_readiness(batch)
                    if batch is self.pqr
                    else pdb_export_readiness(batch)
                )
            finally:
                object.__setattr__(array, "values", original)
            self.assertEqual(report.status.value, "Invalid")
            self.assertEqual(report.tokens, (token,))

        structure = self.pdb.structures[0]
        mutate(
            structure.coordinates,
            numpy.asarray(structure.coordinates.values).reshape(-1),
            self.pdb,
            "coordinates.shape",
        )
        charge = self.property(self.pqr, "partial_charge")
        mutate(
            charge.data,
            numpy.asarray(charge.data.values)[:1],
            self.pqr,
            "dataset.partial_charge.shape",
        )
        radius = self.property(self.pqr, "radius")
        mutate(
            radius.data,
            numpy.asarray(radius.data.values).reshape((-1, 1)),
            self.pqr,
            "dataset.radius.shape",
        )

        multimodel = biological_mapping_fixture()
        frames = next(
            value for value in multimodel.datasets if isinstance(value, FrameSet)
        )
        mutate(
            frames.data,
            numpy.full(
                numpy.asarray(frames.data.values).shape,
                "bad",
                dtype=object,
            ),
            multimodel,
            "dataset.coordinates.invalid",
        )

    def test_numeric_property_shape_and_status_are_validated(self):
        charge = self.property(self.pqr, "partial_charge")
        radius = self.property(self.pqr, "radius")
        cases = (
            (
                replace(
                    self.pqr,
                    datasets=(
                        replace(charge, status=DatasetStatus.PARTIAL),
                        radius,
                    ),
                ),
                ("dataset.partial_charge.status",),
            ),
            (
                replace(
                    self.pqr,
                    datasets=(
                        charge,
                        replace(
                            radius,
                            data=ArrayData(
                                numpy.asarray((1.40,)),
                                ("atom",),
                                "angstrom",
                            ),
                        ),
                    ),
                ),
                ("dataset.radius.shape",),
            ),
        )
        for batch, tokens in cases:
            with self.subTest(tokens=tokens):
                report = pqr_export_readiness(batch)
                self.assertEqual(report.status.value, "Invalid")
                self.assertEqual(report.tokens, tokens)

        b_factor = self.property(self.pdb, "b_factor")
        partial_values = numpy.asarray(b_factor.data.values).copy()
        partial_values[0] = numpy.nan
        partial = replace(
            self.pdb,
            datasets=tuple(
                replace(
                    b_factor,
                    data=ArrayData(
                        partial_values,
                        ("atom",),
                        "angstrom_squared",
                    ),
                    status=DatasetStatus.PARTIAL,
                )
                if value.id == b_factor.id
                else value
                for value in self.pdb.datasets
            ),
        )
        self.assertEqual(pdb_export_readiness(partial).status.value, "Ready")
        complete_with_nan = replace(
            partial,
            datasets=tuple(
                replace(value, status=DatasetStatus.COMPLETE)
                if value.id == b_factor.id
                else value
                for value in partial.datasets
            ),
        )
        report = pdb_export_readiness(complete_with_nan)
        self.assertEqual(report.status.value, "Invalid")
        self.assertEqual(report.tokens, ("dataset.b_factor.values",))

    def test_all_p1_numeric_and_identifier_widths_are_checked(self):
        structure = self.pdb.structures[0]
        hierarchy = self.pdb.biological_hierarchies[0]
        occupancy = self.property(self.pdb, "occupancy")
        b_factor = self.property(self.pdb, "b_factor")
        charge = self.property(self.pqr, "partial_charge")
        radius = self.property(self.pqr, "radius")

        coordinates = numpy.asarray(structure.coordinates.values).copy()
        coordinates[0, 0] = 10000.0
        b_values = numpy.asarray(b_factor.data.values).copy()
        b_values[0] = 10000.0
        occupancy_values = numpy.asarray(occupancy.data.values).copy()
        occupancy_values[0] = 10000.0
        charge_values = numpy.asarray(charge.data.values).copy()
        charge_values[0] = 1000.0
        radius_values = numpy.asarray(radius.data.values).copy()
        radius_values[0] = 100.0

        pdb_cases = (
            (
                replace(
                    self.pdb,
                    structures=(
                        replace(
                            structure,
                            atomic_identity=replace(
                                structure.atomic_identity,
                                atom_names=replace(
                                    structure.atomic_identity.atom_names,
                                    categories=("LONGER", "FE", "CA"),
                                ),
                            ),
                        ),
                    ),
                ),
                "identity.atom_name.overflow",
            ),
            (
                replace(
                    self.pdb,
                    structures=(
                        replace(
                            structure,
                            coordinates=ArrayData(
                                coordinates,
                                ("atom", "xyz"),
                                "angstrom",
                            ),
                        ),
                    ),
                ),
                "coordinates.overflow",
            ),
            (
                replace(
                    self.pdb,
                    biological_hierarchies=(
                        replace(
                            hierarchy,
                            residues=(
                                replace(
                                    hierarchy.residues[0],
                                    sequence_number=10000,
                                ),
                                *hierarchy.residues[1:],
                            ),
                        ),
                    ),
                ),
                "identity.residue_number.overflow",
            ),
            (
                replace(
                    self.pdb,
                    biological_hierarchies=(
                        replace(
                            hierarchy,
                            model=replace(hierarchy.model, number=10000),
                        ),
                    ),
                ),
                "model.overflow",
            ),
            (
                replace(
                    self.pdb,
                    datasets=tuple(
                        replace(
                            occupancy,
                            data=ArrayData(
                                occupancy_values,
                                ("atom",),
                                "dimensionless",
                            ),
                        )
                        if value.id == occupancy.id
                        else value
                        for value in self.pdb.datasets
                    ),
                ),
                "dataset.occupancy.overflow",
            ),
            (
                replace(
                    self.pdb,
                    datasets=tuple(
                        replace(
                            b_factor,
                            data=ArrayData(
                                b_values,
                                ("atom",),
                                "angstrom_squared",
                            ),
                        )
                        if value.id == b_factor.id
                        else value
                        for value in self.pdb.datasets
                    ),
                ),
                "dataset.b_factor.overflow",
            ),
        )
        for batch, token in pdb_cases:
            with self.subTest(token=token):
                report = pdb_export_readiness(batch)
                self.assertEqual(report.status.value, "FieldOverflow")
                self.assertIn(token, report.tokens)

        pqr_cases = (
            (
                replace(
                    self.pqr,
                    datasets=(
                        replace(
                            charge,
                            data=ArrayData(
                                charge_values,
                                ("atom",),
                                "elementary_charge",
                            ),
                        ),
                        radius,
                    ),
                ),
                "dataset.partial_charge.overflow",
            ),
            (
                replace(
                    self.pqr,
                    datasets=(
                        charge,
                        replace(
                            radius,
                            data=ArrayData(
                                radius_values,
                                ("atom",),
                                "angstrom",
                            ),
                        ),
                    ),
                ),
                "dataset.radius.overflow",
            ),
        )
        for batch, token in pqr_cases:
            with self.subTest(token=token):
                report = pqr_export_readiness(batch)
                self.assertEqual(report.status.value, "FieldOverflow")
                self.assertEqual(report.tokens, (token,))


if __name__ == "__main__":
    unittest.main()
