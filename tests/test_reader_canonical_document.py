import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy

import ChemBlender.reader_api as reader_api
import ChemBlender.reader_api.canonical_document as canonical_document


STRUCTURE_ID = UUID("20000000-0000-0000-0000-000000000002")
PROPERTY_ID = UUID("30000000-0000-0000-0000-000000000003")
FRAMES_ID = UUID("40000000-0000-0000-0000-000000000004")
PROVENANCE_ID = UUID("50000000-0000-0000-0000-000000000005")
GRID_ID = UUID("60000000-0000-0000-0000-000000000006")
MODEL_TAGS = (
    "PublicImportBatch",
    "ArrayData",
    "AtomicIdentityData",
    "CategoricalData",
    "SourceRecord",
    "SourceRevision",
    "CIFEnvelope",
    "QCSchemaEnvelope",
    "CJSONEnvelope",
    "PeriodicSiteData",
    "MolecularTopology",
    "RawRecordProperty",
    "MolecularRecord",
    "TopologyRecord",
    "Structure",
    "SymmetryResult",
    "CalculationMetadata",
    "CalculationRecord",
    "PropertyDataset",
    "RecordPropertyColumn",
    "ConformerSet",
    "AtomicProperty",
    "FrameSet",
    "Grid3D",
    "VibrationalModeSet",
    "ExcitationContribution",
    "ExcitedStateReferences",
    "ExcitedStateSet",
    "Spectrum",
    "BandPathBranch",
    "BandStructure",
    "DensityOfStates",
    "PhononModeSet",
    "SurfaceProperty",
    "FermiSurfaceMesh",
    "TopologyConnection",
    "TopologyPath",
    "TopologyGraph",
    "BasisShell",
    "BasisConvention",
    "BasisSet",
    "OrbitalChannel",
    "OrbitalSet",
    "DensityMatrix",
    "ProvenanceRecord",
    "ParserIssue",
    "ParserReport",
    "DiagnosticValue",
    "ImportDiagnostic",
)
ENUM_TAGS = (
    "CalculationStatus",
    "DatasetStatus",
    "IssueKind",
    "BasisFunctionKind",
    "OrbitalKind",
    "DensityMatrixLevel",
    "DensityMatrixSpin",
    "SpectrumKind",
    "SpectrumProfile",
    "SpinChannel",
    "EnergyReference",
    "CriticalPointKind",
    "QualityStatus",
    "DiagnosticSeverity",
    "TopologySource",
)


