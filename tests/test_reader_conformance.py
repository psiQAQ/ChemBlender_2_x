import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from uuid import uuid4

from ChemBlender.core import CapabilitySupport, ImportBatch
from ChemBlender.core.import_pipeline import ImportSource, ValidationMode
from ChemBlender.core.import_pipeline.parse import staged_reader_batch
from ChemBlender.core.model.sources import source_parse_identity
from ChemBlender.reader_api import (
    CIFEnvelope,
    ExecutionMode,
    IssueKind,
    ParserIssue,
    ParserReport,
    PublicImportBatch,
    PublicReaderDescriptor,
    ReaderAvailability,
    ReaderManifestEntry,
    ReaderPluginManifest,
    ReaderPluginRegistry,
    SniffMatch,
    SniffResult,
    SniffRequest,
    SourceRecord,
    SourceRevision,
    builtin_reader_plugin_registry,
    public_batch_from_internal,
)
from ChemBlender.reader_api.conformance import (
    ReaderConformanceCase,
    ReaderConformanceCheck,
    ReaderConformanceResult,
    run_reader_conformance,
)
import ChemBlender.reader_api as reader_api


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
CHECK_NAMES = (
    "manifest",
    "bounded_sniff",
    "deterministic_sniff",
    "availability",
    "parse_output",
    "source_identity",
    "entity_references",
    "required_units",
    "diagnostics",
    "canonical_round_trip",
    "cancellation",
    "exception_isolation",
)


class Boom(Exception):
    pass


def descriptor(
    reader_id="broken", *, plugin_id="org.example.reader", reader_version="1"
):
    return PublicReaderDescriptor(
        plugin_id=plugin_id,
        plugin_version="1.0",
        reader_id=reader_id,
        reader_version=reader_version,
        execution_mode=ExecutionMode.EXTENSION,
        extensions=(".dat",),
        capabilities={"structure": CapabilitySupport.SUPPORTED},
        availability=ReaderAvailability(True, "extension", "available", ""),
    )


def manifest(value):
    return ReaderPluginManifest(
        schema_version="1",
        plugin_id=value.plugin_id,
        plugin_version=value.plugin_version,
        chemblender_api=">=0.1,<1.0",
        execution_mode=value.execution_mode,
        license=("SPDX:MIT",),
        readers=(
            ReaderManifestEntry(
                value.reader_id,
                value.reader_version,
                value.extensions,
                ("structure",),
            ),
        ),
    )


class BrokenPlugin:
    def __init__(self, *, sniff_error=None, parse_error=None):
        self.descriptor = descriptor()
        self.manifest = manifest(self.descriptor)
        self.priority = 0
        self.sniff_error = sniff_error
        self.parse_error = parse_error
        self.parse_calls = 0
        self.sniff_prefix_lengths = []
        self.sniff_requests = []

    def sniff(self, request):
        self.sniff_prefix_lengths.append(len(request.prefix))
        self.sniff_requests.append(request)
        if self.sniff_error is not None:
            raise self.sniff_error
        return SniffResult(SniffMatch.EXACT, self.descriptor.reader_id)

    def parse(self, request):
        self.parse_calls += 1
        if self.parse_error is not None:
            raise self.parse_error
        return PublicImportBatch()


class FactoryPlugin(BrokenPlugin):
    def __init__(self, result_factory):
        super().__init__()
        self.result_factory = result_factory

    def parse(self, request):
        self.parse_calls += 1
        return self.result_factory(request)


class AlternatingSniffPlugin(FactoryPlugin):
    def __init__(self):
        super().__init__(lambda request: PublicImportBatch())
        self.matches = iter(
            (
                SniffMatch.EXACT,
                SniffMatch.EXACT,
                SniffMatch.POSSIBLE,
                SniffMatch.EXACT,
                SniffMatch.EXACT,
            )
        )

    def sniff(self, request):
        self.sniff_prefix_lengths.append(len(request.prefix))
        self.sniff_requests.append(request)
        return SniffResult(next(self.matches), self.descriptor.reader_id)


