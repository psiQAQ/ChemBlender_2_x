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

## Python and dependency qualification

- Blender bundled Python: `3.13.9`.
- Full discovery with the existing extension dependency site on `PYTHONPATH`:
  `2200 Passed / 26 Skipped / 0 Failed`.
- `compileall -q ChemBlender worker tests`: `Passed`.
- Fresh-process core/Reader API import isolation: `4 Passed`.
- Local optional-integration modules: `30 Passed / 7 Skipped / 0 Failed`.
  The skips are the real cclib, IOData and GBasis fixture cases because those
  optional environments are not installed locally; they remain mandatory
  zero-skip jobs in the exact-head remote gate.

The first unconfigured discovery run produced `1 Failed / 23 Errors / 36
Skipped`: every product failure was caused by `ModuleNotFoundError: gemmi`.
The repository workflow supplies the extension dependency site through
`PYTHONPATH`; using the already installed, manifest-pinned `gemmi 0.7.5` and
`rdkit 2026.03.3` from that same site made the full run pass. No package was
installed or changed during this diagnosis.

The required remote integration environments remain pinned to:

- cclib: `cclib 1.8.1`, fixture checkout
  `07260dd0394cb1a2381d4d897746d727a12ad6ce`;
- IOData: `qc-iodata 1.0.1`, fixture checkout
  `adab5813713ba64641565eb2a8c11803a4e9bba6`;
- GBasis: `qc-gbasis 0.1.0` with `qc-iodata 1.0.1`, fixture checkouts
  `6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f` and
  `adab5813713ba64641565eb2a8c11803a4e9bba6`.

The workflow additionally binds every required scientific fixture to its
literal SHA-256 argument in `.github/workflows/optional-qc-core.yml`; those
hash checks are executed before each exact-head integration module.

## Committed-tree extension artifact

The clean Task 2 commit `6ac2e5283275ce309f09456f4400de33c0825546`
was validated and built with Blender `5.1.2` on Windows. The exact output was
`chemblender-2.3.0.zip`; no version or release metadata changed.

| Artifact property | Observed value |
| --- | --- |
| Package SHA-256 | `8e7f3c8a7af0feb100cf8ec37cfc9200f98cd7e2cb5149f15e21be74e578b32b` |
| Package bytes | `29,976,421` |
| ZIP members | `189` |
| Member compressed bytes | `29,953,927` |
| Member unpacked bytes | `32,063,479` |
| Code compressed bytes | `587,908` |
| Resource compressed bytes | `2,477,267` |
| Wheel compressed bytes | `26,888,752` |
| Bad CRC member | `none` |
| Unsafe ZIP paths | `0` |
| Unexplained budget growth | `0 bytes` |

`dependency_inventory.py`, `artifact_size_report.py` and
`verify_release_artifact.py --metadata-mode package-ci` all passed with the
exact arguments used by `extension-package.yml`. The package contains only the
two required, hash-matched Gemmi and RDKit wheels.

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
| Full Python qualification | `2200 Passed / 26 Skipped / 0 Failed` |
| Python compile/import/docs checks | `Passed` |
| Local optional integrations | `30 Passed / 7 Skipped / 0 Failed` |
| Committed-tree artifact audit | `Passed` |
| Blender product qualification | Not Run — Task 4 |
| Remote exact-head CI | Not Run — Task 5 |

## Stop boundary

Reader API stable promotion, manifest version changes, CHANGELOG release work,
tagging and Release publication remain unstarted.
