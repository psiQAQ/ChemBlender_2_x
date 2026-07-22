"""Deterministic, dependency-free analysis report manifests."""

import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from .model import CalculationStatus, DatasetStatus, QCProject
from .recipe import RecipeDefinition, RecipePlan


SCHEMA_NAME = "chemblender_analysis_report"
SCHEMA_VERSION = 1
_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class AnalysisReportError(ValueError):
    pass


def _text(value, name):
    if not isinstance(value, str) or not value:
        raise AnalysisReportError(f"{name} must be non-empty text")
    return value


def _ids(values, name):
    values = tuple(values)
    if any(not isinstance(value, UUID) for value in values):
        raise AnalysisReportError(f"{name} must contain UUID values")
    if len(set(values)) != len(values):
        raise AnalysisReportError(f"{name} must not contain duplicates")
    return values


def _json_value(value, name="value"):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AnalysisReportError(f"{name} must be finite")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item, name) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise AnalysisReportError(f"{name} keys must be strings")
        return {key: _json_value(value[key], name) for key in sorted(value)}
    raise AnalysisReportError(f"{name} is not JSON-compatible")


def _calculation_document(calculation):
    metadata = calculation.metadata
    metadata_document = None
    if metadata is not None:
        metadata_document = {
            "driver": metadata.driver,
            "method": metadata.method,
            "basis": metadata.basis,
            "molecular_charge": metadata.molecular_charge,
            "molecular_multiplicity": metadata.molecular_multiplicity,
            "program": metadata.program,
            "program_version": metadata.program_version,
            "error_type": metadata.error_type,
            "error_message": metadata.error_message,
            "unit_convention": "ChemBlender normalized units",
        }
    return {
        "id": str(calculation.id),
        "revision": calculation.revision,
        "status": calculation.status.value,
        "input_structure_ids": sorted(str(value) for value in calculation.input_structure_ids),
        "result_structure_ids": sorted(str(value) for value in calculation.result_structure_ids),
        "dataset_ids": sorted(str(value) for value in calculation.dataset_ids),
        "provenance_ids": sorted(str(value) for value in calculation.provenance_ids),
        "metadata": metadata_document,
    }


def _dataset_document(dataset):
    return {
        "id": str(dataset.id),
        "revision": dataset.revision,
        "semantic_role": dataset.semantic_role,
        "domain": dataset.domain,
        "dims": list(dataset.data.dims),
        "shape": list(dataset.data.shape),
        "unit": dataset.data.unit,
        "status": dataset.status.value,
        "source_calculation": None
        if dataset.source_calculation is None
        else str(dataset.source_calculation),
        "provenance_ids": sorted(str(value) for value in dataset.provenance_ids),
    }


def _provenance_document(record):
    return {
        "id": str(record.id),
        "revision": record.revision,
        "producer": record.producer,
        "producer_version": record.producer_version,
        "source": record.source,
        "source_hash": record.source_hash,
        "parent_ids": sorted(str(value) for value in record.parent_ids),
        "operation": record.operation,
        "parameters": [
            {"name": name, "value": _json_value(value, f"provenance parameter {name}")}
            for name, value in sorted(record.parameters, key=lambda item: item[0])
        ],
    }


