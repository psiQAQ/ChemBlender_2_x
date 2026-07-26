"""Durable cache repair for ChemBlender-owned Blender Volume objects."""

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from ..core import (
    builtin_scene_presets,
    plan_scene_preset,
    volume_render_cache_key,
)


_CACHE_FORMAT_VERSION = 1
_VOLUME_PRESETS = {"grid_volume", "signed_isosurface", "property_on_surface"}
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


class ViewCacheError(RuntimeError):
    pass


def _is_link_like(path):
    return path.is_symlink() or path.is_junction()


def _absolute_path(path):
    return Path(os.path.abspath(path))


def _safe_cache_target(target, cache_root):
    target = _absolute_path(target)
    cache_root = _absolute_path(cache_root)
    if cache_root not in target.parents:
        raise ViewCacheError("derived cache escaped the verified sidecar")
    if _is_link_like(target):
        raise ViewCacheError("final render cache path is unsafe")
    if target.exists() and not target.is_file():
        raise ViewCacheError("final render cache path is unsafe")
    return target


def _durable_cache_root(sidecar_path, *, create=True):
    sidecar = Path(sidecar_path)
    if sidecar.suffix.lower() != ".cbq" or not sidecar.is_dir():
        raise ViewCacheError("verified sidecar must be an existing .cbq directory")
    if _is_link_like(sidecar):
        raise ViewCacheError("verified sidecar must not be a filesystem link")
    sidecar = sidecar.resolve(strict=True)
    current = sidecar
    for name in ("cache", "render"):
        current = current / name
        if current.exists():
            if _is_link_like(current) or not current.is_dir():
                raise ViewCacheError("render cache path is unsafe")
        else:
            if not create:
                raise ViewCacheError("render cache path is missing")
            current.mkdir()
        if current.resolve(strict=True).parent != sidecar and name == "cache":
            raise ViewCacheError("render cache escaped the verified sidecar")
    if current.resolve(strict=True).parent != sidecar / "cache":
        raise ViewCacheError("render cache escaped the verified sidecar")
    for name in ("volume", "surface"):
        child = current / name
        if child.exists():
            if _is_link_like(child) or not child.is_dir():
                raise ViewCacheError("render cache path is unsafe")
        else:
            if not create:
                raise ViewCacheError("render cache path is missing")
            child.mkdir()
        if child.resolve(strict=True).parent != current:
            raise ViewCacheError("render cache escaped the verified sidecar")
    return current


def _document(value, name):
    if not isinstance(value, str):
        raise ViewCacheError(f"{name} is missing")
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ViewCacheError(f"{name} is invalid") from error
    if not isinstance(result, dict):
        raise ViewCacheError(f"{name} must be an object")
    return result


def _current_plan(obj, project):
    preset_id = obj.get("cb_scene_preset_id")
    if preset_id not in _VOLUME_PRESETS:
        return None
    preset = builtin_scene_presets()[preset_id]
    if obj.get("cb_scene_preset_version") != preset.version:
        raise ViewCacheError("scene preset metadata is stale")
    if obj.get("cb_scene_view_kind") != preset.view_kind:
        raise ViewCacheError("scene view metadata is stale")
    bindings_document = _document(
        obj.get("cb_scene_bindings_json"), "scene bindings metadata"
    )
    if set(bindings_document) != {value.name for value in preset.bindings}:
        raise ViewCacheError("scene bindings metadata is stale")
    bindings = {}
    for spec in preset.bindings:
        value = bindings_document[spec.name]
        if not isinstance(value, dict) or set(value) != {"entity_id", "revision"}:
            raise ViewCacheError("scene bindings metadata is stale")
        try:
            identity = UUID(value["entity_id"])
        except (TypeError, ValueError, AttributeError) as error:
            raise ViewCacheError("scene bindings metadata is invalid") from error
        registry = project.structures if spec.entity_kind == "structure" else project.datasets
        entity = registry.get(identity)
        if entity is None or entity.revision != value["revision"]:
            raise ViewCacheError("scene bindings metadata is stale")
        bindings[spec.name] = identity
    settings_document = _document(
        obj.get("cb_scene_settings_json"), "scene settings metadata"
    )
    supplied = {
        name: settings_document[name]
        for name, _default in preset.default_settings
        if name in settings_document
    }
    if len(supplied) != len(preset.default_settings):
        raise ViewCacheError("scene settings metadata is stale")
    try:
        plan = plan_scene_preset(preset, project, bindings, supplied)
    except (TypeError, ValueError) as error:
        raise ViewCacheError("scene plan metadata is stale") from error
    expected_settings = json.dumps(
        dict(plan.settings), sort_keys=True, separators=(",", ":")
    )
    actual_settings = json.dumps(
        settings_document, sort_keys=True, separators=(",", ":")
    )
    if expected_settings != actual_settings:
        raise ViewCacheError("scene settings metadata is stale")
    if obj.get("cb_scene_render_identity") != plan.render_identity:
        raise ViewCacheError("scene render identity is stale")
    return plan


