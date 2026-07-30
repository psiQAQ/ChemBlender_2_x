# Legacy Migration v1

`ChemBlender.legacy.migration` consumes only the frozen result of
`extract_legacy_objects()`. Importing or planning does not load `bpy`, create
views, or alter legacy objects.

`plan_legacy_migration(report, base_project)` copies `base_project`, appends
new scientific entities, and returns `(candidate_project, view_plans,
migration_report)`. Molecular snapshots produce `Structure` and explicit
`TopologyRecord`; crystal snapshots use `cif_current`, falling back to
`cif_original`, for periodic sites, cell, occupancy, Uij and declared
symmetry. Expanded crystal mesh atoms and cell-only auxiliary objects are
display data and do not create scientific sites or duplicate structures.

`ViewSettings` and `ViewPlan` retain legacy radii, colours, atom scales and
bond display values as immutable presentation data. They contain no Blender
objects. Extraction diagnostics and unavailable or unverified legacy data are
reported as immutable `legacy_unverified` diagnostics with
`QualityStatus.AMBIGUOUS`; malformed atomic shape or edge indices fail closed.

Each migrated object receives a `ProvenanceRecord` with operation
`legacy_blend_migration`. A real regular source `.blend` may contribute its
SHA-256. Otherwise source and source hash are empty, and immutable provenance
parameters retain the legacy object name and collection parents.

`commit_legacy_migration(session, candidate_project)` publishes the candidate
through `solidify_session(..., transfer_verified_project=True)`. The live
session changes only after that path returns its verified reopened project.
Blender view creation, legacy-object backup and rollback are UI responsibilities
outside this module.
