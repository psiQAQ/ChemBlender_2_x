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
