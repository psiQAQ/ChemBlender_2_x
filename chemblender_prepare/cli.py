"""Prepare portable scientific results without importing or launching Blender."""

import argparse
from concurrent.futures import CancelledError
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from cbq_core.model import QCProject
from cbq_core.sidecar import close_project, open_project, save_project
from cbq_core.sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION
from cbq_core.storage.text import ExportCancelled
from .core.import_pipeline import ImportCancelled
from cbq_core.worker_protocol import (
    EntityReference, WorkerError, WorkerRequest, WorkerResult, WorkerStatus,
    _atomic_document, result_document, write_request, write_result,
)


def _check(cancel):
    if cancel is not None and Path(cancel).exists():
        raise CancelledError("Preparation cancelled before result publication")


def _write_progress(directory, document, cancel):
    _check(cancel)
    try:
        _atomic_document(directory / "progress.json", document)
    except PermissionError:
        # Windows readers may briefly hold this advisory file; retry at the next update.
        pass
    _check(cancel)


def _pairs(items):
    result = {}
    for item in items or ():
        key, separator, value = item.partition("=")
        if not separator or not key or key in result:
            raise ValueError("Options require unique KEY=VALUE entries")
        result[key] = value
    return result


def _hash(path, cancel=None):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            _check(cancel)
            digest.update(chunk)
    return digest.hexdigest()


def _cbq_path(value):
    path = Path(value).resolve(strict=True)
    return path.parent if path.name == "manifest.json" else path


def _new_output(value, *, cbq=True):
    path = Path(value).absolute()
    if cbq and path.suffix.lower() != ".cbq":
        raise ValueError("Output must be a new .cbq directory")
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Output already exists: {path}")
    if not path.parent.is_dir():
        raise ValueError("Output parent directory must already exist")
    return path


def _protect_input(source, destination):
    source = _cbq_path(source)
    if Path(destination).resolve().is_relative_to(source):
        raise ValueError("Output/task files must stay outside the input CBQ directory")


def _summary(project):
    from cbq_core.package_import import display_readiness
    groups = ("structures", "datasets", "basis_sets", "orbital_sets", "density_matrices", "topologies",
              "cif_envelopes", "cjson_envelopes", "qcschema_envelopes")
    entities = []
    for group in groups:
        for entity in getattr(project, group).values():
            array = getattr(entity, "data", None)
            status = getattr(entity, "status", None)
            entities.append({
                "id": str(entity.id), "revision": entity.revision,
                "type": type(entity).__name__, "group": group,
                "name": getattr(entity, "name", ""),
                "semantic_role": getattr(entity, "semantic_role", None),
                "unit": getattr(array, "unit", None),
                "shape": list(array.shape) if array is not None else None,
                "status": getattr(status, "value", status),
                "structure_id": str(entity.structure_id) if getattr(entity, "structure_id", None) else None,
            })
    return {
        "project_id": str(project.id), "schema_version": project.schema_version,
        "entities": entities,
        "sources": [{"id": str(value.id), "name": value.display_name} for value in project.sources.values()],
        "diagnostics": [{"code": value.code, "message": value.message} for value in project.diagnostics.values()],
        "display_readiness": list(display_readiness(project)),
    }


def _normalize(project):
    from .core.package_upgrade import upgrade_project
    return upgrade_project(project)


