# CIF controlled export policy

ChemBlender exposes two explicit CIF export modes. Both write through the
shared same-directory atomic text writer and require a periodic `Structure`.

## Preserve

`Preserve` requires the exact `CIFEnvelope` referenced by
`PeriodicSiteData.cif_envelope_id` and its block name/key/index. The patch plan
classifies each supported field as `preserve`, `replace`, `add` or `omit`.

Supported patches are:

- unit-cell lengths and angles;
- atom-site label, element, fractional coordinates and existing Cartesian
  coordinates;
- occupancy;
- isotropic and anisotropic displacement values;
- atom-site ADP type, disorder group and disorder assembly;
- source-declared symmetry name, IT number, Hall symbol and operations.

Other blocks, unknown pairs and unknown loops remain in the Gemmi document.
When replacing an anisotropic or symmetry loop would discard unknown columns,
export fails instead of silently losing them. Replaced numeric values do not
claim to retain source uncertainty tokens.

## Normalized

`Normalized` writes a new minimal block from the selected periodic
`Structure`. It records the cell, sites, fractional coordinates and occupancy,
plus displacement, disorder or declared-symmetry fields only when those values
exist in the model. It does not copy or invent source uncertainty, source-only
metadata, disorder or symmetry.

## Scientific boundary

The exporter reads `Structure`, `PeriodicSiteData` and optional `CIFEnvelope`;
it never persists Gemmi objects. `SymmetryResult` is derived data and is not
written as source-declared symmetry. Callers must explicitly choose a derived
standard `Structure` when that is the intended export target.
