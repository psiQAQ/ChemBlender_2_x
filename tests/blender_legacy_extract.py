import sys
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path

import bpy


ARGUMENTS = sys.argv[sys.argv.index("--") + 1 :]
ROOT = Path(ARGUMENTS[0]).resolve()
MODE = ARGUMENTS[1]
sys.path.insert(0, str(ROOT))


def datablock_names():
    return tuple(
        (name, tuple(sorted(item.name for item in getattr(bpy.data, name))))
        for name in (
            "objects",
            "meshes",
            "collections",
            "materials",
            "node_groups",
            "curves",
            "cameras",
            "lights",
        )
    )


def assert_fixture(report):
    by_name = {item.name: item for item in report.objects}
    assert report.source_verified
    assert report.source_hash == sha256(Path(bpy.data.filepath).read_bytes()).hexdigest()
    name = Path(bpy.data.filepath).name
    if name == "chemblender-2.1-molecule.blend":
        scaffold = by_name["legacy_formaldehyde"]
        assert scaffold.kind == "scaffold"
        assert scaffold.atomic_numbers == (6, 8, 1, 1)
        assert scaffold.coordinates == (
            (0.0, 0.0, 0.0),
            (1.2100000381469727, 0.0, 0.0),
            (-0.6000000238418579, 0.9399999976158142, 0.0),
            (-0.6000000238418579, -0.9399999976158142, 0.0),
        )
        assert scaffold.radii == (
            0.7599999904632568,
            0.6600000262260437,
            0.3100000023841858,
            0.3100000023841858,
        )
        assert scaffold.vdw_radii == (
            1.7000000476837158,
            1.5499999523162842,
            1.2000000476837158,
            1.2000000476837158,
        )
        assert tuple(edge.order for edge in scaffold.edges) == (2, 1, 1)
        assert scaffold.atom_scales == (1.25, 1.100000023841858, 0.800000011920929, 0.800000011920929)
        assert tuple(edge.scale for edge in scaffold.edges) == (0.6499999761581421, 0.8500000238418579, 0.8500000238418579)
    elif name == "chemblender-2.2-edited-scaffold.blend":
        scaffold = by_name["legacy_edited_ethanol"]
        assert scaffold.kind == "scaffold"
        assert scaffold.atomic_numbers[0] == 7
        assert scaffold.coordinates[0] == (-1.0, 0.15000000596046448, 0.0)
        assert scaffold.atom_scales[0] == 1.399999976158142
        assert scaffold.colors[0] == (0.10000000149011612, 0.699999988079071, 0.6499999761581421, 1.0)
        assert scaffold.edges[0].order == 2
        assert scaffold.edges[0].scale == 0.6000000238418579
        assert scaffold.edges[0].dashed is True
    elif name == "chemblender-2.2-crystal.blend":
        crystal = by_name["unit_partial_uij"]
        assert crystal.kind == "crystal"
        assert crystal.cell == (5.0, 6.0, 7.0, 90.0, 100.0, 110.0)
        assert crystal.cif_original.atoms[0].label == "Cu1"
        assert crystal.cif_original.atoms[0].occupancy == 0.75
        assert crystal.cif_original.atoms[0].uij == (
            0.010999999940395355,
            0.013000000268220901,
            0.017000000923871994,
            0.003000000026077032,
            0.0020000000949949026,
            0.0010000000474974513,
        )
        assert crystal.cif_current == crystal.cif_original
        assert by_name["cell_edges_partial_uij"].kind == "cell"
    else:
        raise AssertionError(f"unknown legacy fixture: {name}")
    assert any(item.code == "evaluated_geometry_ignored" for item in report.diagnostics)
    try:
        report.objects = ()
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("legacy report must be immutable")