def _entity(plan, project, name):
    binding = next(value for value in plan.bindings if value.name == name)
    registry = (
        project.structures
        if binding.entity_kind == "structure"
        else project.datasets
    )
    return registry[binding.entity_id]


def _require(value, expected, name):
    if value != expected:
        raise ViewCacheError(f"{name} is stale")


def _surface_key(render_identity, variant):
    return hashlib.sha256(
        f"{render_identity}:{variant}".encode("utf-8")
    ).hexdigest()


def _expected_cache_target(obj, plan, project, cache_root):
    settings = dict(plan.settings)
    if plan.view_kind == "grid_volume":
        grid = _entity(plan, project, "grid")
        key = volume_render_cache_key(
            grid, dataset_index=settings["dataset_index"]
        )
        return _safe_cache_target(
            cache_root / "volume" / f"{key}.vdb", cache_root
        )
    if plan.view_kind == "signed_isosurface":
        phase = obj.get("cb_surface_phase")
        if phase not in {"positive", "negative"}:
            raise ViewCacheError("surface phase is stale")
        key = _surface_key(plan.render_identity, phase)
    else:
        key = _surface_key(plan.render_identity, "property")
    return _safe_cache_target(
        cache_root / "surface" / f"{key}.vdb", cache_root
    )


def _target_and_ensure(obj, plan, project, cache_root):
    settings = dict(plan.settings)
    if plan.view_kind == "grid_volume":
        grid = _entity(plan, project, "grid")
        index = settings["dataset_index"]
        key = volume_render_cache_key(grid, dataset_index=index)
        _require(obj.get("cb_dataset_id"), str(grid.id), "dataset identity")
        _require(obj.get("cb_dataset_revision"), grid.revision, "dataset revision")
        _require(obj.get("cb_dataset_index"), index, "dataset index")
        _require(obj.get("cb_cache_format_version"), _CACHE_FORMAT_VERSION, "cache format")
        _require(obj.get("cb_render_cache_key"), key, "render cache key")
        target = _expected_cache_target(obj, plan, project, cache_root)
        actual = _ensure_grid_volume_cache(
            grid, target, dataset_index=index
        )
        if _absolute_path(actual) != target:
            raise ViewCacheError("cache writer returned an unexpected path")
        return _safe_cache_target(target, cache_root)
    if plan.view_kind == "signed_isosurface":
        grid = _entity(plan, project, "grid")
        index = settings["dataset_index"]
        phase = obj.get("cb_surface_phase")
        if phase not in {"positive", "negative"}:
            raise ViewCacheError("surface phase is stale")
        key = _surface_key(plan.render_identity, phase)
        _require(obj.get("cb_dataset_id"), str(grid.id), "dataset identity")
        _require(obj.get("cb_dataset_revision"), grid.revision, "dataset revision")
        _require(obj.get("cb_dataset_index"), index, "dataset index")
        _require(obj.get("cb_cache_format_version"), _CACHE_FORMAT_VERSION, "cache format")
        _require(obj.get("cb_render_cache_key"), key, "render cache key")
        target = _expected_cache_target(obj, plan, project, cache_root)
        actual = _ensure_signed_surface_cache(
            grid,
            target,
            dataset_index=index,
            render_identity=plan.render_identity,
            phase=phase,
        )
        if _absolute_path(actual) != target:
            raise ViewCacheError("cache writer returned an unexpected path")
        return _safe_cache_target(target, cache_root)
    surface = _entity(plan, project, "surface_grid")
    prop = _entity(plan, project, "property_grid")
    surface_index = settings["surface_dataset_index"]
    property_index = settings["property_dataset_index"]
    key = _surface_key(plan.render_identity, "property")
    _require(obj.get("cb_dataset_id"), str(surface.id), "dataset identity")
    _require(obj.get("cb_dataset_revision"), surface.revision, "dataset revision")
    _require(obj.get("cb_dataset_index"), surface_index, "dataset index")
    _require(obj.get("cb_property_dataset_id"), str(prop.id), "property dataset identity")
    _require(
        obj.get("cb_property_dataset_revision"),
        prop.revision,
        "property dataset revision",
    )
    _require(
        obj.get("cb_property_dataset_index"),
        property_index,
        "property dataset index",
    )
    _require(obj.get("cb_cache_format_version"), _CACHE_FORMAT_VERSION, "cache format")
    _require(obj.get("cb_render_cache_key"), key, "render cache key")
    target = _expected_cache_target(obj, plan, project, cache_root)
    actual = _ensure_property_surface_cache(
        surface,
        prop,
        target,
        surface_dataset_index=surface_index,
        property_dataset_index=property_index,
        render_identity=plan.render_identity,
    )
    if _absolute_path(actual) != target:
        raise ViewCacheError("cache writer returned an unexpected path")
    return _safe_cache_target(target, cache_root)


