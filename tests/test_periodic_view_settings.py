from dataclasses import FrozenInstanceError
import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

import ChemBlender
from ChemBlender.core import (
    ArrayData,
    PeriodicSiteData,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)
from ChemBlender.views.periodic import (
    PeriodicViewSettings,
    _canonical_source_coordinates,
    _derived_periodic_sites,
    _periodic_site_attributes,
    create_periodic_structure_view,
)
from ChemBlender.views.structure import _structure_view_data


def periodic_structure():
    coordinates = numpy.asarray(((0.0, 0.0, 0.0), (0.75, 0.75, 0.75)))
    cell = numpy.diag((3.0, 3.0, 3.0))
    return Structure(
        id=uuid4(),
        revision="periodic-r1",
        atomic_numbers=(6, 8),
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
        cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                coordinates @ numpy.linalg.inv(cell),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("C1", "O1"),
            occupancies=ArrayData(
                numpy.asarray((1.0, numpy.nan)),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=ArrayData(
                numpy.asarray((0.01, numpy.nan)),
                ("atom",),
                "angstrom_squared",
            ),
            anisotropic_displacements=ArrayData(
                numpy.asarray(
                    (
                        (0.10, 0.20, 0.30, 0.01, 0.02, 0.03),
                        (numpy.nan,) * 6,
                    )
                ),
                ("atom", "tensor_component"),
                "angstrom_squared",
            ),
            adp_types=("uani", "none"),
            disorder_groups=(1, 2),
            disorder_assemblies=("A", "A"),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=("x,y,z", "-x,-y,-z"),
            cif_envelope_id=None,
        ),
    )


