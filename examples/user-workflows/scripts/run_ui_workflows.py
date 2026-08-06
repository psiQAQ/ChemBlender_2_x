"""Run ChemBlender user workflows through registered Blender Operators."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

import bpy


SCHEMA_VERSION = "1"
ENABLED_KEY = "bl_ext.user_default.chemblender"
CASE_IDS = (
    "ENV",
    "IMP-XYZ",
    "IMP-SMILES",
    "IMP-CANCEL",
    "DATA-TOPOLOGY",
    "DATA-CRYSTAL",
    "DATA-BIOLOGICAL",
    "VIEW-CUBE",
    "EXP-FORMATS",
    "LIFE-SAVE-REOPEN-PREP",
    "MIG-PREVIEW-PREP",
)
CASE_INPUTS = {
    "ENV": (),
    "IMP-XYZ": (
        "inputs/xyz/water.xyz",
        "inputs/extxyz/carbon-trajectory.extxyz",
        "inputs/qcschema/atomic-result.json",
    ),
    "IMP-SMILES": ("inputs/smiles/ethanol.smi",),
    "IMP-CANCEL": ("inputs/cube/two-datasets.cube",),
    "DATA-TOPOLOGY": ("inputs/mol2/substructure.mol2",),
    "DATA-CRYSTAL": ("inputs/poscar/velocities.CONTCAR",),
    "DATA-BIOLOGICAL": ("inputs/pdb/multimodel.pdb",),
    "VIEW-CUBE": ("inputs/cube/two-datasets.cube",),
    "EXP-FORMATS": ("inputs/pqr/with-chain.pqr",),
    "LIFE-SAVE-REOPEN-PREP": (),
    "MIG-PREVIEW-PREP": (
        "inputs/legacy/chemblender-2.1-molecule.blend",
    ),
}
DEPENDENCIES = {
    case_id: ("ENV",) for case_id in CASE_IDS if case_id != "ENV"
}
DEPENDENCIES["EXP-FORMATS"] = (
    "ENV",
    "IMP-XYZ",
    "IMP-SMILES",
    "DATA-TOPOLOGY",
    "DATA-CRYSTAL",
    "DATA-BIOLOGICAL",
    "VIEW-CUBE",
)
DEPENDENCIES["LIFE-SAVE-REOPEN-PREP"] = ("ENV", "EXP-FORMATS")


def _parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", default=("all",))
    parser.add_argument(
        "--checkpoint",
        choices=("main", "reopen", "migration", "migration-reopen"),
        default="main",
    )
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


def _script_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return _parse_args(argv)


def _require_file(path):
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"not a file: {path}")
    return path


def _require_owned(path, root):
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"path is outside the explicit run directory: {path}")
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            json.dump(
                report,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _extension_repositories():
    extensions = getattr(bpy.context.preferences, "extensions", None)
    repositories = getattr(extensions, "repos", ())
    return [
        {
            key: getattr(repository, key, None)
            for key in ("name", "module", "directory", "remote_url", "use_remote_url")
        }
        for repository in repositories
    ]


def _runtime_snapshot():
    enabled = tuple(sorted(bpy.context.preferences.addons.keys()))
    return {
        "blender_version": bpy.app.version_string,
        "blender_version_tuple": list(bpy.app.version),
        "executable": bpy.app.binary_path,
        "bundled_python": sys.executable,
        "binary_path_python": getattr(bpy.app, "binary_path_python", ""),
        "runtime_system": platform.system(),
        "background": bool(bpy.app.background),
        "extension_repositories": _extension_repositories(),
        "enabled_key": ENABLED_KEY,
        "enabled": ENABLED_KEY in enabled,
        "active_file": bpy.data.filepath,
        "dirty": bool(bpy.data.is_dirty),
        "scene": bpy.context.scene.name if bpy.context.scene else "",
        "object_count": len(bpy.data.objects),
    }


def _json_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return repr(value)


def _operator_rna(identifier, operator):
    properties = []
    try:
        rna = operator.get_rna_type()
        for prop in rna.properties:
            if prop.identifier == "rna_type":
                continue
            item = {"id": prop.identifier, "type": prop.type}
            if prop.type == "ENUM":
                try:
                    item["items"] = [value.identifier for value in prop.enum_items]
                except Exception as error:
                    item["items_error"] = f"{type(error).__name__}: {error}"
            properties.append(item)
    except Exception as error:
        properties.append({"rna_error": f"{type(error).__name__}: {error}"})
    try:
        poll = bool(operator.poll())
    except Exception as error:
        poll = f"{type(error).__name__}: {error}"
    return {"id": identifier, "poll": poll, "properties": properties}


def _finished(result):
    return "FINISHED" in set(result)


def _normal(value):
    return "".join(character for character in value.lower() if character.isalnum())


def _objects():
    return [
        {
            "name": obj.name,
            "type": obj.type,
            "hidden": bool(obj.hide_viewport),
            "selected": bool(obj.select_get()),
        }
        for obj in sorted(bpy.context.scene.objects, key=lambda value: value.name)
    ]


class RunContext:
    def __init__(self, args, report):
        self.args = args
        self.examples_root = args.examples_root.resolve(strict=True)
        self.run_dir = args.run_dir.resolve(strict=True)
        self.report_path = args.report.resolve()
        self.report = report
        self.entities = {}
        self.current = None

    def input(self, relative):
        path = _require_file(self.examples_root / relative)
        if not path.is_relative_to(self.examples_root):
            raise ValueError(f"input escapes examples root: {path}")
        return path

    def output(self, relative):
        path = _require_owned(self.run_dir / relative, self.run_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def call_chem(self, name, **kwargs):
        namespace = bpy.ops.chemblender
        operator = getattr(namespace, name)
        details = _operator_rna(f"bpy.ops.chemblender.{name}", operator)
        details["arguments"] = _json_value(kwargs)
        if details["poll"] is not True:
            raise RuntimeError(f"Operator poll failed: bpy.ops.chemblender.{name}")
        result = operator(**kwargs)
        details["result"] = sorted(result)
        self.current["operators"].append(details)
        return result

    def call_wm(self, name, **kwargs):
        operator = getattr(bpy.ops.wm, name)
        details = _operator_rna(f"bpy.ops.wm.{name}", operator)
        details["arguments"] = _json_value(kwargs)
        if details["poll"] is not True:
            raise RuntimeError(f"Operator poll failed: bpy.ops.wm.{name}")
        result = operator(**kwargs)
        details["result"] = sorted(result)
        self.current["operators"].append(details)
        return result

    def rows(self):
        scene = bpy.context.scene
        settings = getattr(scene, "chemblender_project_browser")
        settings.mode = "by_data"
        settings.search = "__workflow_refresh__"
        settings.search = ""
        return [
            {
                "index": index,
                "entity_id": row.entity_id,
                "kind": row.kind,
                "label": row.label,
                "quality": row.quality,
                "view_count": row.view_count,
            }
            for index, row in enumerate(settings.rows)
        ]

    def select(self, entity_id):
        settings = getattr(bpy.context.scene, "chemblender_project_browser")
        rows = self.rows()
        row = next((item for item in rows if item["entity_id"] == entity_id), None)
        if row is None:
            raise ValueError(f"Project Browser entity is not visible: {entity_id}")
        settings.selected_index = row["index"]
        if settings.active_entity_id != entity_id:
            raise RuntimeError(f"Project Browser selection did not activate: {entity_id}")
        return row

    def remember(self, name, rows, kind):
        expected = _normal(kind)
        row = next(
            (
                item
                for item in rows
                if item["entity_id"] and _normal(item["kind"]) == expected
            ),
            None,
        )
        if row is None:
            raise ValueError(f"new import has no {kind} row")
        self.entities[name] = row["entity_id"]
        return row


def _property_snapshot(name):
    value = getattr(bpy.context.scene, name)
    snapshot = {}
    for prop in value.bl_rna.properties:
        identifier = prop.identifier
        if identifier == "rna_type":
            continue
        item = getattr(value, identifier)
        if prop.type == "COLLECTION":
            snapshot[identifier] = len(item)
        elif isinstance(item, (bool, int, float, str)):
            snapshot[identifier] = item
    return snapshot


def _new_rows(before, after):
    existing = {row["entity_id"] for row in before if row["entity_id"]}
    return [row for row in after if row["entity_id"] and row["entity_id"] not in existing]


def _import_files(context, paths, *, confirm=True):
    parents = {path.parent for path in paths}
    if len(parents) != 1:
        raise ValueError("Quick Import files must share one explicit directory")
    before = context.rows()
    result = context.call_chem(
        "quick_import",
        directory=str(paths[0].parent) + os.sep,
        files=[{"name": path.name} for path in paths],
        validation_mode="balanced",
    )
    if not _finished(result):
        raise RuntimeError(f"Quick Import did not stage: {sorted(result)}")
    preview = _property_snapshot("chemblender_quick_import")
    if not confirm:
        cancelled = context.call_chem("cancel_import")
        if not _finished(cancelled):
            raise RuntimeError(f"Cancel Import failed: {sorted(cancelled)}")
        after = context.rows()
        if {
            row["entity_id"] for row in before if row["entity_id"]
        } != {row["entity_id"] for row in after if row["entity_id"]}:
            raise RuntimeError("cancelled import changed Project Browser entities")
        return {"preview": preview, "new_rows": []}
    committed = context.call_chem("confirm_import")
    if not _finished(committed):
        raise RuntimeError(f"Import Preview did not commit: {sorted(committed)}")
    after = context.rows()
    created = _new_rows(before, after)
    if not created:
        raise RuntimeError("confirmed import created no Project Browser entity")
    return {"preview": preview, "new_rows": created}


def _copy_import_batch(context, relative_paths):
    directory = context.output("staged-inputs")
    directory.mkdir(exist_ok=True)
    paths = []
    for relative in relative_paths:
        source = context.input(relative)
        target = directory / source.name
        if target.exists():
            raise FileExistsError(f"staged input already exists: {target}")
        shutil.copyfile(source, target)
        paths.append(target)
    return paths


def _case_env(context):
    required_operators = (
        "quick_import",
        "import_smiles_text",
        "confirm_import",
        "cancel_import",
        "compute_topology",
        "accept_topology",
        "reject_topology",
        "switch_topology",
        "toggle_selective_constraints",
        "create_biological_view",
        "play_biological_models",
        "resolve_grid_semantics",
        "create_grid_view",
        "export_project_entity",
        "project_link_recovery",
        "preview_legacy_migration",
        "migrate_legacy_scene",
    )
    runtime = _runtime_snapshot()
    if tuple(bpy.app.version) < (5, 1, 0):
        raise RuntimeError("Blender 5.1.0 or newer is required")
    if not runtime["enabled"]:
        raise RuntimeError(f"Extension is not enabled as {ENABLED_KEY}")
    if not bpy.app.background:
        raise RuntimeError("mutation runner requires a background Blender child process")
    missing = [name for name in required_operators if not hasattr(bpy.ops.chemblender, name)]
    if missing:
        raise RuntimeError(f"missing public Operators: {missing}")
    scene_properties = (
        "chemblender_quick_import",
        "chemblender_project_browser",
        "chemblender_topology",
        "chemblender_grid",
    )
    missing_properties = [name for name in scene_properties if not hasattr(bpy.context.scene, name)]
    if missing_properties:
        raise RuntimeError(f"missing public Scene RNA: {missing_properties}")
    return {"status": "passed", "evidence": {"runtime": runtime, "scene_rna": scene_properties}}


def _case_imp_xyz(context):
    context.current["stage"] = "single-file import"
    water = _import_files(context, [context.input("inputs/xyz/water.xyz")])
    structure = context.remember("xyz_structure", water["new_rows"], "structure")
    context.current["stage"] = "multi-file import"
    batch_paths = _copy_import_batch(
        context,
        (
            "inputs/extxyz/carbon-trajectory.extxyz",
            "inputs/qcschema/atomic-result.json",
        ),
    )
    batch = _import_files(context, batch_paths)
    return {
        "status": "passed",
        "evidence": {
            "single_preview": water["preview"],
            "single_structure": structure,
            "multi_preview": batch["preview"],
            "multi_new_rows": batch["new_rows"],
            "objects": _objects(),
        },
    }


def _case_imp_smiles(context):
    context.current["stage"] = "SMILES import"
    before = context.rows()
    result = context.call_chem(
        "import_smiles_text",
        smiles_text="CCO",
        validation_mode="balanced",
    )
    if not _finished(result):
        raise RuntimeError(f"SMILES staging failed: {sorted(result)}")
    preview = _property_snapshot("chemblender_quick_import")
    committed = context.call_chem("confirm_import")
    if not _finished(committed):
        raise RuntimeError(f"SMILES commit failed: {sorted(committed)}")
    created = _new_rows(before, context.rows())
    structure = context.remember("smiles_structure", created, "structure")
    record = context.remember("smiles_record", created, "molecular_record")
    return {
        "status": "passed",
        "evidence": {"preview": preview, "structure": structure, "record": record},
    }


def _case_imp_cancel(context):
    context.current["stage"] = "cancel staged Cube import"
    result = _import_files(
        context,
        [context.input("inputs/cube/two-datasets.cube")],
        confirm=False,
    )
    return {"status": "passed", "evidence": result}


def _case_topology(context):
    context.current["stage"] = "MOL2 import"
    imported = _import_files(
        context,
        [context.input("inputs/mol2/substructure.mol2")],
    )
    structure = context.remember("mol2_structure", imported["new_rows"], "structure")
    context.remember("mol2_record", imported["new_rows"], "molecular_record")
    context.select(structure["entity_id"])
    context.current["stage"] = "topology proposal"
    computed = context.call_chem("compute_topology")
    if not _finished(computed):
        raise RuntimeError(f"Compute Topology failed: {sorted(computed)}")
    settings = getattr(bpy.context.scene, "chemblender_topology")
    proposal_id = settings.proposal_topology_id
    if not proposal_id:
        raise RuntimeError("Compute Topology exposed no proposal ID")
    rejected = context.call_chem("reject_topology", topology_id=proposal_id)
    if not _finished(rejected):
        raise RuntimeError(f"Reject Topology failed: {sorted(rejected)}")
    recomputed = context.call_chem("compute_topology")
    if not _finished(recomputed) or not settings.proposal_topology_id:
        raise RuntimeError("Topology proposal could not be reopened")
    proposal_id = settings.proposal_topology_id
    accepted = context.call_chem("accept_topology", topology_id=proposal_id)
    if not _finished(accepted):
        raise RuntimeError(f"Accept Topology failed: {sorted(accepted)}")
    atoms_only = context.call_chem("switch_topology", atoms_only=True)
    switched = context.call_chem(
        "switch_topology",
        atoms_only=False,
        topology_id=proposal_id,
    )
    if not _finished(atoms_only) or not _finished(switched):
        raise RuntimeError("Switch Topology failed")
    return {
        "status": "passed",
        "evidence": {
            "structure": structure,
            "proposal_id": proposal_id,
            "topology_rna": _property_snapshot("chemblender_topology"),
        },
    }


def _case_crystal(context):
    context.current["stage"] = "CONTCAR import"
    imported = _import_files(
        context,
        [context.input("inputs/poscar/velocities.CONTCAR")],
    )
    structure = context.remember("crystal_structure", imported["new_rows"], "structure")
    context.select(structure["entity_id"])
    context.current["stage"] = "Selective Dynamics view"
    toggled = context.call_chem("toggle_selective_constraints")
    if not _finished(toggled):
        raise RuntimeError(f"Toggle Selective Constraints failed: {sorted(toggled)}")
    symmetry = getattr(bpy.ops.chemblender, "derive_crystal_symmetry")
    return {
        "status": "passed",
        "evidence": {
            "structure": structure,
            "derive_symmetry": _operator_rna(
                "bpy.ops.chemblender.derive_crystal_symmetry",
                symmetry,
            ),
            "objects": _objects(),
        },
    }


def _case_biological(context):
    context.current["stage"] = "PDB import"
    imported = _import_files(
        context,
        [context.input("inputs/pdb/multimodel.pdb")],
    )
    structure = context.remember("bio_structure", imported["new_rows"], "structure")
    context.select(structure["entity_id"])
    context.current["stage"] = "biological View and MODEL playback"
    created = context.call_chem("create_biological_view")
    playback = context.call_chem("play_biological_models", frame_start=1, frame_step=1)
    selected = context.call_chem(
        "select_biological_atoms",
        selector="chain",
        chain_id="A",
    )
    if not all(_finished(result) for result in (created, playback, selected)):
        raise RuntimeError("biological workflow did not finish")
    return {
        "status": "passed",
        "evidence": {
            "structure": structure,
            "frame_end": bpy.context.scene.frame_end,
            "objects": _objects(),
        },
    }


def _case_cube(context):
    context.current["stage"] = "Cube import"
    imported = _import_files(
        context,
        [context.input("inputs/cube/two-datasets.cube")],
    )
    grid = context.remember("cube_grid", imported["new_rows"], "grid3_d")
    context.select(grid["entity_id"])
    settings = getattr(bpy.context.scene, "chemblender_grid")
    settings.dataset_index = 0
    settings.preset_id = "generic_scalar"
    settings.value_unit = "dimensionless"
    before_objects = {item["name"] for item in _objects()}
    context.current["stage"] = "resolve Grid and create Signed Surface"
    resolved = context.call_chem("resolve_grid_semantics")
    surface = context.call_chem("create_grid_view", mode="signed_surface")
    if not _finished(resolved) or not _finished(surface):
        raise RuntimeError("Grid workflow did not finish")
    after_objects = _objects()
    created = [item for item in after_objects if item["name"] not in before_objects]
    if not created:
        raise RuntimeError("Grid View created no visible object")
    return {
        "status": "passed",
        "evidence": {
            "source_grid": grid,
            "grid_rna": _property_snapshot("chemblender_grid"),
            "created_objects": created,
        },
    }


def _export_one(context, entity_id, format_name, filename, **settings):
    context.select(entity_id)
    destination = context.output(f"outputs/exports/{filename}")
    if destination.exists():
        raise FileExistsError(f"export target already exists: {destination}")
    values = {
        "filepath": str(destination),
        "format_name": format_name,
        "confirm_loss": False,
        **settings,
    }
    gate = context.call_chem("export_project_entity", **values)
    confirmed = False
    if not _finished(gate):
        if destination.exists():
            raise RuntimeError("cancelled loss gate left an export target")
        values["confirm_loss"] = True
        result = context.call_chem("export_project_entity", **values)
        confirmed = True
    else:
        result = gate
    if not _finished(result) or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"{format_name} export failed: {sorted(result)}")
    return {
        "path": str(destination),
        "role": f"{format_name}_export",
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "confirmation_required": confirmed,
    }


def _case_exports(context):
    context.current["stage"] = "PQR import"
    imported = _import_files(
        context,
        [context.input("inputs/pqr/with-chain.pqr")],
    )
    pqr_structure = context.remember("pqr_structure", imported["new_rows"], "structure")
    required = (
        "xyz_structure",
        "smiles_structure",
        "smiles_record",
        "mol2_structure",
        "crystal_structure",
        "bio_structure",
        "cube_grid",
        "pqr_structure",
    )
    missing = [name for name in required if name not in context.entities]
    if missing:
        raise RuntimeError(f"export prerequisites are absent: {missing}")
    context.current["stage"] = "Project Browser exports"
    specifications = (
        (context.entities["xyz_structure"], "xyz", "water.xyz", {}),
        (context.entities["xyz_structure"], "extxyz", "water.extxyz", {}),
        (context.entities["smiles_structure"], "mol", "ethanol.mol", {}),
        (context.entities["mol2_structure"], "mol2", "substructure.mol2", {}),
        (context.entities["bio_structure"], "pdb", "multimodel.pdb", {}),
        (context.entities["pqr_structure"], "pqr", "with-chain.pqr", {}),
        (context.entities["smiles_record"], "sdf", "ethanol.sdf", {}),
        (context.entities["smiles_structure"], "smiles", "ethanol.smi", {}),
        (
            context.entities["crystal_structure"],
            "cif",
            "crystal.cif",
            {"cif_mode": "normalized"},
        ),
        (
            context.entities["crystal_structure"],
            "poscar",
            "crystal.POSCAR",
            {},
        ),
        (
            context.entities["cube_grid"],
            "cube",
            "dataset-0.cube",
            {"cube_dataset_index": 0},
        ),
    )
    outputs = [
        _export_one(context, entity_id, format_name, filename, **settings)
        for entity_id, format_name, filename, settings in specifications
    ]
    context.current["stage"] = "multi-format re-import preview and cancel"
    before = {row["entity_id"] for row in context.rows() if row["entity_id"]}
    preview = _import_files(
        context,
        [Path(item["path"]) for item in outputs],
        confirm=False,
    )
    after = {row["entity_id"] for row in context.rows() if row["entity_id"]}
    if before != after:
        raise RuntimeError("export re-import preview changed the project after cancel")
    return {
        "status": "passed",
        "evidence": {"pqr_structure": pqr_structure, "reimport_preview": preview},
        "outputs": outputs,
    }


def _existing_output(context, case_id, role):
    case = next(
        (item for item in context.report["cases"] if item["id"] == case_id),
        None,
    )
    if case is None:
        raise ValueError(f"missing checkpoint case: {case_id}")
    output = next((item for item in case["outputs"] if item["role"] == role), None)
    if output is None:
        raise ValueError(f"missing checkpoint output: {role}")
    return _require_owned(Path(output["path"]), context.run_dir)


def _case_life(context):
    if context.args.checkpoint == "main":
        if not context.rows():
            raise RuntimeError("no Project Browser entities are available to save")
        destination = context.output("outputs/project/workflow.blend")
        if destination.exists() or destination.with_suffix(".cbq").exists():
            raise FileExistsError("project output already exists")
        context.current["stage"] = "Save Project"
        result = context.call_wm("save_as_mainfile", filepath=str(destination))
        sidecar = destination.with_suffix(".cbq")
        if not _finished(result) or not destination.is_file() or not sidecar.is_dir():
            raise RuntimeError("Save Project did not produce a .blend/.cbq pair")
        return {
            "status": "prepared",
            "evidence": {"objects": _objects(), "dirty": bool(bpy.data.is_dirty)},
            "outputs": [
                {
                    "path": str(destination),
                    "role": "project_blend",
                    "bytes": destination.stat().st_size,
                    "sha256": _sha256(destination),
                },
                {"path": str(sidecar), "role": "project_sidecar"},
            ],
            "deferred_reason": "cold reopen in a fresh Blender 5.1 process is required",
        }
    if context.args.checkpoint != "reopen":
        raise ValueError("LIFE continuation requires --checkpoint reopen")
    expected = _existing_output(context, "LIFE-SAVE-REOPEN-PREP", "project_blend")
    active = Path(bpy.data.filepath).resolve()
    if active != expected or not expected.with_suffix(".cbq").is_dir():
        raise RuntimeError("fresh Blender did not open the saved project pair")
    rows = context.rows()
    if not rows or not bpy.context.scene.objects:
        raise RuntimeError("cold reopen exposed no Project Browser rows or Views")
    return {
        "status": "passed",
        "evidence": {
            "active_file": str(active),
            "dirty": bool(bpy.data.is_dirty),
            "rows": rows,
            "objects": _objects(),
        },
        "outputs": next(
            item["outputs"]
            for item in context.report["cases"]
            if item["id"] == "LIFE-SAVE-REOPEN-PREP"
        ),
    }


def _case_migration(context):
    source = context.input("inputs/legacy/chemblender-2.1-molecule.blend")
    if context.args.checkpoint == "main":
        return {
            "status": "prepared",
            "evidence": {"source": str(source), "source_sha256": _sha256(source)},
            "deferred_reason": "open the immutable legacy fixture in a fresh Blender process",
        }
    if context.args.checkpoint == "migration":
        if Path(bpy.data.filepath).resolve() != source:
            raise RuntimeError("migration process did not open the immutable legacy fixture")
        destination = context.output("outputs/legacy/migrated.blend")
        if destination.exists() or destination.with_suffix(".cbq").exists():
            raise FileExistsError("legacy migration output already exists")
        context.current["stage"] = "save legacy working copy"
        saved = context.call_wm("save_as_mainfile", filepath=str(destination))
        if not _finished(saved):
            raise RuntimeError("legacy working copy could not be saved")
        context.current["stage"] = "legacy preview and confirmed migration"
        preview = context.call_chem("preview_legacy_migration")
        migrated = context.call_chem("migrate_legacy_scene", confirmed=True)
        final_save = context.call_wm("save_as_mainfile", filepath=str(destination))
        sidecar = destination.with_suffix(".cbq")
        if not all(_finished(result) for result in (preview, migrated, final_save)):
            raise RuntimeError("legacy preview/migration/save did not finish")
        if not destination.is_file() or not sidecar.is_dir():
            raise RuntimeError("legacy migration did not produce a .blend/.cbq pair")
        return {
            "status": "prepared",
            "evidence": {"objects": _objects()},
            "outputs": [
                {
                    "path": str(destination),
                    "role": "legacy_blend",
                    "bytes": destination.stat().st_size,
                    "sha256": _sha256(destination),
                },
                {"path": str(sidecar), "role": "legacy_sidecar"},
            ],
            "deferred_reason": "cold reopen migrated output in a fresh Blender 5.1 process",
        }
    if context.args.checkpoint != "migration-reopen":
        raise ValueError("migration continuation requires --checkpoint migration or migration-reopen")
    expected = _existing_output(context, "MIG-PREVIEW-PREP", "legacy_blend")
    if Path(bpy.data.filepath).resolve() != expected:
        raise RuntimeError("fresh Blender did not open migrated output")
    rows = context.rows()
    backup = bpy.data.collections.get("ChemBlender Legacy Backup")
    if not rows or backup is None:
        raise RuntimeError("migrated reopen lacks Project rows or legacy backup collection")
    return {
        "status": "passed",
        "evidence": {
            "active_file": str(expected),
            "rows": rows,
            "backup_objects": sorted(obj.name for obj in backup.objects),
            "objects": _objects(),
        },
        "outputs": next(
            item["outputs"]
            for item in context.report["cases"]
            if item["id"] == "MIG-PREVIEW-PREP"
        ),
    }


CASE_FUNCTIONS = {
    "ENV": _case_env,
    "IMP-XYZ": _case_imp_xyz,
    "IMP-SMILES": _case_imp_smiles,
    "IMP-CANCEL": _case_imp_cancel,
    "DATA-TOPOLOGY": _case_topology,
    "DATA-CRYSTAL": _case_crystal,
    "DATA-BIOLOGICAL": _case_biological,
    "VIEW-CUBE": _case_cube,
    "EXP-FORMATS": _case_exports,
    "LIFE-SAVE-REOPEN-PREP": _case_life,
    "MIG-PREVIEW-PREP": _case_migration,
}


def _upsert_case(report, record):
    report["cases"] = [item for item in report["cases"] if item["id"] != record["id"]]
    report["cases"].append(record)
    order = {case_id: index for index, case_id in enumerate(CASE_IDS)}
    report["cases"].sort(key=lambda item: order[item["id"]])


def _case_status(report, case_id):
    record = next((item for item in report["cases"] if item["id"] == case_id), None)
    return record["status"] if record is not None else None


def _update_deferred(report, record):
    report["deferred"] = [item for item in report["deferred"] if item["id"] != record["id"]]
    reason = record.pop("deferred_reason", None)
    if reason:
        report["deferred"].append({"id": record["id"], "reason": reason})


def _run_case(context, case_id):
    dependencies = DEPENDENCIES.get(case_id, ())
    blocked = [name for name in dependencies if _case_status(context.report, name) != "passed"]
    previous = next(
        (item for item in context.report["cases"] if item["id"] == case_id),
        None,
    )
    started = time.perf_counter()
    record = {
        "id": case_id,
        "input": list(CASE_INPUTS[case_id]),
        "operators": [],
        "status": "running",
        "stage": "start",
        "evidence": {},
        "outputs": list(previous["outputs"]) if previous else [],
        "elapsed_seconds": 0.0,
        "error": None,
    }
    if blocked:
        record["status"] = "blocked"
        record["error"] = {"stage": "dependency", "message": f"required cases not passed: {blocked}"}
        _upsert_case(context.report, record)
        _atomic_report(context.report_path, context.report)
        return
    context.current = record
    _upsert_case(context.report, record)
    _atomic_report(context.report_path, context.report)
    try:
        payload = CASE_FUNCTIONS[case_id](context)
    except (MemoryError, KeyboardInterrupt, SystemExit) as error:
        record["status"] = "fatal"
        record["error"] = {
            "stage": record["stage"],
            "type": type(error).__name__,
            "message": str(error),
        }
        record["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        _upsert_case(context.report, record)
        _atomic_report(context.report_path, context.report)
        raise
    except Exception as error:
        record["status"] = "failed"
        record["error"] = {
            "stage": record["stage"],
            "type": type(error).__name__,
            "message": str(error),
            "notes": list(getattr(error, "__notes__", ())),
            "traceback": traceback.format_exc(),
        }
    else:
        record.update(payload)
    record["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    _update_deferred(context.report, record)
    _upsert_case(context.report, record)
    _atomic_report(context.report_path, context.report)
    context.current = None


def _prepare(args):
    examples_root = args.examples_root.resolve(strict=True)
    if not (examples_root / "manifest.json").is_file():
        raise ValueError("--examples-root must contain manifest.json")
    run_dir = args.run_dir.resolve(strict=True)
    if not run_dir.is_dir():
        raise ValueError("--run-dir must be an existing directory")
    report_path = _require_owned(args.report, run_dir)
    if report_path.parent != run_dir:
        raise ValueError("--report must be directly below --run-dir")
    if args.resume:
        if not report_path.is_file():
            raise ValueError("--resume requires the existing report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("resume report schema is incompatible")
        if Path(report["run_dir"]).resolve() != run_dir:
            raise ValueError("resume report belongs to another run directory")
        if Path(report["examples_root"]).resolve() != examples_root:
            raise ValueError("resume report belongs to another examples root")
        report["runtime"] = _runtime_snapshot()
        report.setdefault("runtime_history", []).append(report["runtime"])
    else:
        if any(run_dir.iterdir()):
            raise ValueError("initial --run-dir must be empty")
        report = {
            "schema_version": SCHEMA_VERSION,
            "examples_root": str(examples_root),
            "run_dir": str(run_dir),
            "runtime": _runtime_snapshot(),
            "runtime_history": [],
            "cases": [],
            "deferred": [],
        }
    return RunContext(args, report)


def main(argv=None):
    args = _parse_args(argv) if argv is not None else _script_args()
    selected = list(CASE_IDS) if args.cases == ["all"] or tuple(args.cases) == ("all",) else list(args.cases)
    unknown = [case_id for case_id in selected if case_id not in CASE_FUNCTIONS]
    if unknown:
        raise ValueError(f"unknown case IDs: {unknown}")
    context = _prepare(args)
    _atomic_report(context.report_path, context.report)
    for case_id in CASE_IDS:
        if case_id in selected:
            _run_case(context, case_id)
    failed = [
        item["id"]
        for item in context.report["cases"]
        if item["id"] in selected and item["status"] in {"failed", "fatal", "blocked"}
    ]
    print(json.dumps({"report": str(context.report_path), "failed": failed}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
