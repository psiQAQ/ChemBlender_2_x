# Scientific editing and topology

ChemBlender separates presentation changes from changes to scientific data.
The imported source remains immutable.

## View changes are not scientific edits

**Object transforms**—location, rotation and scale—plus visibility, material
and display settings change only the Blender View. They do not rewrite a
Structure's coordinates, elements, cell, occupancy, topology or provenance.

Editing Structure-view mesh vertices, attributes or edges also does not
silently overwrite the project. Choose **Apply Scientific Edits** to preview
the atom, coordinate, element, bond and cell changes. Confirming creates a
**derived Structure**, derived topology where needed and provenance that points
back to the **source Structure**. Cancelling or a failed commit leaves the
source and project unchanged.

If you export the derived Structure, choose it explicitly. A calculation
result bound to the source Structure revision is not automatically valid for
the derived revision; recompute or import a result for the derived geometry.

## Understand topology sources

A Structure can have more than one TopologyRecord. The Project Browser and
topology controls display its source, quality, parameters and edge count. The
current topology controls do not display the revision as a separate field;
that revision remains recorded in the project entity, View binding and
provenance.

| Source token | Meaning |
| --- | --- |
| `explicit_file` | Connectivity came explicitly from the imported file |
| `rdkit_sanitized` | RDKit parsed/sanitized molecular connectivity |
| `distance_inferred` | ChemBlender proposed connectivity from coordinates and recorded inference parameters |
| `user_edited` | Connectivity belongs to an explicitly derived scientific edit |

An inferred proposal is not file evidence. Review its quality and parameters,
then Accept, Reject or Switch it for the selected Structure View. Switching a
topology changes only that View's binding; it does not replace another View or
rewrite the Structure.

Periodic topology retains cell-image shifts rather than pretending every edge
is an ordinary in-cell covalent bond. A View records both topology identity and
topology revision, so stale or cross-Structure bindings fail closed.

## Revision validity checklist

Before analysis or export, confirm:

1. the selected View points to the intended Structure revision;
2. the selected topology belongs to that Structure and has the intended source;
3. any Partial or Ambiguous badge has been reviewed;
4. result datasets reference the same scientific revision;
5. a scientific edit was committed as a derived entity rather than inferred
   from an Object transform.

See [Data quality](data-quality.md) for badge and diagnostic meanings.
