import gc
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import get_args

import numpy

import ChemBlender.reader_api as reader_api
from ChemBlender.core import (
    BiologicalAtomSiteData,
    BiologicalChain,
    BiologicalHierarchy,
    BiologicalModel,
    BiologicalResidue,
    ChemicalAnnotation,
    ExternalReference,
    FrameSet,
    QCProject,
    builtin_reader_descriptors,
    reader_capability_document,
)
from ChemBlender.core.cjson_adapter import export_cjson, parse_cjson
from ChemBlender.core.exporters import (
    mol2_export_readiness,
    pdb_export_readiness,
    pqr_export_readiness,
)
from ChemBlender.core.formats.mol2 import parse_mol2
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.core.import_pipeline.parse import stage_import_batch
from ChemBlender.core.import_pipeline.request import ImportSource, ValidationMode
from ChemBlender.core.readers import READER_API_VERSION, ReaderNotFoundError
from ChemBlender.core.sidecar import close_project, open_project, save_project
from ChemBlender.reader_api.conformance import run_reader_conformance_v1
from ChemBlender.reader_api.registry import ReaderPluginRegistry
from tests.test_pdb_reader import atom_line
from tests.test_reader_conformance_v1 import FIXTURE as EXAMPLE_FIXTURE
from tests.test_reader_conformance_v1 import example_case


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
MATRIX = ROOT / "docs" / "quantum-visualization" / "reader-capability-matrix.json"
EXAMPLE = ROOT / "examples" / "reader-extension"
BENCHMARK = ROOT / "ChemBlender" / "scripts" / "benchmark_exchange.py"
WAVE3_READERS = ("cjson", "mol2", "pdb", "pqr")
VENDOR_ROOTS = frozenset(
    {"Bio", "ase", "gemmi", "openbabel", "pymatgen", "rdkit"}
)
EXCHANGE_TYPES = (
    BiologicalAtomSiteData,
    BiologicalChain,
    BiologicalHierarchy,
    BiologicalModel,
    BiologicalResidue,
    ChemicalAnnotation,
    ExternalReference,
)


def _stage_cjson(path):
    raw = path.read_bytes()
    return stage_import_batch(
        source=ImportSource(path),
        validation_mode=ValidationMode.BALANCED,
        content_hash=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        plugin_id="chemblender.builtin",
        reader_id="cjson",
        reader_version="0.1.0",
        api_version=READER_API_VERSION,
        parsed_batch=parse_cjson(path),
    )


def _vendor_types(value, seen=None):
    seen = set() if seen is None else seen
    identity = id(value)
    if identity in seen:
        return set()
    seen.add(identity)
    root = type(value).__module__.partition(".")[0]
    found = {type(value)} if root in VENDOR_ROOTS else set()
    if is_dataclass(value):
        for field in fields(value):
            found.update(_vendor_types(getattr(value, field.name), seen))
    elif isinstance(value, Mapping):
        for key, item in value.items():
            found.update(_vendor_types(key, seen))
            found.update(_vendor_types(item, seen))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_vendor_types(item, seen))
    return found