def single_site_structure(*, fractional, symmetry_operations=(), uij=None):
    cell = numpy.diag((3.0, 3.0, 3.0))
    fractional = numpy.asarray((fractional,), dtype=float)
    return Structure(
        id=uuid4(),
        revision="single-site-r1",
        atomic_numbers=(6,),
        coordinates=ArrayData(
            fractional @ cell,
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=ArrayData(
                fractional,
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("C1",),
            occupancies=ArrayData(
                numpy.ones(1),
                ("atom",),
                "dimensionless",
            ),
            isotropic_displacements=None,
            anisotropic_displacements=(
                None
                if uij is None
                else ArrayData(
                    numpy.asarray((uij,), dtype=float),
                    ("atom", "tensor_component"),
                    "angstrom_squared",
                )
            ),
            adp_types=("uani" if uij is not None else "none",),
            disorder_groups=(0,),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=symmetry_operations,
            cif_envelope_id=None,
        ),
    )


class PeriodicViewSettingsTests(unittest.TestCase):
    def test_settings_are_frozen_and_validate_view_choices(self):
        settings = PeriodicViewSettings()

        self.assertEqual(settings.representation, "source_sites")
        self.assertEqual(settings.supercell, (1, 1, 1))
        self.assertEqual(settings.occupancy_mode, "opacity")
        with self.assertRaises(FrozenInstanceError):
            settings.show_cell = False
        for changes in (
            {"representation": "mesh_copy"},
            {"supercell": (1, 0, 1)},
            {"supercell": (1, 1)},
            {"boundary_tolerance": -1.0},
            {"adp_probability": 0.0},
            {"adp_probability": 1.0},
            {"occupancy_mode": "unknown"},
            {"show_constraints": 1},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    PeriodicViewSettings(**changes)

    def test_site_projection_is_stable_and_preserves_missing_values(self):
        attributes, categories = _periodic_site_attributes(periodic_structure())

        self.assertEqual(attributes["siteid"], (0, 1))
        self.assertEqual(attributes["cbq_site_label"], (0, 1))
        self.assertEqual(categories["cbq_site_label"], ("C1", "O1"))
        self.assertEqual(attributes["cbq_disorder_group"], (1, 2))
        self.assertEqual(attributes["cbq_disorder_assembly"], (0, 0))
        self.assertEqual(categories["cbq_disorder_assembly"], ("A",))
        self.assertEqual(attributes["cbq_adp_type"], (0, 1))
        self.assertEqual(categories["cbq_adp_type"], ("uani", "none"))
        self.assertEqual(attributes["cbq_occupancy"][0], 1.0)
        self.assertTrue(numpy.isnan(attributes["cbq_occupancy"][1]))
        self.assertEqual(attributes["cbq_u_iso"][0], 0.01)
        self.assertTrue(numpy.isnan(attributes["cbq_u_iso"][1]))
        self.assertEqual(attributes["cbq_u11"][0], 0.10)
        self.assertTrue(numpy.isnan(attributes["cbq_u11"][1]))
        self.assertEqual(attributes["cbq_u23"][0], 0.03)

    def test_nonperiodic_structure_fails_before_blender_import(self):
        source = periodic_structure()
        nonperiodic = Structure(
            id=source.id,
            revision=source.revision,
            atomic_numbers=source.atomic_numbers,
            coordinates=source.coordinates,
        )

        with self.assertRaisesRegex(ValueError, "periodic"):
            create_periodic_structure_view(nonperiodic)

    def test_expanded_and_supercell_sites_are_derived_not_source_mutations(self):
        source = periodic_structure()
        original_coordinates = source.coordinates.values.copy()

        expanded = _derived_periodic_sites(
            source,
            PeriodicViewSettings(representation="expanded_cell"),
        )
        supercell = _derived_periodic_sites(
            source,
            PeriodicViewSettings(
                representation="supercell",
                supercell=(2, 1, 1),
            ),
        )

        self.assertEqual(expanded["source_atom_ids"], (1,))
        numpy.testing.assert_allclose(expanded["coordinates"], ((2.25,) * 3,))
        self.assertEqual(len(supercell["coordinates"]), 4)
        self.assertEqual(len(source.atomic_numbers), 2)
        numpy.testing.assert_array_equal(
            source.coordinates.values,
            original_coordinates,
        )

    def test_constraint_visibility_does_not_drop_scientific_flags(self):
        class Data:
            def update(self):
                pass

        class Object(dict):
            data = Data()
            users_collection = ()

        source = periodic_structure()
        selective = object()
        obj = Object()
        with (
            patch(
                "ChemBlender.views.periodic.create_structure_view",
                return_value=obj,
            ) as create,
            patch("ChemBlender.views.periodic._write_periodic_attributes"),
            patch(
                "ChemBlender.views.periodic._create_periodic_site_display"
            ) as display,
        ):
            create_periodic_structure_view(
                source,
                settings=PeriodicViewSettings(show_constraints=False),
                selective_dynamics=selective,
            )

        self.assertIs(
            create.call_args.kwargs["selective_dynamics"],
            selective,
        )
        self.assertIs(display.call_args.args[-1], selective)

    def test_unwrapped_sites_use_canonical_main_without_display_duplicates(self):
        for fractional, main_x, derived_x in (
            ((1.0, 0.0, 0.0), 0.0, 3.0),
            ((-0.1, 0.0, 0.0), 2.7, 5.7),
            ((2.1, 0.0, 0.0), 0.3, 3.3),
        ):
            with self.subTest(fractional=fractional):
                source = single_site_structure(fractional=fractional)
                expanded_settings = PeriodicViewSettings(
                    representation="expanded_cell"
                )
                supercell_settings = PeriodicViewSettings(
                    representation="supercell",
                    supercell=(2, 1, 1),
                )

                main = _canonical_source_coordinates(
                    source,
                    expanded_settings,
                )
                expanded = _derived_periodic_sites(
                    source,
                    expanded_settings,
                )
                supercell = _derived_periodic_sites(
                    source,
                    supercell_settings,
                )

                self.assertAlmostEqual(main[0, 0], main_x)
                self.assertEqual(expanded["coordinates"], ())
                self.assertEqual(len(supercell["coordinates"]), 1)
                self.assertAlmostEqual(
                    supercell["coordinates"][0][0],
                    derived_x,
                )

    def test_symmetry_rotation_transforms_derived_uij(self):
        source = single_site_structure(
            fractional=(0.25, 0.10, 0.0),
            symmetry_operations=("x,y,z", "y,x,z"),
            uij=(0.10, 0.20, 0.30, 0.01, 0.02, 0.03),
        )
        derived = _derived_periodic_sites(
            source,
            PeriodicViewSettings(representation="expanded_cell"),
        )

        attributes, _categories = _periodic_site_attributes(
            source,
            source_atom_ids=derived["source_atom_ids"],
            rotations=derived["rotations"],
        )

        self.assertEqual(derived["source_atom_ids"], (0,))
        numpy.testing.assert_allclose(
            (
                attributes["cbq_u11"][0],
                attributes["cbq_u22"][0],
                attributes["cbq_u33"][0],
                attributes["cbq_u12"][0],
                attributes["cbq_u13"][0],
                attributes["cbq_u23"][0],
            ),
            (0.20, 0.10, 0.30, 0.01, 0.03, 0.02),
        )

    def test_derived_display_fault_removes_object_mesh_and_owned_group(self):
        from ChemBlender.views import periodic as periodic_view

        for failure in (
            RuntimeError("node setup failed"),
            GeneratorExit("node setup aborted"),
        ):
            with self.subTest(failure=type(failure).__name__):
                group = type("Group", (dict,), {"users": 0})()
                removed_objects = []
                removed_meshes = []
                removed_groups = []

                class Mesh:
                    name = "Derived Sites"
                    users = 0

                    def from_pydata(self, _vertices, _edges, _faces):
                        pass

                    def update(self):
                        pass

                mesh = Mesh()

                class Display(dict):
                    name = "Derived Sites"

                    def __init__(self):
                        super().__init__()
                        self.data = mesh
                        self.modifiers = []

                class Objects:
                    def new(self, _name, _mesh):
                        mesh.users = 1
                        return Display()

                    def remove(self, obj, *, do_unlink):
                        self.assert_unlink = do_unlink
                        for modifier in obj.modifiers:
                            modifier.node_group.users -= 1
                        obj.data.users = 0
                        removed_objects.append(obj)

                objects = Objects()
                fake_bpy = SimpleNamespace(
                    data=SimpleNamespace(
                        meshes=SimpleNamespace(
                            new=lambda _name: mesh,
                            remove=lambda value: removed_meshes.append(value),
                        ),
                        objects=objects,
                        node_groups=SimpleNamespace(
                            remove=lambda value: removed_groups.append(value)
                        ),
                    )
                )

                def fail_after_group(display):
                    group.users = 1
                    display.modifiers.append(
                        SimpleNamespace(node_group=group)
                    )
                    raise failure

                fake_node = SimpleNamespace(
                    ensure_structure_ball_stick_modifier=fail_after_group
                )
                main = SimpleNamespace(name="Main")
                collection = SimpleNamespace(
                    objects=SimpleNamespace(link=lambda _value: None)
                )
                with (
                    patch.dict(
                        sys.modules,
                        {
                            "bpy": fake_bpy,
                            "ChemBlender.node": fake_node,
                        },
                    ),
                    patch.object(
                        ChemBlender,
                        "node",
                        fake_node,
                        create=True,
                    ),
                    patch.object(
                        periodic_view,
                        "_derived_periodic_sites",
                        return_value={
                            "coordinates": ((1.0, 0.0, 0.0),),
                            "source_atom_ids": (0,),
                            "rotations": (
                                ((1.0, 0.0, 0.0),
                                 (0.0, 1.0, 0.0),
                                 (0.0, 0.0, 1.0)),
                            ),
                        },
                    ),
                    patch.object(
                        periodic_view,
                        "_structure_view_data",
                        return_value={},
                    ),
                    patch.object(periodic_view, "_write_point_attributes"),
                    patch.object(periodic_view, "_write_periodic_attributes"),
                    patch.object(periodic_view, "_write_attribute"),
                ):
                    with self.assertRaises(type(failure)) as raised:
                        periodic_view._create_periodic_site_display(
                            main,
                            collection,
                            periodic_structure(),
                            PeriodicViewSettings(),
                        )

                self.assertIs(raised.exception, failure)
                self.assertEqual(len(removed_objects), 1)
                self.assertEqual(removed_meshes, [mesh])
                self.assertEqual(removed_groups, [group])

    def test_remove_view_does_not_delete_foreign_node_group(self):
        from ChemBlender.views import structure as structure_view

        removed_groups = []
        removed_meshes = []
        foreign_group = type("Group", (dict,), {"users": 1})()

        class Object(dict):
            def __init__(self, name, mesh, modifiers=()):
                super().__init__()
                self.name = name
                self.data = mesh
                self.modifiers = modifiers

        main_mesh = SimpleNamespace(users=1)
        derived_mesh = SimpleNamespace(users=1)
        derived = Object(
            "Derived",
            derived_mesh,
            (SimpleNamespace(node_group=foreign_group),),
        )
        main = Object("Main", main_mesh)
        main["cbq_periodic_site_display_object"] = derived.name

        class Objects:
            def get(self, name):
                return derived if name == derived.name else None

            def remove(self, obj, *, do_unlink):
                self.assert_unlink = do_unlink
                obj.data.users = 0
                for modifier in obj.modifiers:
                    modifier.node_group.users -= 1

        fake_bpy = SimpleNamespace(
            types=SimpleNamespace(Object=Object),
            data=SimpleNamespace(
                objects=Objects(),
                meshes=SimpleNamespace(
                    remove=lambda value: removed_meshes.append(value)
                ),
                node_groups=SimpleNamespace(
                    remove=lambda value: removed_groups.append(value)
                ),
            ),
        )
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            structure_view.remove_structure_view(main)

        self.assertEqual(removed_groups, [])
        self.assertEqual(removed_meshes, [derived_mesh, main_mesh])

    def test_ball_stick_pre_attachment_fatal_removes_modifier_and_group(self):
        fatal = GeneratorExit("socket creation aborted")
        removed_modifiers = []
        removed_groups = []

        class Modifier:
            type = "NODES"
            node_group = None

        class Modifiers:
            def get(self, _name):
                return None

            def new(self, _name, _kind):
                self.modifier = Modifier()
                return self.modifier

            def remove(self, modifier):
                removed_modifiers.append(modifier)

        class Object:
            type = "MESH"
            name = "Structure"

            def __init__(self):
                self.modifiers = Modifiers()

        group = SimpleNamespace(
            users=0,
            interface=SimpleNamespace(new_socket=lambda **_kwargs: (_ for _ in ()).throw(fatal)),
        )
        fake_bpy = ModuleType("bpy")
        fake_bpy.context = SimpleNamespace(
            preferences=SimpleNamespace(
                view=SimpleNamespace(language="en_US")
            )
        )
        fake_bpy.types = SimpleNamespace(Object=Object)
        fake_bpy.data = SimpleNamespace(
            node_groups=SimpleNamespace(
                new=lambda _name, _kind: group,
                remove=lambda value: removed_groups.append(value),
            )
        )
        prior_module = sys.modules.pop("ChemBlender.node", None)
        had_attribute = hasattr(ChemBlender, "node")
        prior_attribute = getattr(ChemBlender, "node", None)
        if had_attribute:
            delattr(ChemBlender, "node")
        try:
            with patch.dict(sys.modules, {"bpy": fake_bpy}):
                node = importlib.import_module("ChemBlender.node")
                with self.assertRaises(GeneratorExit) as raised:
                    node.ensure_structure_ball_stick_modifier(Object())
        finally:
            sys.modules.pop("ChemBlender.node", None)
            if prior_module is not None:
                sys.modules["ChemBlender.node"] = prior_module
            if had_attribute:
                ChemBlender.node = prior_attribute
            elif hasattr(ChemBlender, "node"):
                delattr(ChemBlender, "node")

        self.assertIs(raised.exception, fatal)
        self.assertEqual(len(removed_modifiers), 1)
        self.assertEqual(removed_groups, [group])

    def test_boundary_tolerance_aligns_main_and_periodic_bond_display(self):
        source = single_site_structure(fractional=(0.9995, 0.0, 0.0))
        topology = TopologyRecord(
            id=uuid4(),
            revision="self-image-r1",
            structure_id=source.id,
            bond_indices=ArrayData(
                numpy.asarray(((0, 0),), dtype=int),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=ArrayData(
                numpy.asarray((0.0,)),
                ("bond",),
                "dimensionless",
            ),
            aromatic_flags=None,
            stereo_labels=("",),
            source_kind=TopologySource.EXPLICIT_FILE,
            quality_status=QualityStatus.COMPLETE,
            inference_parameters=(),
            provenance_ids=(),
            bond_lattice_shifts=ArrayData(
                numpy.asarray(((1, 0, 0),), dtype=int),
                ("bond", "xyz"),
                "dimensionless",
            ),
        )

        data = _structure_view_data(
            source,
            topology,
            periodic_boundary_tolerance=1.0e-3,
        )

        self.assertAlmostEqual(data["coordinates"][0][0], 0.0)
        self.assertEqual(len(data["periodic_segments"]), 1)
        numpy.testing.assert_allclose(
            data["periodic_segments"][0]["coordinates"],
            ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0)),
        )


if __name__ == "__main__":
    unittest.main()
