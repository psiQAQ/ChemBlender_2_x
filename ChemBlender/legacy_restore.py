"""Restore validated legacy display records onto current CBQ Structure Views."""

import hashlib
import json
from math import isfinite
from pathlib import Path
from uuid import UUID

from cbq_core.package_import import preview_package


_SETTINGS = {
    "radii", "vdw_radii", "atom_scales", "colors", "bond_scales",
    "dashed", "materials", "node_modifiers",
}


def _reject_constant(value):
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _text(value, name, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be non-empty text")
    return value


def _number(value, name, *, positive=False, unit=False):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    value = float(value)
    if positive and value <= 0.0:
        raise ValueError(f"{name} must be positive")
    if unit and not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")
    return value


def _boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be bool")
    return value


def _sequence(value, name, item, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not list:
        raise ValueError(f"{name} must be a JSON array")
    return tuple(item(current, f"{name}[{index}]") for index, current in enumerate(value))


def _settings(value, name):
    if type(value) is not dict or set(value) != _SETTINGS:
        raise ValueError(f"{name} has an unsupported schema")
    positive = lambda item, path: _number(item, path, positive=True)
    unit = lambda item, path: _number(item, path, unit=True)
    color = lambda item, path: _sequence(item, path, unit)
    colors = _sequence(value["colors"], name + ".colors", color, optional=True)
    if colors is not None and any(len(item) != 4 for item in colors):
        raise ValueError(f"{name}.colors must contain RGBA values")
    materials = []
    for index, material in enumerate(value["materials"] if type(value["materials"]) is list else (None,)):
        path = f"{name}.materials[{index}]"
        if type(material) is not dict or set(material) != {"name", "diffuse_color", "metallic", "roughness"}:
            raise ValueError(f"{path} has an unsupported schema")
        diffuse = _sequence(material["diffuse_color"], path + ".diffuse_color", unit)
        if len(diffuse) != 4:
            raise ValueError(f"{path}.diffuse_color must be RGBA")
        materials.append({"name": _text(material["name"], path + ".name"),
                          "diffuse_color": diffuse,
                          "metallic": _number(material["metallic"], path + ".metallic", unit=True),
                          "roughness": _number(material["roughness"], path + ".roughness", unit=True)})
    modifiers = []
    raw_modifiers = value["node_modifiers"]
    if type(raw_modifiers) is not list:
        raise ValueError(f"{name}.node_modifiers must be a JSON array")
    for index, modifier in enumerate(raw_modifiers):
        path = f"{name}.node_modifiers[{index}]"
        if type(modifier) is not dict or set(modifier) != {"name", "node_group_name", "inputs"}:
            raise ValueError(f"{path} has an unsupported schema")
        inputs, keys = [], set()
        if type(modifier["inputs"]) is not list:
            raise ValueError(f"{path}.inputs must be a JSON array")
        for input_index, pair in enumerate(modifier["inputs"]):
            input_path = f"{path}.inputs[{input_index}]"
            if type(pair) is not list or len(pair) != 2:
                raise ValueError(f"{input_path} must be a name/value pair")
            key = _text(pair[0], input_path + ".name")
            if key in keys:
                raise ValueError(f"{path}.inputs contains a duplicate name")
            keys.add(key)
            raw = pair[1]
            if type(raw) in (str, bool, int):
                normalized = raw
            elif type(raw) is float:
                normalized = _number(raw, input_path + ".value")
            elif type(raw) is list and 2 <= len(raw) <= 4:
                normalized = tuple(_number(item, input_path + ".value") for item in raw)
            else:
                raise ValueError(f"{input_path}.value has an unsupported type")
            inputs.append((key, normalized))
        modifiers.append({"name": _text(modifier["name"], path + ".name"),
                          "node_group_name": _text(modifier["node_group_name"], path + ".node_group_name", optional=True),
                          "inputs": tuple(inputs)})
    dashed = _sequence(value["dashed"], name + ".dashed", _boolean, optional=True)
    return {
        "radii": _sequence(value["radii"], name + ".radii", positive, optional=True),
        "vdw_radii": _sequence(value["vdw_radii"], name + ".vdw_radii", positive, optional=True),
        "atom_scales": _sequence(value["atom_scales"], name + ".atom_scales", positive, optional=True),
        "colors": colors,
        "bond_scales": _sequence(value["bond_scales"], name + ".bond_scales", positive, optional=True),
        "dashed": dashed,
        "materials": tuple(materials),
        "node_modifiers": tuple(modifiers),
    }


def legacy_restore_plan(session, report_path):
    """Validate a report and prove its complete package is already in session."""
    path = Path(report_path).expanduser().resolve(strict=True)
    if not path.is_file() or path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError("migration report must be a regular file")
    report_bytes = path.read_bytes()
    document = json.loads(report_bytes.decode("utf-8"), parse_constant=_reject_constant)
    if type(document) is not dict:
        raise ValueError("migration report must be a JSON object")
    if document.get("format") != "chemblender.legacy-migration-report" or document.get("version") != "1":
        raise ValueError("unsupported legacy migration report")
    if document.get("display_restore_status") != "recorded_only":
        raise ValueError("legacy display report is not pending restoration")
    if document.get("cbq") != "project.cbq":
        raise ValueError("legacy report must reference its adjacent project.cbq")
    try:
        project_id = UUID(document.get("project_id", ""))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("legacy report project_id is invalid") from error
    digest = document.get("manifest_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(item not in "0123456789abcdef" for item in digest):
        raise ValueError("legacy report manifest_sha256 is invalid")
    package = path.parent / "project.cbq"
    manifest = package / "manifest.json"
    if (not package.is_dir() or package.is_symlink()
            or getattr(package, "is_junction", lambda: False)()
            or not manifest.is_file() or manifest.is_symlink()
            or hashlib.sha256(manifest.read_bytes()).hexdigest() != digest):
        raise ValueError("legacy report does not match its verified project.cbq")
    package_preview = preview_package(session, package)
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != digest or path.read_bytes() != report_bytes:
        raise ValueError("legacy migration input changed during validation")
    if UUID(package_preview.source_project_id) != project_id:
        raise ValueError("legacy report identity differs from project.cbq")
    if package_preview.conflicts or package_preview.counts["new"]:
        raise ValueError("Import the complete legacy CBQ before restoring its Views")
    raw_views = document.get("views")
    if type(raw_views) is not list or not raw_views:
        raise ValueError("legacy report has no Views")
    plan, structure_ids, names = [], set(), set()
    report_digest = hashlib.sha256(report_bytes).hexdigest()
    for index, raw in enumerate(raw_views):
        name = f"views[{index}]"
        if type(raw) is not dict or set(raw) != {"structure_id", "legacy_object_name", "kind", "settings"}:
            raise ValueError(f"{name} has an unsupported schema")
        try:
            structure_id = UUID(raw["structure_id"])
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"{name}.structure_id is invalid") from error
        legacy_name = _text(raw["legacy_object_name"], name + ".legacy_object_name")
        kind = raw["kind"]
        if kind not in {"scaffold", "crystal"}:
            raise ValueError(f"{name}.kind is unsupported")
        if structure_id in structure_ids or legacy_name in names:
            raise ValueError("legacy report contains duplicate View identities")
        structure_ids.add(structure_id)
        names.add(legacy_name)
        structure = session.project.structures.get(structure_id)
        if structure is None or (kind == "crystal") != (structure.periodic is not None):
            raise ValueError(f"{name} does not match an imported Structure")
        settings = _settings(raw["settings"], name + ".settings")
        atom_count = len(structure.atomic_numbers)
        for field in ("radii", "vdw_radii", "atom_scales", "colors"):
            if settings[field] is not None and len(settings[field]) != atom_count:
                raise ValueError(f"{name}.settings.{field} has the wrong atom count")
        topologies = tuple(item for item in session.project.topologies.values()
                           if item.structure_id == structure_id)
        if len(topologies) > 1:
            raise ValueError(f"{name} has ambiguous imported topology")
        bond_count = 0 if not topologies else len(topologies[0].bond_indices.values)
        for field in ("bond_scales", "dashed"):
            if settings[field] is not None and len(settings[field]) != bond_count:
                raise ValueError(f"{name}.settings.{field} has the wrong bond count")
        plan.append({"structure_id": structure_id, "legacy_object_name": legacy_name,
                     "kind": kind, "settings": settings, "report_sha256": report_digest})
    return tuple(plan)


def _mean(values):
    return 1.0 if not values else sum(values) / len(values)


def _write_display_attribute(mesh, name, values, data_type, domain, field):
    attribute = mesh.attributes.get(name)
    if attribute is None or attribute.data_type != data_type or attribute.domain != domain:
        raise ValueError(f"legacy display target is incompatible: {name}")
    if len(attribute.data) != len(values):
        raise ValueError(f"legacy display target length is incompatible: {name}")
    for item, value in zip(attribute.data, values):
        setattr(item, field, value)


def _apply_view_settings(view, settings, owned_materials):
    import bpy
    for name, values, data_type, domain, field in (
        ("radius", settings["radii"], "FLOAT", "POINT", "value"),
        ("vdw_radius", settings["vdw_radii"], "FLOAT", "POINT", "value"),
        ("atom_scale_f", settings["atom_scales"], "FLOAT", "POINT", "value"),
        ("bond_scale_f", settings["bond_scales"], "FLOAT", "EDGE", "value"),
    ):
        if values is not None:
            _write_display_attribute(view.data, name, values, data_type, domain, field)
    if settings["dashed"] is not None:
        if view.data.attributes.get("dashed") is None:
            view.data.attributes.new("dashed", "BOOLEAN", "EDGE")
        _write_display_attribute(view.data, "dashed", settings["dashed"], "BOOLEAN", "EDGE", "value")
    if settings["colors"] is not None:
        _write_display_attribute(view.data, "colour", settings["colors"], "FLOAT_COLOR", "POINT", "color")
    for index, snapshot in enumerate(settings["materials"]):
        material = bpy.data.materials.new(f"{view.name} Legacy Material {index}")
        material.diffuse_color = snapshot["diffuse_color"]
        material.metallic = snapshot["metallic"]
        material.roughness = snapshot["roughness"]
        view.data.materials.append(material)
        owned_materials.append(material)
    view["cb_legacy_node_settings"] = json.dumps(settings["node_modifiers"], ensure_ascii=False,
                                                  separators=(",", ":"), sort_keys=True)


def _attach_restore_display(view):
    """Build with fresh packaged assets; legacy groups keep their own identities."""
    import bpy
    from . import node

    def build(modifier):
        names = (
            ("CH_添加分子属性", "CH_分子球棍模型", "CH_添加分子材质") if node.language
            else ("CH_Add Attributes", "CH_Ball and Stick", "CH_Add Material")
        )
        with bpy.data.libraries.load(node.filepath, link=False) as (source, target):
            if any(name not in source.node_groups for name in names):
                raise RuntimeError("packaged legacy display assets are missing")
            target.node_groups = list(names)
        group = modifier.node_group
        source, output = node.set_io_nodes(modifier, (0, 0), (800, 0))
        previous = source.outputs[0]
        for index, asset in enumerate(target.node_groups):
            instance = group.nodes.new("GeometryNodeGroup")
            instance.node_tree = asset
            instance.location = (200 * (index + 1), 0)
            if index == 1:
                instance.inputs[6].default_value = 0.5
                instance.inputs[8].default_value = True
            group.links.new(previous, instance.inputs[0])
            previous = instance.outputs[0]
        group.links.new(previous, output.inputs[0])

    node._ensure_generated_modifier(
        view, node._STRUCTURE_BALL_STICK_MODIFIER,
        node._STRUCTURE_BALL_STICK_CONTRACT, build,
    )


def restore_legacy_views(session, report_path, collection):
    """Create all recorded Views atomically; never mutate scientific data."""
    import bpy
    from .views import (PeriodicViewSettings, StructureViewSettings,
                        create_periodic_structure_view, create_structure_view,
                        remove_structure_view)

    plan = legacy_restore_plan(session, report_path)
    names = tuple(f"{item['legacy_object_name']} (Migrated)" for item in plan)
    if any(bpy.data.objects.get(name) is not None for name in names):
        raise ValueError("a legacy restored View name already exists")
    created, owned_materials = [], []
    old_node_groups = set(bpy.data.node_groups)
    old_active = (session.active_entity_id, session.active_view_object_name)
    try:
        for item, name in zip(plan, names):
            structure = session.project.structures[item["structure_id"]]
            topology = next((value for value in session.project.topologies.values()
                             if value.structure_id == structure.id), None)
            settings = item["settings"]
            if item["kind"] == "crystal":
                view = create_periodic_structure_view(structure, topology, PeriodicViewSettings(),
                                                      attach_ball_and_stick=False,
                                                      name=name, collection=collection)
            else:
                view = create_structure_view(structure, topology,
                    StructureViewSettings(atom_scale=_mean(settings["atom_scales"]),
                                          bond_scale=_mean(settings["bond_scales"]),
                                          attach_ball_and_stick=False),
                    name=name, collection=collection)
            created.append(view)
            _apply_view_settings(view, settings, owned_materials)
            _attach_restore_display(view)
            view["cb_legacy_restore_contract"] = "legacy_view_restore_v1"
            view["cb_legacy_report_sha256"] = item["report_sha256"]
            view["cb_scene_project_id"] = str(session.project.id)
        session.active_entity_id = plan[-1]["structure_id"]
        session.active_view_object_name = created[-1].name
        return tuple(created)
    except BaseException as error:
        session.active_entity_id, session.active_view_object_name = old_active
        for view in reversed(created):
            if view.name in bpy.data.objects:
                try:
                    remove_structure_view(view)
                except BaseException as cleanup:
                    error.add_note(f"legacy View rollback failed: {cleanup}")
        for material in owned_materials:
            if material.name in bpy.data.materials and material.users == 0:
                try:
                    bpy.data.materials.remove(material)
                except BaseException as cleanup:
                    error.add_note(f"legacy material rollback failed: {cleanup}")
        for group in tuple(set(bpy.data.node_groups) - old_node_groups):
            if group.users == 0:
                try:
                    bpy.data.node_groups.remove(group)
                except BaseException as cleanup:
                    error.add_note(f"legacy node-group rollback failed: {cleanup}")
        raise