def _ensure_grid_volume_cache(grid, path, **kwargs):
    from ..grid_volume import ensure_grid_volume_cache

    return ensure_grid_volume_cache(grid, path, **kwargs)


def _ensure_signed_surface_cache(grid, path, **kwargs):
    from ..surface_view import ensure_signed_surface_cache

    return ensure_signed_surface_cache(grid, path, **kwargs)


def _ensure_property_surface_cache(surface_grid, property_grid, path, **kwargs):
    from ..surface_view import ensure_property_surface_cache

    return ensure_property_surface_cache(surface_grid, property_grid, path, **kwargs)


def _blender_path(path, blend_path):
    absolute = str(_absolute_path(path))
    if absolute.startswith("\\\\?\\"):
        raise ViewCacheError("extended path prefixes must not enter Blender RNA")
    try:
        relative = os.path.relpath(absolute, _absolute_path(blend_path).parent)
    except ValueError:
        return absolute
    return "//" + Path(relative).as_posix()


def _blender_absolute_path(value, blend_path):
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("\\\\") or value.startswith("\\\\?\\"):
        return None
    if value.startswith("//"):
        relative = value[2:].replace("/", os.sep)
        return _absolute_path(_absolute_path(blend_path).parent / relative)
    candidate = Path(value)
    if not candidate.is_absolute():
        return None
    return _absolute_path(candidate)


def _is_owned_cache_file(path, root):
    root = _absolute_path(root)
    path = _absolute_path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if not relative.parts:
        return False
    current = root
    for part in relative.parts:
        if _is_link_like(current):
            return False
        current = current / part
    if _is_link_like(path) or not path.is_file():
        return False
    return True


