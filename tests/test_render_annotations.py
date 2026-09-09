"""Annotation wording follows the material actually used by each adapter."""

import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from uuid import uuid4

from cbq_core.scene_preset import builtin_scene_presets


class RenderDescriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = types.ModuleType("_annotation_description_test")
        package.__path__ = [str(Path(__file__).resolve().parents[1] / "ChemBlender")]
        resolver = types.ModuleType(package.__name__ + ".scene_preset_view")
        resolver._entities = lambda plan, project: project
        cls.modules = {
            package.__name__: package,
            resolver.__name__: resolver,
            "bpy": types.ModuleType("bpy"),
        }
        with patch.dict(sys.modules, cls.modules):
            cls.annotations = importlib.import_module(package.__name__ + ".render_annotations")

    def describe(self, kind, entities, *, shaded=True, root=None, **settings):
        values = dict(builtin_scene_presets()[kind].default_settings)
        values.update(template="teaching", shaded=shaded, **settings)
        plan = types.SimpleNamespace(preset_id=kind, view_kind=kind, settings=tuple(values.items()),
                                     render_identity="test-render")
        with patch.dict(sys.modules, self.modules):
            return self.annotations._description(plan, entities, root or {})

    @staticmethod
    def entity(**values):
        return types.SimpleNamespace(id=uuid4(), revision="test-source", **values)

    def has_morphology(self, description):
        return any("Morphology shading" in value for value in description["details"])

    def test_teaching_grid_samples_remain_emission_without_morphology_claim(self):
        grid = self.entity(semantic_role="electrostatic_potential",
                           data=types.SimpleNamespace(unit="hartree_per_elementary_charge"))
        for kind in ("grid_slice", "grid_profile", "grid_colorbar"):
            with self.subTest(kind=kind):
                description = self.describe(kind, {"grid": grid})
                self.assertFalse(self.has_morphology(description))
                self.assertIn("Eh/e", description["details"][0])
        self.assertEqual(self.describe("grid_slice", {"grid": grid})["scalar"]["unit"], grid.data.unit)

    def test_teaching_atomic_scalar_remains_quantitative_emission(self):
        prop = self.entity(semantic_role="atomic_charge", data=types.SimpleNamespace(unit="elementary_charge"))
        description = self.describe("atomic_scalar", {"property": prop}, root={
            "cb_scalar_display_min": -1., "cb_scalar_display_max": 1., "cb_scalar_colormap": "coolwarm"})
        self.assertFalse(self.has_morphology(description))
        self.assertEqual(description["scalar"]["unit"], "elementary_charge")

    def test_property_surfaces_describe_morphology_only_when_lit(self):
        surface = self.entity(semantic_role="electron_density", data=types.SimpleNamespace(unit="electron_per_cubic_bohr"))
        prop = self.entity(semantic_role="electrostatic_potential", data=types.SimpleNamespace(unit="hartree_per_elementary_charge"))
        for kind in ("property_on_surface", "nci_surface"):
            for shaded in (False, True):
                with self.subTest(kind=kind, shaded=shaded):
                    self.assertEqual(self.has_morphology(self.describe(kind,
                        {"surface_grid": surface, "property_grid": prop}, shaded=shaded)), shaded)

    def test_fermi_scalar_describes_morphology_only_when_lit(self):
        surface = self.entity(fermi_energy=2., spin_index=0)
        root = {"cb_color_unit": "dimensionless", "cb_color_min": 0., "cb_color_max": 1.}
        for shaded in (False, True):
            self.assertEqual(self.has_morphology(self.describe("fermi_surface", {"surface": surface},
                shaded=shaded, root=root, color_property="orbital_contribution")), shaded)

    def test_topology_scalar_describes_morphology_only_when_lit(self):
        graph = self.entity(critical_point_ids=(uuid4(),), paths=(),
                            field_values=types.SimpleNamespace(unit="electron_per_cubic_bohr"))
        root = {"cb_color_min": 0., "cb_color_max": 1.}
        for shaded in (False, True):
            self.assertEqual(self.has_morphology(self.describe("topology_graph", {"graph": graph},
                shaded=shaded, root=root, color_property="field_value")), shaded)


if __name__ == "__main__":
    unittest.main()
