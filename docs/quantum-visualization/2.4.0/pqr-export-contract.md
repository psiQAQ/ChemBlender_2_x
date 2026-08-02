# 2.4.0 Native PQR Export Contract

PQR core export provides two pure-Python entry points:

```python
preview_pqr_export(project_entities) -> ExportReport
export_pqr(
    project_entities,
    *,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
) -> MolecularExport
```

The exporter accepts exactly one `Structure`, its one matching
`BiologicalHierarchy`, and complete `partial_charge` (`elementary_charge`) and
positive `radius` (`angstrom`) atomic properties. It reuses
`pqr_export_readiness()` and rejects a `FrameSet`, multiple structures, invalid
PQR labels, non-finite values, field overflow, and an atom name whose native
PQR element inference differs from the Structure atomic number.

Output is deterministic ASCII with LF endings only. Each `ATOM` or `HETATM` record has 11 whitespace fields when its chain ID is non-empty, otherwise 10 whitespace fields;
coordinates have three decimal places and charge/radius have four. It emits no
headers, models, topology, cell, or comments. Real omitted topology, cell,
identity, and molecular charge/multiplicity semantics appear as sorted loss
codes. A loss blocks text and destination publication unless `confirm_loss` is
the exact value `True`.

Destination writes use the shared short-sibling atomic writer. Cancellation is
checked before validation and between records; errors and cancellation leave no
temporary sibling or newly published destination.
