import array
import importlib
import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomFrameProperty,
    DatasetStatus,
    DiagnosticSeverity,
    DiagnosticValue,
    Grid3D,
    FrameSet,
    ImportBatch,
    ImportDiagnostic,
    PeriodicSiteData,
    QCProject,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Structure,
    SymmetryResult,
)
from ChemBlender.core.formats.sdf import parse_sdf
from ChemBlender.core.import_pipeline.conformer_grouping import (
    accept_conformer_group,
    suggest_conformer_groups,
)
from ChemBlender.ui.project_browser.model import (
    BrowserMode,
    BrowserRow,
    ViewRecord,
    build_browser_rows,
)


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
SESSION_ID = UUID("10000000-0000-0000-0000-000000000002")
SOURCE_ID = UUID("20000000-0000-0000-0000-000000000001")
REVISION_ID = UUID("20000000-0000-0000-0000-000000000002")
STRUCTURE_ID = UUID("30000000-0000-0000-0000-000000000001")
GRID_ID = UUID("30000000-0000-0000-0000-000000000002")
FRAME_SET_ID = UUID("30000000-0000-0000-0000-000000000003")
FORCE_ID = UUID("30000000-0000-0000-0000-000000000004")
DIAGNOSTIC_ID = UUID("40000000-0000-0000-0000-000000000001")
SDF_FIXTURE = Path(__file__).with_name("fixtures") / "sdf" / "records.sdf"


class _ArraySentinel:
    shape = (1,)
    dtype = "float64"

    def __array__(self, *_args, **_kwargs):
        raise AssertionError("Project Browser materialized array values")

    def __iter__(self):
        raise AssertionError("Project Browser traversed array values")


def sample_project():
    coordinates = ArrayData(
        memoryview(array.array("d", [0.0, 0.0, 0.0]))
        .cast("B")
        .cast("d", shape=(1, 3)),
        ("atom", "xyz"),
        "angstrom",
    )
    structure = Structure(
        id=STRUCTURE_ID,
        revision="structure-r1",
        atomic_numbers=(8,),
        coordinates=coordinates,
    )
    grid_data = ArrayData(
        memoryview(array.array("d", range(8)))
        .cast("B")
        .cast("d", shape=(2, 2, 2)),
        ("x", "y", "z"),
        "electron_density",
    )
    grid = Grid3D(
        id=GRID_ID,
        revision="grid-r1",
        semantic_role="electron_density",
        domain="grid",
        data=grid_data,
        status=DatasetStatus.PARTIAL,
        source_calculation=None,
        provenance_ids=(),
        origin=(0.0, 0.0, 0.0),
        step_vectors=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        coordinate_unit="angstrom",
        structure_id=STRUCTURE_ID,
    )
    object.__setattr__(coordinates, "values", _ArraySentinel())
    object.__setattr__(grid_data, "values", _ArraySentinel())
    source = SourceRecord(
        id=SOURCE_ID,
        display_name="Water calculation",
        source_kind="local_file",
        created_at_utc="2026-07-25T00:00:00Z",
    )
    revision = SourceRevision(
        id=REVISION_ID,
        source_id=SOURCE_ID,
        content_hash="a" * 64,
        byte_size=123,
        locator="water.xyz",
        locator_kind="local_file",
        original_filename="water.xyz",
        reader_plugin_id="chemblender.builtin",
        reader_id="xyz",
        reader_version="1",
        reader_api_version="0.1",
        import_parameters_hash="b" * 64,
        parse_identity="c" * 64,
        created_entity_ids=(STRUCTURE_ID, GRID_ID),
        diagnostic_ids=(DIAGNOSTIC_ID,),
    )
    diagnostic = ImportDiagnostic(
        id=DIAGNOSTIC_ID,
        severity=DiagnosticSeverity.WARNING,
        quality_status=QualityStatus.PARTIAL,
        source_revision_id=REVISION_ID,
        record_key=None,
        entity_id=GRID_ID,
        field_path="grid.values",
        code="cube.partial_grid",
        message="Recovered damaged grid value",
        original_value=DiagnosticValue("bad"),
        normalized_value=DiagnosticValue(1.0),
        recovery_action="normalize",
        scientific_consequence="grid value is approximate",
        suggested_action="review",
    )
    project = QCProject(PROJECT_ID, "0.2")
    project.commit(
        ImportBatch(
            sources=(source,),
            source_revisions=(revision,),
            structures=(structure,),
            datasets=(grid,),
            diagnostics=(diagnostic,),
        )
    )
    return project


