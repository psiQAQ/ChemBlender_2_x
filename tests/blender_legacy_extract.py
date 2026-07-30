import sys
from dataclasses import FrozenInstanceError
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
    obj.scale = (2.0, 1.0, 1.0)
    obj.modifiers.new("legacy display", "NODES")
    bpy.context.view_layer.update()


def main():
    import ChemBlender

    if bpy.data.filepath:
        ChemBlender.register()
    elif MODE == "synthetic":
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
        assert report.objects[0].coordinates == ((2.0, 0.0, 0.0),)
        assert {item.code for item in report.diagnostics} == {
            "evaluated_geometry_ignored",
            "missing_blend_source_path",
            "nonuniform_transform",
            "unknown_custom_property",
        }
    else:
        assert detection.objects == ()
        assert report.objects == ()
        assert report.diagnostics == ()


if __name__ == "__main__":
    main()