class Wave3ExchangeQualificationTests(unittest.TestCase):
    def test_exchange_benchmark_reports_native_parse_and_preview_metrics(self):
        spec = importlib.util.spec_from_file_location(
            "benchmark_exchange",
            BENCHMARK,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        report = module.benchmark_exchange(
            atom_count=4,
            preview_atom_count=3,
            samples=5,
        )

        self.assertEqual(report["benchmark"], "chemblender-wave3-exchange-v1")
        self.assertEqual(
            set(report["metrics"]),
            {
                "mol2_parse",
                "pdb_parse",
                "pqr_parse",
                "cjson_parse",
                "preview_projection",
            },
        )
        for name, metric in report["metrics"].items():
            with self.subTest(metric=name):
                self.assertEqual(metric["status"], "Passed")
                self.assertEqual(metric["sample_count"], 5)
                self.assertGreaterEqual(
                    metric["p95_seconds"],
                    metric["median_seconds"],
                )
                self.assertGreater(metric["peak_bytes"], 0)
                self.assertGreater(metric["source_bytes"], 0)
                self.assertGreater(metric["atom_count"], 0)
                self.assertFalse(metric["draw_path"])
        self.assertEqual(report["warmup_count"], 1)
        self.assertEqual(
            report["metrics"]["preview_projection"]["blender_rna_projection"],
            "Not Run",
        )
        self.assertNotIn("bpy", sys.modules)
        self.assertIn("numpy_version", report["environment"])

    def test_exchange_benchmark_cli_emits_canonical_json(self):
        completed = subprocess.run(
            (
                sys.executable,
                BENCHMARK,
                "--atoms",
                "4",
                "--preview-atoms",
                "3",
                "--samples",
                "5",
            ),
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = json.loads(completed.stdout)
        self.assertFalse(completed.stdout.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(completed.stdout.endswith(b"\n"))
        self.assertFalse(completed.stdout.endswith(b"\n\n"))
        self.assertNotIn(b"\r\n", completed.stdout)
        self.assertEqual(
            completed.stdout,
            (
                json.dumps(
                    document,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        )

    def test_capability_public_model_and_fresh_import_boundaries(self):
        recorded = {
            row["reader_id"]: row
            for row in json.loads(MATRIX.read_text(encoding="utf-8"))["readers"]
            if row["reader_id"] in WAVE3_READERS
        }
        live = {
            row["reader_id"]: row
            for row in reader_capability_document(builtin_reader_descriptors())[
                "readers"
            ]
            if row["reader_id"] in WAVE3_READERS
        }
        self.assertEqual(recorded, live)
        self.assertEqual(set(live), set(WAVE3_READERS))

        for model_type in EXCHANGE_TYPES:
            with self.subTest(model=model_type.__name__):
                self.assertTrue(
                    model_type.__module__.startswith("ChemBlender.core.model.")
                )
                self.assertFalse(
                    any(
                        getattr(value, "__module__", "").partition(".")[0]
                        in VENDOR_ROOTS
                        for field in fields(model_type)
                        for value in (field.type, *get_args(field.type))
                    )
                )

        script = """
import json
import sys
import ChemBlender.core
import ChemBlender.reader_api
blocked = {"Bio", "ase", "gemmi", "openbabel", "pymatgen", "rdkit"}
roots = {name.partition(".")[0] for name in sys.modules}
print(json.dumps(sorted(blocked & roots)))
"""
        environment = os.environ.copy()
        environment["PYTHONNOUSERSITE"] = "1"
        completed = subprocess.run(
            (sys.executable, "-c", script),
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), [])

    def test_fixed_exchange_fixtures_survive_schema_1_sidecar_round_trip(self):
        mol2_expectations = {
            "small": ("Complete", ()),
            "aromatic": ("Partial", ("dataset.partial_charge",)),
            "substructure": ("Complete", ()),
            "multi": (
                "Partial",
                (
                    "dataset.partial_charge",
                    "dataset.substructure_id",
                    "dataset.substructure_name",
                ),
            ),
        }
        with TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            cryst1 = temporary / "cryst1.pdb"
            cryst1.write_bytes(
                (FIXTURES / "pdb" / "cryst1.pdb").read_bytes()
                + atom_line(1, b" C1 ", x=1.0)
                + b"\n"
            )
            cases = [
                *(
                    (
                        f"mol2-{name}",
                        parse_mol2(FIXTURES / "mol2" / f"{name}.mol2"),
                        mol2_export_readiness,
                        mol2_expectations[name],
                    )
                    for name in mol2_expectations
                ),
                *(
                    (
                        f"pdb-{name}",
                        parse_pdb(
                            cryst1
                            if name == "cryst1"
                            else FIXTURES / "pdb" / f"{name}.pdb"
                        ),
                        pdb_export_readiness,
                        ("Ready", ()),
                    )
                    for name in (
                        "atom-hetatm",
                        "altloc",
                        "conect",
                        "cryst1",
                        "multimodel",
                    )
                ),
                *(
                    (
                        f"pqr-{name}",
                        parse_pqr(FIXTURES / "pqr" / f"{name}.pqr"),
                        pqr_export_readiness,
                        ("Ready", ()),
                    )
                    for name in ("with-chain", "no-chain", "padded")
                ),
                (
                    "cjson-water-results",
                    _stage_cjson(FIXTURES / "cjson" / "water-results.cjson"),
                    None,
                    None,
                ),
            ]

            for name, batch, readiness, expected in cases:
                with self.subTest(case=name):
                    self.assertEqual(_vendor_types(batch), set())
                    if readiness is not None:
                        report = readiness(batch)
                        detail = getattr(
                            report,
                            "missing_fields",
                            getattr(report, "tokens", ()),
                        )
                        self.assertEqual((report.status.value, detail), expected)

                    project = QCProject(batch.sources[0].id, "1.0")
                    project.commit(batch)
                    first = save_project(temporary / f"{name}-first.cbq", project)
                    first_document = json.loads(
                        (first / "manifest.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(first_document["manifest_version"], "1.0")
                    self.assertEqual(first_document["project_schema_version"], "1.0")

                    restored = open_project(first)
                    try:
                        self.assertEqual(restored.schema_version, "1.0")
                        self.assertEqual(_vendor_types(restored), set())
                        second = save_project(
                            temporary / f"{name}-second.cbq",
                            restored,
                        )
                    finally:
                        close_project(restored)
                    second_document = json.loads(
                        (second / "manifest.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        first_document["project"],
                        second_document["project"],
                    )

            cjson = cases[-1][1]
            destination = temporary / "qualified-export.cjson"
            report = export_cjson(
                cjson.cjson_envelopes[0],
                destination,
                max_inline_bytes=1024,
            )
            self.assertTrue(report.written)
            reparsed = parse_cjson(destination)
            numpy.testing.assert_array_equal(
                cjson.structures[0].atomic_numbers,
                reparsed.structures[0].atomic_numbers,
            )
            numpy.testing.assert_allclose(
                cjson.structures[0].coordinates.values,
                reparsed.structures[0].coordinates.values,
            )
            numpy.testing.assert_array_equal(
                cjson.topologies[0].bond_indices.values,
                reparsed.topologies[0].bond_indices.values,
            )
            numpy.testing.assert_array_equal(
                cjson.topologies[0].bond_orders.values,
                reparsed.topologies[0].bond_orders.values,
            )
            self.assertEqual(
                {value.semantic_role for value in cjson.datasets},
                {value.semantic_role for value in reparsed.datasets},
            )
            left_frames = next(
                value for value in cjson.datasets if isinstance(value, FrameSet)
            )
            right_frames = next(
                value for value in reparsed.datasets if isinstance(value, FrameSet)
            )
            numpy.testing.assert_allclose(
                left_frames.data.values,
                right_frames.data.values,
            )

    def test_required_builtin_and_example_reader_conformance_pass(self):
        builtins = subprocess.run(
            (
                sys.executable,
                "-m",
                "unittest",
                (
                    "tests.test_reader_conformance_v1."
                    "ReaderConformanceV1Tests."
                    "test_wave1_to_wave3_builtin_matrix_has_no_required_skip"
                ),
                "-v",
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(builtins.returncode, 0, builtins.stdout + builtins.stderr)

        example = run_reader_conformance_v1((example_case(),))
        self.assertTrue(example["passed"], example)
        self.assertEqual(example["summary"], {"fail": 0, "pass": 1, "skip": 0})

    def test_example_sidecar_opens_without_plugin_and_reparse_is_unavailable(self):
        with TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            business_module = temporary / "reader.py"
            shutil.copy2(EXAMPLE / "reader.py", business_module)
            module_name = "_chemblender_wave3_qualification_reader"
            spec = importlib.util.spec_from_file_location(module_name, business_module)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
                plugin = module.create_plugin(reader_api)
                staging = temporary / "staging"
                staging.mkdir()
                request = reader_api.ParseRequest(
                    EXAMPLE_FIXTURE,
                    hashlib.sha256(EXAMPLE_FIXTURE.read_bytes()).hexdigest(),
                    "balanced",
                    {},
                    staging,
                    lambda _event: None,
                    lambda: False,
                )
                batch = reader_api.internal_batch_from_public(plugin.parse(request))
                project = QCProject(batch.sources[0].id, "1.0")
                project.commit(batch)
                sidecar = save_project(temporary / "example.cbq", project)
            finally:
                sys.modules.pop(module_name, None)

            del module, plugin, batch, project
            gc.collect()
            business_module.unlink()
            self.assertFalse(business_module.exists())
            self.assertNotIn(module_name, sys.modules)

            restored = open_project(sidecar)
            try:
                structure = next(iter(restored.structures.values()))
                self.assertEqual(structure.atomic_numbers, (8, 1, 1))
                revision = next(iter(restored.source_revisions.values()))
                self.assertEqual(revision.reader_id, "simplecoords")
            finally:
                close_project(restored)

            request = reader_api.SniffRequest(
                EXAMPLE_FIXTURE,
                EXAMPLE_FIXTURE.read_bytes(),
            )
            with self.assertRaises(ReaderNotFoundError) as caught:
                ReaderPluginRegistry().select(request)
            self.assertEqual(str(caught.exception), str(EXAMPLE_FIXTURE.resolve()))


if __name__ == "__main__":
    unittest.main()
