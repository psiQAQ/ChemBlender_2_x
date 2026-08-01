# Project and sidecar

A saved ChemBlender project is a pair:

- `example.blend` contains Blender scenes, objects, View bindings and a project
  link.
- `example.cbq/` contains the authoritative scientific project, manifest and
  arrays. Its `cache/` content is derived and rebuildable.

The loaded `.blend` owns one shared ProjectSession across all of its scenes.
When the two paths share a directory, ChemBlender stores a relative sidecar
locator. You can move the pair together without rewriting scientific
identities, provided their relative layout remains the same.

## Save and back up

Use Blender's normal Save or Save As. ChemBlender publishes the sidecar before
the `.blend` save completes and updates every scene link atomically. A clean
save with valid links is a no-op for scientific arrays and manifest content.

Before upgrading, migrating a legacy scene or making important scientific
edits:

1. Close any other Blender process using the project.
2. Copy both `example.blend` and the complete `example.cbq/` directory to a
   backup location.
3. Verify that the copied sidecar contains its manifest and arrays.

Internal temporary backup paths protect an atomic publication failure; they
are removed after success and are not a substitute for your own backup.

## Understand link states

| State | Meaning | Safe first action |
| --- | --- | --- |
| Connected | Project UUID, schema, manifest hash and arrays verified | Continue |
| Missing | The linked sidecar path does not exist | Locate the original pair, then Relink |
| Mismatch | Project UUID or manifest hash differs from the `.blend` link | Stop and identify the correct backup; do not accept by filename alone |
| Incompatible | The sidecar schema cannot be opened by this version | Keep the files unchanged and use a compatible ChemBlender version |
| Invalid | Link metadata, manifest or array integrity is invalid | Preserve evidence; open Diagnostics before recovery |

**Relink** validates the complete candidate once and updates every scene only
after verification. **Verify** rechecks the current locator. **Detach** keeps
the current Blender objects but removes their project link; detached objects
are not a replacement for authoritative scientific data.

## Move or restore a project

Move `example.blend` and `example.cbq/` together. If the relative layout
changed, open the `.blend`, choose Relink, select the actual `.cbq` directory
and confirm that the expected project identity appears. Never create an empty
directory with the old name or copy only selected array files to satisfy a
Missing state.

For rollback, close Blender and restore both members of the same backup pair.
Mixing a `.blend` from one backup with a `.cbq` from another correctly produces
a Mismatch instead of silently adopting different science.

## Clear only derived cache

OpenVDB render files and derivation outputs under `cache/render/` and
`cache/derivation/` are rebuildable. **Clear Derived Cache** is a maintenance
operation backed by `clear_derived_cache()`; the current user panels do not
expose a generic cache-delete button. Use it only from trusted maintenance
tooling or when support directs you to it. It is not a command to delete
arbitrary sidecar content. Close other users of the project, back up the pair,
and remove only those verified cache namespaces. Never delete the sidecar root,
manifest, authoritative arrays or an unknown linked directory.

On reopen, ChemBlender rebuilds a missing owned Volume/Surface cache from the
verified Grid3D. Foreign Blender Volume paths are left unchanged.