def sample_trajectory_project():
    project = sample_project()
    frame_set = FrameSet(
        id=FRAME_SET_ID,
        revision="frames-r1",
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            numpy.zeros((2, 1, 3)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=STRUCTURE_ID,
        comments=("", ""),
    )
    force = AtomFrameProperty(
        id=FORCE_ID,
        revision="force-r1",
        semantic_role="atomic_force",
        domain="atom_frame",
        data=ArrayData(
            numpy.asarray([[[1.0, 2.0, 3.0]], [[4.0, 5.0, 6.0]]]),
            ("frame", "atom", "xyz"),
            "electron_volt_per_angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        frame_set_id=FRAME_SET_ID,
    )
    project.commit(ImportBatch(datasets=(force, frame_set)))
    return project


def sample_views():
    return (
        ViewRecord(
            object_name="Water energy",
            entity_id=GRID_ID,
            revision="grid-r1",
            view_kind="volume",
            label="Density view",
        ),
    )


def sample_molecular_project():
    batch = parse_sdf(SDF_FIXTURE)
    acceptance = accept_conformer_group(
        suggest_conformer_groups(batch)[0],
        batch,
        review_confirmed=True,
    )
    project = SimpleNamespace(
        id=PROJECT_ID,
        molecular_records={
            record.id: record for record in batch.molecular_records
        },
        datasets={
            dataset.id: dataset
            for dataset in (*batch.datasets, acceptance.conformer_set)
        },
        structures={value.id: value for value in batch.structures},
        topologies={value.id: value for value in batch.topologies},
        calculations={},
        symmetry_results={},
        basis_sets={},
        orbital_sets={},
        density_matrices={},
        cif_envelopes={},
        qcschema_envelopes={},
        cjson_envelopes={},
        provenance={},
        diagnostics={},
    )
    return project, batch, acceptance


class ProjectBrowserModelTests(unittest.TestCase):
    def test_molecular_records_and_conformer_properties_are_grouped(self):
        project, batch, acceptance = sample_molecular_project()

        rows = build_browser_rows(
            project,
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=3,
        )

        record_rows = tuple(
            row for row in rows if row.kind == "molecular_record"
        )
        self.assertEqual(
            tuple(row.entity_id for row in record_rows),
            tuple(record.id for record in batch.molecular_records),
        )
        self.assertTrue(
            all(row.parent_id == "group:molecular_records" for row in record_rows)
        )
        conformer_row = next(
            row
            for row in rows
            if row.entity_id == acceptance.conformer_set.id
        )
        property_rows = tuple(
            row
            for row in rows
            if row.kind == "record_property_column"
        )
        self.assertTrue(property_rows)
        self.assertTrue(
            all(row.parent_id == conformer_row.id for row in property_rows)
        )
        self.assertTrue(
            all(
                record.title in next(
                    row.label
                    for row in record_rows
                    if row.entity_id == record.id
                )
                for record in batch.molecular_records
            )
        )

    def test_frame_set_groups_its_related_properties_without_reading_values(self):
        rows = build_browser_rows(
            sample_trajectory_project(),
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=2,
        )
        frame_row = next(row for row in rows if row.entity_id == FRAME_SET_ID)
        force_row = next(row for row in rows if row.entity_id == FORCE_ID)

        self.assertEqual(frame_row.parent_id, "group:datasets")
        self.assertEqual(force_row.parent_id, frame_row.id)
        self.assertEqual(force_row.depth, frame_row.depth + 1)

    def test_rows_and_view_records_are_immutable(self):
        row = BrowserRow(
            id="entity:test",
            parent_id=None,
            depth=0,
            kind="property_dataset",
            label="Energy",
            quality="partial",
            view_count=1,
            entity_id=GRID_ID,
        )
        view = sample_views()[0]

        with self.assertRaises(FrozenInstanceError):
            row.label = "changed"
        with self.assertRaises(FrozenInstanceError):
            view.label = "changed"

    def test_by_source_is_a_deterministic_flat_tree(self):
        source_path = f"source:{SOURCE_ID}"
        revision_path = f"{source_path}/revision:{REVISION_ID}"
        structure_path = f"{revision_path}/entity:{STRUCTURE_ID}"
        grid_path = f"{revision_path}/entity:{GRID_ID}"
        rows = build_browser_rows(
            sample_project(),
            mode=BrowserMode.BY_SOURCE,
            session_id=SESSION_ID,
            browser_revision=1,
            views=sample_views(),
        )

        self.assertEqual(
            [(row.id, row.parent_id, row.depth, row.kind) for row in rows],
            [
                (source_path, None, 0, "source"),
                (
                    revision_path,
                    source_path,
                    1,
                    "source_revision",
                ),
                (
                    structure_path,
                    revision_path,
                    2,
                    "structure",
                ),
                (
                    grid_path,
                    revision_path,
                    2,
                    "grid3d",
                ),
                (
                    (
                        f"{grid_path}/view:Water energy:"
                        f"{GRID_ID}:grid-r1"
                    ),
                    grid_path,
                    3,
                    "view",
                ),
                (
                    f"{revision_path}/diagnostic:{DIAGNOSTIC_ID}",
                    revision_path,
                    2,
                    "diagnostic",
                ),
            ],
        )
        self.assertEqual(rows[3].quality, "partial")
        self.assertEqual(rows[3].view_count, 1)

    def test_by_source_paths_are_unique_across_shared_entities_and_duplicates(self):
        base = sample_project()
        second_source_id = UUID("20000000-0000-0000-0000-000000000003")
        second_revision_id = UUID("20000000-0000-0000-0000-000000000004")
        source = next(iter(base.sources.values()))
        revision = next(iter(base.source_revisions.values()))
        duplicate_revision = SimpleNamespace(
            **{
                name: getattr(revision, name)
                for name in (
                    "content_hash",
                    "byte_size",
                    "locator",
                    "locator_kind",
                    "original_filename",
                    "reader_plugin_id",
                    "reader_id",
                    "reader_version",
                    "reader_api_version",
                    "import_parameters_hash",
                    "parse_identity",
                )
            },
            id=REVISION_ID,
            source_id=SOURCE_ID,
            created_entity_ids=(
                STRUCTURE_ID,
                GRID_ID,
                STRUCTURE_ID,
                GRID_ID,
            ),
            diagnostic_ids=(DIAGNOSTIC_ID, DIAGNOSTIC_ID),
        )
        second_revision = SimpleNamespace(
            **duplicate_revision.__dict__,
        )
        second_revision.id = second_revision_id
        second_revision.source_id = second_source_id
        project = SimpleNamespace(
            id=base.id,
            sources={
                SOURCE_ID: source,
                second_source_id: SimpleNamespace(
                    id=second_source_id,
                    display_name="Second source",
                ),
            },
            source_revisions={
                REVISION_ID: duplicate_revision,
                second_revision_id: second_revision,
            },
            structures=base.structures,
            datasets=base.datasets,
            calculations=base.calculations,
            symmetry_results=base.symmetry_results,
            basis_sets=base.basis_sets,
            orbital_sets=base.orbital_sets,
            density_matrices=base.density_matrices,
            cif_envelopes=base.cif_envelopes,
            qcschema_envelopes=base.qcschema_envelopes,
            cjson_envelopes=base.cjson_envelopes,
            provenance=base.provenance,
            diagnostics=base.diagnostics,
        )
        shared_view = ViewRecord(
            object_name="Shared structure",
            entity_id=STRUCTURE_ID,
            revision="structure-r1",
            view_kind="structure",
            label="Shared structure view",
        )
        duplicate_views = (shared_view, shared_view)

        all_rows = build_browser_rows(
            project,
            mode=BrowserMode.BY_SOURCE,
            session_id=SESSION_ID,
            browser_revision=1,
            views=duplicate_views,
        )
        rows = build_browser_rows(
            project,
            mode=BrowserMode.BY_SOURCE,
            session_id=SESSION_ID,
            browser_revision=1,
            search="shared structure view",
            views=duplicate_views,
        )
        row_ids = {row.id for row in all_rows}

        self.assertEqual(len(row_ids), len(all_rows))
        self.assertTrue(
            all(
                row.parent_id is None or row.parent_id in row_ids
                for row in all_rows
            )
        )
        self.assertEqual(
            [row.kind for row in all_rows].count("diagnostic"),
            2,
        )
        self.assertEqual(
            [row.kind for row in rows].count("source"),
            2,
        )
        self.assertEqual(
            [row.kind for row in rows].count("source_revision"),
            2,
        )
        self.assertEqual([row.kind for row in rows].count("structure"), 2)
        self.assertEqual([row.kind for row in rows].count("view"), 2)
        self.assertTrue(
            all(
                row.id.startswith(f"{row.parent_id}/")
                for row in rows
                if row.parent_id is not None
            )
        )

    def test_by_data_groups_entities_diagnostics_and_views(self):
        grid_path = f"group:datasets/entity:{GRID_ID}"
        structure_path = f"group:structures/entity:{STRUCTURE_ID}"
        rows = build_browser_rows(
            sample_project(),
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=1,
            views=sample_views(),
        )

        self.assertEqual(
            [(row.id, row.parent_id, row.depth, row.kind) for row in rows],
            [
                ("group:datasets", None, 0, "group"),
                (
                    grid_path,
                    "group:datasets",
                    1,
                    "grid3d",
                ),
                (
                    (
                        f"{grid_path}/view:Water energy:"
                        f"{GRID_ID}:grid-r1"
                    ),
                    grid_path,
                    2,
                    "view",
                ),
                ("group:structures", None, 0, "group"),
                (
                    structure_path,
                    "group:structures",
                    1,
                    "structure",
                ),
                ("group:diagnostics", None, 0, "group"),
                (
                    f"group:diagnostics/diagnostic:{DIAGNOSTIC_ID}",
                    "group:diagnostics",
                    1,
                    "diagnostic",
                ),
            ],
        )

    def test_search_keeps_matching_descendant_ancestors(self):
        source_path = f"source:{SOURCE_ID}"
        revision_path = f"{source_path}/revision:{REVISION_ID}"
        rows = build_browser_rows(
            sample_project(),
            mode=BrowserMode.BY_SOURCE,
            session_id=SESSION_ID,
            browser_revision=1,
            search="DAMAGED",
            views=sample_views(),
        )

        self.assertEqual(
            [row.id for row in rows],
            [
                source_path,
                revision_path,
                f"{revision_path}/diagnostic:{DIAGNOSTIC_ID}",
            ],
        )

    def test_projection_never_materializes_array_values(self):
        project = sample_project()
        for mode in BrowserMode:
            with self.subTest(mode=mode):
                rows = build_browser_rows(
                    project,
                    mode=mode,
                    session_id=SESSION_ID,
                    browser_revision=1,
                    search="energy",
                    views=sample_views(),
                )
                self.assertTrue(rows)

    def test_cache_key_includes_revision_project_and_view_fingerprint(self):
        project = sample_project()
        keywords = {
            "mode": BrowserMode.BY_DATA,
            "session_id": SESSION_ID,
            "views": sample_views(),
        }

        first = build_browser_rows(project, browser_revision=4, **keywords)
        repeated = build_browser_rows(project, browser_revision=4, **keywords)
        refreshed = build_browser_rows(project, browser_revision=5, **keywords)
        changed_view = build_browser_rows(
            project,
            browser_revision=4,
            **(keywords | {"views": (ViewRecord(
                object_name="Alternate view",
                entity_id=GRID_ID,
                revision="grid-r1",
                view_kind="volume",
                label="Alternate density",
            ),)}),
        )
        replacement = sample_project()
        replaced = build_browser_rows(
            replacement,
            browser_revision=4,
            **keywords,
        )

        self.assertIs(first, repeated)
        self.assertIsNot(first, refreshed)
        self.assertIsNot(first, changed_view)
        self.assertIsNot(first, replaced)
        self.assertEqual(first, refreshed)

    def test_cache_normalizes_search_and_filters(self):
        project = sample_project()

        first = build_browser_rows(
            project,
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=1,
            search="  DENSITY ",
            filters=("PARTIAL", "grid3d"),
            views=sample_views(),
        )
        normalized = build_browser_rows(
            project,
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=1,
            search="density",
            filters=("grid3d", "partial", "partial"),
            views=sample_views(),
        )

        self.assertEqual(first, normalized)

    def test_cache_keeps_only_current_projection_for_a_browser_scope(self):
        project = sample_project()
        model = importlib.import_module(
            "ChemBlender.ui.project_browser.model"
        )
        model._CACHE.clear()

        for revision in range(40):
            build_browser_rows(
                project,
                mode=BrowserMode.BY_DATA,
                session_id=SESSION_ID,
                browser_revision=revision,
                views=sample_views(),
            )

        scoped = tuple(
            key
            for key in model._CACHE
            if (
                key[0] == id(project)
                and key[2] == SESSION_ID
                and key[4] is BrowserMode.BY_DATA
            )
        )
        self.assertEqual(len(scoped), 1)
        self.assertEqual(scoped[0][3], 39)

    def test_filter_reuses_cached_unfiltered_projection(self):
        project = sample_project()
        model = importlib.import_module(
            "ChemBlender.ui.project_browser.model"
        )
        keywords = {
            "mode": BrowserMode.BY_DATA,
            "session_id": SESSION_ID,
            "browser_revision": 9876,
            "views": sample_views(),
        }

        with patch.object(
            model,
            "_by_data",
            wraps=model._by_data,
        ) as project_rows:
            build_browser_rows(project, **keywords)
            filtered = build_browser_rows(
                project,
                search="density",
                **keywords,
            )

        self.assertEqual(project_rows.call_count, 1)
        self.assertTrue(any(row.label == "Electron Density" for row in filtered))

    def test_filter_keeps_only_matching_entities_views_and_ancestors(self):
        grid_path = f"group:datasets/entity:{GRID_ID}"
        rows = build_browser_rows(
            sample_project(),
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=1,
            filters=("grid3d",),
            views=sample_views(),
        )

        self.assertEqual(
            [row.id for row in rows],
            [
                "group:datasets",
                grid_path,
                (
                    f"{grid_path}/view:Water energy:"
                    f"{GRID_ID}:grid-r1"
                ),
            ],
        )
        empty = build_browser_rows(
            sample_project(),
            mode=BrowserMode.BY_DATA,
            session_id=SESSION_ID,
            browser_revision=1,
            filters=("missing_kind",),
            views=sample_views(),
        )
        self.assertEqual([row.kind for row in empty], ["empty"])

    def test_equivalent_view_sets_share_deterministic_cache_and_order(self):
        project = sample_project()
        alternate = ViewRecord(
            object_name="Alternate density",
            entity_id=GRID_ID,
            revision="grid-r1",
            view_kind="volume",
            label="Alternate density",
        )
        keywords = {
            "mode": BrowserMode.BY_DATA,
            "session_id": SESSION_ID,
            "browser_revision": 1,
        }

        first = build_browser_rows(
            project,
            views=(sample_views()[0], alternate),
            **keywords,
        )
        reordered = build_browser_rows(
            project,
            views=(alternate, sample_views()[0]),
            **keywords,
        )

        self.assertIs(first, reordered)
        self.assertEqual(
            [row.label for row in first if row.kind == "view"],
            ["Alternate density", "Density view"],
        )

    def test_empty_project_has_one_deterministic_row_in_both_modes(self):
        project = QCProject(PROJECT_ID, "0.2")

        for mode in BrowserMode:
            with self.subTest(mode=mode):
                plain = build_browser_rows(
                    project,
                    mode=mode,
                    session_id=SESSION_ID,
                    browser_revision=1,
                )
                filtered = build_browser_rows(
                    project,
                    mode=mode,
                    session_id=SESSION_ID,
                    browser_revision=1,
                    search="missing",
                    filters=("invalid",),
                )
                repeated = build_browser_rows(
                    project,
                    mode=mode,
                    session_id=SESSION_ID,
                    browser_revision=1,
                )

                self.assertEqual(len(plain), 1)
                self.assertEqual(plain[0].kind, "empty")
                self.assertEqual(filtered, plain)
                self.assertIs(repeated, plain)

    def test_views_require_current_revision_and_revision_invalidates_cache(self):
        project = sample_project()
        current = sample_views()[0]
        stale = ViewRecord(
            object_name=current.object_name,
            entity_id=current.entity_id,
            revision="grid-r0",
            view_kind=current.view_kind,
            label=current.label,
        )
        keywords = {
            "mode": BrowserMode.BY_DATA,
            "session_id": SESSION_ID,
            "browser_revision": 1,
        }

        current_rows = build_browser_rows(
            project,
            views=(current,),
            **keywords,
        )
        stale_rows = build_browser_rows(
            project,
            views=(stale,),
            **keywords,
        )

        self.assertEqual(
            [row.kind for row in current_rows].count("view"),
            1,
        )
        self.assertEqual(
            [row.kind for row in stale_rows].count("view"),
            0,
        )
        self.assertIsNot(current_rows, stale_rows)
        with self.assertRaises((TypeError, ValueError)):
            ViewRecord(
                object_name="Density",
                entity_id=GRID_ID,
                revision="",
                view_kind="volume",
                label="Density",
            )


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _PropertyGroup:
    pass


class _UIList:
    pass


class _Panel:
    pass


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class _Scene:
    pass


class ProjectBrowserBlenderContractTests(unittest.TestCase):
    def setUp(self):
        self.fake_bpy = ModuleType("bpy")
        self.fake_props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("CollectionProperty", "collection"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("IntProperty", "int"),
            ("PointerProperty", "pointer"),
            ("StringProperty", "string"),
        ):
            setattr(self.fake_props, name, _property(kind))
        self.fake_bpy.props = self.fake_props
        self.fake_bpy.types = SimpleNamespace(
            Panel=_Panel,
            Operator=_Operator,
            PropertyGroup=_PropertyGroup,
            Scene=_Scene,
            UIList=_UIList,
        )
        self.modules = patch.dict(
            sys.modules,
            {"bpy": self.fake_bpy, "bpy.props": self.fake_props},
        )
        self.modules.start()
        for name in (
            "ChemBlender.ui.project_browser.panel",
            "ChemBlender.ui.properties",
            "ChemBlender.ui.scientific_edit",
            "ChemBlender.ui.topology",
        ):
            sys.modules.pop(name, None)

    def tearDown(self):
        panel = sys.modules.get("ChemBlender.ui.project_browser.panel")
        if panel is not None:
            panel.unregister()
        self.modules.stop()
        for name in (
            "ChemBlender.ui.project_browser.panel",
            "ChemBlender.ui.properties",
            "ChemBlender.ui.scientific_edit",
            "ChemBlender.ui.topology",
        ):
            sys.modules.pop(name, None)
        if hasattr(_Scene, "chemblender_project_browser"):
            del _Scene.chemblender_project_browser
        if hasattr(_Scene, "chemblender_topology"):
            del _Scene.chemblender_topology

    def test_rna_projection_contains_only_small_values(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        row_properties = panel.CHEMBLENDER_PG_project_browser_row.__annotations__
        state_properties = (
            panel.CHEMBLENDER_PG_project_browser.__annotations__
        )
        self.assertEqual(
            {value.kind for value in row_properties.values()},
            {"int", "string"},
        )
        self.assertEqual(
            {value.kind for value in state_properties.values()},
            {"collection", "enum", "int", "string"},
        )
        quality = state_properties["quality_filter"]
        self.assertEqual(quality.keywords["default"], "all")
        self.assertTrue(
            all(identifier for identifier, _label, _description in quality.keywords["items"])
        )

    def test_crystal_symmetry_sections_survive_missing_spglib(self):
        properties = importlib.import_module("ChemBlender.ui.properties")
        structure = Structure(
            id=STRUCTURE_ID,
            revision="periodic-r1",
            atomic_numbers=(14,),
            coordinates=ArrayData(
                numpy.zeros((1, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
            cell=ArrayData(
                numpy.eye(3),
                ("cell_vector", "xyz"),
                "angstrom",
            ),
            periodic=PeriodicSiteData(
                fractional_coordinates=ArrayData(
                    numpy.zeros((1, 3)),
                    ("atom", "xyz"),
                    "dimensionless",
                ),
                site_labels=("Si1",),
                occupancies=ArrayData(
                    numpy.ones(1),
                    ("atom",),
                    "dimensionless",
                ),
                isotropic_displacements=None,
                anisotropic_displacements=None,
                adp_types=("none",),
                disorder_groups=(0,),
                declared_space_group_name="P 1",
                declared_space_group_number=1,
                symmetry_operations=("x,y,z",),
                cif_envelope_id=None,
                declared_hall_symbol="P 1",
            ),
        )
        with patch.object(
            properties,
            "symmetry_availability",
            return_value=(False, "spglib is not installed"),
        ):
            sections = properties.crystal_symmetry_property_sections(
                structure
            )
        self.assertEqual(
            sections["declared"],
            (
                ("Name", "P 1"),
                ("International number", "1"),
                ("Hall symbol", "P 1"),
                ("Operations", "1"),
            ),
        )
        self.assertEqual(
            sections["derived"][0],
            ("International", "Not derived"),
        )
        self.assertFalse(sections["derive_available"])
        self.assertIn("not installed", sections["dependency_reason"])
        self.assertEqual(
            sections["comparison"][0],
            ("Status", "Not derived"),
        )

    def test_standardized_structure_view_keeps_source_view(self):
        properties = importlib.import_module("ChemBlender.ui.properties")
        source = sample_project().structures[STRUCTURE_ID]
        standard = Structure(
            id=UUID("30000000-0000-0000-0000-000000000099"),
            revision="standard-r1",
            atomic_numbers=source.atomic_numbers,
            coordinates=ArrayData(
                numpy.zeros((1, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
            cell=ArrayData(
                numpy.eye(3),
                ("cell_vector", "xyz"),
                "angstrom",
            ),
            periodic=PeriodicSiteData(
                fractional_coordinates=ArrayData(
                    numpy.zeros((1, 3)),
                    ("atom", "xyz"),
                    "dimensionless",
                ),
                site_labels=("O1",),
                occupancies=ArrayData(
                    numpy.ones(1),
                    ("atom",),
                    "dimensionless",
                ),
                isotropic_displacements=None,
                anisotropic_displacements=None,
                adp_types=("none",),
                disorder_groups=(0,),
                declared_space_group_name=None,
                declared_space_group_number=None,
                symmetry_operations=(),
                cif_envelope_id=None,
            ),
        )
        result = object.__new__(SymmetryResult)
        result_id = UUID("40000000-0000-0000-0000-000000000099")
        object.__setattr__(result, "id", result_id)
        object.__setattr__(result, "standardized_structure_id", standard.id)
        project = SimpleNamespace(
            symmetry_results={result_id: result},
            structures={source.id: source, standard.id: standard},
            topologies={},
        )
        session = SimpleNamespace(
            project=project,
            active_entity_id=source.id,
            active_view_object_name="Source",
        )

        class View:
            name = "Standardized"

            def __init__(self):
                self.selected = False

            def select_get(self):
                return self.selected

            def select_set(self, value):
                self.selected = value

        source_view = View()
        source_view.name = "Source"
        standard_view = View()
        created = []

        def create_periodic_structure_view(structure, topology, **keywords):
            created.append((structure, topology, keywords))
            return standard_view

        fake_views = ModuleType("ChemBlender.views")
        fake_views.create_periodic_structure_view = (
            create_periodic_structure_view
        )
        fake_views.remove_structure_view = lambda _view: None
        browser = SimpleNamespace(active_entity_id=str(source.id))
        context = SimpleNamespace(
            scene=SimpleNamespace(
                chemblender_project_browser=browser,
            ),
            collection=object(),
            active_object=source_view,
            view_layer=SimpleNamespace(
                objects=SimpleNamespace(active=source_view),
            ),
        )
        operation = properties.CHEMBLENDER_OT_view_standardized_structure()
        operation.symmetry_result_id = str(result_id)
        with (
            patch.dict(sys.modules, {"ChemBlender.views": fake_views}),
            patch.object(
                properties,
                "get_scene_session",
                return_value=session,
            ),
            patch.object(properties, "advance_browser_revision") as advance,
        ):
            outcome = operation.execute(context)

        self.assertEqual(outcome, {"FINISHED"})
        self.assertEqual(created[0][0], standard)
        self.assertFalse(source_view.selected)
        self.assertTrue(standard_view.selected)
        self.assertEqual(session.active_entity_id, standard.id)
        self.assertEqual(session.active_view_object_name, standard_view.name)
        self.assertIs(context.view_layer.objects.active, standard_view)
        self.assertEqual(browser.active_entity_id, str(standard.id))
        advance.assert_called_once_with(session)

    def test_standardized_view_failure_removes_view_and_restores_source(self):
        properties = importlib.import_module("ChemBlender.ui.properties")
        source = SimpleNamespace(id=STRUCTURE_ID)
        standard_id = UUID("30000000-0000-0000-0000-000000000098")
        standard = SimpleNamespace(
            id=standard_id,
            topology_ids=(),
            periodic=object(),
        )
        result_id = UUID("40000000-0000-0000-0000-000000000098")
        result = object.__new__(SymmetryResult)
        object.__setattr__(result, "id", result_id)
        object.__setattr__(result, "standardized_structure_id", standard_id)
        project = SimpleNamespace(
            symmetry_results={result_id: result},
            structures={STRUCTURE_ID: source, standard_id: standard},
            topologies={},
        )
        session = SimpleNamespace(
            project=project,
            active_entity_id=STRUCTURE_ID,
            active_view_object_name="Source",
        )

        class View:
            def __init__(self, name):
                self.name = name
                self.selected = True

            def select_get(self):
                return self.selected

            def select_set(self, value):
                self.selected = value

        source_view = View("Source")
        standard_view = View("Standardized")
        removed = []
        fake_views = ModuleType("ChemBlender.views")
        browser = SimpleNamespace(active_entity_id=str(STRUCTURE_ID))
        fake_views.remove_structure_view = removed.append
        context = SimpleNamespace(
            scene=SimpleNamespace(
                chemblender_project_browser=browser,
            ),
            collection=object(),
            active_object=source_view,
            view_layer=SimpleNamespace(
                objects=SimpleNamespace(active=source_view),
            ),
        )

        def create_periodic_structure_view(*_args, **_keywords):
            context.active_object = standard_view
            context.view_layer.objects.active = standard_view
            return standard_view

        fake_views.create_periodic_structure_view = (
            create_periodic_structure_view
        )
        operation = properties.CHEMBLENDER_OT_view_standardized_structure()
        operation.symmetry_result_id = str(result_id)
        with (
            patch.dict(sys.modules, {"ChemBlender.views": fake_views}),
            patch.object(
                properties,
                "get_scene_session",
                return_value=session,
            ),
            patch.object(
                properties,
                "Structure",
                SimpleNamespace,
            ),
            patch.object(
                properties,
                "advance_browser_revision",
                side_effect=RuntimeError("refresh failed"),
            ),
        ):
            outcome = operation.execute(context)

        self.assertEqual(outcome, {"CANCELLED"})
        self.assertEqual(removed, [standard_view])
        self.assertEqual(session.active_entity_id, STRUCTURE_ID)
        self.assertEqual(session.active_view_object_name, "Source")
        self.assertEqual(browser.active_entity_id, str(STRUCTURE_ID))
        self.assertTrue(source_view.selected)
        self.assertIs(context.view_layer.objects.active, source_view)

    def test_symmetry_derivation_invalidates_browser_projection(self):
        properties = importlib.import_module("ChemBlender.ui.properties")
        structure = SimpleNamespace(id=STRUCTURE_ID, periodic=object())
        committed = []
        dirty = []
        project = SimpleNamespace(
            structures={STRUCTURE_ID: structure},
            symmetry_results={},
            commit=committed.append,
        )
        session = SimpleNamespace(
            project=project,
            active_entity_id=STRUCTURE_ID,
            mark_dirty=dirty.append,
        )
        context = SimpleNamespace(scene=object())
        operation = properties.CHEMBLENDER_OT_derive_crystal_symmetry()
        operation.symprec = 2.0e-5
        operation.angle_tolerance = 0.5
        batch = object()
        with (
            patch.object(
                properties,
                "get_scene_session",
                return_value=session,
            ),
            patch.object(properties, "Structure", SimpleNamespace),
            patch.object(
                properties,
                "symmetry_availability",
                return_value=(True, ""),
            ),
            patch.object(
                properties,
                "derive_structure_symmetry",
                return_value=batch,
            ),
            patch.object(properties, "advance_browser_revision") as advance,
        ):
            outcome = operation.execute(context)

        self.assertEqual(outcome, {"FINISHED"})
        self.assertEqual(committed, [batch])
        self.assertEqual(dirty, ["symmetry"])
        advance.assert_called_once_with(session)

    def test_topology_and_scientific_edit_classes_have_explicit_roots(self):
        registration = importlib.import_module(
            "ChemBlender.runtime.registration"
        )
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        modules = tuple(
            importlib.import_module(name)
            for name in (
                "ChemBlender.ui.topology",
                "ChemBlender.ui.scientific_edit",
            )
        )

        self.assertTrue(
            {
                ".ui.topology",
                ".ui.scientific_edit",
            }.issubset(registration.REGISTER_MODULE_NAMES)
        )
        for module in modules:
            classes = tuple(
                value
                for name, value in vars(module).items()
                if name.startswith(("CHEMBLENDER_OT_", "CHEMBLENDER_PG_"))
            )
            self.assertTrue(classes)
            self.assertTrue(
                all(cls.__module__ == module.__name__ for cls in classes)
            )
            self.assertFalse(
                any(value in classes for value in vars(panel).values())
            )

    def test_panel_ignores_stale_ui_module_aliases(self):
        ui_package = importlib.import_module("ChemBlender.ui")
        stale_topology = ModuleType("ChemBlender.ui.topology")
        stale_scientific_edit = ModuleType(
            "ChemBlender.ui.scientific_edit"
        )
        with (
            patch.object(
                ui_package,
                "topology",
                stale_topology,
                create=True,
            ),
            patch.object(
                ui_package,
                "scientific_edit",
                stale_scientific_edit,
                create=True,
            ),
        ):
            panel = importlib.import_module(
                "ChemBlender.ui.project_browser.panel"
            )

        self.assertIsNot(panel._topology, stale_topology)
        self.assertIsNot(panel._scientific_edit, stale_scientific_edit)
        self.assertTrue(
            hasattr(
                panel._topology,
                "CHEMBLENDER_PG_topology_settings",
            )
        )
        self.assertTrue(
            hasattr(
                panel._scientific_edit,
                "CHEMBLENDER_OT_apply_scientific_edits",
            )
        )

    def test_ui_list_draws_indentation_icon_quality_and_view_count(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        labels = []

        class Layout:
            def row(self, *, align):
                self.align = align
                return self

            def label(self, **keywords):
                labels.append(keywords)

        item = SimpleNamespace(
            depth=2,
            label="Density",
            kind="grid3d",
            quality="partial",
            view_count=3,
        )

        panel.CHEMBLENDER_UL_project_rows().draw_item(
            None,
            Layout(),
            None,
            item,
            0,
            None,
            "",
        )

        self.assertEqual(
            labels,
            [
                {"text": "    Density (3)", "icon": "VOLUME_DATA"},
                {"text": "Partial"},
            ],
        )

    def test_selection_writes_only_scientific_entity_id_to_session(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        session = SimpleNamespace(
            project=sample_project(),
            active_entity_id=None,
        )
        state = SimpleNamespace(
            rows=[
                SimpleNamespace(entity_id=str(GRID_ID)),
                SimpleNamespace(entity_id=""),
            ],
            selected_index=0,
            active_entity_id="",
        )

        panel.synchronize_browser_selection(session, state)
        self.assertEqual(session.active_entity_id, GRID_ID)
        self.assertEqual(state.active_entity_id, str(GRID_ID))
        state.selected_index = 1
        panel.synchronize_browser_selection(session, state)
        self.assertIsNone(session.active_entity_id)
        self.assertEqual(state.active_entity_id, "")

    def test_selection_rejects_malformed_and_stale_entity_ids(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        session = SimpleNamespace(
            project=sample_project(),
            active_entity_id=GRID_ID,
        )
        state = SimpleNamespace(
            rows=[
                SimpleNamespace(entity_id="not-a-uuid"),
                SimpleNamespace(
                    entity_id="50000000-0000-0000-0000-000000000001"
                ),
            ],
            selected_index=0,
            active_entity_id=str(GRID_ID),
        )

        panel.synchronize_browser_selection(session, state)
        self.assertIsNone(session.active_entity_id)
        self.assertEqual(state.active_entity_id, "")
        state.selected_index = 1
        panel.synchronize_browser_selection(session, state)
        self.assertIsNone(session.active_entity_id)
        self.assertEqual(state.active_entity_id, "")

    def test_selected_force_projects_only_the_active_trajectory_frame(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        structure, dataset, values = panel.atom_frame_vector(
            sample_trajectory_project(),
            FORCE_ID,
            1,
        )

        self.assertEqual(structure.id, STRUCTURE_ID)
        self.assertEqual(structure.revision, "structure-r1")
        self.assertEqual(dataset.id, FORCE_ID)
        numpy.testing.assert_array_equal(values, [[4.0, 5.0, 6.0]])

    def test_force_operator_rejects_missing_or_stale_structure_view(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class ViewObject(dict):
            name = "Water trajectory"

        for missing_structure, revision in (
            (True, "structure-r1"),
            (False, "stale-structure-r0"),
        ):
            with self.subTest(
                missing_structure=missing_structure,
                revision=revision,
            ):
                project = sample_trajectory_project()
                if missing_structure:
                    project.structures.pop(STRUCTURE_ID)
                obj = ViewObject(
                    cb_structure_contract="structure_view_v1",
                    cb_structure_id=str(STRUCTURE_ID),
                    cb_structure_revision=revision,
                    cb_trajectory_frame_index=1,
                )
                session = SimpleNamespace(
                    project=project,
                    active_entity_id=FORCE_ID,
                    active_view_object_name=obj.name,
                )
                context = SimpleNamespace(
                    scene=SimpleNamespace(objects={obj.name: obj}),
                    active_object=obj,
                )
                operation = panel.CHEMBLENDER_OT_apply_frame_force()
                operation.display_scale = 1.0
                with (
                    patch.object(
                        panel,
                        "get_scene_session",
                        return_value=session,
                    ),
                    patch.object(panel, "write_vector_view") as writer,
                ):
                    result = operation.execute(context)

                self.assertEqual(result, {"CANCELLED"})
                writer.assert_not_called()

    def test_force_operator_applies_selected_frame_to_active_structure_view(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class ViewObject(dict):
            name = "Water trajectory"

        obj = ViewObject(
            cb_structure_contract="structure_view_v1",
            cb_structure_id=str(STRUCTURE_ID),
            cb_structure_revision="structure-r1",
            cb_trajectory_frame_index=1,
        )
        session = SimpleNamespace(
            project=sample_trajectory_project(),
            active_entity_id=FORCE_ID,
            active_view_object_name=obj.name,
        )
        context = SimpleNamespace(
            scene=SimpleNamespace(objects={obj.name: obj}),
            active_object=obj,
        )

        def write_vector(view, values, **keywords):
            view["displayed_vectors"] = (
                numpy.asarray(values) * keywords["display_scale"]
            )
            view["vector_dataset_id"] = str(keywords["dataset_id"])
            return object()

        operation = panel.CHEMBLENDER_OT_apply_frame_force()
        operation.display_scale = 0.5
        with (
            patch.object(panel, "get_scene_session", return_value=session),
            patch.object(panel, "write_vector_view", write_vector),
        ):
            result = operation.execute(context)

        self.assertEqual(result, {"FINISHED"})
        numpy.testing.assert_array_equal(
            obj["displayed_vectors"],
            [[2.0, 2.5, 3.0]],
        )
        self.assertEqual(obj["vector_dataset_id"], str(FORCE_ID))

    def test_refresh_preserves_selection_hidden_by_search(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class Rows(list):
            def clear(self):
                super().clear()

            def add(self):
                row = SimpleNamespace()
                self.append(row)
                return row

        session = SimpleNamespace(
            id="session",
            project=sample_project(),
            active_entity_id=GRID_ID,
        )
        settings = SimpleNamespace(
            mode="by_data",
            search="unrelated",
            quality_filter="all",
            selected_index=3,
            active_entity_id=str(GRID_ID),
            rows=Rows(),
        )
        scene = SimpleNamespace(
            chemblender_project_browser=settings,
            objects=(),
        )
        empty = BrowserRow(
            id="empty",
            parent_id=None,
            depth=0,
            kind="empty",
            label="No matching project data",
            quality="",
            view_count=0,
            entity_id=None,
        )
        with (
            patch.object(panel, "get_scene_session", return_value=session),
            patch.object(
                panel,
                "get_quick_import_state",
                return_value=SimpleNamespace(browser_revision=1),
            ),
            patch.object(panel, "build_browser_rows", return_value=(empty,)),
        ):
            panel.refresh_project_browser(scene)

        self.assertEqual(session.active_entity_id, GRID_ID)
        self.assertEqual(settings.active_entity_id, str(GRID_ID))

    def test_refresh_bounds_rna_rows_and_records_total_count(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class Rows(list):
            def add(self):
                row = SimpleNamespace()
                self.append(row)
                return row

        limit = 1000
        rows = tuple(
            BrowserRow(
                id=f"row-{index}",
                parent_id=None,
                depth=0,
                kind="molecular_record",
                label=f"Record {index}",
                quality="complete",
                view_count=0,
                entity_id=None,
            )
            for index in range(limit + 5)
        )
        session = SimpleNamespace(
            id="session",
            project=sample_project(),
            active_entity_id=None,
        )
        settings = SimpleNamespace(
            mode="by_data",
            search="",
            quality_filter="all",
            selected_index=0,
            active_entity_id="",
            rows=Rows(),
        )
        scene = SimpleNamespace(
            chemblender_project_browser=settings,
            objects=(),
        )

        with (
            patch.object(panel, "get_scene_session", return_value=session),
            patch.object(
                panel,
                "get_quick_import_state",
                return_value=SimpleNamespace(browser_revision=1),
            ),
            patch.object(panel, "build_browser_rows", return_value=rows),
        ):
            projected = panel.refresh_project_browser(scene)

        self.assertEqual(panel._BROWSER_RNA_ROW_LIMIT, limit)
        self.assertEqual(len(projected), limit + 5)
        self.assertEqual(len(settings.rows), limit)
        self.assertEqual(settings.total_row_count, limit + 5)

    def test_refresh_clears_stale_and_malformed_hidden_selection(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class Rows(list):
            def clear(self):
                super().clear()

            def add(self):
                row = SimpleNamespace()
                self.append(row)
                return row

        empty = BrowserRow(
            id="empty",
            parent_id=None,
            depth=0,
            kind="empty",
            label="No project data",
            quality="",
            view_count=0,
            entity_id=None,
        )
        for selected_id in (str(GRID_ID), "not-a-uuid"):
            with self.subTest(selected_id=selected_id):
                session = SimpleNamespace(
                    id="session",
                    project=QCProject(PROJECT_ID, "0.2"),
                    active_entity_id=GRID_ID,
                )
                settings = SimpleNamespace(
                    mode="by_data",
                    search="",
                    quality_filter="all",
                    selected_index=2,
                    active_entity_id=selected_id,
                    rows=Rows(),
                )
                scene = SimpleNamespace(
                    chemblender_project_browser=settings,
                    objects=(),
                )
                with (
                    patch.object(
                        panel,
                        "get_scene_session",
                        return_value=session,
                    ),
                    patch.object(
                        panel,
                        "get_quick_import_state",
                        return_value=SimpleNamespace(browser_revision=1),
                    ),
                    patch.object(
                        panel,
                        "build_browser_rows",
                        return_value=(empty,),
                    ),
                ):
                    panel.refresh_project_browser(scene)

                self.assertIsNone(session.active_entity_id)
                self.assertEqual(settings.active_entity_id, "")

    def test_scene_metadata_becomes_presentation_only_view_records(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class ViewObject(dict):
            name = "Density object"

        obj = ViewObject(
            cb_scene_view_kind="grid_volume",
            cb_scene_bindings_json=json.dumps(
                {
                    "grid": {
                        "entity_id": str(GRID_ID),
                        "revision": "grid-r1",
                    }
                }
            ),
        )
        scene = SimpleNamespace(objects=(obj,))

        self.assertEqual(
            panel.presentation_view_records(scene),
            (
                ViewRecord(
                    object_name="Density object",
                    entity_id=GRID_ID,
                    revision="grid-r1",
                    view_kind="grid_volume",
                    label="Density object",
                ),
            ),
        )

    def test_duplicate_scene_bindings_produce_one_view_record(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class ViewObject(dict):
            name = "Density object"

        binding = {
            "entity_id": str(GRID_ID),
            "revision": "grid-r1",
        }
        obj = ViewObject(
            cb_scene_view_kind="volume",
            cb_scene_bindings_json=json.dumps(
                {"grid": binding, "primary_grid": binding}
            ),
        )

        self.assertEqual(
            panel.presentation_view_records(
                SimpleNamespace(objects=(obj,))
            ),
            (
                ViewRecord(
                    object_name="Density object",
                    entity_id=GRID_ID,
                    revision="grid-r1",
                    view_kind="volume",
                    label="Density object",
                ),
            ),
        )

    def test_scene_view_parser_rejects_malformed_exact_fields(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class ViewObject(dict):
            name = "Density object"

        invalid_metadata = (
            (
                "",
                {"grid": {"entity_id": str(GRID_ID), "revision": "grid-r1"}},
            ),
            (
                " ",
                {"grid": {"entity_id": str(GRID_ID), "revision": "grid-r1"}},
            ),
            (
                "volume",
                {"grid": {"entity_id": "", "revision": "grid-r1"}},
            ),
            (
                "volume",
                {"grid": {"entity_id": 1, "revision": "grid-r1"}},
            ),
            (
                "volume",
                {"grid": {"entity_id": str(GRID_ID), "revision": ""}},
            ),
            (
                "volume",
                {"grid": {"entity_id": str(GRID_ID), "revision": " "}},
            ),
            (
                "volume",
                {"grid": {"entity_id": str(GRID_ID), "revision": 1}},
            ),
            (
                "volume",
                {
                    "grid": {
                        "entity_id": str(GRID_ID),
                        "revision": "grid-r1",
                        "extra": True,
                    }
                },
            ),
        )

        for view_kind, bindings in invalid_metadata:
            with self.subTest(view_kind=view_kind, bindings=bindings):
                obj = ViewObject(
                    cb_scene_view_kind=view_kind,
                    cb_scene_bindings_json=json.dumps(bindings),
                )
                self.assertEqual(
                    panel.presentation_view_records(
                        SimpleNamespace(objects=(obj,))
                    ),
                    (),
                )

    def test_single_revision_helper_invalidates_browser_state(self):
        properties = importlib.import_module("ChemBlender.ui.properties")
        with TemporaryDirectory() as directory:
            from ChemBlender.core import close_session, create_session

            session = create_session(temp_parent=Path(directory))
            try:
                state = properties.get_quick_import_state(session)
                self.assertEqual(state.browser_revision, 0)
                self.assertEqual(
                    properties.advance_browser_revision(session),
                    1,
                )
                self.assertEqual(
                    properties.advance_browser_revision(session),
                    2,
                )
                self.assertEqual(state.browser_revision, 2)
            finally:
                properties.clear_quick_import_state(session)
                close_session(session)

    def test_scene_property_registration_is_foreign_safe_and_reversible(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        panel.register()
        owned = _Scene.chemblender_project_browser
        panel.register()
        self.assertIs(_Scene.chemblender_project_browser, owned)
        panel.unregister()
        self.assertFalse(hasattr(_Scene, "chemblender_project_browser"))
        self.assertFalse(hasattr(_Scene, "chemblender_topology"))

        foreign = _Property("foreign")
        _Scene.chemblender_project_browser = foreign
        with self.assertRaisesRegex(RuntimeError, "already owned"):
            panel.register()
        panel.unregister()
        self.assertIs(_Scene.chemblender_project_browser, foreign)

    def test_post_set_verification_failure_rolls_back_cleanly(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        with patch.object(
            panel,
            "_scene_property_identity",
            side_effect=(None, None),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "registration failed",
            ) as caught:
                panel.register()

        self.assertFalse(
            hasattr(_Scene, "chemblender_project_browser")
        )
        self.assertIsNone(panel._OWNED_SCENE_PROPERTY)
        self.assertFalse(getattr(caught.exception, "__notes__", ()))

    def test_failed_registration_delete_is_noted_and_retryable(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        with (
            patch.object(
                panel,
                "_scene_property_identity",
                side_effect=(None, None),
            ),
            patch.object(
                panel,
                "delattr",
                side_effect=OSError("delete blocked"),
                create=True,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "registration failed",
            ) as caught:
                panel.register()

        self.assertTrue(
            any(
                "rollback failed: delete blocked" in note
                for note in caught.exception.__notes__
            )
        )
        self.assertIsNotNone(panel._OWNED_SCENE_PROPERTY)
        self.assertTrue(
            hasattr(_Scene, "chemblender_project_browser")
        )

        panel.unregister()

        self.assertIsNone(panel._OWNED_SCENE_PROPERTY)
        self.assertFalse(
            hasattr(_Scene, "chemblender_project_browser")
        )

    def test_registration_rollback_preserves_foreign_replacement(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        foreign = _Property("foreign-during-rollback")
        call_count = 0

        def identity_probe(_name):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                _Scene.chemblender_project_browser = foreign
            return None

        with patch.object(
            panel,
            "_scene_property_identity",
            side_effect=identity_probe,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "registration failed",
            ) as caught:
                panel.register()

        self.assertIs(
            _Scene.chemblender_project_browser,
            foreign,
        )
        self.assertIsNone(panel._OWNED_SCENE_PROPERTY)
        self.assertTrue(
            any(
                "replaced before rollback" in note
                for note in caught.exception.__notes__
            )
        )

    def test_unregister_preserves_later_foreign_scene_property(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

    def test_surface_quality_and_report_eligibility_are_projected(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )

        class ViewObject(dict):
            name = "Raw Cube surface"

        obj = ViewObject(
            cb_scene_view_kind="signed_isosurface",
            cb_scene_bindings_json=json.dumps(
                {
                    "grid": {
                        "entity_id": str(GRID_ID),
                        "revision": "grid-r1",
                    }
                }
            ),
            cb_view_quality="ambiguous",
            cb_report_eligible=True,
        )

        record, = panel.presentation_view_records(
            SimpleNamespace(objects=(obj,))
        )
        self.assertEqual(record.quality, "ambiguous")
        self.assertFalse(record.report_eligible)
        panel.register()
        foreign = _Property("replacement")
        _Scene.chemblender_project_browser = foreign

        panel.unregister()

        self.assertIs(_Scene.chemblender_project_browser, foreign)

    def test_register_detects_later_foreign_topology_property(self):
        panel = importlib.import_module(
            "ChemBlender.ui.project_browser.panel"
        )
        panel.register()
        foreign = _Property("replacement")
        _Scene.chemblender_topology = foreign

        with self.assertRaisesRegex(
            RuntimeError,
            "chemblender_topology.*no longer owned",
        ):
            panel.register()
        panel.unregister()

        self.assertIs(_Scene.chemblender_topology, foreign)


if __name__ == "__main__":
    unittest.main()
