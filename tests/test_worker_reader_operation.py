import ast
import hashlib
import os
import shutil
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    CapabilitySupport,
    ImportBatch,
    MolecularRecord,
    ParserReport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
    Structure,
)
from ChemBlender.core.worker_protocol import (
    WorkerError,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    write_request,
)
from ChemBlender.reader_api import (
    WorkerReaderExecutionError,
    WorkerReaderIntegrityError,
    parse_with_worker,
)
from ChemBlender.reader_api.worker_bridge import (
    _WorkerReaderCancelled,
    _file_sha256,
    _task_file,
)
from ChemBlender.reader_api.canonical_document import (
    read_public_batch_bundle,
    write_public_batch_bundle,
)
from ChemBlender.reader_api.registry import (
    ReaderPluginRegistry,
    _builtin_manifest,
    _builtin_plugin,
)
from worker.runner import default_registry, run_request


REQUEST_ID = UUID("30000000-0000-0000-0000-000000000003")
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
FIXTURE = Path(__file__).parent / "fixtures" / "xyz" / "water.xyz"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reader_request(source_hash, **parameter_changes):
    parameters = {
        "reader_id": "xyz",
        "source_artifact": "source.xyz",
        "source_sha256": source_hash,
        "validation_mode": "balanced",
        "canonical_parameters": {},
    }
    parameters.update(parameter_changes)
    return WorkerRequest(
        request_id=REQUEST_ID,
        project_locator="unused.cbq",
        project_id=PROJECT_ID,
        project_schema_version="0.2",
        operation_id="reader.parse",
        operation_version="0.1",
        inputs=(),
        parameters=parameters,
    )


class WorkerReaderOperationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.xyz"
        shutil.copyfile(FIXTURE, self.source)
        self.request = reader_request(sha256(self.source))
        self.request_path = self.root / "request.json"
        self.result_path = self.root / "result.json"

    def tearDown(self):
        self.temporary.cleanup()

    def run_reader(self, request=None, *, cancel_path=None):
        request = self.request if request is None else request
        write_request(self.request_path, request)
        return run_request(
            self.request_path,
            self.result_path,
            default_registry(),
            cancel_path=cancel_path,
        )

    def test_fixed_reader_operation_round_trips_without_project_sidecar(self):
        result = self.run_reader()

        self.assertIs(result.status, WorkerStatus.SUCCESS)
        self.assertFalse((self.root / self.request.project_locator).exists())
        self.assertEqual(
            set(result.metadata),
            {
                "operation",
                "schema_version",
                "document_path",
                "document_sha256",
                "artifact_sha256",
            },
        )
        self.assertEqual(result.metadata["operation"], "reader.parse@0.1")
        self.assertEqual(result.metadata["schema_version"], "0.1")
        self.assertEqual(
            result.metadata["document_path"],
            "reader-bundle/import-batch.json",
        )
        batch = parse_with_worker(self.request, result, self.root)
        self.assertIs(type(batch), ImportBatch)
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(batch.report.reader_id, "xyz")

    def test_builtin_molecular_record_is_bound_before_worker_validation(self):
        structure_id = UUID("40000000-0000-0000-0000-000000000004")
        record_id = UUID("50000000-0000-0000-0000-000000000005")

        def parse(request):
            structure = Structure(
                id=structure_id,
                revision="structure-r1",
                atomic_numbers=(1,),
                coordinates=ArrayData(
                    numpy.asarray(((0.0, 0.0, 0.0),)),
                    ("atom", "xyz"),
                    "angstrom",
                ),
            )
            record = MolecularRecord(
                id=record_id,
                revision="record-r1",
                source_revision_id=request.source_revision_id,
                record_key="record-0001",
                structure_id=structure.id,
                topology_id=None,
                raw_block=b"record",
                title="record",
                source_record_index=0,
                block_version="V2000",
                writer_name=None,
                writer_version=None,
                ordered_raw_properties=(),
                provenance_ids=(),
            )
            return ImportBatch(
                structures=(structure,),
                molecular_records=(record,),
                report=ParserReport(
                    "synthetic-record",
                    "1",
                    (structure.id, record.id),
                    ("structure",),
                    (),
                ),
            )

        descriptor = ReaderDescriptor(
            reader_id="synthetic-record",
            reader_version="1",
            extensions=(".xyz",),
            capabilities={"structure": CapabilitySupport.SUPPORTED},
            priority=100,
            sniff=lambda path, prefix: SniffResult(
                SniffMatch.EXACT, "fixture"
            ),
            parse=lambda path: ImportBatch(),
            parse_request=parse,
        )
        registry = ReaderPluginRegistry(
            (_builtin_plugin(descriptor, _builtin_manifest((descriptor,))),)
        )

        with patch(
            "worker.reader_operation.builtin_reader_plugin_registry",
            return_value=registry,
        ):
            result = self.run_reader(
                reader_request(
                    sha256(self.source),
                    reader_id=descriptor.reader_id,
                )
            )

        self.assertIs(result.status, WorkerStatus.SUCCESS)
        batch = parse_with_worker(
            reader_request(
                sha256(self.source),
                reader_id=descriptor.reader_id,
            ),
            result,
            self.root,
        )
        self.assertEqual(batch.source_revisions[0].id, REQUEST_ID)
        self.assertEqual(
            batch.molecular_records[0].source_revision_id,
            REQUEST_ID,
        )
        self.assertEqual(
            batch.source_revisions[0].created_entity_ids,
            (structure_id, record_id),
        )

    def test_request_parameters_are_an_exact_whitelist(self):
        for field in ("module", "callable", "shell", "argv", "extra"):
            with self.subTest(field=field):
                result = self.run_reader(
                    reader_request(sha256(self.source), **{field: "unsafe"})
                )
                self.assertIs(result.status, WorkerStatus.ERROR)
                self.assertEqual(result.error.code, "reader_request_invalid")

    def test_source_artifact_must_be_safe_relative_regular_file(self):
        unsafe = (
            "",
            ".",
            "..",
            "../source.xyz",
            "/source.xyz",
            "C:/source.xyz",
            "source.xyz:stream",
            r"folder\source.xyz",
        )
        for value in unsafe:
            with self.subTest(value=value):
                result = self.run_reader(
                    reader_request(
                        sha256(self.source),
                        source_artifact=value,
                    )
                )
                self.assertIs(result.status, WorkerStatus.ERROR)
                self.assertEqual(result.error.code, "reader_request_invalid")

    def test_windows_alias_and_ads_syntax_is_rejected_before_resolution(self):
        folder = self.root / "folder"
        folder.mkdir()
        shutil.copyfile(self.source, folder / "source.xyz")
        unsafe = (
            "source.xyz.",
            "source.xyz ",
            "folder./source.xyz",
            "folder /source.xyz",
            "source.xyz:stream",
            "source.xyz::$DATA",
            "folder:stream/source.xyz",
        )
        for relative in unsafe:
            with self.subTest(relative=relative), self.assertRaisesRegex(
                WorkerReaderIntegrityError,
                "safe relative POSIX path",
            ):
                _task_file(self.root, relative)

    def test_source_hash_reader_and_availability_fail_stably(self):
        cases = (
            (
                reader_request("0" * 64),
                "reader_source_invalid",
            ),
            (
                reader_request(sha256(self.source), reader_id="missing-reader"),
                "reader_not_found",
            ),
        )
        for request, code in cases:
            with self.subTest(code=code):
                result = self.run_reader(request)
                self.assertIs(result.status, WorkerStatus.ERROR)
                self.assertEqual(result.error.code, code)

        from ChemBlender.core.readers import ReaderAvailability

        with patch(
            "ChemBlender.reader_api.registry._builtin_availability",
            return_value=ReaderAvailability(
                False,
                "built_in",
                "dependency_missing",
                "test",
            ),
        ):
            result = self.run_reader()
        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(result.error.code, "reader_unavailable")

    def test_preexisting_cancel_never_publishes_bundle(self):
        cancel = self.root / "cancel"
        cancel.touch()
        result = self.run_reader(cancel_path=cancel)

        self.assertIs(result.status, WorkerStatus.CANCELLED)
        self.assertFalse((self.root / "reader-bundle").exists())
        cancel.unlink()
        self.assertIs(self.run_reader().status, WorkerStatus.SUCCESS)

    def test_source_hash_checks_cancellation_between_chunks(self):
        large = self.root / "large.bin"
        large.write_bytes(b"x" * 200000)
        checks = []

        def cancelled():
            checks.append(None)
            return len(checks) >= 2

        with self.assertRaises(_WorkerReaderCancelled):
            _file_sha256(large, cancelled)
        self.assertGreaterEqual(len(checks), 2)

    def test_cancellation_during_source_hash_stops_before_parse(self):
        cancel = self.root / "cancel"
        original = _file_sha256

        def cancel_on_hash(path, is_cancelled=None):
            cancel.touch()
            return original(path, is_cancelled)

        with patch(
            "worker.reader_operation._file_sha256",
            side_effect=cancel_on_hash,
        ):
            result = self.run_reader(cancel_path=cancel)
        self.assertIs(result.status, WorkerStatus.CANCELLED)
        self.assertFalse((self.root / "reader-bundle").exists())

    def test_cancellation_after_bundle_write_removes_owned_bundle(self):
        cancel = self.root / "cancel"
        original = _file_sha256

        def cancel_on_output_hash(path, is_cancelled=None):
            if "reader-bundle" in Path(path).parts:
                cancel.touch()
            return original(path, is_cancelled)

        with patch(
            "worker.reader_operation._file_sha256",
            side_effect=cancel_on_output_hash,
        ):
            result = self.run_reader(cancel_path=cancel)
        self.assertIs(result.status, WorkerStatus.CANCELLED)
        self.assertFalse((self.root / "reader-bundle").exists())
        cancel.unlink()
        self.assertIs(self.run_reader().status, WorkerStatus.SUCCESS)

    def test_post_write_validation_failure_removes_owned_bundle(self):
        from ChemBlender.reader_api import CanonicalDocumentIntegrityError

        with patch(
            "worker.reader_operation.read_public_batch_bundle",
            side_effect=CanonicalDocumentIntegrityError("tampered"),
        ):
            result = self.run_reader()
        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(result.error.code, "reader_output_invalid")
        self.assertFalse((self.root / "reader-bundle").exists())

    def test_result_publication_failure_removes_bundle_and_allows_retry(self):
        with patch(
            "worker.runner.write_result",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.run_reader()
        self.assertFalse((self.root / "reader-bundle").exists())
        self.assertIs(self.run_reader().status, WorkerStatus.SUCCESS)

    def test_fatal_result_publication_failure_preserves_error_and_cleans_bundle(self):
        with patch(
            "worker.runner.write_result",
            side_effect=SystemExit(9),
        ):
            with self.assertRaises(SystemExit) as raised:
                self.run_reader()

        self.assertEqual(raised.exception.code, 9)
        self.assertFalse((self.root / "reader-bundle").exists())

    def test_failed_public_batch_is_not_published_as_success(self):
        self.source.write_bytes(b"not an XYZ document\n")
        result = self.run_reader(reader_request(sha256(self.source)))

        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(result.error.code, "reader_parse_failed")
        self.assertFalse((self.root / "reader-bundle").exists())

    def test_main_process_rejects_error_cancel_and_wrong_request(self):
        for status, error in (
            (WorkerStatus.ERROR, WorkerError("reader_failed", "failed")),
            (WorkerStatus.CANCELLED, WorkerError("cancelled", "cancelled")),
        ):
            result = WorkerResult(REQUEST_ID, status, error=error)
            with self.subTest(status=status), self.assertRaises(
                WorkerReaderExecutionError
            ):
                parse_with_worker(self.request, result, self.root)

        result = self.run_reader()
        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(
                replace(self.request, request_id=UUID(int=9)),
                result,
                self.root,
            )
        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(
                self.request,
                replace(result, worker_version="stale"),
                self.root,
            )

    def test_main_process_rejects_stale_source_metadata_and_artifacts(self):
        result = self.run_reader()
        document = self.root / result.metadata["document_path"]
        cases = (
            ("source", self.source),
            ("document", document),
        )
        for label, path in cases:
            with self.subTest(label=label):
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                try:
                    with self.assertRaises(WorkerReaderIntegrityError):
                        parse_with_worker(self.request, result, self.root)
                finally:
                    path.write_bytes(original)

        bad_metadata = dict(result.metadata)
        bad_metadata["extra"] = True
        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(
                self.request,
                replace(result, metadata=bad_metadata),
                self.root,
            )

    def test_main_process_rejects_and_cleans_self_consistent_wrong_revision_id(self):
        result = self.run_reader()
        bundle = self.root / "reader-bundle"
        public = read_public_batch_bundle(bundle)
        tampered = replace(
            public,
            source_revisions=(
                replace(public.source_revisions[0], id=uuid4()),
            ),
        )
        document = write_public_batch_bundle(bundle, tampered)
        metadata = dict(result.metadata)
        metadata["document_sha256"] = sha256(document)

        with self.assertRaisesRegex(
            WorkerReaderIntegrityError,
            "revision identity",
        ):
            parse_with_worker(
                self.request,
                replace(result, metadata=metadata),
                self.root,
            )

        self.assertFalse(bundle.exists())

    def test_main_process_rejects_tampered_array_artifact(self):
        result = self.run_reader()
        artifact = next(
            self.root / Path(*Path(name).parts)
            for name in result.artifacts
            if name.endswith(".npy")
        )
        artifact.write_bytes(artifact.read_bytes() + b"\n")

        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(self.request, result, self.root)

    def test_main_process_rejects_noncanonical_or_unlisted_artifacts(self):
        result = self.run_reader()
        bad_metadata = dict(result.metadata)
        bad_hashes = dict(bad_metadata["artifact_sha256"])
        bad_hashes["source.xyz"] = sha256(self.source)
        bad_metadata["artifact_sha256"] = bad_hashes
        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(
                self.request,
                replace(
                    result,
                    artifacts=(*result.artifacts, "source.xyz"),
                    metadata=bad_metadata,
                ),
                self.root,
            )

        artifact = next(
            self.root / Path(*name.split("/"))
            for name in result.artifacts
            if name.endswith(".npy")
        )
        extra = artifact.with_name("f" * 64 + ".npy")
        shutil.copyfile(artifact, extra)
        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(self.request, result, self.root)

    def test_main_process_rejects_duplicate_and_extra_bundle_inventory(self):
        result = self.run_reader()
        duplicate = replace(
            result,
            artifacts=(result.artifacts[0], *result.artifacts),
        )
        with self.assertRaises(WorkerReaderIntegrityError):
            parse_with_worker(self.request, duplicate, self.root)

        bundle = self.root / "reader-bundle"
        cases = (
            bundle / "evil.pkl",
            bundle / "extra" / "evil.txt",
            bundle / "artifacts" / "extra.txt",
        )
        for path in cases:
            with self.subTest(path=path.relative_to(bundle)):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"evil")
                try:
                    with self.assertRaises(WorkerReaderIntegrityError):
                        parse_with_worker(self.request, result, self.root)
                finally:
                    path.unlink()
                    if path.parent.name == "extra":
                        path.parent.rmdir()

    def test_main_process_rejects_bundle_link_or_junction(self):
        result = self.run_reader()
        outside = self.root / "outside"
        outside.mkdir()
        linked = self.root / "reader-bundle" / "linked"
        try:
            os.symlink(outside, linked, target_is_directory=True)
        except OSError as error:
            if os.name != "nt":
                self.skipTest(f"directory link unavailable: {error}")
            probe = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(linked), str(outside)],
                capture_output=True,
                text=True,
            )
            if probe.returncode:
                self.skipTest(f"directory junction unavailable: {probe.stderr}")
        try:
            with self.assertRaises(WorkerReaderIntegrityError):
                parse_with_worker(self.request, result, self.root)
        finally:
            os.rmdir(linked)

    def test_result_hashes_cover_exact_published_files(self):
        result = self.run_reader()
        document_path = result.metadata["document_path"]
        hashes = result.metadata["artifact_sha256"]

        self.assertEqual(set(result.artifacts), {document_path, *hashes})
        self.assertEqual(
            result.metadata["document_sha256"],
            sha256(self.root / Path(*document_path.split("/"))),
        )
        for relative, expected in hashes.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    sha256(self.root / Path(*relative.split("/"))),
                    expected,
                )

    def test_worker_bridge_modules_use_no_dynamic_or_absolute_imports(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "ChemBlender" / "reader_api" / "worker_bridge.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                self.assertFalse(
                    any(
                        name.startswith(("ChemBlender", "bl_ext"))
                        for name in names
                    )
                )


if __name__ == "__main__":
    unittest.main()