def _recipe_document(recipe, plan, project):
    if not isinstance(recipe, RecipeDefinition) or not isinstance(plan, RecipePlan):
        raise AnalysisReportError("recipe and recipe_plan must be supplied together")
    if (recipe.recipe_id, recipe.version) != (plan.recipe_id, plan.recipe_version):
        raise AnalysisReportError("recipe plan identity does not match recipe")
    specifications = {value.name: value for value in recipe.inputs}
    if {value.name for value in plan.bindings} != set(specifications):
        raise AnalysisReportError("recipe plan bindings do not match recipe inputs")
    registries = {
        "structure": project.structures,
        "dataset": project.datasets,
        "basis_set": project.basis_sets,
        "orbital_set": project.orbital_sets,
        "density_matrix": project.density_matrices,
    }
    bindings = []
    for binding in sorted(plan.bindings, key=lambda value: value.name):
        specification = specifications[binding.name]
        if binding.entity_kind != specification.entity_kind:
            raise AnalysisReportError("recipe binding kind does not match recipe input")
        entity = registries[binding.entity_kind].get(binding.entity_id)
        if entity is None or entity.revision != binding.revision:
            raise AnalysisReportError("recipe binding is missing or stale")
        bindings.append(
            {
                "name": binding.name,
                "entity_kind": binding.entity_kind,
                "entity_id": str(binding.entity_id),
                "revision": binding.revision,
            }
        )
    if not isinstance(plan.derivation_key, str) or not _SHA256.fullmatch(
        plan.derivation_key
    ):
        raise AnalysisReportError("recipe derivation key must be SHA-256 hex")
    return {
        "recipe_id": recipe.recipe_id,
        "version": recipe.version,
        "title": recipe.title,
        "derivation_key": plan.derivation_key,
        "bindings": bindings,
        "parameters": [
            {"name": name, "value": _json_value(value, f"recipe parameter {name}")}
            for name, value in sorted(plan.parameters, key=lambda item: item[0])
        ],
        "citations": [
            {
                "key": citation.key,
                "title": citation.title,
                "doi": citation.doi,
                "url": citation.url,
            }
            for citation in sorted(recipe.citations, key=lambda value: value.key)
        ],
    }


def _provenance_closure(project, initial_ids):
    pending = list(initial_ids)
    found = set()
    while pending:
        identity = pending.pop()
        if identity in found:
            continue
        record = project.provenance.get(identity)
        if record is None:
            raise AnalysisReportError(f"provenance is missing: {identity}")
        found.add(identity)
        pending.extend(record.parent_ids)
    return tuple(project.provenance[value] for value in sorted(found, key=str))


def build_analysis_report(
    project,
    *,
    title,
    calculation_ids=(),
    dataset_ids=(),
    recipe=None,
    recipe_plan=None,
    artifacts=(),
):
    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    title = _text(title, "title")
    calculation_ids = _ids(calculation_ids, "calculation_ids")
    dataset_ids = set(_ids(dataset_ids, "dataset_ids"))
    if not calculation_ids and not dataset_ids:
        raise AnalysisReportError("report requires a calculation or dataset selection")
    try:
        calculations = tuple(project.calculations[value] for value in calculation_ids)
    except KeyError as error:
        raise AnalysisReportError("selected calculation is not present") from error
    for calculation in calculations:
        dataset_ids.update(calculation.dataset_ids)
    try:
        datasets = tuple(project.datasets[value] for value in sorted(dataset_ids, key=str))
    except KeyError as error:
        raise AnalysisReportError("selected dataset is not present") from error

    if (recipe is None) != (recipe_plan is None):
        raise AnalysisReportError("recipe and recipe_plan must be supplied together")
    recipe_document = (
        None if recipe is None else _recipe_document(recipe, recipe_plan, project)
    )
    provenance_ids = {
        identity
        for entity in (*calculations, *datasets)
        for identity in entity.provenance_ids
    }
    provenance = _provenance_closure(project, provenance_ids)

    artifact_documents = tuple(artifacts)
    for artifact in artifact_documents:
        _validate_artifact(artifact)
    artifact_documents = sorted(
        (dict(value) for value in artifact_documents),
        key=lambda value: (value["role"], value["path"]),
    )

    warnings = []
    for calculation in sorted(calculations, key=lambda value: str(value.id)):
        if calculation.status is not CalculationStatus.SUCCESS:
            warnings.append(
                f"calculation {calculation.id} status is {calculation.status.value}"
            )
    for dataset in datasets:
        if dataset.status is not DatasetStatus.COMPLETE:
            warnings.append(f"dataset {dataset.id} status is {dataset.status.value}")
    if any(value.status is CalculationStatus.FAILED for value in calculations):
        status = "failed"
    elif warnings:
        status = "incomplete"
    else:
        status = "complete"
    document = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "project": {"id": str(project.id), "schema_version": project.schema_version},
        "title": title,
        "status": status,
        "calculations": [
            _calculation_document(value)
            for value in sorted(calculations, key=lambda value: str(value.id))
        ],
        "datasets": [_dataset_document(value) for value in datasets],
        "provenance": [_provenance_document(value) for value in provenance],
        "recipe": recipe_document,
        "artifacts": artifact_documents,
        "warnings": warnings,
    }
    return validate_analysis_report(document)