def _publish(project, destination, cancel):
    destination = _new_output(destination)
    _check(cancel)
    project = _normalize(project)
    with TemporaryDirectory(prefix=".cbq-publish-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "result.cbq"
        save_project(staged, project)
        verified = open_project(staged, verify_arrays=True)
        try:
            summary = _summary(verified)
        finally:
            close_project(verified)
        _check(cancel)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Output appeared during preparation: {destination}")
        staged.rename(destination)
    return {**summary, "output": str(destination)}


def _descriptor(source, reader_id=None):
    from .reader_api.protocol import SniffRequest
    from .reader_api.registry import builtin_reader_plugin_registry

    source = Path(source).resolve(strict=True)
    with source.open("rb") as stream:
        prefix = stream.read(65536)
    registry = builtin_reader_plugin_registry()
    return registry.select(SniffRequest(source, prefix), reader_id=reader_id)


def _copy_input(source, destination, cancel):
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"Input must be a regular file: {source}")
    digest = _hash(source, cancel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            _check(cancel)
            writer.write(chunk)
    if _hash(destination, cancel) != digest:
        raise ValueError("Input changed while copying; retry with a stable file")
    return source, digest


def _run_worker(request, directory, cancel):
    from .worker.runner import default_registry, run_request

    request_path = directory / "request.json"
    write_request(request_path, request)
    result = run_request(request_path, directory / "worker-result.json", default_registry(), cancel_path=cancel)
    if result.request_id != request.request_id:
        raise ValueError("Worker result identity mismatch")
    if result.status is WorkerStatus.CANCELLED:
        raise CancelledError(result.error.message)
    if result.status is not WorkerStatus.SUCCESS:
        raise ValueError(f"{result.error.code}: {result.error.message}")
    return result


def _validate_conversion_diagnostics(batch):
    """Preserve the legacy import gate, including isolated SDF record recovery."""
    from cbq_core.model import DiagnosticSeverity, QualityStatus
    valid_records = {record.record_key for record in batch.molecular_records}
    for item in batch.diagnostics:
        if item.severity is not DiagnosticSeverity.ERROR and item.quality_status is not QualityStatus.INVALID:
            continue
        isolated = (item.code == "sdf.record_parse_failed"
            and item.field_path.startswith("record.")
            and item.recovery_action == "other SDF records were retained"
            and item.entity_id is None and valid_records and item.record_key
            and item.record_key not in valid_records)
        if not isolated:
            raise ValueError(f"{item.code}: {item.message}")


def _reader_batch(source, reader_id, parameters, companions, directory, project, cancel, validation_mode):
    from .reader_api.worker_bridge import parse_with_worker

    descriptor = _descriptor(source, reader_id)
    if not descriptor.availability.available:
        raise ValueError(f"Reader {descriptor.reader_id} is unavailable: {descriptor.availability.reason_code}")
    source = Path(source).resolve(strict=True)
    artifact = "inputs/" + source.name
    original, digest = _copy_input(source, directory / artifact, cancel)
    sources = {artifact: (original, digest)}
    parameters = dict(parameters)
    if any(key.endswith(("_artifact", "_sha256")) for key in parameters):
        raise ValueError("Use --companion for files; artifact hashes are generated automatically")
    accepted = {"pymatgen-vasprun-electronic": {"kpoints"}, "phonopy-file": {"force_sets", "born"}}
    if set(companions) - accepted.get(descriptor.reader_id, set()):
        raise ValueError(f"Unsupported companion roles for {descriptor.reader_id}")
    if descriptor.reader_id == "phonopy-file" and "force_sets" not in companions:
        raise ValueError("Phonopy requires --companion force_sets=PATH")
    for role, path in companions.items():
        # These adapters deliberately accept only canonical task-root names.
        relative = {"force_sets": "FORCE_SETS", "born": "BORN", "kpoints":
                    "KPOINTS.gz" if str(path).lower().endswith(".gz") else "KPOINTS"}[role]
        sources[relative] = _copy_input(path, directory / relative, cancel)
        parameters[role + "_artifact"] = relative
        parameters[role + "_sha256"] = sources[relative][1]
    request = WorkerRequest(
        request_id=uuid4(), project_locator="unused.cbq", project_id=project.id,
        project_schema_version=project.schema_version, operation_id="reader.parse", operation_version="0.1",
        inputs=(), parameters={"reader_id": descriptor.reader_id, "source_artifact": artifact,
            "source_sha256": digest, "validation_mode": validation_mode, "canonical_parameters": parameters},
    )
    result = _run_worker(request, directory, cancel)
    batch = deepcopy(parse_with_worker(request, result, directory))
    # A diagnostic-only POSCAR is useful for inspection, but is not a converted structure.
    if descriptor.reader_id == "poscar" and not batch.structures:
        if batch.report is not None and any(issue.path == "poscar.species" for issue in batch.report.issues):
            raise ValueError("VASP 4 requires the actual ordered element symbols: use --param species=Na,Cl (example)")
        raise ValueError("POSCAR contains no valid structure; correct the input before conversion")
    _validate_conversion_diagnostics(batch)
    for relative, (original, expected) in sources.items():
        if _hash(original, cancel) != expected or _hash(directory / relative, cancel) != expected:
            raise ValueError("Original or staged input changed during parsing")
    original_paths = {str(directory / relative): str(value[0]) for relative, value in sources.items()}
    revision = batch.source_revisions[0]
    if revision.content_hash != digest or revision.byte_size != source.stat().st_size:
        raise ValueError("Reader source identity does not match the input")
    return replace(batch,
        sources=(replace(batch.sources[0], display_name=source.name),),
        source_revisions=(replace(revision, locator=str(source), original_filename=source.name),),
        provenance=tuple(replace(value, source=original_paths.get(value.source, value.source)) for value in batch.provenance),
    )


def _inline_smiles_batch(text, validation_mode, directory, cancel):
    from .core.import_pipeline.request import ImportRequest, ImportSource, ValidationMode
    from .core.import_pipeline.staging import StagedImportSession
    from .reader_api.import_pipeline_bridge import preflight_reader_plugins
    from .reader_api.registry import builtin_reader_plugin_registry

    staging = StagedImportSession.create(temp_parent=directory)
    try:
        request = ImportRequest(sources=(ImportSource.smiles_text(text),),
                                validation_mode=ValidationMode(validation_mode))
        preview = preflight_reader_plugins(request, builtin_reader_plugin_registry(), staging,
            is_cancelled=lambda: cancel.exists(),
            progress=lambda stage, completed, total: _write_progress(
                directory, {"stage": stage, "completed": completed, "total": total}, cancel))
        if len(preview.staged_batch_ids) != 1:
            raise ValueError("SMILES could not be parsed; check the text and external RDKit availability")
        batch = deepcopy(staging.materialize_result(preview.staged_batch_ids[0],
                                                    is_cancelled=lambda: cancel.exists()))
        if not batch.structures:
            reasons = "; ".join(value.message for value in batch.diagnostics)
            raise ValueError("SMILES contains no valid structure: " + reasons)
        _check(cancel)
        return batch
    finally:
        staging.discard()


def _pubchem_batch(query, validation_mode, directory, cancel):
    from contextlib import ExitStack
    from cbq_core.session import create_session, close_session
    from .pubchem_import import stage_pubchem_import, attach_verified_pubchem_provenance
    from .core.import_pipeline import StagedImportSession, ValidationMode
    from .reader_api.import_pipeline_bridge import preflight_reader_plugins
    from .reader_api.registry import builtin_reader_plugin_registry
    with ExitStack() as resources:
        owner = create_session(temp_parent=directory)
        resources.callback(close_session, owner)
        _write_progress(directory, {"stage": "PubChem download", "completed": 0, "total": 1}, cancel)
        downloaded = stage_pubchem_import(query, owner, validation_mode=ValidationMode(validation_mode),
                                          is_cancelled=lambda: cancel.exists())
        if downloaded.request is None:
            raise ValueError("; ".join(item.code + ": " + item.message for item in downloaded.diagnostics))
        staging = StagedImportSession.create(temp_parent=directory)
        resources.callback(staging.discard)
        preview = preflight_reader_plugins(downloaded.request, builtin_reader_plugin_registry(), staging,
            is_cancelled=lambda: cancel.exists(),
            _batch_attachment=lambda source, digest, batch: attach_verified_pubchem_provenance(source, digest, batch, owner))
        if len(preview.staged_batch_ids) != 1:
            raise ValueError("PubChem did not produce one valid molecular batch")
        batch = deepcopy(staging.materialize_result(preview.staged_batch_ids[0],
                                                    is_cancelled=lambda: cancel.exists()))
        _validate_conversion_diagnostics(batch)
        if not batch.structures:
            raise ValueError("PubChem result contains no molecular structure")
        _check(cancel)
        source = str(downloaded.request.sources[0].path)
        return replace(batch, source_revisions=tuple(replace(item, locator=downloaded.source_url)
                       for item in batch.source_revisions),
                       provenance=tuple(replace(item, source=downloaded.source_url) if item.source == source else item
                                        for item in batch.provenance))


def _convert(args, directory, cancel):
    if args.entity and args.reader != "critic2":
        raise ValueError("convert --entity is supported only with --reader critic2; no structure binding was applied")
    if sum((bool(args.sources), args.smiles_text is not None, args.pubchem is not None)) != 1:
        raise ValueError("Choose input files, --smiles-text or --pubchem, exclusively")
    if args.pubchem is not None and (args.reader or args.param or args.companion or args.entity
            or args.preset or args.unit or args.dataset_index is not None):
        raise ValueError("PubChem accepts validation mode and project options, not file/grid parameters")
    if args.smiles_text is not None and (args.reader not in (None, "smiles") or args.param
            or args.companion or args.entity or args.preset or args.unit or args.dataset_index is not None):
        raise ValueError("Inline SMILES accepts validation mode and project options, not file/grid parameters")
    destination = _new_output(args.output)
    if args.project:
        _protect_input(args.project, destination)
    project = open_project(_cbq_path(args.project)) if args.project else QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION)
    try:
        imported_structures, imported_grids = [], []
        parameters, companions = _pairs(args.param), _pairs(args.companion)
        if args.smiles_text is not None:
            batch = _inline_smiles_batch(args.smiles_text, args.validation_mode, directory, cancel)
            project.commit(batch)
            imported_structures.extend(value.id for value in batch.structures)
        elif args.pubchem is not None:
            batch = _pubchem_batch(args.pubchem, args.validation_mode, directory, cancel)
            project.commit(batch)
            imported_structures.extend(value.id for value in batch.structures)
        elif args.reader == "critic2":
            from .topology_service import load_topology_batch, commit_topology_batch
            if len(args.sources) != 1 or not args.project or not args.entity:
                raise ValueError("critic2 requires one CPREPORT file, --project and --entity STRUCTURE_UUID")
            if args.infer_bonds or args.preset or args.unit:
                raise ValueError("critic2 import does not accept grid interpretation or bond inference")
            if set(companions) - {"fluxprint"}:
                raise ValueError("critic2 accepts only the fluxprint companion")
            batch = load_topology_batch(args.sources[0], structure=project.structures[UUID(args.entity)],
                field_kind=parameters.pop("field_kind", ""), fluxprint_path=companions.get("fluxprint"),
                temp_parent=directory, is_cancelled=lambda: cancel.exists())
            if parameters:
                raise ValueError("Unsupported critic2 parameters")
            commit_topology_batch(project, batch, is_cancelled=lambda: cancel.exists())
        else:
            for index, source in enumerate(args.sources):
                _check(cancel)
                task = directory / f"reader-{index}"
                task.mkdir()
                batch = _reader_batch(source, args.reader, parameters, companions, task, project, cancel, args.validation_mode)
                project.commit(batch)
                imported_structures.extend(value.id for value in batch.structures)
                imported_grids.extend(value for value in batch.datasets if type(value).__name__ == "Grid3D")
                _write_progress(directory, {"completed": index + 1, "total": len(args.sources)}, cancel)
        if args.infer_bonds:
            from .core.topology.infer import TopologyInferenceSettings, infer_distance_topology
            from .core.topology.periodic import infer_periodic_topology
            for identifier in imported_structures:
                _check(cancel)
                structure = project.structures[identifier]
                if structure.topology_ids or structure.topology is not None:
                    continue
                periodic = structure.periodic is not None and any(structure.periodic.pbc)
                settings = TopologyInferenceSettings(periodic=periodic)
                infer = infer_periodic_topology if periodic else infer_distance_topology
                inferred = infer(structure, settings)
                if not inferred.topologies:
                    raise ValueError("Bond inference failed: " + "; ".join(item.message for item in inferred.report.issues))
                project.commit(inferred)
                topology = inferred.topologies[0]
                revision = hashlib.sha256((structure.revision + ":prepared-topology:" + topology.revision).encode()).hexdigest()
                project.structures[identifier] = replace(structure, revision=revision, topology_ids=(topology.id,))
        if args.preset or args.unit:
            from .core.grid_semantics import resolve_grid_semantics
            if not args.preset or not args.unit:
                raise ValueError("Grid interpretation requires both --preset and --unit")
            if not imported_grids:
                raise ValueError("Input contains no Grid3D to interpret")
            for grid in imported_grids:
                dataset_index = args.dataset_index
                if dataset_index is None:
                    if grid.data.dims == ("dataset", "x", "y", "z") and grid.data.shape[0] > 1:
                        raise ValueError("Multi-dataset grid interpretation requires explicit --dataset-index")
                    dataset_index = 0
                project.commit(resolve_grid_semantics(grid, dataset_index=dataset_index, preset_id=args.preset, value_unit=args.unit))
        return _publish(project, destination, cancel)
    finally:
        close_project(project)


