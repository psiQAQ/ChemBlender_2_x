"""Export an opened legacy blend to a new CBQ/report directory atomically."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from cbq_core.model import QCProject
from cbq_core.sidecar import close_project, open_project, save_project
from cbq_core.sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION
from chemblender_prepare.cli import _check, _hash, _new_output
from .extraction import extract_legacy_objects
from .migration import plan_legacy_migration


def export_legacy_scene(destination, *, preview=False, cancel_file=None):
    """Requires a private Blender process with the input already open.

    The report preserves display values separately from scientific CBQ data.
    It never executes recovered node inputs or loads source paths. Missing
    numeric symmetry operations require the external Prepare upgrade command.
    """
    destination = _new_output(destination, cbq=False)
    if destination.suffix.lower() in {".blend", ".cbq"}:
        raise ValueError("Choose a new result directory, not a .blend or .cbq path")
    _check(cancel_file)
    extraction = extract_legacy_objects()
    if not extraction.source_verified or not extraction.source_hash:
        raise ValueError("Migration requires a verified saved regular .blend file")
    plan = plan_legacy_migration(extraction, QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION))
    if not plan.report.source_hash:
        raise ValueError("The source .blend changed during migration planning")
    if not plan.view_plans:
        raise ValueError("No supported legacy structures were found")
    missing_symmetry = [str(item.id) for item in plan.project.structures.values()
                        if item.periodic is not None and item.periodic.symmetry_operations
                        and item.periodic.symmetry_rotations is None]
    report = {
        "format": "chemblender.legacy-migration-report", "version": "1",
        "source": plan.report.source_path, "source_sha256": plan.report.source_hash,
        "project_id": str(plan.project.id), "output": str(destination),
        "cbq": "project.cbq", "preview": bool(preview),
        "requires_numeric_symmetry_upgrade": missing_symmetry,
        "display_restore_status": "recorded_only",
        "views": [{"structure_id": str(view.structure_id),
                   "legacy_object_name": view.legacy_object_name, "kind": view.kind,
                   "settings": asdict(view.settings)} for view in plan.view_plans],
        "diagnostics": [{**asdict(item), "quality_status": item.quality_status.value}
                        for item in plan.report.diagnostics],
    }
    _check(cancel_file)
    if preview:
        return report
    with TemporaryDirectory(prefix=".legacy-export-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "result"
        staged.mkdir()
        package = staged / "project.cbq"
        save_project(package, plan.project)
        verified = open_project(package, verify_arrays=True)
        try:
            if verified.id != plan.project.id:
                raise ValueError("Exported CBQ identity differs from migration plan")
        finally:
            close_project(verified)
        report["manifest_sha256"] = hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()
        (staged / "migration.json").write_bytes(
            (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        if _hash(plan.report.source_path, cancel_file) != plan.report.source_hash:
            raise ValueError("The source .blend changed before publication")
        _check(cancel_file)
        _new_output(destination, cbq=False)
        staged.rename(destination)
    return report
