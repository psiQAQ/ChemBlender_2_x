import json
import tempfile
import unittest
from pathlib import Path

import numpy

from ChemBlender.core.model import CalculationStatus, DatasetStatus, QCProject
from ChemBlender.core.qcschema_adapter import (
    QCSCHEMA_READER,
    QCSchemaCompatibilityError,
    export_qcschema,
    export_qcschema_atomic_result,
    parse_qcschema_molecule,
    parse_qcschema_atomic_result,
)
from ChemBlender.core.readers import ReaderRegistry
from ChemBlender.core.readers import SniffMatch


FIXTURES = Path(__file__).parent / "fixtures" / "qcschema"


class QCSchemaAdapterTests(unittest.TestCase):
    def parse(self, name):
        return parse_qcschema_atomic_result(FIXTURES / name)

    def test_v1_import_normalizes_structure_calculation_properties_and_provenance(self):
        batch = self.parse("atomic_result_v1.json")

        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(batch.structures[0].atomic_numbers, (8, 1, 1))
        self.assertEqual(batch.structures[0].coordinates.unit, "bohr")
        self.assertEqual(batch.calculations[0].status, CalculationStatus.SUCCESS)
        metadata = batch.calculations[0].metadata
        self.assertEqual(metadata.driver, "energy")
        self.assertEqual(metadata.method, "HF")
        self.assertEqual(metadata.basis, "sto-3g")
        self.assertEqual(metadata.molecular_charge, 0)
        self.assertEqual(metadata.molecular_multiplicity, 1)
        self.assertEqual(metadata.program, "fixture-engine")
        self.assertEqual(metadata.program_version, "1.2.3")
        roles = {dataset.semantic_role: dataset for dataset in batch.datasets}
        self.assertEqual(roles["return_energy"].data.unit, "hartree")
        self.assertEqual(roles["calcinfo_nalpha"].data.unit, "dimensionless")
        self.assertEqual(roles["return_result"].data.dims, ())
        self.assertEqual(len(batch.qcschema_envelopes), 1)
        self.assertEqual(batch.report.issues, ())

    def test_v2_import_uses_input_specification_and_result_molecule(self):
        batch = self.parse("atomic_result_v2.json")

        calculation = batch.calculations[0]
        self.assertEqual(calculation.metadata.driver, "gradient")
        self.assertEqual(calculation.metadata.method, "B3LYP")
        self.assertEqual(calculation.metadata.program, "fixture-program")
        self.assertEqual(len(calculation.input_structure_ids), 1)
        self.assertEqual(len(calculation.result_structure_ids), 1)
        self.assertNotEqual(calculation.input_structure_ids, calculation.result_structure_ids)
        gradient = next(item for item in batch.datasets if item.semantic_role == "return_result")
        self.assertEqual(gradient.data.dims, ("atom", "xyz"))
        self.assertEqual(gradient.data.unit, "hartree_per_bohr")
        numpy.testing.assert_allclose(gradient.data.values[1], [0.0, 0.0, -0.01])
        self.assertIn("structure", batch.report.parsed_capabilities)
        self.assertIn("energy", batch.report.parsed_capabilities)

    def test_raw_envelope_round_trips_every_json_field_for_each_version(self):
        for filename in ("atomic_result_v1.json", "atomic_result_v2.json"):
            with self.subTest(filename=filename):
                source = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
                envelope = self.parse(filename).qcschema_envelopes[0]
                self.assertEqual(export_qcschema_atomic_result(envelope), source)

    def test_standalone_v3_molecule_normalizes_charge_and_round_trips(self):
        source = json.loads((FIXTURES / "molecule_v3.json").read_text(encoding="utf-8"))
        batch = parse_qcschema_molecule(FIXTURES / "molecule_v3.json")
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (7, 1, 1, 1))
        self.assertEqual(structure.molecular_charge, 1)
        self.assertEqual(structure.molecular_multiplicity, 1)
        self.assertEqual(export_qcschema(batch.qcschema_envelopes[0]), source)
        self.assertIs(ReaderRegistry((QCSCHEMA_READER,)).select(FIXTURES / "molecule_v3.json"), QCSCHEMA_READER)

    def test_sniffer_recognizes_truncated_large_qcschema_prefix(self):
        prefix = b'{"schema_name":"qcschema_atomic_result","schema_version":2,"native_files":'
        self.assertEqual(
            QCSCHEMA_READER.sniff(Path("large.json"), prefix).match,
            SniffMatch.PROBABLE,
        )

    def test_project_and_sidecar_accept_qcschema_envelope(self):
        from ChemBlender.core.sidecar import open_project, save_project

        batch = self.parse("atomic_result_v1.json")
        project = QCProject(id=batch.report.created_entity_ids[0], schema_version="0.1")
        project.commit(batch)
        with tempfile.TemporaryDirectory() as directory:
            path = save_project(Path(directory) / "project.cbq", project)
            restored = open_project(path)
        envelope = next(iter(restored.qcschema_envelopes.values()))
        self.assertEqual(export_qcschema_atomic_result(envelope)["extras"]["fixture_marker"], "preserve-me")

    def test_unknown_schema_is_rejected_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.json"
            path.write_text(json.dumps({"schema_name": "qcschema_output", "schema_version": 7}), encoding="utf-8")
            with self.assertRaisesRegex(QCSchemaCompatibilityError, "qcschema_output/7"):
                parse_qcschema_atomic_result(path)

    def test_non_numeric_property_is_preserved_and_reported(self):
        document = json.loads((FIXTURES / "atomic_result_v1.json").read_text(encoding="utf-8"))
        document["properties"]["custom_label"] = "opaque"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            batch = parse_qcschema_atomic_result(path)
        self.assertEqual(export_qcschema_atomic_result(batch.qcschema_envelopes[0]), document)
        self.assertTrue(any(issue.path == "properties.custom_label" for issue in batch.report.issues))
        self.assertNotIn("custom_label", {dataset.semantic_role for dataset in batch.datasets})

    def test_v1_failed_result_maps_structured_error(self):
        document = json.loads((FIXTURES / "atomic_result_v1.json").read_text(encoding="utf-8"))
        document["success"] = False
        document["error"] = {
            "error_type": "convergence_error",
            "error_message": "SCF did not converge",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failed.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            batch = parse_qcschema_atomic_result(path)
        calculation = batch.calculations[0]
        self.assertEqual(calculation.status, CalculationStatus.FAILED)
        self.assertEqual(calculation.metadata.error_type, "convergence_error")
        self.assertEqual(calculation.metadata.error_message, "SCF did not converge")


if __name__ == "__main__":
    unittest.main()
