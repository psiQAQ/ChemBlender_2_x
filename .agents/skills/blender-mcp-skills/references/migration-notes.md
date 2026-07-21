# Migration Notes (Legacy Add-on -> Extension Add-on)

## Context

From Blender 4.2+, extension packaging is the recommended distribution path.

## Migration checklist

1. Add `blender_manifest.toml`.
2. Keep source in a module folder with `__init__.py`.
3. Move metadata from legacy add-on style into manifest fields.
4. Use extension build command for packaging.
5. Re-test registration and reload flow.

## Compatibility strategy

This skill is extension-only and targets **4.2+**.

Do not add dual-support or legacy branches in the default template.

## Operational note

During active development, direct local file edits + disable/enable cycle are usually faster than pushing full source through runtime code strings.
