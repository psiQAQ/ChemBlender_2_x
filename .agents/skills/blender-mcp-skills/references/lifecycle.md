# Add-on Lifecycle (Enable, Update, Disable)

## Enable phase

1. Blender imports add-on package/module.
2. `register()` runs.
3. Classes are registered with `bpy.utils.register_class`.
4. Scene properties are attached.
5. UI panels/operators become available.

## Update phase

Recommended update cycle:

1. Modify files on disk.
2. Run `bpy.ops.preferences.addon_disable(module="<module_name>")`.
3. Run `bpy.ops.preferences.addon_enable(module="<module_name>")`.
4. Verify panel/operator/property state.

### Why cache cleanup matters

Blender typically clears top-level module state, but submodules can remain cached in `sys.modules`.
Clear submodule entries before import to force fresh code loading.

## Disable phase

1. `unregister()` runs in reverse order.
2. Scene properties are removed.
3. Classes are unregistered.
4. Add-on is removed from `bpy.context.preferences.addons`.

## Validation checklist

- Panel class is gone from `bpy.types`.
- Scene property is removed.
- Add-on module key is absent in preferences add-ons list.
