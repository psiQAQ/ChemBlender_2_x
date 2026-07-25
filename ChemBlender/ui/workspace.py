"""Optional ChemBlender workspace loader."""

from pathlib import Path
import os

import bpy


WORKSPACE_NAME = "ChemBlender"
_ASSET_NAME = "Chem_Workspace.blend"
_pending_rollback = None


def workspace_asset_path() -> Path:
    package_dir = Path(os.path.abspath(__file__)).parents[1]
    return package_dir / "assets" / _ASSET_NAME


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return any(
        candidate.is_symlink() or is_junction(candidate)
        for candidate in (path, path.parent, path.parent.parent)
    )


def _area_center(area):
    return (
        area.x + area.width / 2,
        area.y + area.height / 2,
    )


def workspace_is_compatible(workspace) -> bool:
    screens = tuple(getattr(workspace, "screens", ()))
    if not screens:
        return False
    for screen in screens:
        areas = tuple(screen.areas)
        views = tuple(area for area in areas if area.type == "VIEW_3D")
        if len(views) < 2:
            continue
        central = max(views, key=lambda area: area.width * area.height)
        central_x, central_y = _area_center(central)
        left = tuple(
            area
            for area in views
            if area is not central
            and _area_center(area)[0] < central_x
            and bool(
                getattr(
                    getattr(area.spaces, "active", None),
                    "show_region_ui",
                    False,
                )
            )
        )
        right = tuple(
            area
            for area in areas
            if area.type == "PROPERTIES"
            and _area_center(area)[0] > central_x
        )
        bottom = tuple(
            area
            for area in areas
            if area.type in {"TEXT_EDITOR", "GRAPH_EDITOR"}
            and _area_center(area)[1] < central_y
        )
        if left and right and bottom:
            return True
    return False


def _new_data(workspaces_before, screens_before):
    return (
        tuple(
            workspace
            for workspace in bpy.data.workspaces
            if not any(workspace is item for item in workspaces_before)
        ),
        tuple(
            screen
            for screen in bpy.data.screens
            if not any(screen is item for item in screens_before)
        ),
    )


def _remove_owned_data(workspaces, screens):
    current_workspaces = tuple(bpy.data.workspaces)
    current_screens = tuple(bpy.data.screens)
    ids = (
        *(
            item
            for item in workspaces
            if any(item is current for current in current_workspaces)
        ),
        *(
            item
            for item in screens
            if any(item is current for current in current_screens)
        ),
    )
    if ids:
        bpy.data.batch_remove(ids=ids)


def _remove_new_data(workspaces_before, screens_before):
    _remove_owned_data(*_new_data(workspaces_before, screens_before))


def _live_windows():
    context = getattr(bpy, "context", None)
    manager = getattr(context, "window_manager", None)
    windows = getattr(manager, "windows", None)
    return None if windows is None else tuple(windows)


def _same_window(left, right):
    if left is right:
        return True
    try:
        left_pointer = left.as_pointer()
        right_pointer = right.as_pointer()
    except (AttributeError, ReferenceError):
        return False
    return bool(left_pointer) and left_pointer == right_pointer


def _retry_pending_rollback(window=None):
    global _pending_rollback

    if _pending_rollback is None:
        return True
    owner, original, attempted, workspaces, screens = _pending_rollback
    if not _same_window(window, owner):
        return False

    live_windows = _live_windows()
    if live_windows is not None and not any(
        _same_window(owner, candidate) for candidate in live_windows
    ):
        raise RuntimeError("owner window is no longer available")
    if not any(original is workspace for workspace in bpy.data.workspaces):
        raise RuntimeError("original workspace is no longer available")

    if owner.workspace is attempted:
        owner.workspace = original
        if owner.workspace is not original:
            raise RuntimeError("original workspace could not be restored")
    elif owner.workspace is not original:
        raise RuntimeError("owner window no longer has a rollback workspace")

    if live_windows is not None and any(
        not _same_window(candidate, owner)
        and any(
            candidate.workspace is workspace for workspace in workspaces
        )
        for candidate in live_windows
    ):
        raise RuntimeError("owned workspace is in use by another window")

    _remove_owned_data(workspaces, screens)
    _pending_rollback = None
    return True


