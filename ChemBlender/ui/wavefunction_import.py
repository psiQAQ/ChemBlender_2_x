"""Explicit external-worker wavefunction import and transactional publication."""

import hashlib
import os
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from ..core.import_pipeline import (
    ImportCancelled, ImportCommitDecisions, ImportPreview, SourcePreview,
    StagedImportSession, commit_import_preview, detect_import_conflicts,
)
from ..core.iodata_adapter import sniff_iodata_wavefunction
from ..core.readers import SniffMatch
from ..core.worker_protocol import WorkerRequest
from ..reader_api.worker_bridge import WorkerReaderExecutionError, parse_with_worker
from ..worker_client import start_worker
from .tasks import Task, TaskWorker


_ACTIVE_IMPORTS = []


def _source_hash(path, is_cancelled):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if is_cancelled():
                raise ImportCancelled("wavefunction import cancelled")
            digest.update(chunk)
    return digest.hexdigest()


def load_wavefunction_batch(
    source, *, python_executable, repository, project_id, schema_version,
    temp_parent, is_cancelled=lambda: False, progress=lambda _stage, _value: None,
):
    """Parse in an external Python; return arrays independent of worker files."""
    source = Path(source).resolve(strict=True)
    if source.suffix.lower() not in {".fchk", ".fch", ".molden", ".input"}:
        raise ValueError("select an FCHK or Molden wavefunction file")
    with source.open("rb") as stream:
        prefix = stream.read(65536)
    if sniff_iodata_wavefunction(source, prefix).match != SniffMatch.EXACT:
        raise ValueError("file content is not a supported FCHK or Molden wavefunction")
    if is_cancelled():
        raise ImportCancelled("wavefunction import cancelled")
    digest = _source_hash(source, is_cancelled)
    # IOData recognizes *.molden.input, not arbitrary *.input filenames.
    artifact = "source.molden" if source.suffix.lower() in {".molden", ".input"} else "source.fchk"
    request = WorkerRequest(
        request_id=uuid4(), project_locator="unused.cbq", project_id=project_id,
        project_schema_version=schema_version, operation_id="reader.parse",
        operation_version="0.1", inputs=(), parameters={
            "reader_id": "iodata_wavefunction", "source_artifact": artifact,
            "source_sha256": digest, "validation_mode": "balanced",
            "canonical_parameters": {},
        },
    )
    progress("copy source", 0.1)
    with TemporaryDirectory(prefix="wf-", dir=temp_parent) as workspace:
        # Blender's Windows executable does not opt into long filesystem paths.
        # Include the immutable SHA-256 filename, not just the task directory.
        artifact_path = (Path(workspace).absolute() / str(request.request_id)
                         / "reader-bundle" / "artifacts" / ("0" * 64 + ".npy"))
        if os.name == "nt" and len(str(artifact_path).encode("utf-16-le")) // 2 >= 260:
            raise ValueError(
                "Wavefunction import temporary path exceeds Blender's Windows "
                "path limit. Set a shorter Temporary Files directory in Blender "
                "Preferences and reopen the project before importing."
            )
        handle = start_worker(
            request, workspace, python_executable=python_executable,
            working_directory=repository, staged_inputs={artifact: source},
        )
        try:
            progress("parse wavefunction", 0.3)
            while True:
                if is_cancelled():
                    handle.request_cancel()
                    raise ImportCancelled("wavefunction import cancelled")
                result = handle.poll()
                if result is not None:
                    break
                time.sleep(0.05)
            handle.wait(timeout=5)
            if is_cancelled():
                raise ImportCancelled("wavefunction import cancelled")
            task_directory = handle.request_path.parent
            try:
                batch = parse_with_worker(request, result, task_directory)
            except WorkerReaderExecutionError as error:
                if result.error.code == "reader_unavailable":
                    raise WorkerReaderExecutionError(
                        "FCHK/Molden import requires qc-iodata in the configured "
                        f"Worker Python ({python_executable}). Open Worker Setup "
                        "to select an environment with qc-iodata."
                    ) from error
                raise
            # The canonical decoder currently owns its arrays. Copy explicitly
            # so future decoder storage choices cannot outlive this workspace.
            batch = deepcopy(batch)
            if not batch.structures or not batch.basis_sets or not batch.orbital_sets:
                raise ValueError("wavefunction must contain a structure, basis and orbitals")
            if _source_hash(source, is_cancelled) != digest:
                raise ValueError("source changed during import; select it again")
            progress("verify source", 0.9)
            revision = batch.source_revisions[0]
            if revision.content_hash != digest or revision.byte_size != (task_directory / artifact).stat().st_size:
                raise ValueError("worker source identity does not match the verified source")
            staged_source = str(task_directory / artifact)
            return replace(
                batch,
                sources=(replace(batch.sources[0], display_name=source.name),),
                source_revisions=(replace(
                    revision, locator=str(source), original_filename=source.name,
                ),),
                provenance=tuple(
                    replace(record, source=str(source))
                    if record.source == staged_source else record
                    for record in batch.provenance
                ),
            )
        finally:
            # Only this launcher-owned process is stopped. No live Blender or
            # other worker is touched, including during session teardown.
            handle.terminate()