class SelectionProbePlugin(BrokenPlugin):
    def __init__(self, reader_id, matches, *, priority=0):
        super().__init__()
        self.descriptor = descriptor(
            reader_id, plugin_id=f"org.example.{reader_id}"
        )
        self.manifest = manifest(self.descriptor)
        self.priority = priority
        self.matches = iter(matches)

    def sniff(self, request):
        self.sniff_prefix_lengths.append(len(request.prefix))
        return SniffResult(next(self.matches), self.descriptor.reader_id)


def check(result, name):
    return next(item for item in result.checks if item.name == name)


def checks(*, failed=()):
    return tuple(
        ReaderConformanceCheck(name, name not in failed, name)
        for name in CHECK_NAMES
    )


def identity_parameters(validation_mode="balanced", canonical_parameters=()):
    return tuple(
        sorted(
            (
                ("source_content_state", "verified"),
                ("validation_mode", validation_mode),
                *canonical_parameters,
            )
        )
    )


def identity_parameters_hash(parameters):
    return hashlib.sha256(
        json.dumps(
            parameters, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def envelope_batch(
    source_path,
    *,
    validation_mode="balanced",
    canonical_parameters=(),
    revisions=(),
    revision_id=None,
):
    content_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source = SourceRecord(uuid4(), source_path.name, "file", "2026-07-25")
    envelope = CIFEnvelope(
        uuid4(), content_hash, "block", b"data", ("_tag",), ()
    )
    report = ParserReport(
        "broken", "1", (envelope.id,), ("structure",), ()
    )
    if not revisions:
        parameters = identity_parameters(validation_mode, canonical_parameters)
        revisions = (
            SourceRevision(
                uuid4() if revision_id is None else revision_id,
                source.id,
                content_hash,
                source_path.stat().st_size,
                str(source_path.resolve()),
                "local_file",
                source_path.name,
                "org.example.reader",
                "broken",
                "1",
                "0.1",
                identity_parameters_hash(parameters),
                source_parse_identity(
                    content_hash,
                    "org.example.reader",
                    "broken",
                    "1",
                    parameters,
                ),
                (envelope.id,),
                (),
            ),
        )
    return PublicImportBatch(
        sources=(source,),
        source_revisions=revisions,
        cif_envelopes=(envelope,),
        report=report,
    )


class ReaderConformanceContractTests(unittest.TestCase):
    def test_public_reader_api_exports_only_the_documented_conformance_names(self):
        expected = {
            "ReaderConformanceCase",
            "ReaderConformanceCheck",
            "ReaderConformanceResult",
            "run_reader_conformance",
        }
        self.assertTrue(expected <= set(reader_api.__all__))
        for name in expected:
            self.assertIs(getattr(reader_api, name), globals()[name])

    def test_public_types_are_frozen_slots_and_normalize_deterministically(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.dat"
            source.write_bytes(b"fixture")
            case = ReaderConformanceCase(
                name="fixture",
                registry=ReaderPluginRegistry(),
                reader_id="example",
                source_path=source,
                expected_capabilities=("structure", "grid", "structure"),
                canonical_parameters={"z": "last", "a": "first"},
            )
            for key in ("source_content_state", "validation_mode"):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    ReaderConformanceCase(
                        "reserved",
                        ReaderPluginRegistry(),
                        "example",
                        source,
                        (),
                        canonical_parameters={key: "forged"},
                    )

        self.assertEqual(case.source_path, source.resolve())
        self.assertEqual(case.expected_capabilities, ("grid", "structure"))
        self.assertIs(type(case.canonical_parameters), MappingProxyType)
        self.assertEqual(
            dict(case.canonical_parameters), {"a": "first", "z": "last"}
        )
        self.assertEqual(
            tuple(field.name for field in fields(case)),
            (
                "name",
                "registry",
                "reader_id",
                "source_path",
                "expected_capabilities",
                "validation_mode",
                "canonical_parameters",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            case.name = "other"

    def test_result_is_deterministic_json_safe_and_reports_aggregate_pass(self):
        result = ReaderConformanceResult(
            "0.1", "fixture", "xyz", checks(failed=("parse_output",))
        )

        self.assertFalse(result.passed)
        self.assertEqual(
            tuple(item["name"] for item in result.as_dict()["checks"]),
            CHECK_NAMES,
        )
        self.assertFalse(result.as_dict()["checks"][4]["passed"])
        self.assertEqual(
            json.dumps(result.as_dict(), sort_keys=True),
            json.dumps(result.as_dict(), sort_keys=True),
        )

    def test_result_rejects_empty_duplicate_or_unordered_checks(self):
        invalid = (
            (),
            checks()[:-1] + (checks()[-2],),
            tuple(reversed(checks())),
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    ReaderConformanceResult("0.1", "fixture", "xyz", values)

    def test_builtin_xyz_and_cube_satisfy_all_ordered_checks(self):
        registry = builtin_reader_plugin_registry()
        cases = (
            ("water", "xyz/water.xyz", ("structure",)),
            ("sheared", "cube/sheared.cube", ("grid", "structure")),
        )
        for name, relative, capabilities in cases:
            with self.subTest(relative=relative):
                result = run_reader_conformance(
                    ReaderConformanceCase(
                        name,
                        registry,
                        registry.select(
                            SniffRequest(
                                FIXTURES / relative,
                                (FIXTURES / relative).read_bytes()[:65536],
                            )
                        ).reader_id,
                        FIXTURES / relative,
                        capabilities,
                    )
                )
                self.assertIs(type(result), ReaderConformanceResult)
                self.assertTrue(result.passed, result.as_dict())
                self.assertEqual(
                    tuple(check.name for check in result.checks), CHECK_NAMES
                )

    def test_reader_failures_are_machine_readable_and_cancellation_skips_parse(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "broken.dat"
            source.write_bytes(b"broken")
            for plugin, error_type in (
                (
                    BrokenPlugin(sniff_error=RuntimeError("sniff exploded")),
                    "RuntimeError",
                ),
                (
                    BrokenPlugin(parse_error=RuntimeError("parse exploded")),
                    "RuntimeError",
                ),
                (BrokenPlugin(parse_error=Boom("parse exploded")), "Boom"),
            ):
                with self.subTest(plugin=plugin):
                    result = run_reader_conformance(
                        ReaderConformanceCase(
                            "broken",
                            ReaderPluginRegistry((plugin,)),
                            "broken",
                            source,
                            ("structure",),
                        )
                    )
                    self.assertFalse(result.passed)
                    self.assertTrue(
                        any(
                            not check.passed and error_type in check.detail
                            for check in result.checks
                        ),
                        result.as_dict(),
                    )
                    cancellation = next(
                        check
                        for check in result.checks
                        if check.name == "cancellation"
                    )
                    self.assertTrue(cancellation.passed, result.as_dict())
                    self.assertEqual(plugin.parse_calls, 1)
                    isolation = next(
                        check
                        for check in result.checks
                        if check.name == "exception_isolation"
                    )
                    self.assertTrue(isolation.passed, result.as_dict())
                    self.assertIn(error_type, isolation.detail)

    def test_sniff_prefix_is_capped_before_reaching_the_plugin(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "long.dat"
            source.write_bytes(b"x" * 65537)
            plugin = BrokenPlugin()

            run_reader_conformance(
                ReaderConformanceCase(
                    "long",
                    ReaderPluginRegistry((plugin,)),
                    "broken",
                    source,
                    ("structure",),
                )
            )

        self.assertTrue(plugin.sniff_prefix_lengths)
        self.assertTrue(
            all(length <= 65536 for length in plugin.sniff_prefix_lengths),
            plugin.sniff_prefix_lengths,
        )

    def test_deterministic_sniff_requires_equal_exact_results(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "alternating.dat"
            source.write_bytes(b"fixture")
            plugin = AlternatingSniffPlugin()
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "alternating",
                    ReaderPluginRegistry((plugin,)),
                    "broken",
                    source,
                    ("structure",),
                )
            )

        self.assertFalse(check(result, "deterministic_sniff").passed)

    def test_deterministic_sniff_requires_stable_registry_selection(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "selection.dat"
            source.write_bytes(b"fixture")
            target = BrokenPlugin()
            rival = SelectionProbePlugin(
                "other",
                (SniffMatch.NONE, SniffMatch.NONE, SniffMatch.EXACT),
                priority=1,
            )
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "selection",
                    ReaderPluginRegistry((target, rival)),
                    "broken",
                    source,
                    ("structure",),
                )
            )

        self.assertFalse(check(result, "deterministic_sniff").passed)
        self.assertIs(target.sniff_requests[1], target.sniff_requests[2])

    def test_source_identity_rejects_any_incorrect_source_revision(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.dat"
            source.write_bytes(b"fixture")
            for changes in (
                {"content_hash": "0" * 64},
                {"reader_plugin_id": "org.example.other"},
                {"reader_id": "other"},
                {"reader_version": "2"},
                {"source_id": uuid4()},
                {"byte_size": source.stat().st_size + 1},
                {"created_entity_ids": ()},
                {"diagnostic_ids": (uuid4(),)},
            ):
                with self.subTest(changes=changes):
                    def result_factory(request, changes=changes):
                        batch = envelope_batch(source)
                        valid = batch.source_revisions[0]
                        return replace(
                            batch,
                            source_revisions=(
                                valid,
                                replace(valid, id=uuid4(), **changes),
                            ),
                        )

                    plugin = FactoryPlugin(
                        result_factory
                    )
                    result = run_reader_conformance(
                        ReaderConformanceCase(
                            "source",
                            ReaderPluginRegistry((plugin,)),
                            "broken",
                            source,
                            ("structure",),
                        )
                    )
                    self.assertFalse(check(result, "source_identity").passed)

    def test_source_identity_binds_import_parameters_and_validation_mode(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.dat"
            source.write_bytes(b"fixture")
            cases = (
                (
                    "tampered_hash",
                    "balanced",
                    "balanced",
                    {"import_parameters_hash": "0" * 64},
                ),
                ("strict_mode", "strict", "balanced", {}),
            )
            for name, case_mode, revision_mode, changes in cases:
                with self.subTest(name=name):
                    def result_factory(request, revision_mode=revision_mode, changes=changes):
                        batch = envelope_batch(
                            source,
                            validation_mode=revision_mode,
                            canonical_parameters=(("a", "first"), ("z", "last")),
                        )
                        revision = replace(batch.source_revisions[0], **changes)
                        return replace(batch, source_revisions=(revision,))

                    result = run_reader_conformance(
                        ReaderConformanceCase(
                            name,
                            ReaderPluginRegistry((FactoryPlugin(result_factory),)),
                            "broken",
                            source,
                            ("structure",),
                            validation_mode=case_mode,
                            canonical_parameters={"z": "last", "a": "first"},
                        )
                    )
                    self.assertFalse(check(result, "source_identity").passed)

    def test_source_identity_accepts_full_canonical_parameters(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.dat"
            source.write_bytes(b"fixture")
            parameters = (("a", "first"), ("z", "last"))
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "complete",
                    ReaderPluginRegistry(
                        (
                            FactoryPlugin(
                                lambda request: envelope_batch(
                                    source,
                                    validation_mode="strict",
                                    canonical_parameters=parameters,
                                    revision_id=request.source_revision_id,
                                )
                            ),
                        )
                    ),
                    "broken",
                    source,
                    ("structure",),
                    validation_mode="strict",
                    canonical_parameters={"z": "last", "a": "first"},
                )
            )

        self.assertTrue(check(result, "source_identity").passed, result.as_dict())

    def test_source_identity_rejects_weak_or_tampered_provenance_fallback(self):
        source = FIXTURES / "xyz" / "water.xyz"
        builtin = builtin_reader_plugin_registry()._plugin("xyz")

        class Proxy:
            descriptor = builtin.descriptor
            manifest = builtin.manifest
            priority = builtin.priority

            def __init__(self, change):
                self.change = change

            def sniff(self, request):
                return builtin.sniff(request)

            def parse(self, request):
                batch = builtin.parse(request)
                provenance = replace(batch.provenance[0], **self.change)
                return replace(batch, provenance=(provenance,))

        cases = (
            ({"producer": "forged"}, "balanced", {}),
            ({"producer_version": "9"}, "balanced", {}),
            ({"source": str(source.parent.resolve())}, "balanced", {}),
            ({"source_hash": "0" * 64}, "balanced", {}),
            ({"revision": "0" * 64}, "balanced", {}),
            ({"operation": "convert"}, "balanced", {}),
            ({"parameters": (("format", "other"),)}, "balanced", {}),
            ({}, "strict", {}),
            ({}, "balanced", {"charge": "2"}),
        )
        for changes, validation_mode, parameters in cases:
            with self.subTest(
                changes=changes,
                validation_mode=validation_mode,
                parameters=parameters,
            ):
                result = run_reader_conformance(
                    ReaderConformanceCase(
                        "tampered",
                        ReaderPluginRegistry((Proxy(changes),)),
                        "xyz",
                        source,
                        ("structure",),
                        validation_mode=validation_mode,
                        canonical_parameters=parameters,
                    )
                )
                self.assertFalse(check(result, "source_identity").passed)

    def test_third_party_reader_requires_source_revision_identity(self):
        source = FIXTURES / "xyz" / "water.xyz"
        from ChemBlender.core.xyz import XYZ_READER

        plugin = FactoryPlugin(
            lambda request: public_batch_from_internal(XYZ_READER.parse(source))
        )
        result = run_reader_conformance(
            ReaderConformanceCase(
                "third-party",
                ReaderPluginRegistry((plugin,)),
                "broken",
                source,
                ("structure",),
            )
        )

        self.assertFalse(check(result, "source_identity").passed)

    def test_source_identity_matches_staged_reader_batch_parameters_hash(self):
        with TemporaryDirectory() as temporary:
            source_path = Path(temporary) / "source.dat"
            source_path.write_bytes(b"fixture")
            source = ImportSource(source_path)
            internal = staged_reader_batch(
                source=source,
                validation_mode=ValidationMode.BALANCED,
                content_hash=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                byte_size=source_path.stat().st_size,
                runtime=None,
                reader_override="broken",
                parsed_batch=ImportBatch(
                    report=ParserReport("broken", "0", (), ("structure",), ())
                ),
            )
            plugin = FactoryPlugin(
                lambda request: public_batch_from_internal(
                    replace(
                        internal,
                        source_revisions=(
                            replace(
                                internal.source_revisions[0],
                                id=request.source_revision_id,
                            ),
                        ),
                    )
                )
            )
            plugin.descriptor = descriptor(
                plugin_id="chemblender.preflight", reader_version="0"
            )
            plugin.manifest = manifest(plugin.descriptor)
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "staged",
                    ReaderPluginRegistry((plugin,)),
                    "broken",
                    source_path,
                    ("structure",),
                )
            )

        self.assertTrue(check(result, "source_identity").passed, result.as_dict())

    def test_parse_failure_does_not_infer_exception_type_from_report_message(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "fabricated.dat"
            source.write_bytes(b"fixture")
            plugin = FactoryPlugin(
                lambda request: PublicImportBatch(
                    report=ParserReport(
                        "broken",
                        "1",
                        (),
                        (),
                        (
                            ParserIssue(
                                IssueKind.INVALID,
                                "reader.parse",
                                "reader parse failed: Fabricated",
                            ),
                        ),
                    )
                )
            )
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "fabricated",
                    ReaderPluginRegistry((plugin,)),
                    "broken",
                    source,
                    ("structure",),
                )
            )

        self.assertFalse(check(result, "parse_output").passed)
        self.assertEqual(
            check(result, "exception_isolation").detail, "no exception observed"
        )

    def test_parse_failure_does_not_admit_empty_failure_batch(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "failure.dat"
            source.write_bytes(b"fixture")
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "failure",
                    ReaderPluginRegistry((BrokenPlugin(parse_error=Boom()),)),
                    "broken",
                    source,
                    ("structure",),
                )
            )

        for name in (
            "parse_output",
            "source_identity",
            "entity_references",
            "required_units",
            "diagnostics",
            "canonical_round_trip",
        ):
            with self.subTest(name=name):
                self.assertFalse(check(result, name).passed)
        self.assertEqual(
            check(result, "exception_isolation").detail,
            "isolated exceptions: Boom",
        )

    def test_envelope_only_batch_passes_required_units_vacuously(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "envelope.dat"
            source.write_bytes(b"fixture")
            plugin = FactoryPlugin(
                lambda request: envelope_batch(
                    source,
                    revision_id=request.source_revision_id,
                )
            )
            result = run_reader_conformance(
                ReaderConformanceCase(
                    "envelope",
                    ReaderPluginRegistry((plugin,)),
                    "broken",
                    source,
                    ("structure",),
                )
            )

        self.assertTrue(check(result, "required_units").passed, result.as_dict())


if __name__ == "__main__":
    unittest.main()
