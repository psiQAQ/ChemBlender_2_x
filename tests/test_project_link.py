import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from ChemBlender.core import QCProject, save_project
from ChemBlender.project_link import (
    ProjectLinkStatus,
    resolve_project_link,
    write_project_link,
)


class ProjectLinkTests(unittest.TestCase):
    def test_relative_link_connects_and_reports_failures_without_mutating_scene(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            blend = root / "scenes" / "view.blend"
            sidecar = root / "projects" / "sample.cbq"
            project = QCProject(
                id=UUID("10000000-0000-0000-0000-000000000001"),
                schema_version="0.1",
            )
            save_project(sidecar, project)
            scene = {"unrelated": "preserve"}
            locator = write_project_link(scene, project, sidecar, blend_path=blend)

            self.assertFalse(Path(locator).is_absolute())
            result = resolve_project_link(scene, blend_path=blend)
            self.assertEqual(result.status, ProjectLinkStatus.CONNECTED)
            self.assertEqual(result.project.id, project.id)

            scene["cbq_project_id"] = str(UUID(int=2))
            result = resolve_project_link(scene, blend_path=blend)
            self.assertEqual(result.status, ProjectLinkStatus.MISMATCH)
            self.assertEqual(scene["unrelated"], "preserve")

            scene["cbq_project_id"] = str(project.id)
            scene["cbq_project_schema_version"] = "9"
            result = resolve_project_link(scene, blend_path=blend)
            self.assertEqual(result.status, ProjectLinkStatus.INCOMPATIBLE)
            self.assertEqual(scene["unrelated"], "preserve")

            scene["cbq_project_schema_version"] = "0.1"
            scene["cbq_sidecar_locator"] = "missing.cbq"
            result = resolve_project_link(scene, blend_path=blend)
            self.assertEqual(result.status, ProjectLinkStatus.MISSING)
            self.assertEqual(scene["unrelated"], "preserve")

    def test_invalid_scene_link_is_explicit(self):
        result = resolve_project_link({})
        self.assertEqual(result.status, ProjectLinkStatus.INVALID)
        self.assertIsNone(result.path)


if __name__ == "__main__":
    unittest.main()
