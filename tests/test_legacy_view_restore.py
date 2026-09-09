"""Current Viewer restoration contract for external legacy export reports."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData, ImportBatch, QCProject, Structure
from cbq_core.session import close_session, create_session
from cbq_core.sidecar import save_project
from ChemBlender.legacy_restore import legacy_restore_plan


class LegacyViewRestorePlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.structure = Structure(
            uuid4(), "legacy", (6, 1),
            ArrayData(numpy.asarray(((0., 0., 0.), (1., 0., 0.))),
                      ("atom", "xyz"), "angstrom"),
        )
        project = QCProject(uuid4(), "1.1")
        project.commit(ImportBatch(structures=(self.structure,)))
        self.package = save_project(self.root / "project.cbq", project)
        manifest = self.package / "manifest.json"
        self.report = {
            "format": "chemblender.legacy-migration-report",
            "version": "1",
            "project_id": str(project.id),
            "cbq": "project.cbq",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "display_restore_status": "recorded_only",
            "views": [{
                "structure_id": str(self.structure.id),
                "legacy_object_name": "Legacy Molecule",
                "kind": "scaffold",
                "settings": {
                    "radii": [.76, .31], "vdw_radii": [1.7, 1.2],
                    "atom_scales": [1.1, .9], "colors": [[.1, .2, .3, 1.], [1., 1., 1., 1.]],
                    "bond_scales": [], "dashed": [],
                    "materials": [{"name": "Legacy", "diffuse_color": [.2, .3, .4, 1.],
                                   "metallic": .1, "roughness": .6}],
                    "node_modifiers": [{"name": "Legacy Nodes", "node_group_name": "Old Group",
                                        "inputs": [["Scale", 1.25], ["Tint", [.1, .2, .3, 1.]]]}],
                },
            }],
        }
        self.report_path = self.root / "migration.json"
        self._write(self.report)
        self.session = create_session(temp_parent=self.root, project=project)

    def tearDown(self):
        close_session(self.session)
        self.temporary.cleanup()

    def _write(self, value, *, allow_nan=False):
        self.report_path.write_bytes((json.dumps(value, allow_nan=allow_nan) + "\n").encode())

    def test_accepts_verified_fully_imported_report_and_normalizes_values(self):
        plan = legacy_restore_plan(self.session, self.report_path)
        self.assertEqual(plan[0]["structure_id"], self.structure.id)
        self.assertEqual(plan[0]["settings"]["radii"], (.76, .31))
        self.assertEqual(plan[0]["settings"]["colors"][0], (.1, .2, .3, 1.))
        self.assertEqual(plan[0]["settings"]["node_modifiers"][0]["inputs"][1][1],
                         (.1, .2, .3, 1.))

    def test_rejects_untrusted_report_or_package_identity(self):
        mutations = (
            ("format", "other"), ("version", "2"), ("cbq", "../project.cbq"),
            ("manifest_sha256", "0" * 64), ("display_restore_status", "restored"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = {**self.report, key: value}
                self._write(document)
                with self.assertRaises((OSError, TypeError, ValueError)):
                    legacy_restore_plan(self.session, self.report_path)
        self._write(self.report)

    def test_rejects_invalid_display_data_and_missing_current_entities(self):
        invalid_views = []
        invalid_views.append({**self.report["views"][0], "kind": "script"})
        settings = dict(self.report["views"][0]["settings"])
        settings["radii"] = [float("nan"), .31]
        invalid_views.append({**self.report["views"][0], "settings": settings})
        settings = dict(self.report["views"][0]["settings"])
        settings["node_modifiers"] = [{"name": "x", "node_group_name": None,
                                        "inputs": [["unsafe", {"run": "code"}]]}]
        invalid_views.append({**self.report["views"][0], "settings": settings})
        for view in invalid_views:
            with self.subTest(view=view):
                self._write({**self.report, "views": [view]}, allow_nan=True)
                with self.assertRaises((TypeError, ValueError)):
                    legacy_restore_plan(self.session, self.report_path)
        empty = create_session(temp_parent=self.root)
        try:
            self._write(self.report)
            with self.assertRaisesRegex(ValueError, "Import the complete legacy CBQ"):
                legacy_restore_plan(empty, self.report_path)
        finally:
            close_session(empty)


if __name__ == "__main__":
    unittest.main()
