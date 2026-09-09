"""Real file-to-CBQ and CLI/GUI process boundaries, without Blender."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from cbq_core.sidecar import open_project, close_project
from chemblender_prepare.cli import main
from chemblender_prepare.gui import CliProcess, PrepareWindow, command_arguments


ROOT = Path(__file__).resolve().parents[1]


class PrepareCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="prepare-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.xyz = self.root / "water calculation.xyz"
        self.xyz.write_text("3\nwater\nO 0 0 0\nH 0.758 0 0.504\nH -0.758 0 0.504\n", encoding="utf-8")
        self.output = self.root / "water.cbq"

    def cli(self, *arguments, success=True):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main([str(value) for value in arguments] + ["--json"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0 if success else 1, result)
        self.assertEqual(result["status"], "success" if success else result["status"], result)
        return result

    def convert(self):
        return self.cli("convert", self.xyz, "-o", self.output)

    def test_pubchem_conversion_verifies_provenance_and_cleans_failed_tasks(self):
        import hashlib
        from types import SimpleNamespace
        from chemblender_prepare import pubchem_import
        payload = (ROOT / "tests/fixtures/sdf/records.sdf").read_bytes()
        arguments = command_arguments({"command": "convert", "source_kind": "pubchem",
                      "pubchem": "2244", "output": str(self.output)})
        self.assertIn("--pubchem", arguments)
        with patch.object(pubchem_import, "_fetch", return_value=SimpleNamespace(status_code=200, content=payload)) as fetch:
            self.cli(*arguments)
        fetch.assert_called_once()
        url = fetch.call_args.args[0]
        project = open_project(self.output, verify_arrays=True)
        try:
            evidence, = [item for item in project.provenance.values() if item.operation == "pubchem_import"]
            self.assertEqual(evidence.source, url)
            self.assertEqual(evidence.source_hash, hashlib.sha256(payload).hexdigest())
            self.assertEqual({item.locator for item in project.source_revisions.values()}, {url})
            self.assertEqual(len(project.structures), 2)
        finally:
            close_project(project)
        for failure in ("network", "cancel", "tamper"):
            target = self.root / (failure + ".cbq")
            cancel = self.root / (failure + ".cancel")
            task = self.root / (failure + "-task")
            def fetch(*args, **kwargs):
                if failure == "network":
                    raise OSError("offline")
                if failure == "cancel":
                    cancel.touch()
                return SimpleNamespace(status_code=200, content=payload)
            attach = pubchem_import.attach_verified_pubchem_provenance
            def attachment(source, digest, batch, owner):
                if failure == "tamper":
                    source.path.write_bytes(b"changed")
                return attach(source, digest, batch, owner)
            with patch.object(pubchem_import, "_fetch", side_effect=fetch), patch.object(
                    pubchem_import, "attach_verified_pubchem_provenance", side_effect=attachment):
                result = self.cli("convert", "--pubchem", "2244", "-o", target,
                                  "--task-directory", task, "--cancel-file", cancel, success=False)
            self.assertEqual(result["status"], "cancelled" if failure == "cancel" else "error")
            self.assertFalse(target.exists())
            self.assertFalse(list(task.rglob("*.sdf")))

    def test_tk_legacy_smiles_presets_fill_text_without_computing(self):
        import tkinter as tk
        from cbq_core.element_data import preset_smiles
        root = tk.Tk()
        root.withdraw()
        window = PrepareWindow(root)
        try:
            window.values["source_kind"].set("smiles")
            root.update()
            self.assertLessEqual(root.winfo_reqheight(), 850)
            widget = window.field_widgets["smiles_preset"][1]
            self.assertEqual(tuple(widget["values"]), ("", *preset_smiles))
            for key in ("Glc", "G", "PE"):
                widget.set(key)
                widget.event_generate("<<ComboboxSelected>>")
                root.update()
                self.assertIsNone(window.job)
                self.assertEqual(window.values["smiles_text"].get(), preset_smiles[key][1])
                target = self.root / (key + ".cbq")
                values = {name: value.get() for name, value in window.values.items()}
                values["output"] = str(target)
                arguments = command_arguments(values)
                self.assertEqual(arguments[arguments.index("--smiles-text") + 1], preset_smiles[key][1])
                self.cli(*arguments)
                project = open_project(target, verify_arrays=True)
                try:
                    self.assertEqual(len(project.structures), 1)
                    self.assertTrue(project.topologies)
                    self.assertEqual(next(iter(project.source_revisions.values())).locator, "inline:smiles")
                finally:
                    close_project(project)
            window.values["smiles_text"].set("C/C=C/C")
            widget.set("")
            widget.event_generate("<<ComboboxSelected>>")
            root.update()
            self.assertEqual(window.values["smiles_text"].get(), "C/C=C/C")
        finally:
            root.destroy()

    def test_external_gui_routes_legacy_file_formats_to_verified_cbq(self):
        cases = (("sample.cif", "cif/cscl.cif"), ("POSCAR", "poscar/si.POSCAR"),
                 ("CONTCAR", "poscar/velocities.CONTCAR"), ("sample.sdf", "sdf/records.sdf"),
                 ("sample.mol2", "mol2/small.mol2"))
        for index, (name, fixture) in enumerate(cases):
            with self.subTest(format=name):
                source = self.root / name
                original = (ROOT / "tests/fixtures" / fixture).read_bytes()
                source.write_bytes(original)
                target = self.root / f"converted-{index}.cbq"
                arguments = command_arguments({"command": "convert", "sources": str(source),
                    "output": str(target), "validation-mode": "strict"})
                self.assertIn(str(source), arguments)
                self.assertIn("strict", arguments)
                self.cli(*arguments)
                project = open_project(target, verify_arrays=True)
                try:
                    self.assertTrue(project.structures)
                    self.assertTrue(project.source_revisions)
                    self.assertEqual({value.locator for value in project.source_revisions.values()}, {str(source)})
                finally:
                    close_project(project)
                self.assertEqual(source.read_bytes(), original)

    def test_sdf_record_recovery_is_visible_and_all_failed_input_is_rejected(self):
        source = ROOT / "tests/fixtures/sdf/malformed-middle.sdf"
        inspected = self.cli("inspect", source)["metadata"]["molecular"]
        self.assertEqual(inspected["record_count"], 2)
        self.assertEqual([item["code"] for item in inspected["diagnostics"]], ["sdf.record_parse_failed"])
        self.cli("convert", source, "-o", self.output)
        project = open_project(self.output, verify_arrays=True)
        try:
            self.assertEqual(sorted(record.source_record_index for record in project.molecular_records.values()), [0, 2])
            self.assertEqual([item.code for item in project.diagnostics.values()], ["sdf.record_parse_failed"])
        finally:
            close_project(project)
        failed = self.root / "all-failed.sdf"
        failed.write_bytes((ROOT / "tests/fixtures/mol/water-v2000.mol").read_bytes().replace(b" O   ", b" Xx  ", 1) + b"$$$$\n")
        target = self.root / "invalid.cbq"
        from dataclasses import replace
        from chemblender_prepare.reader_api import worker_bridge
        parse = worker_bridge.parse_with_worker
        for corruption in ("valid_record", "plugin"):
            def corrupt(*args, **kwargs):
                batch = parse(*args, **kwargs)
                diagnostic = batch.diagnostics[0]
                diagnostic = (replace(diagnostic, record_key=batch.molecular_records[0].record_key)
                              if corruption == "valid_record" else replace(diagnostic, code="plugin.integrity_failure"))
                return replace(batch, diagnostics=(diagnostic,))
            with patch.object(worker_bridge, "parse_with_worker", side_effect=corrupt):
                rejected = self.cli("convert", source, "-o", target, success=False)
            self.assertIn("sdf.record_parse_failed" if corruption == "valid_record" else "plugin.integrity_failure",
                          rejected["error"]["message"])
            self.assertFalse(target.exists())
        result = self.cli("convert", failed, "-o", target, success=False)
        self.assertIn("sdf.record_parse_failed", result["error"]["message"])
        self.assertFalse(target.exists())

    def test_conformer_projection_bounds_and_tk_rejects_hidden_mapping(self):
        import tkinter as tk
        from types import SimpleNamespace
        from uuid import uuid4
        from chemblender_prepare.cli import _conformer_summaries
        evidence = tuple(SimpleNamespace(record_id=uuid4(), kind="complete_atom_maps",
                         atom_mapping=tuple(range(1000)), requires_review=index == 100)
                         for index in range(101))
        group = SimpleNamespace(id=uuid4(), snapshot="a" * 64,
                    record_ids=tuple(item.record_id for item in evidence), evidence=evidence)
        projected = _conformer_summaries((group,) * 101)
        self.assertEqual(len(projected), 100)
        value = projected[0]
        self.assertEqual(value["record_count"], 101)
        self.assertTrue(value["requires_review"])
        self.assertTrue(value["evidence_truncated"])
        self.assertEqual(len(value["evidence"]), 100)
        self.assertEqual(len(value["evidence"][0]["atom_mapping"]), 100)
        self.assertEqual(value["evidence"][0]["atom_count"], 1000)
        self.assertTrue(value["evidence"][0]["mapping_truncated"])
        root = tk.Tk()
        root.withdraw()
        window = PrepareWindow(root)
        root.update()
        try:
            for kind in ("missing", "evidence", "mapping"):
                data = json.loads(json.dumps(value))
                if kind == "mapping":
                    data["evidence_truncated"] = False
                    data["evidence"] = data["evidence"][:2]
                    data["record_count"] = 2
                report = {"status": "success", "metadata": {"command": "inspect",
                          "cbq_path": str(self.output), "conformer_suggestions": [] if kind == "missing" else [data]}}
                window.report.delete("1.0", "end")
                window.report.insert("1.0", json.dumps(report))
                with patch("chemblender_prepare.core.import_pipeline.conformer_grouping.suggest_conformer_groups",
                           side_effect=AssertionError("GUI must not compute")), patch("tkinter.messagebox.showerror") as error:
                    window.review_conformers()
                    if kind != "missing":
                        dialog, = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
                        dialog.children["candidate"].current(0)
                        dialog.children["reviewed"].invoke()
                        dialog.children["apply"].invoke()
                        self.assertTrue(dialog.winfo_exists())
                        dialog.destroy()
                    error.assert_called_once()
                    self.assertIsNone(window.job)
                    self.assertFalse(self.output.exists())
        finally:
            root.destroy()

    def test_tk_conformer_review_requires_selection_and_runs_explicitly(self):
        import tkinter as tk
        from cbq_core.model import ConformerSet
        prepared = self.root / "prepared.cbq"
        self.cli("convert", ROOT / "tests/fixtures/sdf/records.sdf", "-o", prepared)
        report = self.cli("inspect", prepared)
        original = {str(p.relative_to(prepared)): p.read_bytes() for p in prepared.rglob("*") if p.is_file()}
        root = tk.Tk()
        root.withdraw()
        window = PrepareWindow(root)
        try:
            with patch("tkinter.messagebox.showerror") as error:
                window.report.insert("1.0", json.dumps({**report, "metadata": {**report["metadata"], "conformer_suggestions": [{}]}}))
                window.review_conformers()
                error.assert_called_once()
                self.assertFalse(any(isinstance(child, tk.Toplevel) for child in root.winfo_children()))
            window.report.delete("1.0", "end")
            window.report.insert("1.0", json.dumps(report))
            window.values["output"].set(str(prepared))
            with patch("chemblender_prepare.core.import_pipeline.conformer_grouping.suggest_conformer_groups",
                       side_effect=AssertionError("GUI must not regroup")):
                window.review_conformers()
            dialog, = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
            choice = dialog.children["candidate"]
            self.assertEqual(choice.current(), -1)
            dialog.children["apply"].invoke()
            self.assertIsNone(window.job)
            choice.current(0)
            choice.event_generate("<<ComboboxSelected>>")
            root.update()
            with patch("tkinter.messagebox.showerror") as error:
                dialog.children["apply"].invoke()
                error.assert_called_once()
            dialog.children["reviewed"].invoke()
            choice.event_generate("<<ComboboxSelected>>")
            root.update()
            self.assertNotIn("selected", dialog.children["reviewed"].state())
            dialog.children["reviewed"].invoke()
            dialog.children["apply"].invoke()
            self.assertIsNone(window.job)
            self.assertEqual(window.values["output"].get(), "")
            self.assertEqual(window.sources.get("1.0", "end").strip(), str(prepared))
            self.assertTrue(json.loads(window.values["parameters"].get())["review_confirmed"])
            window.values["output"].set(str(self.output))
            window.start()
            self.assertIsNotNone(window.job)
            deadline = time.monotonic() + 20
            while window.job is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            self.assertIsNone(window.job)
            self.assertEqual(json.loads(window.report.get("1.0", "end"))["status"], "success")
            project = open_project(self.output, verify_arrays=True)
            try:
                self.assertEqual(sum(isinstance(value, ConformerSet) for value in project.datasets.values()), 1)
            finally:
                close_project(project)
            self.assertEqual(original, {str(p.relative_to(prepared)): p.read_bytes() for p in prepared.rglob("*") if p.is_file()})
        finally:
            if window.job is not None:
                window.job.cancel()
                window.job.process.wait(timeout=10)
                window.job.close()
            root.destroy()

    def test_explicit_conformer_acceptance_reopens_and_rejects_stale_or_unreviewed(self):
        from uuid import uuid4
        from cbq_core.model import ConformerSet
        source = self.root / "records.sdf"
        source.write_bytes((ROOT / "tests/fixtures/sdf/records.sdf").read_bytes())
        prepared = self.root / "prepared.cbq"
        self.cli("convert", source, "-o", prepared)
        source.unlink()
        original = {str(p.relative_to(prepared)): p.read_bytes() for p in prepared.rglob("*") if p.is_file()}
        group, = self.cli("inspect", prepared)["metadata"]["conformer_suggestions"]
        self.assertEqual(group, self.cli("inspect", prepared)["metadata"]["conformer_suggestions"][0])
        inputs = [part for item in group["evidence"] for part in ("--input", item["record_id"])]
        valid = {"suggestion_id": group["id"], "snapshot": group["snapshot"], "review_confirmed": True}
        for parameters in ({**valid, "review_confirmed": False}, {**valid, "snapshot": "0" * 64},
                           {**valid, "suggestion_id": str(uuid4())}, {**valid, "review_confirmed": "true"}):
            with self.subTest(parameters=parameters):
                result = self.cli("derive", prepared, "-o", self.output, "--operation", "molecule.group_conformers",
                                  "--parameters", json.dumps(parameters), *inputs, success=False)
                self.assertEqual(result["status"], "error")
                self.assertFalse(self.output.exists())
        missing = self.cli("derive", prepared, "-o", self.output, "--operation", "molecule.group_conformers",
                           "--parameters", json.dumps(valid), *inputs[:2], success=False)
        self.assertIn("exactly", missing["error"]["message"])
        self.assertFalse(self.output.exists())
        from chemblender_prepare.core.import_pipeline import conformer_grouping as grouping
        original_accept = grouping.accept_conformer_group
        cancel = self.root / "group.cancel"
        def cancel_during_accept(*args, **kwargs):
            cancel.touch()
            return original_accept(*args, **kwargs)
        with patch.object(grouping, "accept_conformer_group", side_effect=cancel_during_accept):
            cancelled = self.cli("derive", prepared, "-o", self.output, "--operation", "molecule.group_conformers",
                                "--parameters", json.dumps(valid), *inputs, "--cancel-file", cancel, success=False)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertFalse(self.output.exists())
        cancel.unlink()
        self.cli("derive", prepared, "-o", self.output, "--operation", "molecule.group_conformers",
                 "--parameters", json.dumps(valid), *inputs)
        self.assertEqual(original, {str(p.relative_to(prepared)): p.read_bytes() for p in prepared.rglob("*") if p.is_file()})
        project = open_project(self.output, verify_arrays=True)
        try:
            conformer, = [value for value in project.datasets.values() if isinstance(value, ConformerSet)]
            self.assertEqual(len(conformer.record_ids), 2)
            self.assertEqual(len(project.molecular_records), 2)
            self.assertEqual(len(project.structures), 2)
            self.assertTrue(all(identity in project.provenance for identity in conformer.provenance_ids))
            import numpy as np
            from cbq_core.model import RecordPropertyColumn
            self.assertEqual(conformer.data.unit, "angstrom")
            np.testing.assert_array_equal(conformer.atom_mappings.values, [[0, 1, 2], [0, 1, 2]])
            expected = [[0., 0., 0.], [0.7586, 0., 0.5043], [-0.7586, 0., 0.5043]]
            np.testing.assert_allclose(conformer.data.values, [expected, expected], rtol=0, atol=1e-12)
            columns = [value for value in project.datasets.values() if isinstance(value, RecordPropertyColumn)
                       and set(conformer.provenance_ids).intersection(value.provenance_ids)]
            self.assertEqual(len(columns), 2)
            for column in columns:
                self.assertEqual(column.record_ids, conformer.record_ids)
                expected_values = [-1.25, -2.] if "energy" in column.semantic_role else [True, False]
                np.testing.assert_array_equal(column.data.values, expected_values)
        finally:
            close_project(project)

    def test_sdf_inspection_in_gui_child_reports_evidence_without_grouping(self):
        source = ROOT / "tests/fixtures/sdf/records.sdf"
        original = source.read_bytes()
        job = CliProcess(command_arguments({"command": "inspect", "sources": str(source)}))
        try:
            deadline = time.monotonic() + 15
            result = None
            while result is None and time.monotonic() < deadline:
                result = job.poll()
                time.sleep(0.01)
            self.assertIsNotNone(result)
            self.assertEqual(result.status.value, "success")
            data = result.metadata["molecular"]
            self.assertEqual(data["record_count"], 2)
            self.assertEqual(data["typed_column_count"], 2)
            self.assertEqual(data["grouping_action"], "keep_independent")
            self.assertEqual(data["conformer_suggestion_count"], 1)
            group, = data["conformer_suggestions"]
            self.assertTrue(group["requires_review"])
            self.assertEqual(len(group["snapshot"]), 64)
            self.assertEqual(len(group["evidence"]), 2)
            self.assertTrue(all(len(item["atom_mapping"]) == 3 for item in group["evidence"]))
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(list(job.root.rglob("*.cbq")))
        finally:
            if job.process.poll() is None:
                job.cancel()
                job.process.wait(timeout=10)
            job.close()

    def test_sdf_inspection_cancel_and_changed_source_discard_staging(self):
        from chemblender_prepare.core.import_pipeline import conformer_grouping as grouping
        from chemblender_prepare.core.import_pipeline.staging import StagedImportSession
        original = (ROOT / "tests/fixtures/sdf/records.sdf").read_bytes()
        source = self.root / "records.sdf"
        create = StagedImportSession.create
        roots = []
        def track(*args, **kwargs):
            staging = create(*args, **kwargs)
            roots.append(staging.root)
            return staging
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                source.write_bytes(original)
                cancel = self.root / "inspection.cancel"
                def interrupt(*args, **kwargs):
                    if cancelled:
                        self.assertFalse(kwargs["is_cancelled"]())
                        cancel.touch()
                        self.assertTrue(kwargs["is_cancelled"]())
                        raise grouping.ConformerGroupingCancelled()
                    source.write_bytes(original + b"\n")
                    return ()
                with patch.object(StagedImportSession, "create", side_effect=track), patch.object(grouping, "suggest_staged_conformer_groups", side_effect=interrupt):
                    result = self.cli("inspect", source, "--cancel-file", cancel, success=False)
                self.assertEqual(result["status"], "cancelled" if cancelled else "error")
                self.assertTrue(roots)
                self.assertTrue(all(not root.exists() for root in roots))
                self.assertFalse(self.output.exists())

    def test_inline_smiles_preserves_text_identity_units_and_planar_warning(self):
        import hashlib
        from chemblender_prepare.reader_api import import_pipeline_bridge
        args = command_arguments({"command": "convert", "source_kind": "smiles",
            "smiles_text": "CO", "sources": "stale-file.xyz", "reader": "cube",
            "params": "ignored=old", "output": str(self.output), "validation-mode": "strict"})
        with patch.object(import_pipeline_bridge, "preflight_reader_plugins",
                          wraps=import_pipeline_bridge.preflight_reader_plugins) as preflight:
            result = self.cli(*args)
        request = preflight.call_args.args[0]
        self.assertEqual(request.sources[0].text, "CO")
        self.assertIsNone(request.sources[0].path)
        self.assertEqual(request.validation_mode.value, "strict")
        self.assertIn("smiles.planar_2d_generated", {d["code"] for d in result["metadata"]["diagnostics"]})
        project = open_project(self.output, verify_arrays=True)
        try:
            revision = next(iter(project.source_revisions.values()))
            self.assertEqual(revision.locator, "inline:smiles")
            self.assertEqual(revision.locator_kind, "inline_text")
            self.assertEqual(revision.content_hash, hashlib.sha256(b"CO").hexdigest())
            self.assertEqual(len(project.molecular_records), 1)
            molecule = next(iter(project.structures.values()))
            self.assertEqual(tuple(molecule.atomic_numbers), (6, 8))
            self.assertEqual(molecule.coordinates.unit, "angstrom")
        finally:
            close_project(project)

    def test_inline_smiles_invalid_mixed_and_cancelled_inputs_publish_nothing(self):
        for arguments in (("--smiles-text", "not-a-smiles"),
                          (str(self.xyz), "--smiles-text", "CO"),
                          ("--smiles-text", "CO", "--reader", "cube"),
                          ("--smiles-text", "")):
            with self.subTest(arguments=arguments):
                self.cli("convert", *arguments, "-o", self.output, success=False)
                self.assertFalse(self.output.exists())
        cancel = self.root / "cancel-smiles"
        cancel.touch()
        result = self.cli("convert", "--smiles-text", "CO", "-o", self.output,
                          "--cancel-file", cancel, success=False)
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(self.output.exists())

    def test_esp_derive_requires_explicit_charges_and_publishes_rdm_with_grid(self):
        configuration = self.root / "processor.json"
        configuration.write_text(json.dumps({
            "schema_version": "1",
            "python": {"wavefunction": sys.executable},
            "critic2": None,
        }), encoding="utf-8")
        environment = patch.dict(
            os.environ, {"CHEMBLENDER_PREPARE_CONFIG": str(configuration)}
        )
        environment.start()
        self.addCleanup(environment.stop)
        import numpy
        from uuid import uuid4
        from cbq_core.model import QCProject, ImportBatch, AtomicProperty, ArrayData, DatasetStatus
        from cbq_core.sidecar import save_project
        from tests.test_wavefunction_grid import entities
        structure, basis, orbitals = entities()
        charges = AtomicProperty(id=uuid4(), revision="effective-charges", semantic_role="nuclear_charge",
            domain="atom", data=ArrayData(numpy.array([.5]), ("atom",), "elementary_charge"),
            status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(), structure_id=structure.id)
        project = QCProject(uuid4(), "1.1")
        project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,), orbital_sets=(orbitals,),
                                   datasets=(charges,)))
        source = save_project(self.root / "orbitals.cbq", project)
        before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        params = {"origin": [1., 1., 1.], "step_vectors": [[.5, 0, 0], [0, .5, 0], [0, 0, .5]],
                  "shape": [3, 3, 3], "chunk_size": 8, "density_level": "scf"}
        base = ["derive", source, "--operation", "wavefunction.esp_from_orbitals_grid"]
        for entity in (structure, basis, orbitals):
            base.extend(("--input", str(entity.id)))
        def evaluate(s, b, d, c, points):
            numpy.testing.assert_array_equal(c, [.5])
            return numpy.full(len(points), .25)
        with patch("chemblender_prepare.core.wavefunction_observables._evaluate_esp", side_effect=evaluate) as evaluator:
            self.cli(*base, "--parameters", json.dumps(params), "-o", self.output, success=False)
            self.assertFalse(self.output.exists())
            evaluator.assert_not_called()
            base.extend(("--input", str(charges.id)))
            invalid = {k: v for k, v in params.items() if k != "density_level"}
            self.cli(*base, "--parameters", json.dumps(invalid), "-o", self.output, success=False)
            self.assertFalse(self.output.exists())
            evaluator.assert_not_called()
            self.cli(*base, "--parameters", json.dumps(params), "-o", self.output)
            self.assertGreater(evaluator.call_count, 1)
        result = open_project(self.output, verify_arrays=True)
        try:
            self.assertEqual(len(result.density_matrices), 1)
            self.assertEqual(len(result.provenance), 2)
            grid = next(v for v in result.datasets.values() if v.semantic_role == "electrostatic_potential")
            self.assertEqual(grid.structure_id, structure.id)
            numpy.testing.assert_array_equal(grid.data.values, numpy.full((3, 3, 3), .25))
            self.assertIn(charges.id, result.datasets)
        finally:
            close_project(result)
        self.assertEqual(before, {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()})

        from dataclasses import replace
        from chemblender_prepare.worker import runner
        run = runner.run_request
        for failure in ("late_cancel", "wrong_identity", "backend_failure"):
            target = self.root / (failure + ".cbq")
            marker = self.root / (failure + ".cancel")
            def finish(*args, **kwargs):
                result = run(*args, **kwargs)
                self.assertEqual(result.status.value, "success")
                self.assertFalse(target.exists())
                self.assertEqual(before, {p.relative_to(source): p.read_bytes()
                                          for p in source.rglob("*") if p.is_file()})
                if failure == "late_cancel":
                    marker.touch()
                    return result
                return replace(result, request_id=uuid4())
            effect = OSError("backend failed") if failure == "backend_failure" else evaluate
            with patch("chemblender_prepare.core.wavefunction_observables._evaluate_esp", side_effect=effect), \
                    patch.object(runner, "run_request", side_effect=finish if failure != "backend_failure" else run):
                result = self.cli(*base, "--parameters", json.dumps(params), "-o", target,
                                  "--cancel-file", marker, success=False)
            self.assertEqual(result["status"], "cancelled" if failure == "late_cancel" else "error")
            self.assertFalse(target.exists())
            self.assertEqual(before, {p.relative_to(source): p.read_bytes()
                                      for p in source.rglob("*") if p.is_file()})

    def test_derive_artifact_preserves_source_extension(self):
        from cbq_core.model import QCProject
        from cbq_core.sidecar import save_project
        from cbq_core.worker_protocol import WorkerResult, WorkerStatus
        from uuid import uuid4

        source = save_project(
            self.root / "empty.cbq", QCProject(uuid4(), "1.1")
        )
        wavefunction = self.root / "water.wfx"
        wavefunction.write_text("real wavefunction fixture", encoding="utf-8")

        def worker(request, directory, _cancel):
            document = request.parameters["source_artifacts"]["wavefunction"]
            self.assertEqual(document["path"], "inputs/wavefunction.wfx")
            self.assertTrue((directory / document["path"]).is_file())
            return WorkerResult(request.request_id, WorkerStatus.SUCCESS)

        with patch("chemblender_prepare.cli._run_worker", side_effect=worker):
            self.cli(
                "derive", source, "--operation", "project.verify",
                "--artifact", f"wavefunction={wavefunction}", "-o", self.output,
            )

    def test_formats_and_raw_inspection_do_not_load_blender(self):
        result = self.cli("formats")
        readers = result["metadata"]["readers"]
        self.assertEqual(len(readers), 22)
        self.assertIn("availability", next(value for value in readers if value["reader_id"] == "cube"))
        inspected = self.cli("inspect", self.xyz)
        self.assertEqual(inspected["metadata"]["reader_id"], "xyz")
        # The full suite may already contain mocked Blender modules; verify a cold interpreter.
        import subprocess
        script = """
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'bpy', 'ChemBlender'}:
        raise AssertionError('external preparation imported Blender: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from chemblender_prepare.cli import main
assert main(['formats', '--json']) == 0
assert main(['inspect', sys.argv[1], '--json']) == 0
assert 'bpy' not in sys.modules
"""
        cold = subprocess.run([sys.executable, "-c", script, str(self.xyz)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(cold.returncode, 0, cold.stderr)

    def test_convert_owned_arrays_inspect_validate_export(self):
        converted = self.convert()
        self.assertTrue((self.output / "manifest.json").is_file())
        self.xyz.unlink()
        inspected = self.cli("inspect", self.output)
        self.assertEqual(inspected["metadata"]["project_id"], converted["metadata"]["project_id"])
        self.cli("validate", self.output / "manifest.json")
        structure = next(value for value in inspected["metadata"]["entities"] if value["type"] == "Structure")
        exported = self.root / "exported.xyz"
        self.cli("export", self.output, "-o", exported, "--entity", structure["id"], "--format", "xyz", "--preview")
        self.assertFalse(exported.exists())
        self.cli("export", self.output, "-o", exported, "--entity", structure["id"], "--format", "xyz", "--confirm-loss")
        self.assertEqual(exported.read_text(encoding="utf-8").splitlines()[0], "3")

    def test_vasp4_requires_species_before_publishing_a_result(self):
        source = ROOT / "tests/fixtures/poscar/vasp4-counts.POSCAR"
        result = self.cli("convert", source, "-o", self.output,
                          "--reader", "poscar", success=False)
        self.assertFalse(self.output.exists())
        self.assertIn("species", result["error"]["message"])
        self.assertIn("--param", result["error"]["message"])

    def test_vasp4_gui_parameters_produce_correct_species_and_preserve_base(self):
        source = ROOT / "tests/fixtures/poscar/vasp4-counts.POSCAR"
        args = command_arguments({"command": "convert", "sources": str(source),
            "output": str(self.output), "reader": "poscar", "params": "species=Na,Cl"})
        self.cli(*args)
        first = open_project(self.output)
        try:
            structure = next(iter(first.structures.values()))
            self.assertEqual(structure.atomic_numbers, (11, 11, 17))
            first_id, first_revision = structure.id, structure.revision
        finally:
            close_project(first)
        original = {p.relative_to(self.output): p.read_bytes()
                    for p in self.output.rglob("*") if p.is_file()}
        second = self.root / "combined.cbq"
        self.cli("convert", source, "--project", self.output, "-o", second,
                 "--reader", "poscar", "--param", "species=K,Br")
        restored = open_project(second)
        try:
            self.assertEqual(restored.structures[first_id].revision, first_revision)
            self.assertEqual({value.atomic_numbers for value in restored.structures.values()},
                             {(11, 11, 17), (19, 19, 35)})
        finally:
            close_project(restored)
        self.assertEqual(original, {p.relative_to(self.output): p.read_bytes()
                                  for p in self.output.rglob("*") if p.is_file()})
        bad = self.root / "bad.cbq"
        self.cli("convert", source, "--project", self.output, "-o", bad,
                 "--reader", "poscar", "--param", "species=Na", success=False)
        self.assertFalse(bad.exists())
        self.assertEqual(original, {p.relative_to(self.output): p.read_bytes()
                                  for p in self.output.rglob("*") if p.is_file()})

    def test_existing_output_is_never_replaced(self):
        self.convert()
        before = (self.output / "manifest.json").read_bytes()
        self.cli("convert", self.xyz, "-o", self.output, success=False)
        self.assertEqual((self.output / "manifest.json").read_bytes(), before)

    def test_invalid_second_source_does_not_publish_first(self):
        bad = self.root / "broken.xyz"
        bad.write_text("3\nbroken\nO 0 0 0\n", encoding="utf-8")
        self.cli("convert", self.xyz, bad, "-o", self.output, success=False)
        self.assertFalse(self.output.exists())

    def test_interrupted_conversion_preserves_input_package_and_cleans_publication(self):
        from chemblender_prepare import cli
        self.convert()
        before = {p.relative_to(self.output): p.read_bytes()
                  for p in self.output.rglob("*") if p.is_file()}
        for phase in ("after_reader", "after_save", "corrupt_saved_array"):
            with self.subTest(phase=phase):
                target = self.root / (phase + ".cbq")
                cancel = self.root / (phase + ".cancel")
                task_roots, injected = [], []
                original_reader, original_save = cli._reader_batch, cli.save_project

                def reader(*args, **kwargs):
                    task_roots.append(Path(args[4]).parent)
                    result = original_reader(*args, **kwargs)
                    if phase == "after_reader":
                        cancel.touch()
                        injected.append(phase)
                    return result

                def save(path, project, *args, **kwargs):
                    result = original_save(path, project, *args, **kwargs)
                    if phase == "after_save":
                        cancel.touch()
                        injected.append(phase)
                    elif phase == "corrupt_saved_array":
                        array = next((Path(path) / "arrays").glob("*.npy"))
                        array.write_bytes(b"damaged array")
                        injected.append(phase)
                    return result

                with patch.object(cli, "_reader_batch", side_effect=reader), patch.object(
                    cli, "save_project", side_effect=save
                ):
                    result = self.cli("convert", self.xyz, "--project", self.output,
                        "-o", target, "--cancel-file", cancel, success=False)
                self.assertEqual(result["status"], "error" if phase == "corrupt_saved_array" else "cancelled", result)
                self.assertEqual(injected, [phase])
                self.assertFalse(target.exists())
                self.assertFalse(list(self.root.glob(".cbq-publish-*")))
                self.assertTrue(task_roots)
                self.assertTrue(all(not path.exists() for path in task_roots))
                self.assertEqual(before, {p.relative_to(self.output): p.read_bytes()
                    for p in self.output.rglob("*") if p.is_file()})
                self.cli("validate", self.output)

    def test_progress_sharing_violation_does_not_fail_conversion_or_hide_cancel(self):
        from chemblender_prepare import cli
        for inputs in ((str(self.xyz),), ("--smiles-text", "CO")):
            for cancelled in (False, True):
                with self.subTest(inputs=inputs, cancelled=cancelled):
                    target = self.root / (str(len(list(self.root.iterdir()))) + ".cbq")
                    cancel = target.with_suffix(".cancel")
                    def locked(path, document):
                        self.assertEqual(path.name, "progress.json")
                        if cancelled:
                            cancel.touch()
                        raise PermissionError("progress held by GUI")
                    with patch.object(cli, "_atomic_document", side_effect=locked) as progress:
                        result = self.cli("convert", *inputs, "-o", target,
                                          "--cancel-file", cancel, success=not cancelled)
                    self.assertGreater(progress.call_count, 0)
                    self.assertEqual(result["status"], "cancelled" if cancelled else "success")
                    self.assertEqual(target.exists(), not cancelled)
                    if not cancelled:
                        self.cli("validate", target)

    def test_cancel_before_execution_has_no_result_package(self):
        cancel = self.root / "cancel"
        cancel.touch()
        result = self.cli("convert", self.xyz, "-o", self.output, "--cancel-file", cancel, success=False)
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(self.output.exists())

    def test_publish_validation_failure_rolls_back(self):
        with patch("chemblender_prepare.cli.open_project", side_effect=ValueError("injected verification failure")):
            self.cli("convert", self.xyz, "-o", self.output, success=False)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".cbq-publish-*")))

    def test_upgrade_and_project_verify_preserve_input_bytes(self):
        self.convert()
        before = {path.relative_to(self.output): path.read_bytes() for path in self.output.rglob("*") if path.is_file()}
        upgraded = self.root / "upgraded.cbq"
        self.cli("upgrade", self.output, "-o", upgraded)
        verified = self.root / "verified.cbq"
        self.cli("derive", self.output, "-o", verified, "--operation", "project.verify")
        self.assertEqual(before, {path.relative_to(self.output): path.read_bytes() for path in self.output.rglob("*") if path.is_file()})
        self.cli("validate", upgraded)
        self.cli("validate", verified)

    def test_convert_rejects_unused_structure_binding(self):
        from uuid import uuid4
        result = self.cli("convert", self.xyz, "--entity", uuid4(), "-o", self.output,
                          success=False)
        self.assertIn("--entity", str(result))
        self.assertFalse(self.output.exists())

    def test_corrupted_array_is_rejected(self):
        self.convert()
        array = next((self.output / "arrays").glob("*.npy"))
        content = bytearray(array.read_bytes())
        content[-1] ^= 1
        array.write_bytes(content)
        self.cli("validate", self.output, success=False)

    def test_literal_paths_and_parameters_use_argv(self):
        arguments = command_arguments({"command": "convert", "sources": str(self.xyz),
            "output": str(self.output), "params": "title=$(literal)`value", "reader": "xyz"})
        self.assertIn(str(self.xyz), arguments)
        self.assertIn("title=$(literal)`value", arguments)

    def test_gui_process_runs_the_real_cli(self):
        job = CliProcess(["convert", str(self.xyz), "-o", str(self.output), "--json"])
        try:
            deadline = time.monotonic() + 30
            result = None
            while result is None and time.monotonic() < deadline:
                result = job.poll()
                time.sleep(.03)
            self.assertIsNotNone(result)
            self.assertEqual(result.status.value, "success", result)
            self.assertTrue(self.output.is_dir())
        finally:
            if job.process.poll() is None:
                job.cancel()
                job.process.wait(timeout=30)
            job.close()

    def test_multidataset_interpretation_requires_explicit_gui_selection(self):
        source = ROOT / "examples/user-workflows/inputs/cube/two-datasets.cube"
        args = command_arguments({"command": "convert", "sources": str(source),
                                  "output": str(self.output), "preset": "electron_density",
                                  "unit": "electron_per_cubic_bohr", "dataset_index": ""})
        result = self.cli(*args, success=False)
        self.assertIn("--dataset-index", json.dumps(result))
        self.assertFalse(self.output.exists())

    def test_multidataset_cube_interpretation_and_selected_export(self):
        import numpy
        from cbq_core.model import DatasetStatus, Grid3D
        from chemblender_prepare.core.cube import parse_cube
        source = ROOT / "examples/user-workflows/inputs/cube/two-datasets.cube"
        self.cli("convert", source, "-o", self.output, "--preset", "electron_density",
                 "--unit", "electron_per_cubic_bohr", "--dataset-index", "1")
        project = open_project(self.output)
        try:
            grids = [value for value in project.datasets.values() if isinstance(value, Grid3D)]
            original = next(value for value in grids if value.status is DatasetStatus.AMBIGUOUS)
            resolved = next(value for value in grids if value.status is DatasetStatus.COMPLETE)
            numpy.testing.assert_array_equal(numpy.asarray(resolved.data.values).ravel(), [100, 101, 102, 103])
            self.assertEqual(resolved.origin, original.origin)
            self.assertEqual(resolved.step_vectors, original.step_vectors)
            rejected = self.root / "unselected.cube"
            for flags in ((), ("--preview",)):
                failure = self.cli("export", self.output, "-o", rejected, "--entity", original.id,
                                   "--format", "cube", "--confirm-loss", *flags, success=False)
                self.assertIn("dataset_index.missing", json.dumps(failure))
                self.assertFalse(rejected.exists())
            exported = self.root / "selected.cube"
            self.cli("export", self.output, "-o", exported, "--entity", original.id,
                     "--format", "cube", "--dataset-index", "1", "--confirm-loss")
            reread = parse_cube(exported).datasets[0]
            numpy.testing.assert_array_equal(numpy.asarray(reread.data.values).ravel(), [100, 101, 102, 103])
        finally:
            close_project(project)

    def test_poscar_cli_settings_preserve_scientific_cell_and_require_loss_confirmation(self):
        import numpy
        from chemblender_prepare.core.formats.poscar import parse_poscar
        source = ROOT / "tests/fixtures/poscar/cscl-selective.vasp"
        self.cli("convert", source, "-o", self.output)
        project = open_project(self.output)
        try:
            structure = next(iter(project.structures.values()))
            volume = abs(float(numpy.linalg.det(structure.cell.values)))
            destination = self.root / "POSCAR"
            options = ("export", self.output, "-o", destination, "--entity", structure.id,
                       "--format", "poscar", "--poscar-comment", "explicit export",
                       "--poscar-coordinate-mode", "cartesian", "--poscar-scale-policy", "target_volume",
                       "--poscar-target-volume", str(volume), "--no-poscar-include-selective-dynamics",
                       "--poscar-velocity-mode", "direct")
            preview = self.cli(*options, "--preview")
            self.assertTrue(preview["metadata"]["preview"]["requires_confirmation"])
            self.assertFalse(destination.exists())
            self.cli(*options, success=False)
            self.assertFalse(destination.exists())
            self.cli(*options, "--confirm-loss")
            reparsed = parse_poscar(destination)
            numpy.testing.assert_allclose(reparsed.structures[0].cell.values, structure.cell.values)
            numpy.testing.assert_allclose(reparsed.structures[0].coordinates.values, structure.coordinates.values)
            self.assertEqual(reparsed.structures[0].atomic_numbers, structure.atomic_numbers)
            self.assertFalse(any(d.semantic_role == "selective_dynamics" for d in reparsed.datasets))
            lines = destination.read_text().splitlines()
            self.assertEqual(lines[0], "explicit export")
            self.assertAlmostEqual(float(lines[1]), -volume)
            self.assertIn("Cartesian", lines)
            bad = self.root / "invalid.POSCAR"
            self.cli("export", self.output, "-o", bad, "--entity", structure.id, "--format", "poscar",
                     "--poscar-scale-policy", "target_volume", "--poscar-target-volume", "-1", success=False)
            self.assertFalse(bad.exists())
        finally:
            close_project(project)

    def test_explicit_bond_inference_is_stored_in_cbq(self):
        self.cli("convert", self.xyz, "-o", self.output, "--infer-bonds")
        project = open_project(self.output)
        try:
            structure = next(iter(project.structures.values()))
            self.assertEqual(len(structure.topology_ids), 1)
            topology = project.topologies[structure.topology_ids[0]]
            self.assertEqual(topology.source_kind.value, "distance_inferred")
            self.assertEqual(topology.bond_indices.shape[0], 2)
        finally:
            close_project(project)

    def test_grid_operations_reuse_affine_and_keep_source_package_unchanged(self):
        import numpy
        source = ROOT / "examples/user-workflows/inputs/cube/two-datasets.cube"
        result = self.cli("convert", source, "-o", self.output,
            "--preset", "electron_density", "--unit", "electron_per_cubic_bohr", "--dataset-index", "1")
        entities = result["metadata"]["entities"]
        original = next(item["id"] for item in entities if item["type"] == "Grid3D" and item["status"] == "ambiguous")
        density = next(item["id"] for item in entities if item["type"] == "Grid3D" and item["status"] == "complete")
        interpreted = self.root / "interpreted.cbq"
        self.cli("derive", self.output, "-o", interpreted, "--operation", "grid.resolve_semantics",
            "--input", original, "--parameters", json.dumps({"dataset_index": 0, "preset_id": "electron_density",
            "value_unit": "electron_per_cubic_bohr"}))
        inspected = self.cli("inspect", interpreted)
        other = next(item["id"] for item in inspected["metadata"]["entities"]
                     if item["type"] == "Grid3D" and item["status"] == "complete" and item["id"] != density)
        difference = self.root / "difference.cbq"
        self.cli("derive", interpreted, "-o", difference, "--operation", "grid.difference",
                 "--input", density, "--input", other, "--parameters", '{"chunk_size": 2}')
        project = open_project(difference)
        try:
            grid = next(item for item in project.datasets.values() if item.semantic_role == "difference_density")
            numpy.testing.assert_array_equal(numpy.asarray(grid.data.values).ravel(), [90, 90, 90, 90])
        finally:
            close_project(project)

    @unittest.skipUnless(importlib.util.find_spec("gemmi"), "Gemmi format extra required")
    def test_cif_contains_numeric_symmetry_and_exports(self):
        import numpy
        source = ROOT / "tests/fixtures/cif/cscl.cif"
        result = self.cli("convert", source, "-o", self.output)
        project = open_project(self.output)
        try:
            structure = next(iter(project.structures.values()))
            self.assertIsNotNone(structure.periodic.symmetry_rotations)
            self.assertTrue(numpy.isfinite(structure.periodic.symmetry_translations.values).all())
            self.assertEqual(len(structure.periodic.symmetry_operations), structure.periodic.symmetry_rotations.shape[0])
            for format_name, mode in (("cif", ["--cif-mode", "preserve"]), ("poscar", [])):
                target = self.root / ("exported." + format_name)
                self.cli("export", self.output, "-o", target, "--entity", structure.id,
                         "--format", format_name, "--confirm-loss", *mode)
                self.assertTrue(target.stat().st_size)
            self.assertEqual(result["metadata"]["schema_version"], "1.1")
        finally:
            close_project(project)

    def test_json_envelopes_roundtrip_through_public_export(self):
        for format_name, filename, kind in (("cjson", "cjson/water-results.cjson", "CJSONEnvelope"),
                                           ("qcschema", "qcschema/atomic-result.json", "QCSchemaEnvelope")):
            with self.subTest(format=format_name):
                source = ROOT / "examples/user-workflows/inputs" / filename
                output = self.root / (format_name + ".cbq")
                result = self.cli("convert", source, "-o", output)
                entity = next(value["id"] for value in result["metadata"]["entities"] if value["type"] == kind)
                target = self.root / ("exported." + format_name)
                self.cli("export", output, "-o", target, "--entity", entity, "--format", format_name, "--confirm-loss")
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), json.loads(source.read_text(encoding="utf-8")))

    @unittest.skipUnless(importlib.util.find_spec("rdkit"), "RDKit format extra required")
    def test_native_molecular_exports_use_preserved_file_context(self):
        cases = (("mol", "mol/water-v2000.mol"), ("sdf", "sdf/mixed-properties.sdf"),
                 ("mol2", "mol2/substructure.mol2"), ("pdb", "pdb/multimodel.pdb"),
                 ("pqr", "pqr/with-chain.pqr"), ("smiles", "smiles/ethanol.smi"),
                 ("extxyz", "xyz/water.xyz"))
        for format_name, relative in cases:
            with self.subTest(format=format_name):
                source = self.xyz if format_name == "extxyz" else ROOT / "examples/user-workflows/inputs" / relative
                output = self.root / (format_name + ".cbq")
                result = self.cli("convert", source, "-o", output)
                entity = next(value["id"] for value in result["metadata"]["entities"] if value["type"] == "Structure")
                target = self.root / ("exported." + ("smi" if format_name == "smiles" else format_name))
                self.cli("export", output, "-o", target, "--entity", entity, "--format", format_name, "--confirm-loss")
                self.assertGreater(target.stat().st_size, 0)
                self.cli("convert", target, "-o", self.root / (format_name + "-roundtrip.cbq"))

    def test_tk_changed_inputs_invalidate_export_confirmation_without_starting_work(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except (ImportError, tk.TclError) as error:
            self.skipTest(str(error))
        root.withdraw()
        window = PrepareWindow(root)
        try:
            window.values["command"].set("export")
            window.values["format"].set("poscar")
            root.update()
            self.assertLessEqual(root.winfo_reqheight(), 850)
            for name, value in window.values.items():
                with self.subTest(field=name):
                    window.confirm_loss.set(True)
                    window.preview.set(False)
                    value.set(value.get())
                    self.assertFalse(window.confirm_loss.get())
                    self.assertTrue(window.preview.get())
                    self.assertIsNone(window.job)
            for widget in (window.sources, *window.text_values.values()):
                window.confirm_loss.set(True)
                window.preview.set(False)
                widget.insert("1.0", "changed input")
                root.update()
                self.assertFalse(window.confirm_loss.get())
                self.assertTrue(window.preview.get())
                self.assertIsNone(window.job)
            window.confirm_loss.set(True)
            root.update()
            self.assertTrue(window.confirm_loss.get())
        finally:
            root.destroy()

    def test_tk_inline_smiles_runs_external_child(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except (ImportError, tk.TclError) as error:
            self.skipTest(str(error))
        root.withdraw()
        window = PrepareWindow(root)
        try:
            window.values["source_kind"].set("smiles")
            window.values["smiles_text"].set("CO")
            window.values["validation-mode"].set("strict")
            window.values["output"].set(str(self.output))
            root.update()
            self.assertTrue(window.field_widgets["smiles_text"][1].grid_info())
            self.assertFalse(window.field_widgets["reader"][1].grid_info())
            self.assertIsNone(window.job)
            window.start()
            deadline = time.monotonic() + 30
            while window.job is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            self.assertIsNone(window.job)
            self.assertIn("smiles.planar_2d_generated", window.report.get("1.0", "end"))
            project = open_project(self.output, verify_arrays=True)
            try:
                self.assertEqual(next(iter(project.source_revisions.values())).locator, "inline:smiles")
            finally:
                close_project(project)
        finally:
            if window.job is not None:
                window.job.cancel()
                window.job.process.wait(timeout=30)
                window.job.close()
            root.destroy()

    def test_tk_window_invokes_cli_and_displays_result(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except (ImportError, tk.TclError) as error:
            self.skipTest(str(error))
        root.withdraw()
        window = PrepareWindow(root)
        try:
            selector = window.field_widgets["validation-mode"][1]
            self.assertEqual(tuple(selector["values"]), ("strict", "balanced", "maximum"))
            self.assertEqual(str(selector["state"]), "readonly")
            self.assertEqual(window.values["validation-mode"].get(), "balanced")
            window.values["validation-mode"].set("maximum")
            window.sources.insert("1.0", str(self.xyz))
            window.values["output"].set(str(self.output))
            window.start()
            deadline = time.monotonic() + 30
            while window.job is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            self.assertIsNone(window.job)
            self.assertTrue(self.output.is_dir())
            self.assertIn('"status": "success"', window.report.get("1.0", "end"))
        finally:
            if window.job is not None:
                window.job.cancel()
                window.job.process.wait(timeout=30)
                window.job.close()
            root.destroy()

    @unittest.skipUnless(importlib.util.find_spec("iodata") and importlib.util.find_spec("gbasis"), "IOData/GBasis environment required")
    def test_real_fchk_mo_derive_uses_existing_numerics(self):
        import numpy
        source = ROOT / "examples/scientific-visualization/inputs/wavefunction/water_sto3g_hf_g03.fchk"
        converted = self.cli("convert", source, "-o", self.output, "--reader", "iodata_wavefunction")
        entities = converted["metadata"]["entities"]
        references = [next(value["id"] for value in entities if value["type"] == kind)
                      for kind in ("Structure", "BasisSet", "OrbitalSet")]
        project = open_project(self.output)
        try:
            orbitals = next(iter(project.orbital_sets.values()))
            channel = orbitals.channels[0].label
        finally:
            close_project(project)
        parameters = {"origin": [-1.0, -1.0, -1.0], "step_vectors": [[.5, 0, 0], [0, .5, 0], [0, 0, .5]],
                      "shape": [5, 5, 5], "channel": channel, "orbital_index": 0, "chunk_size": 17}
        destination = self.root / "orbital.cbq"
        arguments = ["derive", self.output, "-o", destination, "--operation", "wavefunction.mo_grid", "--parameters", json.dumps(parameters)]
        for value in references:
            arguments.extend(("--input", value))
        result = self.cli(*arguments)
        project = open_project(destination)
        try:
            grid = next(value for value in project.datasets.values() if value.semantic_role == "molecular_orbital")
            self.assertEqual(grid.data.shape, (5, 5, 5))
            self.assertTrue(numpy.isfinite(numpy.asarray(grid.data.values)).all())
            self.assertGreater(float(numpy.abs(numpy.asarray(grid.data.values)).max()), 0)
            self.assertIn(str(grid.id), result["metadata"]["derived_outputs"])
        finally:
            close_project(project)

        charges = next(value["id"] for value in entities if value.get("semantic_role") == "nuclear_charge")
        esp_parameters = {"origin": [3., 2., 1.],
            "step_vectors": [[.1, 0, 0], [0, .1, 0], [0, 0, .1]],
            "shape": [3, 1, 1], "chunk_size": 2, "density_level": "scf"}
        esp_destination = self.root / "esp.cbq"
        arguments = ["derive", self.output, "-o", esp_destination,
            "--operation", "wavefunction.esp_from_orbitals_grid", "--parameters", json.dumps(esp_parameters)]
        for value in (*references, charges):
            arguments.extend(("--input", value))
        result = self.cli(*arguments)
        project = open_project(esp_destination, verify_arrays=True)
        try:
            grid = next(value for value in project.datasets.values() if value.semantic_role == "electrostatic_potential")
            # Imported and orbital-derived SCF matrices differ by FCHK rounding.
            self.assertAlmostEqual(float(grid.data.values[0, 0, 0]), .0297531414634, places=7)
            self.assertEqual(str(grid.structure_id), references[0])
            self.assertIn(str(grid.id), result["metadata"]["derived_outputs"])
            self.assertTrue(set(result["metadata"]["derived_outputs"]) & {str(v) for v in project.density_matrices})
        finally:
            close_project(project)



if __name__ == "__main__":
    unittest.main()