def _validate_artifact(document):
    fields = {"role", "path", "media_type", "sha256", "size"}
    if not isinstance(document, dict) or set(document) != fields:
        raise AnalysisReportError("invalid report artifact")
    if not isinstance(document["role"], str) or not _TOKEN.fullmatch(document["role"]):
        raise AnalysisReportError("artifact role must be a lower token")
    _text(document["media_type"], "artifact media_type")
    path = document["path"]
    if not isinstance(path, str) or PurePosixPath(path).is_absolute() or any(
        value in {"", ".", ".."} for value in PurePosixPath(path).parts
    ):
        raise AnalysisReportError("artifact path must be a safe relative POSIX path")
    if "\\" in path:
        raise AnalysisReportError("artifact path must use POSIX separators")
    if not isinstance(document["sha256"], str) or not _SHA256.fullmatch(
        document["sha256"]
    ):
        raise AnalysisReportError("artifact sha256 is invalid")
    if isinstance(document["size"], bool) or not isinstance(document["size"], int) or document[
        "size"
    ] < 0:
        raise AnalysisReportError("artifact size is invalid")


def describe_report_artifact(root, relative_path, *, role, media_type):
    root = Path(root).resolve()
    if not root.is_dir():
        raise AnalysisReportError("artifact root must be an existing directory")
    relative_path = str(relative_path)
    candidate_document = {
        "role": role,
        "path": relative_path,
        "media_type": media_type,
        "sha256": "0" * 64,
        "size": 0,
    }
    _validate_artifact(candidate_document)
    candidate = (root / Path(*PurePosixPath(relative_path).parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise AnalysisReportError("artifact path escapes its root") from error
    if not candidate.is_file():
        raise AnalysisReportError("artifact does not exist")
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    document = dict(candidate_document)
    document["sha256"] = digest.hexdigest()
    document["size"] = candidate.stat().st_size
    return document


def validate_analysis_report(document):
    fields = {
        "schema_name",
        "schema_version",
        "project",
        "title",
        "status",
        "calculations",
        "datasets",
        "provenance",
        "recipe",
        "artifacts",
        "warnings",
    }
    if not isinstance(document, dict) or set(document) != fields:
        raise AnalysisReportError("invalid analysis report fields")
    if (document["schema_name"], document["schema_version"]) != (
        SCHEMA_NAME,
        SCHEMA_VERSION,
    ):
        raise AnalysisReportError("unsupported analysis report schema")
    if document["status"] not in {"complete", "incomplete", "failed"}:
        raise AnalysisReportError("invalid analysis report status")
    _text(document["title"], "title")
    project = document["project"]
    if not isinstance(project, dict) or set(project) != {"id", "schema_version"}:
        raise AnalysisReportError("invalid report project identity")
    try:
        UUID(project["id"])
    except (TypeError, ValueError) as error:
        raise AnalysisReportError("invalid report project UUID") from error
    _text(project["schema_version"], "project schema_version")
    for name in ("calculations", "datasets", "provenance", "artifacts", "warnings"):
        if not isinstance(document[name], list):
            raise AnalysisReportError(f"{name} must be a list")
    if any(not isinstance(value, str) or not value for value in document["warnings"]):
        raise AnalysisReportError("warnings must contain text")

    def exact(value, expected, label):
        if not isinstance(value, dict) or set(value) != expected:
            raise AnalysisReportError(f"invalid {label} fields")

    def uuid_text(value, label):
        try:
            UUID(value)
        except (TypeError, ValueError) as error:
            raise AnalysisReportError(f"invalid {label} UUID") from error

    def uuid_list(values, label):
        if not isinstance(values, list):
            raise AnalysisReportError(f"{label} must be a list")
        for value in values:
            uuid_text(value, label)
        if len(set(values)) != len(values):
            raise AnalysisReportError(f"{label} must not contain duplicates")

    calculation_fields = {
        "id",
        "revision",
        "status",
        "input_structure_ids",
        "result_structure_ids",
        "dataset_ids",
        "provenance_ids",
        "metadata",
    }
    metadata_fields = {
        "driver",
        "method",
        "basis",
        "molecular_charge",
        "molecular_multiplicity",
        "program",
        "program_version",
        "error_type",
        "error_message",
        "unit_convention",
    }
    for value in document["calculations"]:
        exact(value, calculation_fields, "calculation")
        uuid_text(value["id"], "calculation")
        _text(value["revision"], "calculation revision")
        if value["status"] not in {item.value for item in CalculationStatus}:
            raise AnalysisReportError("invalid calculation status")
        for name in (
            "input_structure_ids",
            "result_structure_ids",
            "dataset_ids",
            "provenance_ids",
        ):
            uuid_list(value[name], f"calculation {name}")
        if value["metadata"] is not None:
            exact(value["metadata"], metadata_fields, "calculation metadata")
            for name in (
                "driver",
                "method",
                "program",
                "program_version",
                "unit_convention",
            ):
                _text(value["metadata"][name], f"metadata {name}")

    dataset_fields = {
        "id",
        "revision",
        "semantic_role",
        "domain",
        "dims",
        "shape",
        "unit",
        "status",
        "source_calculation",
        "provenance_ids",
    }
    for value in document["datasets"]:
        exact(value, dataset_fields, "dataset")
        uuid_text(value["id"], "dataset")
        for name in ("revision", "semantic_role", "domain", "unit"):
            _text(value[name], f"dataset {name}")
        if value["status"] not in {item.value for item in DatasetStatus}:
            raise AnalysisReportError("invalid dataset status")
        if not isinstance(value["dims"], list) or any(
            not isinstance(item, str) or not item for item in value["dims"]
        ):
            raise AnalysisReportError("dataset dims are invalid")
        if not isinstance(value["shape"], list) or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in value["shape"]
        ):
            raise AnalysisReportError("dataset shape is invalid")
        if len(value["dims"]) != len(value["shape"]):
            raise AnalysisReportError("dataset dims/shape rank differs")
        if value["source_calculation"] is not None:
            uuid_text(value["source_calculation"], "dataset source calculation")
        uuid_list(value["provenance_ids"], "dataset provenance_ids")

    provenance_fields = {
        "id",
        "revision",
        "producer",
        "producer_version",
        "source",
        "source_hash",
        "parent_ids",
        "operation",
        "parameters",
    }
    for value in document["provenance"]:
        exact(value, provenance_fields, "provenance")
        uuid_text(value["id"], "provenance")
        for name in ("revision", "producer", "producer_version", "operation"):
            _text(value[name], f"provenance {name}")
        if not isinstance(value["source"], str):
            raise AnalysisReportError("provenance source must be text")
        if value["source_hash"] and not _SHA256.fullmatch(value["source_hash"]):
            raise AnalysisReportError("provenance source_hash is invalid")
        uuid_list(value["parent_ids"], "provenance parent_ids")
        if not isinstance(value["parameters"], list):
            raise AnalysisReportError("provenance parameters must be a list")
        for parameter in value["parameters"]:
            exact(parameter, {"name", "value"}, "provenance parameter")
            _text(parameter["name"], "provenance parameter name")
            _json_value(parameter["value"], "provenance parameter")

    recipe = document["recipe"]
    if recipe is not None:
        exact(
            recipe,
            {
                "recipe_id",
                "version",
                "title",
                "derivation_key",
                "bindings",
                "parameters",
                "citations",
            },
            "recipe",
        )
        for name in ("recipe_id", "version", "title"):
            _text(recipe[name], f"recipe {name}")
        if not isinstance(recipe["derivation_key"], str) or not _SHA256.fullmatch(
            recipe["derivation_key"]
        ):
            raise AnalysisReportError("recipe derivation_key is invalid")
        for name in ("bindings", "parameters", "citations"):
            if not isinstance(recipe[name], list):
                raise AnalysisReportError(f"recipe {name} must be a list")
        for binding in recipe["bindings"]:
            exact(
                binding,
                {"name", "entity_kind", "entity_id", "revision"},
                "recipe binding",
            )
            for name in ("name", "entity_kind", "revision"):
                _text(binding[name], f"recipe binding {name}")
            uuid_text(binding["entity_id"], "recipe binding entity")
        for parameter in recipe["parameters"]:
            exact(parameter, {"name", "value"}, "recipe parameter")
            _text(parameter["name"], "recipe parameter name")
            _json_value(parameter["value"], "recipe parameter")
        for citation in recipe["citations"]:
            exact(citation, {"key", "title", "doi", "url"}, "recipe citation")
            _text(citation["key"], "citation key")
            _text(citation["title"], "citation title")
            if not isinstance(citation["doi"], str) or not isinstance(
                citation["url"], str
            ):
                raise AnalysisReportError("citation DOI and URL must be text")
    for artifact in document["artifacts"]:
        _validate_artifact(artifact)
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise AnalysisReportError("report must be finite JSON") from error
    normalized = json.loads(encoded)
    normalized["calculations"].sort(key=lambda value: value["id"])
    normalized["datasets"].sort(key=lambda value: value["id"])
    normalized["provenance"].sort(key=lambda value: value["id"])
    normalized["artifacts"].sort(key=lambda value: (value["role"], value["path"]))
    normalized["warnings"].sort()
    if normalized["recipe"] is not None:
        normalized["recipe"]["bindings"].sort(key=lambda value: value["name"])
        normalized["recipe"]["parameters"].sort(key=lambda value: value["name"])
        normalized["recipe"]["citations"].sort(key=lambda value: value["key"])
    for value in normalized["provenance"]:
        value["parameters"].sort(key=lambda item: item["name"])
    return normalized


def _cell(value):
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def render_analysis_report_markdown(document):
    document = validate_analysis_report(document)
    lines = [
        f"# {_cell(document['title'])}",
        "",
        f"状态：`{document['status']}`",
        "",
    ]
    if document["status"] != "complete":
        lines.extend(("> 此报告包含失败、不完整或有歧义的数据，不能作为有效计算结论。", ""))
    lines.extend(
        (
            "## 计算",
            "",
            "| ID | 状态 | 程序 | 方法 | 基组 |",
            "| --- | --- | --- | --- | --- |",
        )
    )
    for value in document["calculations"]:
        metadata = value["metadata"] or {}
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                _cell(value["id"]),
                _cell(value["status"]),
                _cell(metadata.get("program", "")),
                _cell(metadata.get("method", "")),
                _cell(metadata.get("basis") or ""),
            )
        )
    lines.extend(
        (
            "",
            "## 数据集",
            "",
            "| ID | 语义 | 状态 | 维度 | 单位 |",
            "| --- | --- | --- | --- | --- |",
        )
    )
    for value in document["datasets"]:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                _cell(value["id"]),
                _cell(value["semantic_role"]),
                _cell(value["status"]),
                _cell(" × ".join(str(item) for item in value["shape"])),
                _cell(value["unit"]),
            )
        )
    recipe = document["recipe"]
    if recipe is not None:
        lines.extend(
            (
                "",
                "## Recipe",
                "",
                f"`{_cell(recipe['recipe_id'])}@{_cell(recipe['version'])}` — {_cell(recipe['title'])}",
                "",
                "### 引用",
                "",
            )
        )
        for citation in recipe["citations"]:
            target = citation["doi"] or citation["url"]
            lines.append(f"- `{_cell(citation['key'])}`：{_cell(citation['title'])} — {_cell(target)}")
    lines.extend(("", "## Provenance", ""))
    for value in document["provenance"]:
        lines.append(
            f"- `{_cell(value['id'])}`：{_cell(value['producer'])} {_cell(value['producer_version'])} / `{_cell(value['operation'])}`"
        )
    if document["artifacts"]:
        lines.extend(("", "## Artifacts", ""))
        for value in document["artifacts"]:
            lines.append(
                f"- `{_cell(value['role'])}`：`{_cell(value['path'])}` ({_cell(value['media_type'])}, SHA-256 `{value['sha256']}`)"
            )
    if document["warnings"]:
        lines.extend(("", "## 警告", ""))
        lines.extend(f"- {_cell(value)}" for value in document["warnings"])
    return "\n".join(lines) + "\n"


def write_analysis_report_bundle(directory, document):
    document = validate_analysis_report(document)
    target = Path(directory)
    if target.exists():
        raise AnalysisReportError("report bundle already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.mkdir()
        manifest = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8") + b"\n"
        markdown = render_analysis_report_markdown(document).encode("utf-8")
        for name, data in (("manifest.json", manifest), ("report.md", markdown)):
            with (temporary / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return target / "manifest.json", target / "report.md"
