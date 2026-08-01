# Project Browser

Project Browser displays the scientific project, not just Blender objects.
An entity can remain in the project even when it has no Blender View.

## Choose a projection

- **By Source** groups each source, its immutable revisions, the entities
  created by those revisions and their Views.
- **By Data** groups entities by scientific kind, such as Structure,
  Topology, Grid3D, property, record or View.

Search and the quality filter apply to the current projection. Large projects
are paged; **Entries per Page**, **Prev**, **Next** and **Jump** change only
the RNA projection, not the scientific project. Selecting a row sets the
active project entity for the controls below the list.

## Read quality and diagnostics

Rows can show **Complete**, **Partial**, **Ambiguous**, **Incomplete** or
**Invalid** quality. These badges describe the reader/import contract, not a
guarantee that a scientific calculation is correct. Open diagnostics for the
original value, normalization or recovery, scientific consequence and
suggested action. See [Data quality](data-quality.md).

## Handle a new source revision

Importing a new revision never silently switches an existing View. Project
Browser presents the exact current and replacement revision IDs and offers:

- **Update Selected Views** — create replacements only for the selected
  logical Views and hide those current Views.
- **Comparison View** — create the replacement beside the current View.
- **Keep Current** — keep every current View unchanged.

If creation fails, ChemBlender rolls back the new Views and restores the old
visibility. Results attached to the old Structure revision remain attached to
that revision; creating a new View does not make them valid for new geometry.

## Recover a project link

When the `.blend` cannot verify its sidecar, Project Browser shows only the
actions allowed for the live state: **Relink**, **Verify**, **Inspect
Existing**, **Diagnostics** or **Detach**. Inspect Existing does not adopt a
candidate sidecar and does not make Blender globally read-only. Detach removes
link metadata but preserves existing Blender objects.

Read [Project and sidecar](project-sidecar.md) before selecting a replacement
`.cbq`.