def _derive(args, directory, cancel):
    destination = _new_output(args.output)
    source = _cbq_path(args.source)
    _protect_input(source, destination)
    working = directory / "working.cbq"
    project = open_project(source)
    sources = {}
    try:
        save_project(working, project)
        entities = {value.id: value for name in project.__dataclass_fields__ for value in
                    (getattr(project, name).values() if isinstance(getattr(project, name), dict) else ())}
        references = tuple(EntityReference(UUID(value), entities[UUID(value)].revision) for value in args.input)
        parameters = json.loads(args.parameters)
        if not isinstance(parameters, dict):
            raise ValueError("--parameters must be a JSON object")
        if args.artifact:
            artifacts = {}
            for name, path in _pairs(args.artifact).items():
                if Path(name).name != name or ":" in name or name in {".", ".."}:
                    raise ValueError("Artifact name must be a simple filename")
                relative = "inputs/" + name
                original, digest = _copy_input(path, directory / relative, cancel)
                sources[name] = (original, directory / relative, digest)
                artifacts[name] = {"path": relative, "sha256": digest}
            if "source_artifacts" in parameters:
                raise ValueError("source_artifacts is generated from --artifact")
            parameters["source_artifacts"] = artifacts
        request = WorkerRequest(uuid4(), str(working), project.id, project.schema_version,
            args.operation, args.operation_version, references, parameters)
    finally:
        close_project(project)
    result = _run_worker(request, directory, cancel)
    for original, staged, digest in sources.values():
        if _hash(original, cancel) != digest or _hash(staged, cancel) != digest:
            raise ValueError("Original or staged source changed during derivation")
    project = open_project(working)
    try:
        output_ids = {item.entity_id for item in result.outputs}
        for identifier, provenance in tuple(project.provenance.items()):
            if identifier in output_ids and sources:
                parameters = dict(provenance.parameters)
                if "source_artifacts" in parameters:
                    parameters["source_artifacts"] = {name: {"path": str(value[0]), "sha256": value[2]}
                                                       for name, value in sources.items()}
                    project.provenance[identifier] = replace(provenance,
                        parameters=tuple(parameters.items()))
        return {**_publish(project, destination, cancel), "operation": args.operation,
                "derived_outputs": [str(item.entity_id) for item in result.outputs]}
    finally:
        close_project(project)


