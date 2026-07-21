import bpy

from .utils import dependency_manager


def _addon_module_name():
    return __package__ or __name__.rpartition(".")[0]


def _addon_preferences(context):
    addon = context.preferences.addons.get(_addon_module_name())
    return addon.preferences if addon else None


class EXAMPLE_OT_install_missing_dependencies(bpy.types.Operator):
    bl_idname = "example.install_missing_dependencies"
    bl_label = "Install Missing Dependencies"
    bl_description = "Install missing Python packages into this extension's private dependency directory"

    def execute(self, context):
        prefs = _addon_preferences(context)
        use_tsinghua_mirror = getattr(prefs, "use_tsinghua_mirror", True)
        no_cache_dir = getattr(prefs, "pip_no_cache_dir", False)

        try:
            result = dependency_manager.install_missing_dependencies(
                use_tsinghua_mirror=use_tsinghua_mirror,
                no_cache_dir=no_cache_dir,
            )
        except Exception as exc:
            print("Failed to install Python dependencies:", exc)
            self.report({"ERROR"}, "Failed to install Python dependencies. See Blender console for details.")
            return {"CANCELLED"}

        if result is None:
            self.report({"INFO"}, "All Python dependencies are already installed.")
            return {"FINISHED"}

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            self.report({"ERROR"}, "Failed to install Python dependencies. See Blender console for details.")
            return {"CANCELLED"}

        self.report({"INFO"}, "Python dependencies installed into the extension private directory.")
        return {"FINISHED"}


class EXAMPLE_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = _addon_module_name()

    show_debug: bpy.props.BoolProperty(
        name="Show Debug",
        description="Enable debug behavior in this extension",
        default=False,
    )

    use_tsinghua_mirror: bpy.props.BoolProperty(
        name="Use Tsinghua PyPI Mirror",
        description="Use the Tsinghua PyPI mirror when installing missing dependencies",
        default=True,
    )

    pip_no_cache_dir: bpy.props.BoolProperty(
        name="Disable Pip Cache",
        description="Pass --no-cache-dir when installing missing dependencies",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "show_debug")

        box = layout.box()
        box.label(text="Python Dependencies")
        box.label(text=f"Private path: {dependency_manager.PRIVATE_DEPS_PATH}")
        box.label(text=f"Private path active: {dependency_manager.private_deps_path_enabled()}")
        box.prop(self, "use_tsinghua_mirror")
        box.prop(self, "pip_no_cache_dir")

        for status in dependency_manager.get_dependency_status():
            icon = "CHECKMARK" if status.installed else "ERROR"
            state = "Installed" if status.installed else "Missing"
            box.label(text=f"{status.spec.display_name}: {state}", icon=icon)
            box.label(text=f"Requirement: {status.spec.pip_requirement}")
            box.label(text=f"Origin: {status.origin or 'Not found'}")

        if not dependency_manager.all_dependencies_ready():
            box.operator(EXAMPLE_OT_install_missing_dependencies.bl_idname)