def _validate_fallback_cache(
    *,
    session,
    obj,
    plan,
    old_filepath,
    blend_path,
    cache_root,
):
    path = _blender_absolute_path(old_filepath, blend_path)
    if path is None:
        return False
    roots = (
        session.temporary_root / "view-cache",
        cache_root,
    )
    if not any(_is_owned_cache_file(path, root) for root in roots):
        return False
    try:
        if plan.view_kind == "grid_volume":
            from ..grid_volume import _validate_vdb

            grid = _entity(plan, session.project, "grid")
            index = dict(plan.settings)["dataset_index"]
            key = volume_render_cache_key(grid, dataset_index=index)
            _validate_vdb(path, ("density",), key)
        elif plan.view_kind == "signed_isosurface":
            from ..surface_view import _validate_vdb

            phase = obj.get("cb_surface_phase")
            if phase not in {"positive", "negative"}:
                return False
            key = _surface_key(plan.render_identity, phase)
            _validate_vdb(path, ("density",), key)
        else:
            from ..surface_view import _validate_vdb

            key = _surface_key(plan.render_identity, "property")
            _validate_vdb(path, ("density", "property"), key)
    except BaseException as error:
        if isinstance(error, _FATAL_EXCEPTIONS):
            raise
        return False
    return True


def repair_project_view_caches(
    *,
    session,
    objects,
    blend_path,
    previous_sidecar_path=None,
):
    """Repair owned Volume caches without changing scientific project state."""
    repaired = 0
    try:
        planned = []
        for obj in tuple(objects):
            if getattr(obj, "type", None) != "VOLUME":
                continue
            plan = _current_plan(obj, session.project)
            if plan is None:
                continue
            planned.append((obj, plan))
        planned = tuple(planned)
        if planned:
            if session.sidecar_path is None or session.link_status != "connected":
                raise ViewCacheError(
                    "view cache repair requires a connected session"
                )
            cache_root = _durable_cache_root(session.sidecar_path)
        for obj, plan in planned:
            old_filepath = obj.data.filepath
            old_cache_path = obj.get("cb_cache_path")
            try:
                target = _safe_cache_target(
                    _target_and_ensure(
                        obj, plan, session.project, cache_root
                    ),
                    cache_root,
                )
                if not target.is_file():
                    raise ViewCacheError("render cache writer did not create a file")
                obj.data.filepath = str(target)
                obj.data.grids.load()
                obj.data.filepath = _blender_path(target, blend_path)
                obj["cb_cache_path"] = str(target)
            except BaseException as error:
                if isinstance(error, _FATAL_EXCEPTIONS):
                    raise
                fallback_target = None
                if previous_sidecar_path is not None:
                    try:
                        previous_cache_root = _durable_cache_root(
                            previous_sidecar_path,
                            create=False,
                        )
                        if previous_cache_root != cache_root:
                            fallback_target = _expected_cache_target(
                                obj,
                                plan,
                                session.project,
                                previous_cache_root,
                            )
                            if not _validate_fallback_cache(
                                session=session,
                                obj=obj,
                                plan=plan,
                                old_filepath=str(fallback_target),
                                blend_path=blend_path,
                                cache_root=previous_cache_root,
                            ):
                                raise ViewCacheError(
                                    "previous render cache is invalid"
                                )
                            obj.data.filepath = str(fallback_target)
                            obj.data.grids.load()
                            obj.data.filepath = _blender_path(
                                fallback_target, blend_path
                            )
                    except BaseException as fallback_error:
                        if isinstance(fallback_error, _FATAL_EXCEPTIONS):
                            raise
                        fallback_target = None
                if fallback_target is None:
                    obj.data.filepath = old_filepath
                    if _validate_fallback_cache(
                        session=session,
                        obj=obj,
                        plan=plan,
                        old_filepath=old_filepath,
                        blend_path=blend_path,
                        cache_root=cache_root,
                    ):
                        try:
                            obj.data.grids.load()
                        except BaseException as fallback_error:
                            if isinstance(fallback_error, _FATAL_EXCEPTIONS):
                                raise
                            pass
                    if old_cache_path is None:
                        try:
                            del obj["cb_cache_path"]
                        except KeyError:
                            pass
                    else:
                        obj["cb_cache_path"] = old_cache_path
                else:
                    obj["cb_cache_path"] = str(fallback_target)
                raise ViewCacheError(f"{obj.name}: {error}") from error
            repaired += 1
    except BaseException:
        session.mark_dirty("view_cache")
        raise
    if "view_cache" in session.dirty_reasons:
        session.clear_dirty("view_cache")
    return repaired