def _conformer_summaries(suggestions):
    return [{
        "id": str(group.id), "snapshot": group.snapshot,
        "record_count": len(group.record_ids),
        "requires_review": any(value.requires_review for value in group.evidence),
        "evidence": [{"record_id": str(value.record_id), "kind": value.kind,
                      "requires_review": value.requires_review,
                      "atom_count": len(value.atom_mapping),
                      "atom_mapping": value.atom_mapping[:100],
                      "mapping_truncated": len(value.atom_mapping) > 100}
                     for value in group.evidence[:100]],
        "evidence_truncated": len(group.evidence) > 100,
    } for group in suggestions[:100]]


def _execute(args, directory, cancel):
    _check(cancel)
    if args.command == "formats":
        from .core.reader_catalog import reader_capability_document
        from .reader_api.registry import builtin_reader_plugin_registry
        document = reader_capability_document()
        descriptors = {value.reader_id: value for value in builtin_reader_plugin_registry().descriptors}
        for reader in document["readers"]:
            reader["availability"] = asdict(descriptors[reader["reader_id"]].availability)
        from .worker.runner import default_registry
        document["operations"] = [{"operation_id": key[0], "operation_version": key[1]}
                                  for key in sorted(default_registry()._operations)]
        document["special_imports"] = {"critic2": "convert --reader critic2 --project INPUT.cbq --entity STRUCTURE_UUID --param field_kind=ELECTRON_DENSITY_AU",
            "fermi": "derive INPUT.cbq --operation periodic.fermi_surface --artifact INCAR=PATH --artifact KPOINTS=PATH --artifact POSCAR=PATH --artifact OUTCAR=PATH --artifact PROCAR=PATH"}
        return document
    if args.command == "convert":
        return _convert(args, directory, cancel)
    if args.command == "derive":
        return _derive(args, directory, cancel)
    source = Path(args.source).resolve(strict=True)
    if args.command == "inspect" and source.is_file() and source.name != "manifest.json":
        descriptor = _descriptor(source, args.reader)
        metadata = {"source": str(source), "sha256": _hash(source, cancel), "reader_id": descriptor.reader_id,
                    "capabilities": {name: value.value for name, value in descriptor.capabilities.items()},
                    "availability": asdict(descriptor.availability)}
        if descriptor.reader_id == "poscar":
            from .core.formats.poscar import parse_poscar_document, _determinant
            raw = source.read_bytes()
            _check(cancel)
            if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("Input changed during inspection")
            document = parse_poscar_document(raw)
            metadata["poscar"] = {
                "comment": document.comment if len(document.comment) <= 256 else document.comment[:255] + "…",
                "scale": document.scale, "scale_factor": document.scale_factor,
                "cell": document.lattice, "cell_volume": abs(_determinant(document.lattice)), "cell_unit": "angstrom",
                "species": document.species, "counts": document.counts,
                "coordinate_mode": document.coordinate_mode,
                "selective_dynamics": document.selective_dynamics is not None,
                "ion_velocities": document.velocities is not None,
                "lattice_velocities": document.lattice_velocities is not None,
                "requires_species_assignment": document.species is None,
                "diagnostics": [{"kind": issue.kind.value, "path": issue.path, "message": issue.message}
                                for issue in document.diagnostics],
            }
            _check(cancel)
        elif descriptor.reader_id in {"extxyz", "mol", "sdf"} and descriptor.availability.available:
            from .extxyz_preview import extxyz_preview_summary
            from .core.import_pipeline.request import ImportRequest, ImportSource
            from .core.import_pipeline.staging import StagedImportSession
            from .reader_api.import_pipeline_bridge import preflight_reader_plugins
            from .reader_api.registry import builtin_reader_plugin_registry
            staging = StagedImportSession.create(temp_parent=directory)
            try:
                preview = preflight_reader_plugins(ImportRequest(sources=(ImportSource(source),)),
                    builtin_reader_plugin_registry(), staging, is_cancelled=lambda: cancel.exists())
                item, = preview.source_previews
                if item.content_hash != metadata["sha256"] or _hash(source, cancel) != metadata["sha256"]:
                    raise ValueError("Input changed during inspection")
                if len(item.staged_batch_ids) != 1:
                    raise ValueError("Inspection did not produce a valid preview")
                batch = staging.result(item.staged_batch_ids[0])
                if descriptor.reader_id == "extxyz":
                    metadata["extxyz"] = asdict(extxyz_preview_summary(batch))
                else:
                    from .core.import_pipeline.conformer_grouping import suggest_staged_conformer_groups, ConformerGroupingCancelled
                    from cbq_core.model import RecordPropertyColumn
                    try:
                        suggestions = suggest_staged_conformer_groups(preview, staging, is_cancelled=lambda: cancel.exists())
                    except ConformerGroupingCancelled as error:
                        raise CancelledError("Conformer inspection cancelled") from error
                    metadata["molecular"] = {
                        "record_count": len(batch.molecular_records),
                        "records": [{"id": str(record.id), "record_key": record.record_key[:256],
                                     "revision": record.revision, "title": record.title[:256],
                                     "block_version": record.block_version,
                                     "raw_property_count": len(record.ordered_raw_properties)}
                                    for record in batch.molecular_records[:100]],
                        "records_truncated": len(batch.molecular_records) > 100,
                        "typed_column_count": sum(isinstance(value, RecordPropertyColumn) for value in batch.datasets),
                        "topology_count": len(batch.topologies),
                        "diagnostic_count": len(batch.diagnostics),
                        "diagnostics": [{"code": value.code, "severity": value.severity.value,
                                         "message": value.message[:1024]} for value in batch.diagnostics[:100]],
                        "conformer_suggestion_count": len(suggestions),
                        "grouping_action": "keep_independent",
                        "conformer_suggestions": _conformer_summaries(suggestions),
                        "suggestions_truncated": len(suggestions) > 100,
                    }
                    if _hash(source, cancel) != metadata["sha256"]:
                        raise ValueError("Input changed during inspection")
                _check(cancel)
            finally:
                staging.discard()
        elif descriptor.reader_id == "mol2":
            from .core.formats.mol2 import parse_mol2, mol2_preview_summary
            batch = parse_mol2(source)
            if (any(value.content_hash != metadata["sha256"] for value in batch.source_revisions)
                    or _hash(source, cancel) != metadata["sha256"]):
                raise ValueError("Input changed during inspection")
            metadata["mol2"] = mol2_preview_summary(batch)
            metadata["mol2"]["interpreted_topology_count"] = len(batch.topologies)
            metadata["mol2"]["diagnostic_count"] = len(batch.diagnostics)
            metadata["mol2"]["diagnostics"] = [
                {"code": value.code, "severity": value.severity.value, "message": value.message[:1024]}
                for value in batch.diagnostics[:100]]
            _check(cancel)
        elif descriptor.reader_id == "cif" and descriptor.availability.available:
            from .core.formats.cif import parse_cif
            batch = parse_cif(source)
            envelope = batch.cif_envelopes[0]
            if (hashlib.sha256(envelope.source_bytes).hexdigest() != metadata["sha256"]
                    or _hash(source, cancel) != metadata["sha256"]):
                raise ValueError("Input changed during inspection")
            structures = {value.periodic.cif_block_index: value for value in batch.structures}
            blocks = []
            for index, name in enumerate(envelope.block_names[:100]):
                _check(cancel)
                structure = structures.get(index)
                blocks.append({
                    "index": index, "name": name[:256],
                    "has_structure": structure is not None,
                    "site_count": len(structure.atomic_numbers) if structure else 0,
                    "cell": structure.cell.values.tolist() if structure else None,
                    "cell_unit": structure.cell.unit if structure else None,
                })
            issues = batch.report.issues if batch.report else ()
            metadata["cif"] = {
                "block_count": len(envelope.block_names), "valid_block_count": len(structures),
                "site_count": sum(len(value.atomic_numbers) for value in batch.structures),
                "conversion_policy": "all_valid_blocks", "blocks": blocks,
                "blocks_truncated": len(envelope.block_names) > len(blocks),
                "diagnostics": [{"kind": issue.kind.value, "path": issue.path[:256],
                                 "message": issue.message[:1024]} for issue in issues[:100]],
                "diagnostic_count": len(issues),
            }
            _check(cancel)
        return metadata
    project = open_project(_cbq_path(source), verify_arrays=True)
    try:
        if args.command in {"inspect", "validate"}:
            summary = _summary(project)
            if args.command == "inspect" and project.molecular_records:
                from .core.import_pipeline.conformer_grouping import project_conformer_batch, suggest_conformer_groups, ConformerGroupingCancelled
                try:
                    groups = suggest_conformer_groups(project_conformer_batch(project), is_cancelled=lambda: cancel.exists())
                except ConformerGroupingCancelled as error:
                    raise CancelledError("Conformer inspection cancelled") from error
                summary.update(cbq_path=str(_cbq_path(source)), conformer_suggestion_count=len(groups),
                    conformer_suggestions=_conformer_summaries(groups), suggestions_truncated=len(groups) > 100)
            return summary
        if args.command == "upgrade":
            _protect_input(source, args.output)
            return _publish(project, args.output, cancel)
        if args.command == "export":
            from .export_service import resolve_export_selection, preview_export_selection, export_selection
            destination = _new_output(args.output, cbq=False)
            _protect_input(source, destination)
            from .core.exporters import PoscarExportSettings
            poscar_values = {name: getattr(args, "poscar_" + name) for name in (
                "comment", "coordinate_mode", "scale_policy", "target_volume", "source_scale",
                "include_selective_dynamics", "velocity_mode",
            ) if getattr(args, "poscar_" + name) is not None}
            if poscar_values and args.format != "poscar":
                raise ValueError("POSCAR settings require --format poscar")
            poscar_settings = PoscarExportSettings(**poscar_values) if poscar_values else None
            if args.format in {"cjson", "qcschema"}:
                return _export_envelope(args, project, destination, cancel)
            selection = resolve_export_selection(project, UUID(args.entity))
            preview = preview_export_selection(selection, args.format, missing_value_token=args.missing_value_token, dataset_index=args.dataset_index,
                cif_mode=args.cif_mode, poscar_settings=poscar_settings, destination=destination)
            if args.preview:
                return {"preview": asdict(preview), "output": str(destination)}
            if preview.requires_confirmation and not args.confirm_loss:
                raise ValueError("Export requires loss confirmation; review --preview, then use --confirm-loss")
            _check(cancel)
            report = export_selection(destination, selection, format_name=args.format,
                confirm_loss=args.confirm_loss, dataset_index=args.dataset_index, cif_mode=args.cif_mode,
                poscar_settings=poscar_settings,
                missing_value_token=args.missing_value_token, is_cancelled=lambda: cancel.exists())
            return {"output": str(destination), "report": asdict(report)}
        raise ValueError("Unsupported command")
    finally:
        close_project(project)