def commit_wavefunction_batch(session, batch):
    """Publish a verified batch on the main thread through existing staging."""
    staging = StagedImportSession.create(temp_parent=session.temporary_root)
    try:
        batch_id = uuid4()
        staging.register_result(batch_id, batch)
        revision = batch.source_revisions[0]
        source_preview = SourcePreview(
            source_id=revision.source_id, source_path=Path(revision.locator),
            selected_reader_id=revision.reader_id, content_hash=revision.content_hash,
            byte_size=revision.byte_size, staged_batch_ids=(batch_id,),
            diagnostic_ids=revision.diagnostic_ids,
        )
        preview = ImportPreview(
            staging.id, (source_preview,), staged_batch_ids=(batch_id,),
            diagnostic_ids=revision.diagnostic_ids,
        )
        if detect_import_conflicts(session.project, preview, staging):
            raise ValueError("source is already imported; select its existing orbitals or resolve the source revision in Quick Import")
        result = commit_import_preview(session, staging, preview, ImportCommitDecisions())
        session.active_entity_id = batch.orbital_sets[0].id
        return result
    finally:
        staging.discard()


def _cancel_session_imports(session):
    for operator in tuple(_ACTIVE_IMPORTS):
        if operator._session is session:
            operator._job.request_cancel()
            operator._job.join()
            operator._finish_modal()


def register():
    from .session import register_session_cleanup
    register_session_cleanup(_cancel_session_imports)


def unregister():
    from .session import unregister_session_cleanup
    for operator in tuple(_ACTIVE_IMPORTS):
        _cancel_session_imports(operator._session)
    unregister_session_cleanup(_cancel_session_imports)


def draw_wavefunction_import(layout, context, session):
    row = layout.row()
    row.enabled = not any(operator._session is session for operator in _ACTIVE_IMPORTS)
    row.operator("chemblender.import_wavefunction", text="Import FCHK / Molden", icon="IMPORT")
    for operator in _ACTIVE_IMPORTS:
        if operator._session is session:
            snapshot = operator._job.task.snapshot()
            layout.label(text=f"{snapshot.stage}: {snapshot.progress:.0%} (Esc to cancel)")


try:
    import bpy
    from bpy.props import StringProperty
    from bpy_extras.io_utils import ImportHelper
except ModuleNotFoundError:
    bpy = None


if bpy is not None:
    class CHEMBLENDER_OT_import_wavefunction(bpy.types.Operator, ImportHelper):
        bl_idname = "chemblender.import_wavefunction"
        bl_label = "Import Wavefunction"
        bl_description = "Parse FCHK or Molden with the configured external Python worker"

        filter_glob: StringProperty(default="*.fchk;*.fch;*.molden;*.input", options={"HIDDEN"})

        def execute(self, context):
            from .session import get_scene_session
            from .wavefunction import worker_configuration

            self._timer = None
            self._manager = context.window_manager
            self._session = get_scene_session(context.scene)
            if any(operator._session is self._session for operator in _ACTIVE_IMPORTS):
                self.report({"ERROR"}, "a wavefunction import is already running")
                return {"CANCELLED"}
            try:
                executable, repository = worker_configuration(context.scene.chemblender_wavefunction)
                session = self._session
                source = self.filepath
                self._job = TaskWorker(Task(), lambda cancelled, progress: load_wavefunction_batch(
                    source, python_executable=executable, repository=repository,
                    project_id=session.project.id, schema_version=session.project.schema_version,
                    temp_parent=session.temporary_root, is_cancelled=cancelled, progress=progress,
                ))
                _ACTIVE_IMPORTS.append(self)
                self._job.start("import wavefunction")
                if bpy.app.background:
                    self._job.join()
                    return self._complete(context)
                self._timer = self._manager.event_timer_add(0.1, window=context.window)
                self._manager.modal_handler_add(self)
                return {"RUNNING_MODAL"}
            except Exception as error:
                if self in _ACTIVE_IMPORTS:
                    self._job.request_cancel()
                    self._job.join()
                self._finish_modal()
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}

        def modal(self, context, event):
            if self not in _ACTIVE_IMPORTS:
                return {"CANCELLED"}
            if event.type == "ESC":
                self._job.request_cancel()
            if self._job.done:
                return self._complete(context)
            return {"PASS_THROUGH"}

        def _complete(self, context):
            from .session import get_scene_session, _notify_session_mutation
            from .wavefunction import select_wavefunction_source
            try:
                if self._job.task.is_cancelled() or isinstance(self._job.error, ImportCancelled):
                    return {"CANCELLED"}
                self._job.raise_if_failed()
                if get_scene_session(context.scene) is not self._session:
                    raise RuntimeError("project changed while importing the wavefunction")
                commit_wavefunction_batch(self._session, self._job.result)
                context.scene.chemblender_project_browser.active_entity_id = str(self._session.active_entity_id)
                select_wavefunction_source(
                    context.scene.chemblender_wavefunction,
                    self._session.project.orbital_sets[self._session.active_entity_id],
                )
                _notify_session_mutation(self._session)
                self.report({"INFO"}, "Wavefunction imported")
                return {"FINISHED"}
            except Exception as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            finally:
                self._finish_modal()

        def _finish_modal(self):
            if getattr(self, "_timer", None) is not None:
                self._manager.event_timer_remove(self._timer)
                self._timer = None
            if self in _ACTIVE_IMPORTS:
                _ACTIVE_IMPORTS.remove(self)

        def cancel(self, context):
            job = getattr(self, "_job", None)
            if job is not None:
                job.request_cancel()
                job.join()
            self._finish_modal()