def create_ambiguous_legacy_object():
    mesh = bpy.data.meshes.new("synthetic legacy mesh")
    mesh.from_pydata(((1.0, 0.0, 0.0),), (), ())
    atomic_numbers = mesh.attributes.new("atomic_num", "INT", "POINT")
    atomic_numbers.data[0].value = 6
    obj = bpy.data.objects.new("synthetic legacy", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["Type"] = "scaffold"
    obj["unexpected legacy value"] = "unverified"
    material = bpy.data.materials.new("synthetic legacy material")
    material.diffuse_color = (0.1, 0.2, 0.3, 1.0)
    material.metallic = 0.4
    material.roughness = 0.5
    mesh.materials.append(material)
    parent = bpy.data.objects.new("synthetic legacy parent", None)
    bpy.context.scene.collection.objects.link(parent)
    parent.scale = (2.0, 1.0, 1.0)
    obj.parent = parent
    obj.modifiers.new("legacy display", "NODES")
    modifier = obj.modifiers[-1]
    modifier.node_group = bpy.data.node_groups.new(
        "synthetic legacy nodes", "GeometryNodeTree"
    )
    modifier["legacy_scalar"] = 1.5
    modifier["legacy_text"] = "legacy display"
    modifier["legacy_vector"] = (1.0, 2.0, 3.0)
    modifier["legacy_unsupported"] = {"nested": 1}
    bpy.context.view_layer.update()


def create_current_structure_view():
    import numpy
    from uuid import uuid4

    from ChemBlender.core import ArrayData, Structure
    from ChemBlender.views import StructureViewSettings, create_structure_view

    return create_structure_view(
        Structure(
            id=uuid4(),
            revision="legacy-detection-current-view-r1",
            atomic_numbers=(6,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        ),
        settings=StructureViewSettings(attach_ball_and_stick=False),
        name="current structure view",
        collection=bpy.context.scene.collection,
    )


def main():
    import ChemBlender

    if bpy.data.filepath:
        ChemBlender.register()
    elif MODE == "synthetic":
        create_ambiguous_legacy_object()
    elif MODE == "current":
        current = create_current_structure_view()
        assert current["cb_structure_contract"] == "structure_view_v1"
    elif MODE == "mixed":
        create_current_structure_view()
        create_ambiguous_legacy_object()
    before = datablock_names()
    from ChemBlender.legacy import detect_legacy_scene, extract_legacy_objects

    detection = detect_legacy_scene()
    report = extract_legacy_objects(detection)
    after = datablock_names()
    assert before == after, (before, after)
    if bpy.data.filepath:
        assert detection.objects
        assert_fixture(report)
    elif MODE == "synthetic":
        assert len(report.objects) == 1
        snapshot = report.objects[0]
        assert snapshot.coordinates == ((2.0, 0.0, 0.0),)
        assert snapshot.materials[0].name == "synthetic legacy material"
        assert abs(snapshot.materials[0].metallic - 0.4) < 1.0e-6
        assert snapshot.node_modifiers[0].node_group_name == "synthetic legacy nodes"
        assert snapshot.node_modifiers[0].inputs == (
            ("legacy_scalar", 1.5),
            ("legacy_text", "legacy display"),
            ("legacy_vector", (1.0, 2.0, 3.0)),
        )
        assert "unsupported_node_input" in {item.code for item in report.diagnostics}
        assert {item.code for item in report.diagnostics} == {
            "evaluated_geometry_ignored",
            "missing_blend_source_path",
            "nonuniform_transform",
            "unknown_custom_property",
            "unsupported_node_input",
        }
    elif MODE == "current":
        assert detection.objects == ()
        assert report.objects == ()
        assert report.diagnostics == ()
    elif MODE == "mixed":
        assert tuple(item.name for item in detection.objects) == (
            "synthetic legacy",
        )
        assert tuple(item.name for item in report.objects) == (
            "synthetic legacy",
        )
    else:
        assert detection.objects == ()
        assert report.objects == ()
        assert report.diagnostics == ()


if __name__ == "__main__":
    main()