def _export_envelope(args, project, destination, cancel):
    if args.format == "cjson":
        from .core.cjson_adapter import export_cjson, preview_cjson_export
        envelope = project.cjson_envelopes[UUID(args.entity)]
        report = preview_cjson_export(envelope)
        if args.preview:
            return {"output": str(destination), "preview": asdict(report)}
        if report.requires_confirmation and not args.confirm_loss:
            raise ValueError("CJSON export omits large inline data; read --preview then use --confirm-loss")
        report = export_cjson(envelope, destination, confirm_loss=args.confirm_loss, is_cancelled=lambda: cancel.exists())
    else:
        from .core.qcschema_adapter import export_qcschema
        from cbq_core.storage.text import atomic_write_chunks
        from .core.exporters import ExportReport, ExportReportEntry
        envelope = project.qcschema_envelopes[UUID(args.entity)]
        report = ExportReport("qcschema", False, 1, False,
            (ExportReportEntry("source_envelope", "Original QCSchema envelope; derived project fields are not added"),))
        if args.preview:
            return {"output": str(destination), "preview": asdict(report)}
        document = export_qcschema(envelope)
        atomic_write_chunks(destination, (json.dumps(document, ensure_ascii=False, allow_nan=False) + "\n",),
                            is_cancelled=lambda: cancel.exists())
        report = replace(report, written=True)
    return {"output": str(destination), "report": asdict(report)}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Write the existing WorkerResult JSON to stdout")
    common.add_argument("--task-directory", type=Path, help="New task directory for progress and result files")
    common.add_argument("--cancel-file", type=Path, help="Creating this file requests cancellation")
    common.add_argument("--result-file", type=Path, help="Also write WorkerResult to this file")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("capabilities", help="Report live processor capabilities")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("worker", help="Run one Worker Protocol v1 request")
    command.add_argument("request", type=Path)
    command.add_argument("result", type=Path)
    command.add_argument("--cancel-file", type=Path)
    command = commands.add_parser("doctor", help="Diagnose local processor routing")
    command.add_argument("--json", action="store_true")
    command.add_argument("--task-directory", type=Path)
    commands.add_parser("formats", parents=[common], help="List actual reader capabilities and availability")
    for name in ("inspect", "validate", "upgrade", "export", "derive"):
        command = commands.add_parser(name, parents=[common])
        command.add_argument("source", help="CBQ directory or manifest.json; inspect also accepts a raw file")
        if name == "inspect":
            command.add_argument("--reader")
        if name in {"upgrade", "export", "derive"}:
            command.add_argument("-o", "--output", required=True)
        if name == "export":
            command.add_argument("--entity", required=True)
            command.add_argument("--format", required=True, choices=("xyz", "extxyz", "cube", "mol", "mol2", "pdb", "pqr", "sdf", "smiles", "cif", "poscar", "cjson", "qcschema"))
            command.add_argument("--preview", action="store_true")
            command.add_argument("--confirm-loss", action="store_true")
            command.add_argument("--dataset-index", type=int)
            command.add_argument("--cif-mode", choices=("preserve", "normalized"))
            command.add_argument("--missing-value-token")
            command.add_argument("--poscar-comment")
            command.add_argument("--poscar-coordinate-mode", choices=("direct", "cartesian"))
            command.add_argument("--poscar-scale-policy", choices=("unit", "preserve_source", "target_volume"))
            command.add_argument("--poscar-target-volume", type=float)
            command.add_argument("--poscar-source-scale", type=float)
            command.add_argument("--poscar-include-selective-dynamics", action=argparse.BooleanOptionalAction)
            command.add_argument("--poscar-velocity-mode", choices=("direct", "cartesian"))
        if name == "derive":
            command.add_argument("--operation", required=True)
            command.add_argument("--operation-version", default="1")
            command.add_argument("--input", action="append", default=[], help="Input entity UUID, in the operation's documented order")
            command.add_argument("--parameters", default="{}", help="Existing operation parameters as a JSON object")
            command.add_argument("--artifact", action="append", default=[], help="Explicit Fermi input NAME=PATH")
    command = commands.add_parser("convert", parents=[common])
    command.add_argument("sources", nargs="*")
    command.add_argument("--smiles-text", help="Inline SMILES; planar coordinates, not a 3D calculation")
    command.add_argument("--pubchem", help="Download a PubChem compound by CID or name")
    command.add_argument("-o", "--output", required=True)
    command.add_argument("--reader", help="Override reader; critic2 uses --project and --entity")
    command.add_argument("--param", action="append", default=[], help="Reader canonical parameter KEY=VALUE")
    command.add_argument("--companion", action="append", default=[], help="Companion file ROLE=PATH")
    command.add_argument("--project", help="Existing CBQ to add the converted results to, without modifying it")
    command.add_argument("--entity", help="Existing Structure UUID for critic2")
    command.add_argument("--validation-mode", choices=("strict", "balanced", "maximum"), default="balanced")
    command.add_argument("--preset", help="Explicit interpretation of an ambiguous grid, e.g. electron_density")
    command.add_argument("--unit", help="Explicit scientific value-unit token")
    command.add_argument("--dataset-index", type=int)
    command.add_argument("--infer-bonds", action="store_true", help="Explicit distance-based inference only for newly imported structures lacking bonds")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command in {"capabilities", "doctor", "worker"}:
        from .runtime import (
            capability_document,
            doctor_document,
            load_configuration,
            run_worker,
        )
        try:
            configuration = load_configuration()
            if args.command == "worker":
                result = run_worker(args.request, args.result, args.cancel_file,
                                    configuration)
                return 0 if result.status is WorkerStatus.SUCCESS else 1
            document = (capability_document(configuration)
                        if args.command == "capabilities"
                        else doctor_document(configuration, args.task_directory))
            print(json.dumps(document, ensure_ascii=False, allow_nan=False,
                             indent=None if args.json else 2))
            return 0 if document.get("status") != "failed" else 1
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 2
    request_id = uuid4()
    temporary = None
    try:
        protected = getattr(args, "project", None)
        if args.command in {"derive", "upgrade", "export", "validate", "inspect"}:
            candidate = Path(args.source)
            if candidate.is_dir() or candidate.name == "manifest.json":
                protected = candidate
        if protected:
            for target in (args.task_directory, args.result_file, args.cancel_file):
                if target:
                    _protect_input(protected, target)
        if args.task_directory is None:
            temporary = TemporaryDirectory(prefix="cbq-prepare-")
            directory = Path(temporary.name)
        else:
            directory = args.task_directory.absolute()
            directory.mkdir(parents=True, exist_ok=False)
        cancel = args.cancel_file.absolute() if args.cancel_file else directory / "cancel"
        try:
            # Third-party readers may print; stdout remains exactly one result.
            with redirect_stdout(sys.stderr):
                metadata = _execute(args, directory, cancel)
            metadata = json.loads(json.dumps(metadata, ensure_ascii=False, allow_nan=False))
            result = WorkerResult(request_id, WorkerStatus.SUCCESS, metadata={"command": args.command, **metadata})
        except (CancelledError, ImportCancelled, ExportCancelled, KeyboardInterrupt) as error:
            result = WorkerResult(request_id, WorkerStatus.CANCELLED, error=WorkerError("cancelled", str(error) or "Cancelled"))
        except Exception as error:
            result = WorkerResult(request_id, WorkerStatus.ERROR, error=WorkerError("prepare_failed", str(error) or type(error).__name__))
        write_result(directory / "result.json", result)
        if args.result_file:
            write_result(args.result_file, result)
        document = result_document(result)
        print(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=None if args.json else 2))
        return 0 if result.status is WorkerStatus.SUCCESS else 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            temporary.cleanup()
