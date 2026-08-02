# ChemBlender 2.4.0 Final Qualification

## Scope

- Baseline: `aa6a92978f397011dafb3d79adac29d608262db4`.
- Branch: `codex/2.4.0-final-qualification`.
- This gate audits committed behavior only. It does not add a capability,
  dependency, workflow, schema, version, CHANGELOG entry, tag or Release.
- Reader API stable promotion remains deferred.

## Frozen public and scientific boundaries

| Boundary | Frozen value | Verification |
| --- | --- | --- |
| Reader API | Reader API: `1.0-rc1` | public schema snapshot, manifest and conformance contracts |
| Sidecar manifest | Sidecar manifest: `1.0` | v1 storage and migration contracts |
| Project schema | Project schema: `1.0` | current and legacy sidecar round trips |
| Canonical reader document | Canonical document: `0.1` | strict schema, type registry, hashes and safe paths |
| Core public facade | `ChemBlender.core` | exact `__all__`, registered models/enums and attribute resolution |
| Reader public facade | `ChemBlender.reader_api` | exact RC snapshot and installed-namespace import contract |

The focused public, sidecar and canonical suites found no third-party object in
the project or persisted entity boundaries and required no source change.

## Export maturity and execution modes

The generated capability matrix contains 14 export-capable reader descriptors.
The following rows are derived from the committed reader catalog.

| Reader | Maturity | Execution mode | Loss policy |
| --- | --- | --- | --- |
| CIF | F5 | project_browser | preview_confirmation |
| CJSON | F5 | core | controlled_envelope |
| Cube | F5 | project_browser | preview_confirmation |
| extXYZ | F5 | project_browser | preview_confirmation |
| MOL | F5 | project_browser | preview_confirmation |
| MOL V2000 | F5 | project_browser | preview_confirmation |
| MOL2 | F5 | project_browser | preview_confirmation |
| PDB | F5 | project_browser | preview_confirmation |
| POSCAR | F5 | project_browser | preview_confirmation |
| PQR | F5 | project_browser | preview_confirmation |
| QCSchema | F5 | core | source_envelope |
| SDF | F5 | project_browser | preview_confirmation |
| SMILES | F5 | project_browser | preview_confirmation |
| XYZ | F4 | project_browser | single_structure_coordinates_only |

## Optional dependency isolation

Fresh subprocess contracts for `ChemBlender.core` and
`ChemBlender.reader_api` confirmed that these optional roots are not imported
by the public facades: `rdkit`, `gemmi`, `spglib`, `cclib`, `iodata`, `gbasis`,
`ase` and `pymatgen`. Blender's `bpy` is also absent from the core import.

The ignored local wheel inputs were verified against `dependencies.toml`:

- Gemmi SHA-256:
  `ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d`;
- RDKit SHA-256:
  `f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48`.

No wheel was installed into Blender or the system environment during this
boundary audit.

## Generated documents

- `generate_format_docs.py --check`: `Passed`.
- Generated document drift: `0 files`.
- Capability matrix Reader API token: `1.0-rc1`.

## Verification ledger

| Gate | Result |
| --- | --- |
| Task 0 routing RED | `2 Failed` before cursor activation |
| Task 0 documentation routing | `31 Passed` |
| Task 1 evidence RED | missing `final-qualification.md` |
| Task 1 frozen-boundary focused suite | `162 Passed` |
| Full Python qualification | Not Run — Task 2 |
| Committed-tree artifact audit | Not Run — Task 3 |
| Blender product qualification | Not Run — Task 4 |
| Remote exact-head CI | Not Run — Task 5 |

## Stop boundary

Reader API stable promotion, manifest version changes, CHANGELOG release work,
tagging and Release publication remain unstarted.