def sample_batch(mapping=None):
    coordinates = numpy.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]])
    structure = reader_api.Structure(
        id=STRUCTURE_ID,
        revision="structure-r1",
        atomic_numbers=(1, 1),
        coordinates=reader_api.ArrayData(
            coordinates, ("atom", "xyz"), "angstrom"
        ),
        topology=reader_api.MolecularTopology(
            bond_indices=reader_api.ArrayData(
                numpy.asarray([[0, 1]], dtype=numpy.int64),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=reader_api.ArrayData(
                numpy.asarray([1.0]), ("bond",), "dimensionless"
            ),
        ),
    )
    provenance = reader_api.ProvenanceRecord(
        id=PROVENANCE_ID,
        revision="provenance-r1",
        producer="test",
        producer_version="1",
        source="h2.xyz",
        source_hash="a" * 64,
        parent_ids=(),
        operation="parse",
        parameters=(("mapping", mapping or {"b": 2, "a": 1}),),
    )
    categorical = reader_api.AtomicProperty(
        id=PROPERTY_ID,
        revision="hybridization-r1",
        semantic_role="hybridization",
        domain="atom",
        data=reader_api.ArrayData(
            numpy.asarray(["s", "s"]), ("atom",), "dimensionless"
        ),
        status=reader_api.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        structure_id=STRUCTURE_ID,
    )
    frames = reader_api.FrameSet(
        id=FRAMES_ID,
        revision="frames-r1",
        semantic_role="coordinates",
        domain="frame",
        data=reader_api.ArrayData(
            numpy.stack((coordinates, coordinates + 1.0)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=reader_api.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        structure_id=STRUCTURE_ID,
        comments=("first", "second"),
    )
    grid = reader_api.Grid3D(
        id=GRID_ID,
        revision="grid-r1",
        semantic_role="electron_density",
        domain="grid",
        data=reader_api.ArrayData(
            numpy.arange(8, dtype=numpy.float64).reshape((2, 2, 2)),
            ("x", "y", "z"),
            "electron_per_cubic_angstrom",
        ),
        status=reader_api.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        origin=(0.0, 0.0, 0.0),
        step_vectors=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        coordinate_unit="angstrom",
        structure_id=STRUCTURE_ID,
    )
    return reader_api.PublicImportBatch(
        structures=(structure,),
        datasets=(categorical, frames, grid),
        provenance=(provenance,),
    )


def find_array_descriptor(value):
    if isinstance(value, dict):
        if value.get("$array") == "npy":
            return value
        for item in value.values():
            found = find_array_descriptor(item)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_array_descriptor(item)
            if found is not None:
                return found
    return None


def document_bytes(document):
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def property_batch(values):
    return reader_api.PublicImportBatch(
        datasets=(
            reader_api.PropertyDataset(
                id=uuid4(),
                revision="array-r1",
                semantic_role="test_values",
                domain="test",
                data=reader_api.ArrayData(
                    values, ("entry",), "dimensionless"
                ),
                status=reader_api.DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(),
            ),
        )
    )


class ReaderCanonicalDocumentTests(unittest.TestCase):
    def test_public_surface_exports_canonical_document_api(self):
        expected = (
            "CanonicalDocumentError",
            "CanonicalDocumentCompatibilityError",
            "CanonicalDocumentIntegrityError",
            "public_batch_document",
            "public_batch_from_document",
            "write_public_batch_bundle",
            "read_public_batch_bundle",
        )
        for name in expected:
            with self.subTest(name=name):
                self.assertIn(name, reader_api.__all__)
                self.assertTrue(hasattr(reader_api, name))
        self.assertTrue(
            issubclass(
                reader_api.CanonicalDocumentCompatibilityError,
                reader_api.CanonicalDocumentError,
            )
        )
        self.assertTrue(
            issubclass(
                reader_api.CanonicalDocumentIntegrityError,
                reader_api.CanonicalDocumentError,
            )
        )

    def test_complex_batch_round_trip_is_deterministic(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            first_bytes = reader_api.public_batch_document(
                sample_batch({"b": 2, "a": 1}), first
            )
            second_bytes = reader_api.public_batch_document(
                sample_batch({"a": 1, "b": 2}), second
            )
            self.assertEqual(first_bytes, second_bytes)
            self.assertNotIn(b"NaN", first_bytes)
            self.assertEqual(
                set(json.loads(first_bytes)),
                {"format", "schema_version", "batch"},
            )
            restored = reader_api.public_batch_from_document(first_bytes, first)

        self.assertIs(type(restored), reader_api.PublicImportBatch)
        self.assertIs(type(restored.structures[0]), reader_api.Structure)
        self.assertIs(
            type(restored.structures[0].topology),
            reader_api.MolecularTopology,
        )
        self.assertEqual(
            restored.structures[0].coordinates.dims, ("atom", "xyz")
        )
        numpy.testing.assert_array_equal(
            restored.structures[0].topology.bond_indices.values,
            numpy.asarray([[0, 1]], dtype=numpy.int64),
        )
        numpy.testing.assert_array_equal(
            restored.datasets[0].data.values, numpy.asarray(["s", "s"])
        )
        numpy.testing.assert_array_equal(
            restored.datasets[1].data.values[1],
            numpy.asarray([[1.0, 1.0, 1.0], [1.0, 1.0, 1.74]]),
        )
        self.assertEqual(restored.datasets[2].data.values[1, 1, 1], 7.0)
        self.assertEqual(
            restored.provenance[0].parameters,
            (("mapping", {"a": 1, "b": 2}),),
        )

    def test_incomplete_exact_model_is_a_stable_integrity_error(self):
        incomplete_grid = object.__new__(reader_api.Grid3D)
        batch = reader_api.PublicImportBatch(datasets=(incomplete_grid,))

        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                reader_api.CanonicalDocumentIntegrityError,
                "^incomplete public model value$",
            ):
                reader_api.public_batch_document(batch, temporary)

    def test_incomplete_nested_array_is_a_stable_integrity_error(self):
        batch = sample_batch()
        object.__setattr__(
            batch.datasets[2],
            "data",
            object.__new__(reader_api.ArrayData),
        )

        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                reader_api.CanonicalDocumentIntegrityError,
                "^incomplete public model value$",
            ):
                reader_api.public_batch_document(batch, temporary)

    def test_bundle_uses_content_addressed_safe_artifacts(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "result"
            document_path = reader_api.write_public_batch_bundle(
                root, sample_batch()
            )
            self.assertEqual(document_path, root / "import-batch.json")
            document = json.loads(document_path.read_bytes())
            descriptor = find_array_descriptor(document)
            self.assertEqual(
                descriptor["path"],
                f"artifacts/{descriptor['content_sha256']}.npy",
            )
            self.assertEqual(len(descriptor["content_sha256"]), 64)
            self.assertEqual(len(descriptor["file_sha256"]), 64)
            restored = reader_api.read_public_batch_bundle(root)
            self.assertIs(type(restored), reader_api.PublicImportBatch)

    def test_post_write_hash_and_cleanup_errors_are_stable(self):
        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing.npy"
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                canonical_document._file_hash(missing)

            root = Path(temporary) / "result"
            with patch.object(
                canonical_document.os,
                "replace",
                side_effect=OSError("replace failed"),
            ), patch.object(
                canonical_document.Path,
                "unlink",
                side_effect=OSError("cleanup failed"),
            ):
                with self.assertRaisesRegex(
                    reader_api.CanonicalDocumentIntegrityError,
                    "cannot write canonical document",
                ) as caught:
                    reader_api.write_public_batch_bundle(
                        root, reader_api.PublicImportBatch()
                    )
            self.assertEqual(str(caught.exception.__cause__), "replace failed")

            cleanup_root = Path(temporary) / "cleanup-result"
            with patch.object(
                canonical_document.Path,
                "unlink",
                side_effect=OSError("cleanup failed"),
            ):
                with self.assertRaisesRegex(
                    reader_api.CanonicalDocumentIntegrityError,
                    "cannot clean canonical temporary file",
                ) as caught:
                    reader_api.write_public_batch_bundle(
                        cleanup_root, reader_api.PublicImportBatch()
                    )
            self.assertEqual(str(caught.exception.__cause__), "cleanup failed")

    def test_array_write_error_is_not_masked_by_cleanup_error(self):
        with TemporaryDirectory() as temporary, patch.object(
            canonical_document._numpy(),
            "save",
            side_effect=OSError("array write failed"),
        ), patch.object(
            canonical_document.Path,
            "unlink",
            side_effect=OSError("cleanup failed"),
        ):
            with self.assertRaisesRegex(
                reader_api.CanonicalDocumentIntegrityError,
                "cannot write array artifact",
            ) as caught:
                reader_api.public_batch_document(
                    property_batch(numpy.asarray([1.0, 2.0])),
                    temporary,
                )
        self.assertEqual(str(caught.exception.__cause__), "array write failed")

    def test_array_cleanup_error_is_stable_without_a_write_error(self):
        with TemporaryDirectory() as temporary, patch.object(
            canonical_document.Path,
            "unlink",
            side_effect=OSError("array cleanup failed"),
        ):
            with self.assertRaisesRegex(
                reader_api.CanonicalDocumentIntegrityError,
                "cannot clean canonical temporary file",
            ) as caught:
                reader_api.public_batch_document(
                    property_batch(numpy.asarray([1.0, 2.0])),
                    temporary,
                )
        self.assertEqual(str(caught.exception.__cause__), "array cleanup failed")

    def test_registered_model_and_enum_tags_are_exact(self):
        self.assertEqual(tuple(canonical_document._MODEL_TYPES), MODEL_TAGS)
        self.assertEqual(tuple(canonical_document._MODEL_ENUMS), ENUM_TAGS)
        self.assertEqual(len(MODEL_TAGS), 49)
        self.assertEqual(len(ENUM_TAGS), 15)
        for name in MODEL_TAGS + ENUM_TAGS:
            with self.subTest(name=name):
                self.assertIs(
                    getattr(canonical_document._model, name),
                    getattr(reader_api, name),
                )

    def test_structured_and_subarray_dtypes_are_rejected_explicitly(self):
        structured = numpy.zeros(
            2, dtype=numpy.dtype([("x", "<f4"), ("y", "<f4")])
        )
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                reader_api.CanonicalDocumentIntegrityError,
                "structured or subarray dtype",
            ):
                reader_api.public_batch_document(
                    property_batch(structured), temporary
                )

        for dtype in ("i4,f4", "(2,)i4"):
            with self.subTest(dtype=dtype), TemporaryDirectory() as temporary:
                raw = reader_api.public_batch_document(
                    property_batch(numpy.asarray([1.0, 2.0])), temporary
                )
                malformed = json.loads(raw)
                find_array_descriptor(malformed)["dtype"] = dtype
                with self.assertRaisesRegex(
                    reader_api.CanonicalDocumentIntegrityError,
                    "structured or subarray dtype",
                ):
                    reader_api.public_batch_from_document(
                        document_bytes(malformed), temporary
                    )

    def test_preexisting_alternate_npy_header_cannot_change_document_bytes(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            batch = sample_batch()
            expected = reader_api.public_batch_document(batch, first)
            descriptor = find_array_descriptor(json.loads(expected))
            first_artifact = Path(first).joinpath(
                *descriptor["path"].split("/")
            )
            second_artifact = Path(second).joinpath(
                *descriptor["path"].split("/")
            )
            second_artifact.parent.mkdir(parents=True)
            with second_artifact.open("wb") as stream:
                numpy.lib.format.write_array(
                    stream,
                    numpy.load(first_artifact, allow_pickle=False),
                    version=(2, 0),
                    allow_pickle=False,
                )
            self.assertNotEqual(
                hashlib.sha256(first_artifact.read_bytes()).hexdigest(),
                hashlib.sha256(second_artifact.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                reader_api.public_batch_document(batch, second),
                expected,
            )

    def test_encoder_recursion_is_a_typed_integrity_error(self):
        nested = []
        for _ in range(sys.getrecursionlimit() + 100):
            nested = [nested]
        provenance = object.__new__(reader_api.ProvenanceRecord)
        values = {
            "id": PROVENANCE_ID,
            "revision": "recursive-r1",
            "producer": "test",
            "producer_version": "1",
            "source": "recursive",
            "source_hash": "a" * 64,
            "parent_ids": (),
            "operation": "parse",
            "parameters": (("nested", nested),),
        }
        for name, value in values.items():
            object.__setattr__(provenance, name, value)
        with TemporaryDirectory() as temporary:
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_document(
                    reader_api.PublicImportBatch(provenance=(provenance,)),
                    temporary,
                )

    def test_json_parser_recursion_is_a_typed_integrity_error(self):
        with TemporaryDirectory() as temporary, patch.object(
            canonical_document.json,
            "loads",
            side_effect=RecursionError("decoder recursion limit"),
        ):
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_from_document(b"{}", temporary)

    def test_decoder_recursion_is_a_typed_integrity_error(self):
        nested = None
        for _ in range(sys.getrecursionlimit() + 100):
            nested = {"$tuple": [nested]}
        parsed = {
            "batch": nested,
            "format": "chemblender.reader-import",
            "schema_version": "0.1",
        }
        with TemporaryDirectory() as temporary:
            Path(temporary, "artifacts").mkdir()
            loads = patch.object(
                canonical_document.json, "loads", return_value=parsed
            )
            with loads:
                with self.assertRaises(
                    reader_api.CanonicalDocumentIntegrityError
                ):
                    reader_api.public_batch_from_document(b"{}", temporary)

    def test_document_read_does_not_validate_project_graph(self):
        batch = sample_batch()
        dangling = reader_api.Grid3D(
            **{
                field: getattr(batch.datasets[2], field)
                for field in (
                    "id",
                    "revision",
                    "semantic_role",
                    "domain",
                    "data",
                    "status",
                    "source_calculation",
                    "provenance_ids",
                    "origin",
                    "step_vectors",
                    "coordinate_unit",
                )
            },
            structure_id=uuid4(),
        )
        batch = reader_api.PublicImportBatch(
            structures=batch.structures,
            datasets=(dangling,),
            provenance=batch.provenance,
        )
        with TemporaryDirectory() as temporary:
            document = reader_api.public_batch_document(batch, temporary)
            restored = reader_api.public_batch_from_document(
                document, temporary
            )
        self.assertEqual(restored.datasets[0].structure_id, dangling.structure_id)

    def test_schema_and_registered_type_compatibility_is_strict(self):
        with TemporaryDirectory() as temporary:
            raw = reader_api.public_batch_document(
                reader_api.PublicImportBatch(), temporary
            )
            valid = json.loads(raw)
            cases = []
            for key in ("format", "schema_version", "batch"):
                malformed = dict(valid)
                malformed.pop(key)
                cases.append(malformed)
            malformed = dict(valid)
            malformed["extra"] = None
            cases.append(malformed)
            malformed = dict(valid)
            malformed["schema_version"] = "9"
            cases.append(malformed)
            malformed = dict(valid)
            malformed["batch"] = {"$type": "Unknown"}
            cases.append(malformed)
            malformed = dict(valid)
            malformed["batch"] = {"$type": []}
            cases.append(malformed)
            malformed = dict(valid)
            malformed["batch"] = {"$enum": [], "value": "complete"}
            cases.append(malformed)
            malformed = dict(valid)
            malformed["batch"] = {"$pickle": "gASV"}
            cases.append(malformed)
            for malformed in cases:
                with self.subTest(malformed=malformed):
                    with self.assertRaises(
                        reader_api.CanonicalDocumentCompatibilityError
                    ):
                        reader_api.public_batch_from_document(
                            document_bytes(malformed), temporary
                        )

    def test_tags_require_exact_fields_and_one_tag(self):
        with TemporaryDirectory() as temporary:
            valid = json.loads(
                reader_api.public_batch_document(
                    reader_api.PublicImportBatch(), temporary
                )
            )
            invalid_batches = (
                {"$type": "PublicImportBatch", "extra": None},
                {"$uuid": str(uuid4()), "extra": None},
                {"$tuple": [], "$list": []},
                {"$tuple": "not-a-list"},
                {"$dict": [["duplicate", 1], ["duplicate", 2]]},
            )
            for batch in invalid_batches:
                malformed = dict(valid, batch=batch)
                with self.subTest(batch=batch):
                    with self.assertRaises(
                        reader_api.CanonicalDocumentIntegrityError
                    ):
                        reader_api.public_batch_from_document(
                            document_bytes(malformed), temporary
                        )

    def test_non_finite_json_values_are_integrity_errors(self):
        malformed = (
            b'{"batch":NaN,"format":"chemblender.reader-import",'
            b'"schema_version":"0.1"}'
        )
        with TemporaryDirectory() as temporary:
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_from_document(malformed, temporary)

        batch = sample_batch()
        bad_grid = object.__new__(reader_api.Grid3D)
        for field in batch.datasets[2].__dataclass_fields__:
            object.__setattr__(
                bad_grid, field, getattr(batch.datasets[2], field)
            )
        object.__setattr__(bad_grid, "origin", (float("nan"), 0.0, 0.0))
        with TemporaryDirectory() as temporary:
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_document(
                    reader_api.PublicImportBatch(
                        structures=batch.structures,
                        datasets=(bad_grid,),
                        provenance=batch.provenance,
                    ),
                    temporary,
                )

    def test_array_descriptor_rejects_path_escape_and_bad_metadata(self):
        with TemporaryDirectory() as temporary:
            raw = reader_api.public_batch_document(sample_batch(), temporary)
            valid = json.loads(raw)
            descriptor = find_array_descriptor(valid)
            cases = (
                ("path", "../outside.npy"),
                ("path", "C:/outside.npy"),
                ("path", "/outside.npy"),
                ("path", "artifacts/not-the-content-hash.npy"),
                ("content_sha256", "0" * 64),
                ("file_sha256", "0" * 64),
                ("shape", [True, 3]),
                ("shape", [-1, 3]),
                ("dtype", "|O"),
            )
            for key, value in cases:
                malformed = json.loads(raw)
                find_array_descriptor(malformed)[key] = value
                with self.subTest(key=key, value=value):
                    with self.assertRaises(
                        reader_api.CanonicalDocumentIntegrityError
                    ):
                        reader_api.public_batch_from_document(
                            document_bytes(malformed), temporary
                        )

    def test_array_file_shape_dtype_and_content_hash_are_verified(self):
        replacements = (
            numpy.asarray([1.0]),
            numpy.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
            numpy.asarray(
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=numpy.float32
            ),
        )
        for replacement in replacements:
            with self.subTest(shape=replacement.shape, dtype=replacement.dtype):
                with TemporaryDirectory() as temporary:
                    raw = reader_api.public_batch_document(
                        sample_batch(), temporary
                    )
                    valid = json.loads(raw)
                    descriptor = find_array_descriptor(valid)
                    artifact = Path(temporary).joinpath(
                        *descriptor["path"].split("/")
                    )
                    numpy.save(artifact, replacement, allow_pickle=False)
                    descriptor["file_sha256"] = hashlib.sha256(
                        artifact.read_bytes()
                    ).hexdigest()
                    with self.assertRaises(
                        reader_api.CanonicalDocumentIntegrityError
                    ):
                        reader_api.public_batch_from_document(
                            document_bytes(valid), temporary
                        )

    def test_pickle_backed_npy_and_object_arrays_are_rejected(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_document(
                    reader_api.PublicImportBatch(
                        structures=(
                            reader_api.Structure(
                                id=STRUCTURE_ID,
                                revision="unsafe",
                                atomic_numbers=(1,),
                                coordinates=reader_api.ArrayData(
                                    numpy.asarray(
                                        [[object(), object(), object()]],
                                        dtype=object,
                                    ),
                                    ("atom", "xyz"),
                                    "angstrom",
                                ),
                            ),
                        )
                    ),
                    temporary,
                )

            raw = reader_api.public_batch_document(sample_batch(), temporary)
            valid = json.loads(raw)
            descriptor = find_array_descriptor(valid)
            artifact = Path(temporary).joinpath(*descriptor["path"].split("/"))
            numpy.save(artifact, numpy.asarray([object()], dtype=object))
            descriptor["file_sha256"] = hashlib.sha256(
                artifact.read_bytes()
            ).hexdigest()
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_from_document(
                    document_bytes(valid), temporary
                )

    def test_symlink_escape_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            raw = reader_api.public_batch_document(sample_batch(), root)
            artifacts = root / "artifacts"
            outside = Path(temporary) / "outside-artifacts"
            artifacts.rename(outside)
            try:
                os.symlink(outside, artifacts, target_is_directory=True)
            except OSError as error:
                if os.name != "nt":
                    self.skipTest(f"symlink unavailable: {error}")
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(artifacts), str(outside)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode:
                    self.skipTest(f"directory link unavailable: {result.stderr}")
            with self.assertRaises(
                reader_api.CanonicalDocumentIntegrityError
            ):
                reader_api.public_batch_from_document(raw, root)

    def test_implementation_uses_only_relative_imports(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "ChemBlender"
            / "reader_api"
            / "canonical_document.py"
        )
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(
                    any(alias.name.startswith("ChemBlender") for alias in node.names)
                )
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertFalse(node.module.startswith("ChemBlender"))


if __name__ == "__main__":
    unittest.main()
