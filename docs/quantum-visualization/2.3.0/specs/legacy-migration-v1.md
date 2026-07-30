# Legacy Migration v1

`ChemBlender.legacy.migration` consumes only the frozen result of
`extract_legacy_objects()`. Importing or planning does not load `bpy`, create
views, or alter legacy objects.

`plan_legacy_migration(report, base_project)` copies `base_project`, appends
new scientific entities, and returns a frozen `LegacyMigrationPlan` that owns
the staged `QCProject`, `ViewPlan` tuple, report, exact base-project reference,
and base/candidate registry inventories. Each inventory includes entity identity
and a deterministic persisted-content fingerprint, so an in-place array change
is rejected before publication. Molecular snapshots produce `Structure` and explicit
`TopologyRecord`; crystal snapshots use `cif_current`, falling back to
`cif_original`, for periodic sites, cell, occupancy, Uij and declared
symmetry. Expanded crystal mesh atoms and cell-only auxiliary objects are
display data and do not create scientific sites or duplicate structures.

`ViewSettings` and `ViewPlan` retain only shape-valid per-resulting-Structure
legacy radii, colours and atom scales; bond scale/dashed values are reordered
to the canonical topology order. Material parameters and Geometry Nodes
modifier inputs are retained only after finite scalar/vector, non-empty name,
and primitive-container validation. They contain no Blender objects.
Extraction diagnostics and unavailable or unverified legacy data are reported
as immutable `legacy_unverified` diagnostics with
`QualityStatus.AMBIGUOUS`; malformed atomic shape or edge indices fail closed.

Each migrated object receives a `ProvenanceRecord` with operation
`legacy_blend_migration`. Only a source marked `source_verified` by actual
extraction from a saved, regular, non-link `.blend`, with its exact
extraction-time SHA-256, may contribute provenance. Planning rechecks the
regular path and requires the current file hash to match; otherwise source and
source hash are empty, and
immutable provenance parameters retain the legacy object name and collection
parents.

`commit_legacy_migration(session, plan)` publishes the plan candidate through
`solidify_session(..., transfer_verified_project=True)`. The live session
changes only after that path returns its verified reopened project; it first
requires the exact planned base-project object, unchanged base inventory, and
unchanged candidate inventory (including registry object identity). A failed
publication leaves the plan valid for retry.
Blender view creation, legacy-object backup and rollback are UI responsibilities
outside this module.