def register():
    return None


def unregister():
    _retry_pending_rollback(getattr(bpy.context, "window", None))


def _append_workspace(path: Path):
    with bpy.data.libraries.load(str(path), link=False) as (
        data_from,
        data_to,
    ):
        if WORKSPACE_NAME not in data_from.workspaces:
            raise RuntimeError("workspace asset has no ChemBlender workspace")
        data_to.workspaces = [WORKSPACE_NAME]
    workspace = data_to.workspaces[0]
    if workspace is None:
        raise RuntimeError("workspace append returned no workspace")
    return workspace


class CHEMBLENDER_OT_open_workspace(bpy.types.Operator):
    bl_idname = "chemblender.open_workspace"
    bl_label = "Open ChemBlender Workspace"
    bl_options = {"REGISTER"}

    def execute(self, context):
        global _pending_rollback

        window = getattr(context, "window", None)
        if window is None:
            self.report({"ERROR"}, "ChemBlender workspace requires a window")
            return {"CANCELLED"}
        try:
            rollback_ready = _retry_pending_rollback(window)
        except Exception as error:
            self.report(
                {"ERROR"},
                f"ChemBlender workspace rollback retry failed: {error}",
            )
            return {"CANCELLED"}
        if not rollback_ready:
            self.report(
                {"ERROR"},
                "ChemBlender workspace rollback belongs to another window",
            )
            return {"CANCELLED"}

        original = window.workspace
        existing = bpy.data.workspaces.get(WORKSPACE_NAME)
        if existing is not None:
            if not workspace_is_compatible(existing):
                self.report(
                    {"ERROR"},
                    "Existing ChemBlender workspace is incompatible",
                )
                return {"CANCELLED"}
            try:
                window.workspace = existing
            except Exception as error:
                restored = False
                try:
                    window.workspace = original
                except Exception:
                    pass
                else:
                    restored = window.workspace is original
                detail = (
                    ""
                    if restored
                    else "; rollback failed: original workspace not restored"
                )
                self.report(
                    {"ERROR"},
                    f"ChemBlender workspace switch failed: {error}{detail}",
                )
                if not restored:
                    _pending_rollback = (
                        window,
                        original,
                        existing,
                        (),
                        (),
                    )
                return {"CANCELLED"}
            return {"FINISHED"}

        path = workspace_asset_path()
        if _is_link_like(path) or not path.is_file():
            self.report(
                {"ERROR"},
                "ChemBlender workspace asset is missing or unsafe",
            )
            return {"CANCELLED"}

        workspaces_before = tuple(bpy.data.workspaces)
        screens_before = tuple(bpy.data.screens)
        try:
            workspace = _append_workspace(path)
            if not workspace_is_compatible(workspace):
                raise RuntimeError("appended ChemBlender workspace is incompatible")
            window.workspace = workspace
        except Exception as error:
            owned_data = _new_data(workspaces_before, screens_before)
            attempted = owned_data[0][0] if owned_data[0] else None
            restored = False
            try:
                window.workspace = original
            except Exception:
                pass
            else:
                restored = window.workspace is original
            cleanup_error = None
            if restored:
                try:
                    _remove_owned_data(*owned_data)
                except Exception as failure:
                    cleanup_error = failure
                    _pending_rollback = (
                        window,
                        original,
                        attempted,
                        *owned_data,
                    )
            if not restored:
                cleanup_error = RuntimeError(
                    "original workspace could not be restored"
                )
                _pending_rollback = (
                    window,
                    original,
                    attempted,
                    *owned_data,
                )
            detail = (
                f"; rollback failed: {cleanup_error}"
                if cleanup_error is not None
                else ""
            )
            self.report(
                {"ERROR"},
                f"ChemBlender workspace open failed: {error}{detail}",
            )
            return {"CANCELLED"}
        return {"FINISHED"}


__all__ = (
    "CHEMBLENDER_OT_open_workspace",
    "WORKSPACE_NAME",
    "register",
    "unregister",
    "workspace_asset_path",
    "workspace_is_compatible",
)
