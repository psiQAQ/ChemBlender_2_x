import copy
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomicProperty,
    CIFEnvelope,
    DatasetStatus,
    FrameSet,
    Grid3D,
    ImportBatch,
    MolecularTopology,
    PropertyDataset,
    ProvenanceRecord,
    QCProject,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Structure,
    TopologyRecord,
    TopologySource,
    TrajectoryFrameManager,
)
from ChemBlender.core.sidecar import (
    LazyNpyArray,
    SidecarCompatibilityError,
    SidecarIntegrityError,
    _array_content_hash,
    close_project,
    open_project,
    save_project,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
STRUCTURE_ID = UUID("20000000-0000-0000-0000-000000000002")
DATASET_ID = UUID("30000000-0000-0000-0000-000000000003")
FRAMES_ID = UUID("40000000-0000-0000-0000-000000000004")
PROVENANCE_ID = UUID("50000000-0000-0000-0000-000000000005")
GRID_ID = UUID("60000000-0000-0000-0000-000000000006")


def manifest_hash(manifest):
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_manifest(path, manifest, *, update_hash=True):
    if update_hash and manifest.get("manifest_version") == "0.2":
        manifest["manifest_sha256"] = manifest_hash(manifest)
    path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def sample_project():
    coordinates = numpy.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]])
    structure = Structure(
        id=STRUCTURE_ID,
        revision="structure-r1",
        atomic_numbers=(1, 1),
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
        topology=MolecularTopology(
            bond_indices=ArrayData(
                numpy.asarray([[0, 1]], dtype=numpy.int64),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=ArrayData(
                numpy.asarray([1.0]), ("bond",), "dimensionless"
            ),
        ),
    )
    provenance = ProvenanceRecord(
        id=PROVENANCE_ID,
        revision="provenance-r1",
        producer="test",
        producer_version="1",
        source="h2.xyz",
        source_hash="a" * 64,
        parent_ids=(),
        operation="parse",
        parameters=(("charge", 0),),
    )
    charges = AtomicProperty(
        id=DATASET_ID,
        revision="charges-r1",
        semantic_role="mulliken_charge",
        domain="atom",
        data=ArrayData(numpy.asarray([0.1, -0.1]), ("atom",), "elementary_charge"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        structure_id=STRUCTURE_ID,
    )
    frames = FrameSet(
        id=FRAMES_ID,
        revision="frames-r1",
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            numpy.stack((coordinates, coordinates + 1.0)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        structure_id=STRUCTURE_ID,
        comments=("first", "second"),
    )
    grid = Grid3D(
        id=GRID_ID,
        revision="grid-r1",
        semantic_role="electron_density",
        domain="grid",
        data=ArrayData(
            numpy.arange(8, dtype=numpy.float64).reshape((2, 2, 2)),
            ("x", "y", "z"),
            "electron_per_cubic_angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(PROVENANCE_ID,),
        origin=(0.0, 0.0, 0.0),
        step_vectors=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        coordinate_unit="angstrom",
        structure_id=STRUCTURE_ID,
    )
    project = QCProject(id=PROJECT_ID, schema_version="0.1")
    project.commit(
        ImportBatch(
            structures=(structure,),
            datasets=(charges, frames, grid),
            provenance=(provenance,),
        )
    )
    return project


def topology_project(indices, orders, *, native):
    indices = numpy.asarray(indices, dtype=numpy.int64)
    atom_count = int(indices.max(initial=0)) + 1
    structure_id = uuid4()
    bonds = MolecularTopology(
        bond_indices=ArrayData(
            indices,
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=ArrayData(
            numpy.asarray(orders, dtype=float),
            ("bond",),
            "dimensionless",
        ),
    )
    topology_id = uuid4()
    structure = Structure(
        id=structure_id,
        revision="topology-structure",
        atomic_numbers=(6,) * atom_count,
        coordinates=ArrayData(
            numpy.zeros((atom_count, 3)),
            ("atom", "xyz"),
            "angstrom",
        ),
        topology=None if native else bonds,
        topology_ids=(topology_id,) if native else (),
    )
    project = QCProject(id=uuid4(), schema_version="0.2" if native else "0.1")
    topologies = (
        (
            TopologyRecord(
                id=topology_id,
                revision="current-topology",
                structure_id=structure_id,
                bond_indices=bonds.bond_indices,
                bond_orders=bonds.bond_orders,
                aromatic_flags=None,
                stereo_labels=("",) * len(indices),
                source_kind=TopologySource.EXPLICIT_FILE,
                quality_status=QualityStatus.COMPLETE,
                inference_parameters=(),
                provenance_ids=(),
            ),
        )
        if native
        else ()
    )
    project.commit(ImportBatch(structures=(structure,), topologies=topologies))
    return project, structure


class SidecarStorageTests(unittest.TestCase):
    def test_current_noncanonical_topology_failure_closes_lazy_arrays(self):
        project, _structure = topology_project(((0, 1),), (1.0,), native=True)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "current.cbq"
            save_project(path, project)
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            topology_value = manifest["project"]["topologies"]["$dict"][0][1]
            descriptor = topology_value["bond_indices"]["values"]
            content_hash, reversed_indices = _array_content_hash(
                numpy.asarray(((1, 0),), dtype=numpy.int64)
            )
            array_path = path / "arrays" / f"{content_hash}.npy"
            with array_path.open("wb") as stream:
                numpy.save(stream, reversed_indices, allow_pickle=False)
            descriptor.update(
                {
                    "path": f"arrays/{array_path.name}",
                    "content_sha256": content_hash,
                    "file_sha256": hashlib.sha256(array_path.read_bytes()).hexdigest(),
                    "shape": list(reversed_indices.shape),
                    "dtype": reversed_indices.dtype.str,
                }
            )
            write_manifest(manifest_path, manifest)

            closed = []
            original_close = LazyNpyArray.close

            def record_close(array):
                closed.append(id(array))
                original_close(array)

            with (
                patch.object(LazyNpyArray, "close", record_close),
                self.assertRaisesRegex(
                    SidecarIntegrityError,
                    "invalid TopologyRecord",
                ),
            ):
                open_project(path)
            self.assertEqual(len(closed), len(set(closed)))
            self.assertGreaterEqual(len(closed), 2)

    def test_legacy_topology_cleanup_failure_is_noted_on_primary_error(self):
        project, _structure = topology_project(
            ((0, 1), (1, 0)),
            (1.0, 1.0),
            native=False,
        )
        original_close = LazyNpyArray.close

        def close_then_fail(array):
            original_close(array)
            raise OSError("injected cleanup failure")

        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-duplicate.cbq"
            save_project(path, project)
            with (
                patch.object(LazyNpyArray, "close", close_then_fail),
                self.assertRaisesRegex(
                    SidecarIntegrityError,
                    "invalid TopologyRecord",
                ) as caught,
            ):
                open_project(path)

        cause = caught.exception.__cause__
        self.assertIsInstance(cause, ValueError)
        self.assertIn("repeat", str(cause))
        self.assertTrue(
            any(
                "injected cleanup failure" in note
                for note in getattr(cause, "__notes__", ())
            )
        )
        self.assertTrue(
            any(
                "injected cleanup failure" in note
                for note in getattr(caught.exception, "__notes__", ())
            )
        )

    def test_legacy_embedded_topology_is_canonicalized_on_open(self):
        project, structure = topology_project(
            ((2, 1), (1, 0)),
            (2.0, 1.0),
            native=False,
        )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.cbq"
            save_project(path, project)
            before = {
                item.relative_to(path): item.read_bytes()
                for item in path.rglob("*")
                if item.is_file()
            }
            restored = open_project(path)

            topology = next(iter(restored.topologies.values()))
            self.assertEqual(topology.bond_indices.values.tolist(), [[0, 1], [1, 2]])
            self.assertEqual(topology.bond_orders.values.tolist(), [1.0, 2.0])
            self.assertIsNone(restored.structures[structure.id].topology)
            close_project(restored)
            self.assertEqual(
                before,
                {
                    item.relative_to(path): item.read_bytes()
                    for item in path.rglob("*")
                    if item.is_file()
                },
            )

    def test_v02_tagged_objects_and_array_descriptors_require_exact_schemas(self):
        project = sample_project()
        project.provenance[PROVENANCE_ID] = ProvenanceRecord(
            id=PROVENANCE_ID,
            revision="provenance-r1",
            producer="test",
            producer_version="1",
            source="h2.xyz",
            source_hash="a" * 64,
            parent_ids=(),
            operation="parse",
            parameters=(("values", [1]),),
        )
        project.commit(
            ImportBatch(
                cif_envelopes=(
                    CIFEnvelope(
                        id=UUID("70000000-0000-0000-0000-000000000007"),
                        revision="cif-r1",
                        block_name="data_test",
                        source_bytes=b"data_test",
                        tag_names=("_cell_length_a",),
                        provenance_ids=(PROVENANCE_ID,),
                    ),
                )
            )
        )

        def tagged(value, tag):
            found = []
            if isinstance(value, dict):
                if tag in value:
                    found.append(value)
                for item in value.values():
                    found.extend(tagged(item, tag))
            elif isinstance(value, list):
                for item in value:
                    found.extend(tagged(item, tag))
            return found

        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "strict.cbq", project)
            manifest_path = root / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            invalid_documents = {}
            for tag in ("$uuid", "$enum", "$bytes", "$tuple", "$list", "$dict"):
                document = copy.deepcopy(original)
                targets = tagged(document["project"], tag)
                target = targets[1] if tag == "$uuid" else targets[0]
                target["unexpected"] = True
                invalid_documents[f"extra_{tag}"] = document

            document = copy.deepcopy(original)
            uuid_tag = tagged(document["project"], "$uuid")[1]
            uuid_tag["$enum"] = "DatasetStatus"
            invalid_documents["multiple_tags"] = document

            document = copy.deepcopy(original)
            tagged(document["project"], "$enum")[0].pop("value")
            invalid_documents["missing_enum_value"] = document

            document = copy.deepcopy(original)
            array_data = next(
                item
                for item in tagged(document["project"], "$type")
                if item["$type"] == "ArrayData"
            )
            array_data["unexpected"] = True
            invalid_documents["extra_array_data_field"] = document

            for tag in ("$tuple", "$list", "$dict"):
                document = copy.deepcopy(original)
                target = tagged(document["project"], tag)[0]
                target[tag] = "not-a-list"
                invalid_documents[f"payload_{tag}"] = document

            document = copy.deepcopy(original)
            mapping = next(
                item
                for item in tagged(document["project"], "$dict")
                if item["$dict"]
            )
            mapping["$dict"].append(copy.deepcopy(mapping["$dict"][0]))
            invalid_documents["duplicate_decoded_dict_key"] = document

            for mutation in (
                lambda array: array.__setitem__("unexpected", True),
                lambda array: array.pop("dtype"),
                lambda array: array.__setitem__("shape", [True]),
                lambda array: array.__setitem__("shape", ["1"]),
                lambda array: array.__setitem__("shape", [1.0]),
                lambda array: array.__setitem__("shape", [-1]),
                lambda array: array.__setitem__("dtype", "object"),
            ):
                document = copy.deepcopy(original)
                array = tagged(document["project"], "$array")[0]
                mutation(array)
                invalid_documents[f"array_{len(invalid_documents)}"] = document

            for name, manifest in invalid_documents.items():
                with self.subTest(name=name):
                    write_manifest(manifest_path, manifest)
                    with self.assertRaises(SidecarIntegrityError):
                        open_project(root)

    def test_raw_overflow_number_is_an_integrity_error(self):
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "overflow.cbq", sample_project())
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = {key: value for key, value in manifest.items() if key != "project"}
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            manifest_path.write_text(raw[:-1] + ",\"project\":1e400}\n", encoding="utf-8")

            with self.assertRaises(SidecarIntegrityError):
                open_project(root)

    def test_committed_v01_fixture_migrates_to_current_in_memory(self):
        project = open_project(FIXTURES / "sidecar" / "model-v01")
        try:
            self.assertEqual(project.id, PROJECT_ID)
            self.assertEqual(project.schema_version, "0.2")
            self.assertEqual(project.calculation_groups, {})
            self.assertEqual(project.sources, {})
            self.assertEqual(project.source_revisions, {})
            self.assertEqual(set(project.structures), {STRUCTURE_ID})
            self.assertEqual(
                set(project.datasets),
                {DATASET_ID, FRAMES_ID, GRID_ID},
            )
            self.assertEqual(set(project.provenance), {PROVENANCE_ID})

            structure = project.structures[STRUCTURE_ID]
            self.assertIs(type(structure), Structure)
            self.assertIsNone(structure.topology)
            self.assertEqual(structure.revision, "structure-r1")
            topology = project.topologies[structure.topology_ids[0]]
            self.assertIs(type(topology), TopologyRecord)
            self.assertEqual(topology.source_kind, TopologySource.DISTANCE_INFERRED)
            self.assertEqual(topology.quality_status, QualityStatus.AMBIGUOUS)
            self.assertEqual(topology.bond_indices.shape, (1, 2))
            self.assertEqual(topology.bond_orders.shape, (1,))

            charges = project.datasets[DATASET_ID]
            frames = project.datasets[FRAMES_ID]
            grid = project.datasets[GRID_ID]
            self.assertIs(type(charges), AtomicProperty)
            self.assertIs(type(frames), FrameSet)
            self.assertIs(type(grid), Grid3D)
            self.assertEqual(charges.revision, "charges-r1")
            self.assertEqual(frames.revision, "frames-r1")
            self.assertEqual(grid.revision, "grid-r1")
            self.assertEqual(charges.structure_id, STRUCTURE_ID)
            self.assertEqual(frames.structure_id, STRUCTURE_ID)
            self.assertEqual(grid.structure_id, STRUCTURE_ID)
            self.assertIsInstance(charges.data.values, LazyNpyArray)

            provenance = project.provenance[PROVENANCE_ID]
            self.assertIs(type(provenance), ProvenanceRecord)
            self.assertEqual(provenance.revision, "provenance-r1")
        finally:
            close_project(project)

    def test_existing_v02_without_calculation_groups_migrates_empty_registry(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "legacy-v02.cbq"
            save_project(root, sample_project())
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["project"]["calculation_groups"]
            write_manifest(manifest_path, manifest)

            project = open_project(root)
            try:
                self.assertEqual(project.schema_version, "0.2")
                self.assertEqual(project.calculation_groups, {})
            finally:
                close_project(project)

    def test_unknown_manifest_version_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "unknown.cbq"
            root.mkdir()
            write_manifest(
                root / "manifest.json",
                {
                    "format": "chemblender.cbq",
                    "manifest_version": "9.9",
                },
                update_hash=False,
            )

            with self.assertRaises(SidecarCompatibilityError):
                open_project(root)

    def test_new_manifest_is_v02_canonical_hashed_and_does_not_mutate_v01_caller(self):
        project = sample_project()
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "h2.cbq", project)
            manifest_path = root / "manifest.json"
            document = manifest_path.read_bytes()
            manifest = json.loads(document)

            self.assertEqual(project.schema_version, "0.1")
            self.assertEqual(manifest["manifest_version"], "0.2")
            self.assertEqual(manifest["project_schema_version"], "0.2")
            self.assertEqual(manifest["project"]["schema_version"], "0.2")
            self.assertEqual(UUID(manifest["generation_id"]).version, 4)
            created = datetime.fromisoformat(
                manifest["created_at_utc"].replace("Z", "+00:00")
            )
            self.assertEqual(created.tzinfo, timezone.utc)
            self.assertEqual(manifest["manifest_sha256"], manifest_hash(manifest))
            self.assertEqual(
                document,
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n",
            )
            restored = open_project(root, expected_schema_version="0.1")
            self.assertEqual(restored.schema_version, "0.2")
            close_project(restored)

    def test_v02_manifest_hash_detects_tampering(self):
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "h2.cbq", sample_project())
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifest_version"], "0.2")
            manifest["project_schema_version"] = "tampered"
            write_manifest(manifest_path, manifest, update_hash=False)

            with self.assertRaisesRegex(SidecarIntegrityError, "manifest hash"):
                open_project(root)

    def test_v02_manifest_strictly_validates_generation_metadata_and_fields(self):
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "h2.cbq", sample_project())
            manifest_path = root / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(original["manifest_version"], "0.2")
            invalid_documents = (
                {key: value for key, value in original.items() if key != "format"},
                original | {"generation_id": "not-a-uuid"},
                original | {"created_at_utc": "not-a-timestamp"},
                original | {"unexpected": True},
            )

            for manifest in invalid_documents:
                with self.subTest(manifest=set(manifest)):
                    write_manifest(manifest_path, copy.deepcopy(manifest))
                    with patch(
                        "ChemBlender.core.sidecar._Decoder.decode",
                        side_effect=AssertionError("decoder reached"),
                    ):
                        with self.assertRaises(SidecarIntegrityError):
                            open_project(root)

    def test_v02_header_payload_mismatch_is_integrity_error_before_decode(self):
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "h2.cbq", sample_project())
            manifest_path = root / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            other_id = str(UUID("90000000-0000-0000-0000-000000000009"))
            invalid_documents = {
                "project_type": lambda document: document["project"].__setitem__(
                    "$type", "Structure"
                ),
                "header_uuid": lambda document: document.__setitem__(
                    "project_id", other_id
                ),
                "payload_uuid": lambda document: document["project"][
                    "id"
                ].__setitem__("$uuid", other_id),
                "payload_uuid_shape": lambda document: document["project"].__setitem__(
                    "id", {"$uuid": document["project_id"], "unexpected": True}
                ),
                "header_schema": lambda document: document.__setitem__(
                    "project_schema_version", "9"
                ),
                "payload_schema": lambda document: document["project"].__setitem__(
                    "schema_version", "9"
                ),
            }

            for name, mutate in invalid_documents.items():
                with self.subTest(name=name):
                    manifest = copy.deepcopy(original)
                    mutate(manifest)
                    write_manifest(manifest_path, manifest)
                    with patch(
                        "ChemBlender.core.sidecar._Decoder.decode",
                        side_effect=AssertionError("decoder reached"),
                    ):
                        with self.assertRaisesRegex(
                            SidecarIntegrityError,
                            "header and project payload disagree",
                        ):
                            open_project(root)

    def test_v02_matching_unsupported_schema_is_compatibility_error_before_decode(self):
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "h2.cbq", sample_project())
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["project_schema_version"] = "9"
            manifest["project"]["schema_version"] = "9"
            write_manifest(manifest_path, manifest)

            with patch(
                "ChemBlender.core.sidecar._Decoder.decode",
                side_effect=AssertionError("decoder reached"),
            ):
                with self.assertRaises(SidecarCompatibilityError):
                    open_project(root)

    def test_scalar_array_round_trip_preserves_zero_rank(self):
        dataset = PropertyDataset(
            id=UUID("60000000-0000-0000-0000-000000000006"),
            revision="scalar-v1",
            semantic_role="return_energy",
            domain="global",
            data=ArrayData(numpy.asarray(-1.25), (), "hartree"),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
        )
        project = QCProject(
            id=UUID("70000000-0000-0000-0000-000000000007"),
            schema_version="0.1",
        )
        project.commit(ImportBatch(datasets=(dataset,)))
        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "scalar.cbq", project)
            restored = open_project(root)
            scalar = restored.datasets[dataset.id].data
            self.assertEqual(scalar.shape, ())
            self.assertEqual(float(numpy.asarray(scalar.values)), -1.25)
            close_project(restored)

    def test_round_trip_restores_identity_and_lazy_arrays(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            loaded = open_project(root)

            self.assertEqual(loaded.id, PROJECT_ID)
            self.assertEqual(loaded.structures[STRUCTURE_ID].revision, "structure-r1")
            self.assertEqual(loaded.datasets[DATASET_ID].provenance_ids, (PROVENANCE_ID,))
            values = loaded.datasets[FRAMES_ID].data.values
            self.assertIsInstance(values, LazyNpyArray)
            self.assertFalse(values.loaded)
            close_project(loaded)

    def test_nonempty_source_registries_round_trip_through_v02(self):
        source = SourceRecord(
            id=UUID("70000000-0000-0000-0000-000000000007"),
            display_name="H2 input",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        revision = SourceRevision(
            id=UUID("80000000-0000-0000-0000-000000000008"),
            source_id=source.id,
            content_hash="a" * 64,
            byte_size=42,
            locator="inputs/h2.xyz",
            locator_kind="path",
            original_filename="h2.xyz",
            reader_plugin_id="chemblender.builtin",
            reader_id="xyz",
            reader_version="2",
            reader_api_version="0.1",
            import_parameters_hash="b" * 64,
            parse_identity="c" * 64,
            created_entity_ids=(STRUCTURE_ID, DATASET_ID),
            diagnostic_ids=(),
        )
        project = sample_project()
        project.commit(
            ImportBatch(
                sources=(source,),
                source_revisions=(revision,),
            )
        )

        with TemporaryDirectory() as directory:
            root = save_project(Path(directory) / "sources.cbq", project)
            close_project(project)
            restored = open_project(root)
            try:
                self.assertEqual(restored.schema_version, "0.2")
                self.assertEqual(restored.sources, {source.id: source})
                self.assertEqual(
                    restored.source_revisions,
                    {revision.id: revision},
                )
                self.assertEqual(
                    restored.source_revisions[revision.id].locator,
                    revision.locator,
                )
                self.assertEqual(
                    restored.source_revisions[revision.id].created_entity_ids,
                    revision.created_entity_ids,
                )
                self.assertEqual(
                    restored.provenance,
                    project.provenance,
                )
            finally:
                close_project(restored)

    def test_trajectory_manager_releases_lazy_sidecar_memory_map(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            loaded = open_project(root)
            values = loaded.datasets[FRAMES_ID].data.values
            manager = TrajectoryFrameManager(loaded.datasets[FRAMES_ID])
            self.assertFalse(values.loaded)
            self.assertTrue(
                numpy.allclose(manager.frame(1)[1], [1.0, 1.0, 1.74])
            )
            self.assertTrue(values.loaded)
            manager.close()
            self.assertFalse(values.loaded)
            self.assertTrue(numpy.allclose(numpy.asarray(values)[1, 1], [1.0, 1.0, 1.74]))
            self.assertTrue(values.loaded)
            close_project(loaded)
            self.assertFalse(values.loaded)

    def test_content_addressing_deduplicates_equal_arrays(self):
        project = sample_project()
        project.datasets[DATASET_ID] = PropertyDataset(
            id=DATASET_ID,
            revision="charges-r2",
            semantic_role="mulliken_charge",
            domain="atom",
            data=ArrayData(
                numpy.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(PROVENANCE_ID,),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, project)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            references = []

            def visit(value):
                if isinstance(value, dict):
                    if value.get("$type") == "ArrayData":
                        references.append(value["values"]["path"])
                    for child in value.values():
                        visit(child)
                elif isinstance(value, list):
                    for child in value:
                        visit(child)

            visit(manifest["project"])
            self.assertLess(len(set(references)), len(references))
            self.assertEqual(len(list((root / "arrays").glob("*.npy"))), len(set(references)))

    def test_tamper_and_expected_identity_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            with self.assertRaises(SidecarCompatibilityError):
                open_project(root, expected_project_id=UUID(int=0))
            with self.assertRaises(SidecarCompatibilityError):
                open_project(root, expected_schema_version="9")
            array_path = next((root / "arrays").glob("*.npy"))
            array_path.write_bytes(array_path.read_bytes() + b"tampered")
            with self.assertRaises(SidecarIntegrityError):
                open_project(root)

    def test_array_path_cannot_escape_sidecar(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            def replace_first_array(value):
                if isinstance(value, dict):
                    if value.get("$array") == "npy":
                        value["path"] = "../outside.npy"
                        return True
                    return any(replace_first_array(child) for child in value.values())
                if isinstance(value, list):
                    return any(replace_first_array(child) for child in value)
                return False

            self.assertTrue(replace_first_array(manifest["project"]))
            write_manifest(manifest_path, manifest)
            with self.assertRaises(SidecarIntegrityError):
                open_project(root)

    def test_failed_manifest_replace_preserves_previous_project(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "h2.cbq"
            save_project(root, sample_project())
            previous = (root / "manifest.json").read_bytes()
            with patch("ChemBlender.core.sidecar.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_project(root, sample_project())
            self.assertEqual((root / "manifest.json").read_bytes(), previous)
            self.assertEqual(open_project(root).id, PROJECT_ID)

    def test_object_arrays_are_rejected(self):
        project = sample_project()
        project.datasets[DATASET_ID] = PropertyDataset(
            id=DATASET_ID,
            revision="bad",
            semantic_role="labels",
            domain="atom",
            data=ArrayData(numpy.asarray([object(), object()], dtype=object), ("atom",), "dimensionless"),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(PROVENANCE_ID,),
        )
        with TemporaryDirectory() as directory:
            with self.assertRaises(SidecarIntegrityError):
                save_project(Path(directory) / "bad.cbq", project)

    def test_nonfinite_manifest_values_are_rejected_as_integrity_errors(self):
        provenance = ProvenanceRecord(
            id=PROVENANCE_ID,
            revision="bad",
            producer="test",
            producer_version="1",
            source="",
            source_hash="",
            parent_ids=(),
            operation="parse",
            parameters=(("not_finite", float("nan")),),
        )
        project = QCProject(
            UUID("70000000-0000-0000-0000-000000000007"),
            "0.2",
            provenance={provenance.id: provenance},
        )
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                SidecarIntegrityError,
                "canonical JSON",
            ):
                save_project(Path(directory) / "bad.cbq", project)


if __name__ == "__main__":
    unittest.main()
