# MOL2 export P1 readiness boundary

## Scope

P1 only defines `mol2_export_readiness(project_entities)`. It is a pure
Python, project-wide representability check; it neither writes a MOL2 file nor
adds UI, reader behavior, a capability-matrix entry, or an `export_mol2()`
API.

The result is the frozen/slotted `Mol2ExportReadiness` value:

| field | contract |
| --- | --- |
| `status` | `Mol2ExportStatus` with exactly `Complete`, `Partial`, or `Unsupported` |
| `missing_fields` | ordinally sorted, duplicate-free field tokens |

The function accepts the existing entity groups on `ImportBatch` or
`QCProject`: `Structure`/`AtomicIdentityData`, `TopologyRecord`,
`MolecularRecord`, `AtomicProperty`, and `ChemicalAnnotation`. It introduces
no scientific model and does not inspect Blender data.

## Status and missing-field contract

`Unsupported` means a safe MOL2 atom/bond graph cannot be formed. Its tokens
are `structure`, `structure.atomic_identity.atom_names`, `topology`,
`topology.bond_type_mapping`, and `dataset.atom_type`.

`Partial` means a structural MOL2 can be emitted only after accepting loss or
confirming a value. The additional tokens are:

| token | required entity value |
| --- | --- |
| `annotation.molecule_type` | `tripos:molecule_type` string annotation |
| `annotation.charge_type` | `tripos:charge_type` string annotation |
| `dataset.partial_charge` | complete atom `partial_charge`, unless charge type is exactly `NO_CHARGES` |
| `dataset.substructure_id` | complete atom `substructure_id` |
| `dataset.substructure_name` | complete categorical atom `substructure_name` |
| `molecular_record.raw_tripos` | a linked raw block beginning `@<TRIPOS>MOLECULE` |

`Complete` has no missing fields: every structure has the supported atom and
bond representation plus all entries in the table. Missing-field collection is
independent: an absent topology does not hide missing optional values.

## Future writer mapping

- Atom names come from complete `AtomicIdentityData.atom_names`; Tripos atom
  types come from complete categorical `AtomicProperty(semantic_role="atom_type")`.
- `ChemicalAnnotation(namespace="tripos", key="charge_type")` supplies the
  molecule charge-type line. A non-`NO_CHARGES` value requires the complete
  numeric `partial_charge` property.
- `substructure_id` and `substructure_name` map atom membership and the
  `SUBSTRUCTURE` output. Their absence is a confirmation/loss boundary, not a
  reason to invent a scientific topology.
- `TopologyRecord.bond_orders`, `aromatic_flags`, and `stereo_labels` map
  `1`/`2`/`3`, aromatic `ar`, and `amide`. A topology with no aromatic flags
  may only use orders `1`, `2`, or `3`; labels other than empty or `amide` are
  `topology.bond_type_mapping` and therefore `Unsupported`.

Generic `Structure`/`TopologyRecord` cannot reconstruct source atom or bond
IDs, original Tripos token spelling/order, molecule comments/status bits,
full `SUBSTRUCTURE` record fields, `SET`/unknown sections, or other raw record
semantics. `MolecularRecord.raw_block` is therefore required for `Complete`,
but its absence is `Partial`: a future writer must request confirmation rather
than claim a lossless Tripos round trip.
