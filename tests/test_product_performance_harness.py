import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender" / "scripts" / "benchmark_230_product.py"


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "benchmark_230_product", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductPerformanceHarnessTests(unittest.TestCase):
    def test_orchestrator_initializes_checkout_imports_before_any_work(self):
        harness = load_harness()

        class Initialized(Exception):
            pass

        with patch.object(
            harness,
            "_base_harness",
            side_effect=Initialized("initialized"),
        ):
            with self.assertRaisesRegex(Initialized, "initialized"):
                harness.run_product_qualification(SimpleNamespace())

    def test_product_registry_is_exact_and_uses_approved_measurements(self):
        harness = load_harness()

        self.assertEqual(
            tuple(harness.PRODUCT_CASES),
            (
                "extension_enable",
                "preflight_feedback",
                "default_view",
                "vdb_cache",
                "trajectory_frame",
                "browser_projection_filter",
            ),
        )
        for name, case in harness.PRODUCT_CASES.items():
            expected_cache = "hot" if name == "trajectory_frame" else "cold"
            self.assertEqual(case.cache_state, expected_cache)
            self.assertEqual(case.measurement, f"{expected_cache}_p95")
            self.assertEqual(case.execution, "blender")
            self.assertTrue(case.boundary)

    def test_worker_command_installs_the_exact_package_in_blender(self):
        harness = load_harness()
        command = harness.worker_command(
            Path("C:/Blender/blender.exe"),
            SCRIPT,
            case_name="default_view",
            package=Path("C:/artifact/chemblender-2.3.0-rc.1.zip"),
            package_sha256="a" * 64,
            profile=Path("C:/profiles/default-view-0"),
            workspace=Path("C:/evidence/inputs"),
            sample_index=0,
        )

        self.assertEqual(command[:3], [
            "C:\\Blender\\blender.exe",
            "--background",
            "--factory-startup",
        ])
        self.assertIn("--python-exit-code", command)
        self.assertIn("--python", command)
        self.assertIn(str(SCRIPT), command)
        self.assertEqual(command[command.index("--") + 1], "worker")
        self.assertEqual(command[command.index("--case") + 1], "default_view")
        self.assertEqual(
            command[command.index("--package-sha256") + 1], "a" * 64
        )
        self.assertEqual(command[command.index("--sample-index") + 1], "0")

    def test_worker_marker_is_bound_to_case_package_profile_and_checkout(self):
        harness = load_harness()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            installed = profile / "extensions" / "user_default" / "chemblender"
            installed.mkdir(parents=True)
            checkout = root / "checkout"
            checkout.mkdir()
            document = {
                "assertions": {
                    "installed_package": True,
                    "product_boundary": True,
                },
                "blender_version": "5.1.2",
                "case": "vdb_cache",
                "elapsed_seconds": 0.25,
                "gemmi_version": "0.7.5",
                "installed_origin": str(installed / "__init__.py"),
                "package_sha256": "b" * 64,
                "python_executable": "C:/Blender/blender.exe",
                "python_implementation": "CPython",
                "python_version": "3.13.9",
                "rdkit_version": "2026.03.3",
                "sample_index": 2,
            }
            stdout = "noise\n" + harness.WORKER_MARKER + json.dumps(document) + "\n"

            parsed = harness.parse_worker_output(
                stdout,
                expected_case="vdb_cache",
                expected_sample_index=2,
                expected_package_sha256="b" * 64,
                profile=profile,
                checkout_root=checkout,
            )
            self.assertEqual(parsed, document)

            wrong_case = dict(document, case="default_view")
            with self.assertRaisesRegex(ValueError, "case"):
                harness.parse_worker_output(
                    harness.WORKER_MARKER + json.dumps(wrong_case),
                    expected_case="vdb_cache",
                    expected_sample_index=2,
                    expected_package_sha256="b" * 64,
                    profile=profile,
                    checkout_root=checkout,
                )
            source_import = dict(
                document,
                installed_origin=str(checkout / "ChemBlender" / "__init__.py"),
            )
            with self.assertRaisesRegex(ValueError, "installed origin"):
                harness.parse_worker_output(
                    harness.WORKER_MARKER + json.dumps(source_import),
                    expected_case="vdb_cache",
                    expected_sample_index=2,
                    expected_package_sha256="b" * 64,
                    profile=profile,
                    checkout_root=checkout,
                )

    def test_case_result_requires_five_finite_samples(self):
        harness = load_harness()
        with self.assertRaisesRegex(ValueError, "five"):
            harness.case_result("extension_enable", [0.1] * 4)

        result = harness.case_result(
            "trajectory_frame", [0.011, 0.012, 0.013, 0.014, 0.015]
        )
        self.assertEqual(result["measurement"], "hot_p95")
        self.assertEqual(result["cache_state"], "hot")
        self.assertEqual(result["sample_seconds"], [
            0.011,
            0.012,
            0.013,
            0.014,
            0.015,
        ])
        self.assertEqual(result["cold_seconds"], 0.011)
        self.assertEqual(result["hot_seconds"], 0.013)
        self.assertEqual(result["p95_seconds"], 0.015)

    def test_report_is_qualified_and_bound_to_clean_source_and_runtime(self):
        harness = load_harness()
        samples = {
            name: [0.01 + index * 0.001 for index in range(5)]
            for name in harness.PRODUCT_CASES
        }
        runtime = {
            "blender_version": "5.1.2",
            "gemmi_version": "0.7.5",
            "python_executable": "C:/Blender/blender.exe",
            "python_implementation": "CPython",
            "python_version": "3.13.9",
            "rdkit_version": "2026.03.3",
        }

        report = harness.build_report(
            samples,
            runtime=runtime,
            source_commit="c" * 40,
            source_dirty=False,
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["sample_count"], 5)
        self.assertEqual(report["scale"], "interactive")
        self.assertEqual(report["source_commit"], "c" * 40)
        self.assertFalse(report["source_dirty"])
        self.assertEqual(len(report["cases"]), 6)

        with self.assertRaisesRegex(ValueError, "clean source"):
            harness.build_report(
                samples,
                runtime=runtime,
                source_commit="c" * 40,
                source_dirty=True,
            )

    def test_sample_profiles_are_unique_and_evidence_records_raw_streams(self):
        harness = load_harness()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = {
                harness.sample_profile(root / "profiles", "default_view", index)
                for index in range(5)
            }
            self.assertEqual(len(profiles), 5)
            self.assertTrue(all(path.parent.name == "default_view" for path in profiles))

            command = ["blender.exe", "--background"]
            record = harness.write_process_evidence(
                root / "raw",
                label="default-view-000",
                command=command,
                environment={"BLENDER_USER_RESOURCES": "C:/profiles/0"},
                returncode=0,
                stdout="worker stdout\n",
                stderr="worker stderr\n",
                duration_seconds=1.25,
            )
            self.assertEqual(record["command"], command)
            self.assertEqual(record["returncode"], 0)
            self.assertEqual(record["duration_seconds"], 1.25)
            self.assertEqual(
                (root / "raw" / record["stdout_path"]).read_text(
                    encoding="utf-8"
                ),
                "worker stdout\n",
            )
            self.assertEqual(
                (root / "raw" / record["stderr_path"]).read_text(
                    encoding="utf-8"
                ),
                "worker stderr\n",
            )

    def test_prepared_profile_is_bound_to_exact_package_before_cold_launch(self):
        harness = load_harness()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "short-profile"
            origin = (
                profile
                / "extensions"
                / "user_default"
                / "chemblender"
                / "__init__.py"
            )
            origin.parent.mkdir(parents=True)
            origin.write_text("", encoding="utf-8")

            harness.write_prepared_profile_marker(
                profile,
                package_sha256="d" * 64,
                installed_origin=origin,
            )
            self.assertEqual(
                harness.verify_prepared_profile(
                    profile,
                    package_sha256="d" * 64,
                ),
                origin.resolve(),
            )
            with self.assertRaisesRegex(ValueError, "package hash"):
                harness.verify_prepared_profile(
                    profile,
                    package_sha256="e" * 64,
                )

    def test_prepare_process_creates_profile_and_measurement_reuses_it(self):
        harness = load_harness()
        with TemporaryDirectory() as directory:
            profile = Path(directory) / "profile"
            harness.ensure_process_profile(profile, "prepare_profile")
            self.assertTrue((profile / "temp").is_dir())
            harness.ensure_process_profile(profile, "default_view")
            with self.assertRaises(FileExistsError):
                harness.ensure_process_profile(profile, "prepare_profile")

    def test_browser_preparation_uses_product_reader_staging(self):
        harness = load_harness()
        events = []
        batch = SimpleNamespace(molecular_records=tuple(range(10_000)))

        class Project:
            molecular_records = ()

            def commit(self, candidate):
                self.molecular_records = candidate.molecular_records
                events.append("commit")

        project = Project()
        session = SimpleNamespace(project=project)
        staging = SimpleNamespace(result=lambda batch_id: batch)

        def reject_direct_parse(_source):
            raise AssertionError("browser preparation bypassed reader staging")

        def save_project(destination, candidate):
            self.assertIs(candidate, project)
            destination.mkdir()
            events.append("save")

        modules = {
            "core": SimpleNamespace(
                close_session=lambda candidate: events.append("close"),
                create_session=lambda **_kwargs: session,
                parse_sdf=reject_direct_parse,
                save_project=save_project,
            ),
            "core.import_pipeline.request": SimpleNamespace(
                ImportRequest=lambda **kwargs: SimpleNamespace(**kwargs),
                ImportSource=lambda path: path,
            ),
            "reader_api.import_pipeline_bridge": SimpleNamespace(
                preflight_reader_plugins=lambda *_args, **_kwargs: SimpleNamespace(
                    staged_batch_ids=("batch",)
                )
            ),
            "reader_api.registry": SimpleNamespace(
                builtin_reader_plugin_registry=lambda: object()
            ),
            "ui.properties": SimpleNamespace(
                clear_quick_import_state=lambda candidate: events.append("clear"),
                create_quick_import_staging=lambda candidate: staging,
            ),
        }

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "records.sdf").write_bytes(b"fixture")
            with patch.object(
                harness,
                "_product_module",
                side_effect=lambda name: modules[name],
            ):
                _elapsed, assertions = harness._prepare_browser_project(
                    None, workspace, -1
                )

        self.assertEqual(events, ["commit", "save", "clear", "close"])
        self.assertTrue(assertions["sidecar_written"])
        self.assertTrue(assertions["ten_thousand_sdf_records"])

    def test_default_view_uses_staged_source_revision(self):
        harness = load_harness()
        events = []
        revision = object()
        batch = SimpleNamespace(source_revisions=(revision,))

        class Project:
            structures = {}
            datasets = {}

            def commit(self, candidate):
                if candidate is not batch:
                    raise AssertionError("unexpected staged batch")
                events.append("commit")

        project = Project()
        session = SimpleNamespace(project=project)
        staging = SimpleNamespace(result=lambda batch_id: batch)
        obj = SimpleNamespace(
            name="Structure View",
            type="MESH",
            data=SimpleNamespace(vertices=tuple(range(50_000))),
        )

        def reject_direct_parse(_source):
            raise AssertionError("default view bypassed reader staging")

        modules = {
            "core": SimpleNamespace(
                builtin_scene_presets=lambda: {"preset": object()},
                close_session=lambda candidate: events.append("close"),
                create_session=lambda **_kwargs: session,
                parse_xyz=reject_direct_parse,
                plan_scene_preset=lambda *_args: object(),
            ),
            "core.import_pipeline.request": SimpleNamespace(
                ImportRequest=lambda **kwargs: SimpleNamespace(**kwargs),
                ImportSource=lambda path: path,
            ),
            "reader_api.import_pipeline_bridge": SimpleNamespace(
                preflight_reader_plugins=lambda *_args, **_kwargs: SimpleNamespace(
                    staged_batch_ids=("batch",)
                )
            ),
            "reader_api.registry": SimpleNamespace(
                builtin_reader_plugin_registry=lambda: object()
            ),
            "scene_preset_view": SimpleNamespace(
                _remove_objects=lambda objects: events.append("remove"),
                apply_scene_preset=lambda *_args: (obj,),
            ),
            "ui.default_views": SimpleNamespace(
                plan_default_view=lambda candidate, *_args: SimpleNamespace(
                    preset_id="preset", bindings=(), settings=()
                )
            ),
            "ui.properties": SimpleNamespace(
                clear_quick_import_state=lambda candidate: events.append("clear"),
                create_quick_import_staging=lambda candidate: staging,
            ),
        }
        bpy = SimpleNamespace(
            context=SimpleNamespace(
                view_layer=SimpleNamespace(update=lambda: events.append("update"))
            ),
            data=SimpleNamespace(objects={obj.name: obj}),
        )

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "structure.xyz").write_bytes(b"fixture")
            with patch.object(
                harness,
                "_product_module",
                side_effect=lambda name: modules[name],
            ):
                _elapsed, assertions = harness._measure_default_view(
                    bpy, workspace, 0
                )

        self.assertEqual(
            events,
            ["commit", "update", "remove", "clear", "close"],
        )
        self.assertTrue(assertions["structure_scene_preset"])


if __name__ == "__main__":
    unittest.main()
