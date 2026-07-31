# Legacy scene migration

The **Legacy Migration** panel converts detected ChemBlender 2.1/2.2 mesh
objects into the 2.3 Project model. It is an explicit migration, not a file-open
side effect. Current `structure_view_v1` objects and already owned migration
backup objects are not treated as legacy input.

## Work on a copy

1. Close other Blender processes using the project.
2. Copy the source `.blend` and, if present, its complete `.cbq/` directory to
   a new working location. Keep the `.blend` and `.cbq` together.
3. Open and save the working-copy `.blend` as a regular file. The wizard needs
   a saved path and publishes a same-basename `.cbq` beside it.
4. Keep the external pre-migration pair until the migrated pair has saved and
   reopened successfully.

The migration refuses to replace an unrelated existing `.cbq`. Do not delete
or rename an unknown sidecar merely to make the wizard continue.

## Detect and preview

Loading a scene only records a non-mutating detection result. In the panel:

1. Choose **Preview Legacy Migration**.
2. Review the destination, every legacy object, the proposed Structure,
   Topology/PeriodicSite and Provenance entities, recovered display settings,
   and all unsupported diagnostics.
3. Treat an item marked **backup only** as an original object that will be
   preserved but will not create a Project entity or migrated View. Cell-only
   helper geometry is one such case.
4. Run **Migrate to Project** only after the preview is acceptable and provide
   the explicit confirmation that the original objects will move to backup.

Execution re-extracts and replans the scene; an earlier preview is not a permit
to commit changed objects.

## What a successful migration does

- Molecule scaffolds become `Structure` plus explicit `TopologyRecord` data.
- Crystal scaffolds use the retained CIF site/cell data to create `Structure`
  plus `PeriodicSiteData`. Evaluated modifier geometry is not promoted to
  scientific coordinates.
- Recovered display values are applied only when their shape and values pass
  validation. Unsupported values stay in diagnostics rather than becoming
  scientific facts.
- The candidate Project is published and verified before every Blender scene
  is relinked to the new sidecar.
- Original detected objects move to the hidden
  `ChemBlender Legacy Backup` collection. The collection and objects carry the
  same project and transaction markers; each original is linked only to that
  collection.

Save the `.blend`, reopen it, confirm the Project link is Connected, inspect
the migrated Views, and leave the backup collection intact while validating
the result.

## Provenance and diagnostics

Source provenance is trusted only when extraction sees a saved regular
non-linked `.blend`, records its source path and source hash, and planning
rechecks the same SHA-256. If that proof is absent, invalid or changes, the
provenance source fields remain empty and a diagnostic is retained; a filename
is never fabricated as proof.

Missing bond orders or display arrays, unknown custom properties, ignored
modifier output, non-uniform transforms and other unverified recovery facts
are reported with stable `legacy_unverified` diagnostics and Ambiguous quality.
Read the scientific consequence before using or exporting the migrated data.

The shipped acceptance evidence uses three hash-locked fixtures:

| Fixture | SHA-256 |
| --- | --- |
| `chemblender-2.1-molecule.blend` | `36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4` |
| `chemblender-2.2-crystal.blend` | `f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a` |
| `chemblender-2.2-edited-scaffold.blend` | `a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740` |

Their provenance and inventory are recorded in the
[fixture README](../../tests/fixtures/legacy-blend/README.md); the installed
Extension save/reopen run is recorded in the
[Wave 4 usability results](../quantum-visualization/2.3.0/usability-results-rc1.md).
These fixtures prove the named cases only. Preview diagnostics remain the
authority for a different scene.

## Failure rollback and completed-migration recovery

Before a migration reports success, its transaction rollback attempts to
remove candidate Views/materials, restore scene links and session state,
restore the prior sidecar, and put original objects back in their former
collections. Cleanup failures are attached to the original error. Preserve the
working files and diagnostic text if any rollback step reports a residual path.

After a successful migration there is no supported automatic undo or
"unmigrate" command. Blender Undo is not the recovery contract, and the hidden
backup collection alone cannot restore the former Project/sidecar state. To
return to the old state, close Blender and restore the external pre-migration
`.blend` and `.cbq` backup pair together.

If `ChemBlender Legacy Backup` already exists, stop: the file may already have
been migrated or contain retained evidence. Do not merge, rename or delete the
collection until the Project link, transaction markers and external backup are
understood.

For sidecar link recovery, continue with
[Project and sidecar](project-sidecar.md). For the 2.2-to-2.3 package and schema
upgrade, see [Upgrade to ChemBlender 2.3.0](../migration/2.3.0.md).
