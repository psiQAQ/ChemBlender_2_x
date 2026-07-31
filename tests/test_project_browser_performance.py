"""Project Browser paging and filter performance contracts."""

import math
from dataclasses import replace
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
from unittest import TestCase
from uuid import UUID, NAMESPACE_URL, uuid5

import numpy

import ChemBlender.ui.project_browser.model as browser_model
from ChemBlender.benchmarks.datasets import generate_sdf_fixture
from ChemBlender.core.formats.sdf import iter_sdf_file_records
from ChemBlender.core.model import (
    ArrayData,
    DatasetStatus,
    Grid3D,
    MolecularRecord,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)
from ChemBlender.core.model.sources import SourceRecord, SourceRevision
from ChemBlender.core.sidecar import LazyNpyArray, _array_content_hash
from ChemBlender.ui.project_browser import (
    BrowserMode,
    ViewRecord,
    build_browser_rows,
)


PROJECT_ID = UUID("b0000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("b0000000-0000-0000-0000-000000000002")
SOURCE_REVISION_ID = UUID("b0000000-0000-0000-0000-000000000003")
GRID_ID = UUID("b0000000-0000-0000-0000-000000000004")
SESSION_ID = UUID("b0000000-0000-0000-0000-000000000005")
STRUCTURE_ID = UUID("b0000000-0000-0000-0000-000000000006")
TOPOLOGY_ID = UUID("b0000000-0000-0000-0000-000000000007")


def _project_with_indexed_records(root, record_count):
    """Use the production SDF boundary index without parsing every record."""
    fixture = generate_sdf_fixture(root / "records.sdf", record_count=record_count)
    boundaries = tuple(iter_sdf_file_records(fixture.path))
    source = SourceRecord(
        SOURCE_ID,
        "Browser benchmark SDF",
        "local_file",
        "2026-07-31T00:00:00Z",
    )
    records = {}
    for boundary in boundaries:
        record_id = uuid5(
            SOURCE_REVISION_ID,
            f"browser-record:{boundary.index}:{boundary.raw_hash}",
        )
        records[record_id] = MolecularRecord(
            record_id,
            boundary.raw_hash,
            SOURCE_REVISION_ID,
            f"record-{boundary.index:06d}",
            STRUCTURE_ID,
            TOPOLOGY_ID,
            b"",
            f"benchmark-{boundary.index:06d}",
            boundary.index,
            "V2000",
            None,
            None,
            (),
            (),
        )
    revision = SourceRevision(
        SOURCE_REVISION_ID,
        SOURCE_ID,
        fixture.sha256,
        fixture.path.stat().st_size,
        str(fixture.path),
        "local_file",
        fixture.path.name,
        "chemblender.builtin",
        "sdf",
        "1",
        "0.1",
        "0" * 64,
        "1" * 64,
        (*records, STRUCTURE_ID, TOPOLOGY_ID, GRID_ID),
        (),
    )
    structure = Structure(
        STRUCTURE_ID,
        "structure-r1",
        (),
        ArrayData(
            numpy.empty((0, 3), dtype=numpy.float32),
            ("atom", "xyz"),
            "angstrom",
        ),
        topology_ids=(TOPOLOGY_ID,),
    )
    topology = TopologyRecord(
        TOPOLOGY_ID,
        "topology-r1",
        STRUCTURE_ID,
        ArrayData(
            numpy.empty((0, 2), dtype=numpy.int64),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        ArrayData(
            numpy.empty((0,), dtype=numpy.float64),
            ("bond",),
            "dimensionless",
        ),
        None,
        (),
        TopologySource.EXPLICIT_FILE,
        QualityStatus.COMPLETE,
        (),
        (),
    )
    array_path = root / "lazy-grid.npy"
    values = numpy.lib.format.open_memmap(
        array_path, mode="w+", dtype=numpy.float32, shape=(2, 2, 2)
    )
    values.fill(0.0)
    values.flush()
    del values
    mapped = numpy.load(array_path, mmap_mode="r", allow_pickle=False)
    try:
        content_hash, _ = _array_content_hash(mapped)
    finally:
        mapped._mmap.close()
    lazy = LazyNpyArray(array_path, (2, 2, 2), "float32", content_hash)
    grid = Grid3D(
        GRID_ID,
        "grid-r1",
        "electron_density",
        "grid",
        ArrayData(lazy, ("x", "y", "z"), "dimensionless"),
        DatasetStatus.COMPLETE,
        None,
        (),
        (0.0, 0.0, 0.0),
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        "angstrom",
    )
    return (
        SimpleNamespace(
            id=PROJECT_ID,
            sources={source.id: source},
            source_revisions={revision.id: revision},
            structures={structure.id: structure},
            topologies={topology.id: topology},
            molecular_records=records,
            biological_hierarchies={},
            annotations={},
            external_references={},
            cif_envelopes={},
            qcschema_envelopes={},
            cjson_envelopes={},
            symmetry_results={},
            calculations={},
            datasets={grid.id: grid},
            basis_sets={},
            orbital_sets={},
            density_matrices={},
            provenance={},
            diagnostics={},
            calculation_groups={},
        ),
        lazy,
    )


def _p95(samples):
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


class ProjectBrowserPerformanceTests(TestCase):
    def test_page_arguments_require_exact_bounded_integers(self):
        with TemporaryDirectory() as directory:
            project, _lazy = _project_with_indexed_records(
                Path(directory), 10_000
            )
            self.assertTrue(build_browser_rows(project, page=0, page_size=1))
            for page in (True, -1, 1.0, "1"):
                with self.subTest(page=page), self.assertRaises(
                    (TypeError, ValueError)
                ):
                    build_browser_rows(project, page=page)
            for page_size in (True, 0, 999, 1000, 1001, 1.0, "100"):
                with self.subTest(page_size=page_size), self.assertRaises(
                    (TypeError, ValueError)
                ):
                    build_browser_rows(project, page_size=page_size)

    def test_large_record_group_pages_before_materializing_rows(self):
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(Path(directory), 10_000)
            rows = build_browser_rows(
                project,
                mode=BrowserMode.BY_DATA,
                session_id=SESSION_ID,
                browser_revision=1,
                page=2,
                page_size=64,
            )

        records = [row for row in rows if row.kind == "molecular_record"]
        summary = next(row for row in rows if row.kind == "record_page")
        self.assertEqual(len(records), 64)
        self.assertEqual(records[0].label, "benchmark-000128 · V2000")
        self.assertEqual(records[-1].label, "benchmark-000191 · V2000")
        self.assertEqual(summary.total_count, 10_000)
        self.assertEqual(summary.page, 2)
        self.assertEqual(summary.page_count, 157)
        self.assertLess(len(rows), 80)
        self.assertFalse(lazy.loaded)

    def test_large_source_projection_keeps_bounded_source_ancestors(self):
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(
                Path(directory), 10_000
            )
            rows = build_browser_rows(
                project,
                mode=BrowserMode.BY_SOURCE,
                session_id=SESSION_ID,
                browser_revision=1,
                page=2,
                page_size=64,
            )

        self.assertEqual(
            len([row for row in rows if row.kind == "molecular_record"]),
            64,
        )
        self.assertEqual([row.kind for row in rows[:3]], [
            "record_page",
            "source",
            "source_revision",
        ])
        self.assertTrue(all(
            row.parent_id is not None
            for row in rows
            if row.kind == "molecular_record"
        ))
        self.assertLess(len(rows), 70)
        self.assertFalse(lazy.loaded)

    def test_paged_records_keep_view_children_within_rna_row_limit(self):
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(
                Path(directory), 10_000
            )
            first = next(iter(project.molecular_records.values()))
            rows = build_browser_rows(
                project,
                mode=BrowserMode.BY_DATA,
                session_id=SESSION_ID,
                browser_revision=1,
                page_size=998,
                views=(ViewRecord(
                    object_name="Record view",
                    entity_id=first.id,
                    revision=first.revision,
                    view_kind="record",
                    label="Record view",
                ),),
            )

        self.assertEqual(
            [row.label for row in rows if row.kind == "view"],
            ["Record view"],
        )
        self.assertLessEqual(len(rows), 1000)
        self.assertFalse(lazy.loaded)

    def test_record_search_index_includes_source_names(self):
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(
                Path(directory), 10_000
            )
            source_rows = build_browser_rows(
                project,
                mode=BrowserMode.BY_DATA,
                session_id=SESSION_ID,
                browser_revision=1,
                search="  BROWSER BENCHMARK SDF  ",
                page_size=64,
            )
        self.assertEqual(
            len([row for row in source_rows if row.kind == "molecular_record"]),
            64,
        )
        self.assertEqual(
            next(row for row in source_rows if row.kind == "result_page").total_count,
            10_003,
        )
        self.assertFalse(lazy.loaded)

    def test_large_projection_summarizes_and_pages_other_registries(self):
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(
                Path(directory), 10_000
            )
            default_rows = build_browser_rows(
                project,
                mode=BrowserMode.BY_SOURCE,
                session_id=SESSION_ID,
                browser_revision=1,
                page_size=64,
            )
            searches = {
                term: build_browser_rows(
                    project,
                    mode=BrowserMode.BY_SOURCE,
                    session_id=SESSION_ID,
                    browser_revision=1,
                    search=term,
                    page_size=64,
                )
                for term in (
                    "structure",
                    "topology_record",
                    "electron density",
                )
            }

        summary = next(
            row for row in default_rows if row.kind == "projection_summary"
        )
        self.assertEqual(summary.total_count, 3)
        self.assertIn("1 source / 1 revision", summary.label)
        self.assertIn("Search or Filter", summary.label)
        for term, kind in (
            ("structure", "structure"),
            ("topology_record", "topology_record"),
            ("electron density", "grid3d"),
        ):
            with self.subTest(term=term):
                rows = searches[term]
                page = next(row for row in rows if row.kind == "result_page")
                self.assertEqual(page.total_count, 1)
                self.assertEqual(
                    [row.kind for row in rows if row.entity_id is not None],
                    [kind],
                )
                self.assertLessEqual(len(rows), 1000)
        self.assertFalse(lazy.loaded)

    def test_unreliable_direct_calls_do_not_persist_project_rows(self):
        browser_model._CACHE.clear()
        browser_model._INDEX_CACHE.clear()
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(Path(directory), 10_000)
            first = build_browser_rows(project, mode=BrowserMode.BY_DATA)
            second = build_browser_rows(project, mode=BrowserMode.BY_DATA)

        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        self.assertFalse(browser_model._CACHE)
        self.assertFalse(browser_model._INDEX_CACHE)
        self.assertFalse(lazy.loaded)

    def test_index_reuses_revision_changes_and_rebuilds_for_registry_growth(self):
        browser_model._CACHE.clear()
        browser_model._INDEX_CACHE.clear()
        with TemporaryDirectory() as directory:
            project, lazy = _project_with_indexed_records(
                Path(directory), 10_000
            )
            build_browser_rows(
                project,
                session_id=SESSION_ID,
                browser_revision=1,
                page_size=64,
            )
            first_index = next(iter(browser_model._INDEX_CACHE.values()))
            build_browser_rows(
                project,
                session_id=SESSION_ID,
                browser_revision=2,
                page_size=64,
            )
            self.assertIs(
                next(iter(browser_model._INDEX_CACHE.values())),
                first_index,
            )

            grid = project.datasets[GRID_ID]
            added = replace(
                grid,
                id=uuid5(NAMESPACE_URL, "second-browser-grid"),
                revision="grid-r2",
                semantic_role="spin_density",
            )
            project.datasets[added.id] = added
            build_browser_rows(
                project,
                session_id=SESSION_ID,
                browser_revision=3,
                page_size=64,
            )
            rebuilt = next(iter(browser_model._INDEX_CACHE.values()))

        self.assertIsNot(rebuilt, first_index)
        self.assertEqual(len(rebuilt), len(first_index) + 1)
        self.assertFalse(lazy.loaded)

    def test_casefolded_filter_is_bounded_for_reference_record_scales(self):
        measurements = {}
        for record_count in (10_000, 100_000):
            with self.subTest(record_count=record_count), TemporaryDirectory() as directory:
                project, lazy = _project_with_indexed_records(
                    Path(directory), record_count
                )
                build_browser_rows(
                    project,
                    mode=BrowserMode.BY_DATA,
                    session_id=SESSION_ID,
                    browser_revision=record_count,
                    page_size=100,
                )
                samples = []
                for index in (
                    record_count // 5,
                    record_count * 2 // 5,
                    record_count * 3 // 5,
                    record_count * 4 // 5,
                    record_count - 1,
                ):
                    started = perf_counter()
                    rows = build_browser_rows(
                        project,
                        mode=BrowserMode.BY_DATA,
                        session_id=SESSION_ID,
                        browser_revision=record_count,
                        search=f"  BENCHMARK-{index:06d}  ",
                        page_size=100,
                    )
                    samples.append(perf_counter() - started)
                    self.assertEqual(
                        [row.label for row in rows if row.kind == "molecular_record"],
                        [f"benchmark-{index:06d} · V2000"],
                    )
                    self.assertFalse(lazy.loaded)
                measurements[record_count] = _p95(samples)

        self.assertLessEqual(measurements[10_000], 0.2)
        self.assertLessEqual(measurements[100_000], 0.2)


if __name__ == "__main__":
    import unittest

    unittest.main()
