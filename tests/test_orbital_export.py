import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.session import create_session
from cbq_core.session import close_session
from chemblender_prepare.core.wavefunction_grid import evaluate_molecular_orbital_grid
from ChemBlender.ui import orbital_export as export
from tests.test_wavefunction_grid import entities


class OrbitalExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.structure, self.basis, self.orbitals = entities()
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(structures=(self.structure,), basis_sets=(self.basis,),
                                   orbital_sets=(self.orbitals,)))
        self.session = create_session(temp_parent=self.root, project=project)
        self.session.active_entity_id = self.orbitals.id
        self.settings = SimpleNamespace(channel="restricted", orbital_source_uuid=str(self.orbitals.id),
            origin=(-1., -1., -1.), shape=(3, 3, 3), spacing=1., memory_limit_mb=1024,
)
        self.context = SimpleNamespace(scene=SimpleNamespace(camera=SimpleNamespace(type="CAMERA"),
            chemblender_project_browser=SimpleNamespace(active_entity_id=str(self.orbitals.id))))
        self.rendered = []
        self.scope_restored = False
        owner = self

        class Renderer:
            def __init__(self, *_args):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                owner.scope_restored = True

            def document(self):
                return {}

            def render(self, plan, destination, cache):
                owner.rendered.append(plan.bindings[0].entity_id)
                destination.write_bytes(b"\x89PNG\r\n\x1a\nfixture")

        self.renderer = Renderer

    def tearDown(self):
        export.clear_orbital_exports(self.session)
        close_session(self.session)
        self.temporary.cleanup()

    def cache(self, number):
        with patch("chemblender_prepare.core.wavefunction_grid._evaluate_channel",
                   side_effect=lambda _s, _b, c, points: numpy.ones((len(c), len(points)))):
            batch = evaluate_molecular_orbital_grid(self.structure, self.basis, self.orbitals,
                origin=self.settings.origin, step_vectors=((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)),
                shape=self.settings.shape, channel="restricted", orbital_index=number - 1)
        self.session.project.commit(batch)
        return batch.datasets[0]

    def iterator(self, **kwargs):
        return export.iter_orbital_images(self.context, self.session, self.settings,
            orbital_numbers=(1, 2), destination=self.root / "images", **kwargs)

    def test_explicit_number_parser_preserves_order_and_rejects_invalid_ranges(self):
        self.assertEqual(export.parse_orbital_numbers("3, 1-2,2", 3), (3, 1, 2))
        for value in ("", "HOMO", "1,", "0", "3-2", "1-999999999999999", "1.0", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                export.parse_orbital_numbers(value, 3)

    def test_preflight_requires_prepared_grids_without_files_or_workers(self):
        self.cache(1)
        before = set(self.root.iterdir())
        with self.assertRaisesRegex(ValueError, "Orbital 2 has no prepared grid"):
            self.iterator()
        self.assertEqual(set(self.root.iterdir()), before)
        self.cache(2)
        prepared = export.preflight_orbital_export(self.context, self.session, self.settings,
            orbital_numbers="1-2", destination=self.root / "images")
        self.assertFalse(hasattr(prepared, "worker"))
        self.context.scene.camera = None
        with self.assertRaisesRegex(ValueError, "camera"):
            self.iterator()
        self.context.scene.camera = SimpleNamespace(type="CAMERA")
        # Old evaluation controls cannot change which scientific data is rendered.
        self.settings.spacing = .5
        iterator = self.iterator()
        iterator.close()

    def test_cached_images_and_complete_report_publish_together_after_display_restoration(self):
        grids = [self.cache(1), self.cache(2)]
        with patch.object(export, "_RenderScope", self.renderer):
            iterator = self.iterator()
            self.assertEqual(next(iterator)["stage"], "Render MO 1")
            self.assertFalse((self.root / "images").exists())
            self.assertEqual(next(iterator)["stage"], "Rendered MO 1")
            self.assertEqual(self.rendered, [grids[0].id])
            self.assertFalse((self.root / "images").exists())
            list(iterator)
        target = self.root / "images"
        self.assertTrue(self.scope_restored)
        self.assertEqual(self.rendered, [grid.id for grid in grids])
        self.assertEqual({path.name for path in target.iterdir()}, {"images", "display.json", "manifest.json", "report.md"})
        document = json.loads((target / "display.json").read_text(encoding="utf-8"))
        self.assertEqual([row["orbital_number"] for row in document["orbitals"]], [1, 2])
        self.assertTrue(all(row["reused_scientific_cache"] for row in document["orbitals"]))
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        for artifact in manifest["artifacts"]:
            self.assertTrue((target / artifact["path"]).is_file())
        self.assertFalse(export._EXPORTS)
        self.assertEqual(self.session.active_entity_id, self.orbitals.id)

    def test_second_render_failure_discards_first_image_and_restores_display(self):
        for number in (1, 2):
            self.cache(number)
        original = self.renderer.render

        def render(renderer, plan, destination, cache):
            if self.rendered:
                raise RuntimeError("injected second render failure")
            original(renderer, plan, destination, cache)

        with patch.object(export, "_RenderScope", self.renderer), patch.object(self.renderer, "render", render):
            with self.assertRaisesRegex(RuntimeError, "second render"):
                list(self.iterator())
        self.assertTrue(self.scope_restored)
        self.assertEqual(len(self.rendered), 1)
        self.assertFalse((self.root / "images").exists())
        self.assertFalse(list(self.root.glob(".cb-orbitals-*")))
        self.assertEqual(len(self.session.project.datasets), 2)

    def test_cancellation_and_session_close_remove_staging_and_preserve_scientific_cache(self):
        for number in (1, 2):
            self.cache(number)
        cancelled = False
        with patch.object(export, "_RenderScope", self.renderer):
            iterator = self.iterator(is_cancelled=lambda: cancelled)
            next(iterator)
            next(iterator)
            cancelled = True
            with self.assertRaises(export.OrbitalExportCancelled):
                next(iterator)
            self.assertFalse((self.root / "images").exists())
            self.assertFalse(list(self.root.glob(".cb-orbitals-*")))
            self.scope_restored = False
            iterator = self.iterator()
            next(iterator)
            export.clear_orbital_exports(self.session)
        self.assertTrue(self.scope_restored)
        self.assertFalse(export._EXPORTS)
        self.assertFalse(list(self.root.glob(".cb-orbitals-*")))
        self.assertEqual(len(self.session.project.datasets), 2)

    def test_changed_source_after_yield_does_not_render_or_publish(self):
        for number in (1, 2):
            self.cache(number)
        with patch.object(export, "_RenderScope", self.renderer):
            iterator = self.iterator()
            next(iterator)
            self.session.project.orbital_sets[self.orbitals.id] = replace(self.orbitals, revision="changed")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                next(iterator)
        self.assertEqual(self.rendered, [])
        self.assertFalse((self.root / "images").exists())

    def test_immediate_close_and_clear_release_unstarted_export(self):
        for number in (1, 2):
            self.cache(number)
        with patch.object(export, "_RenderScope", side_effect=AssertionError("unexpected display mutation")):
            for _ in range(2):
                iterator = self.iterator()
                iterator.close()
                self.assertFalse(export._EXPORTS)
            iterator = self.iterator()
            export.clear_orbital_exports(self.session)
            self.assertFalse(export._EXPORTS)
            self.assertEqual(list(iterator), [])
        self.assertFalse(list(self.root.glob(".cb-orbitals-*")))

    def test_replaced_rendered_grid_discards_package_before_next_image_or_final_report(self):
        first = self.cache(1)
        self.cache(2)
        for after_images in (1, 2):
            for revision in (first.revision, "replacement-revision"):
                with self.subTest(after_images=after_images, revision=revision):
                    self.session.project.datasets[first.id] = first
                    self.scope_restored = False
                    self.rendered.clear()
                    with patch.object(export, "_RenderScope", self.renderer):
                        iterator = self.iterator()
                        for _ in range(after_images):
                            next(iterator)  # Render stage before the main-thread render.
                            next(iterator)  # Completed image, still unpublished.
                        replacement = replace(first, revision=revision)
                        self.session.project.datasets[first.id] = replacement
                        with self.assertRaisesRegex(ValueError, "orbital grid changed"):
                            next(iterator)
                    self.assertTrue(self.scope_restored)
                    self.assertEqual(len(self.rendered), after_images)
                    self.assertIs(self.session.project.datasets[first.id], replacement)
                    self.assertFalse((self.root / "images").exists())
                    self.assertFalse(list(self.root.glob(".cb-orbitals-*")))
                    self.assertFalse(export._EXPORTS)

    def test_cache_miss_leaves_project_unchanged_before_display_starts(self):
        with patch.object(export, "_RenderScope", side_effect=AssertionError("unexpected display mutation")):
            with self.assertRaisesRegex(ValueError, "no prepared grid"):
                self.iterator()
        self.assertEqual(self.session.project.datasets, {})
        self.assertFalse(export._EXPORTS)
        self.assertFalse((self.root / "images").exists())

    def test_existing_destination_is_never_replaced_even_when_created_during_export(self):
        for number in (1, 2):
            self.cache(number)
        with patch.object(export, "_RenderScope", self.renderer):
            iterator = self.iterator()
            next(iterator)
            target = self.root / "images"
            target.mkdir()
            sentinel = target / "user.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "another operation"):
                list(iterator)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            with self.assertRaisesRegex(ValueError, "new output directory"):
                self.iterator()
        self.assertFalse(list(self.root.glob(".cb-orbitals-*")))


if __name__ == "__main__":
    unittest.main()
