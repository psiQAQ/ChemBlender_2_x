# Representative Example Corpus

- Goal ID: `CB-REPRESENTATIVE-EXAMPLE-CORPUS`
- State: `active`
- Branch: `codex/representative-example-corpus`
- Worktree: `D:\workspace\ChemBlender_2_x\.worktrees\representative-example-corpus`
- Baseline: `03786d497cf9c8a2021a7633fcbf3c67ecc81115`
- Design: `docs/superpowers/specs/2026-08-08-chemblender-representative-example-corpus-design.md`
- Plan: `docs/superpowers/plans/2026-08-08-chemblender-representative-example-corpus.md`
- Current task: Task 2 authoritative inputs are green; build deterministic Task 3 derived formats.

## Goal

Add provenance- and specification-backed representative examples beside the existing
contract fixtures, document every input file, verify format semantics and Blender 5.1
public-Operator workflows, save bounded reopenable demonstrations, and integrate local
commits into local `main` without remote writes.

## Constraints

- Preserve the existing small contract fixtures and their byte/hash behavior.
- Prefer official specifications and authoritative databases with explicit reuse terms.
- Do not commit a source whose redistribution license is unclear.
- Do not add runtime dependencies or a submodule unless the approved design proves it necessary.
- Each committed file should remain below 50 MiB and may never exceed 100 MiB.
- Use Blender 5.1 and public `bpy.ops.chemblender.*` / public RNA for product validation.
- Local commits only; do not push, tag, publish, release, create a PR or alter remotes.

## Evidence So Far

- Baseline branch/worktree clean at `03786d4`.
- 58 user-workflow and documentation tests Passed on Blender bundled Python 3.13.9.
- Source discovery covers PubChem, rMD17, RCSB PDB, APBS, COD, VASP, Avogadro,
  MolSSI/QCElemental, Daylight, libAtoms and h5cube documentation.
- NCBI places no restriction itself on molecular-data reuse but cannot transfer submitter
  rights, so final small-molecule source selection moved from PubChem to the wwPDB CCD
  (`AIN`, `CFF`, `TA1`) under the PDB archive CC0 policy.
- Direct-source size checks: `1D3Z.pdb` 1,015,821 bytes, Open Babel `5sun_protein.mol2`
  779,286 bytes, COD `4503272.cif` 14,996 bytes, APBS PQR about 70 KiB, and the selected
  Avogadro/QCSchema records below 4 KiB. Size is treated as encoding size, not resolution.
- Local PySCF cannot import because SciPy is absent. No dependency install is authorized;
  the representative Cube will be a documented analytic H2 1s LCAO density on a 64-cubed grid.
- Manifest schema 2 contract is implemented for all 17 existing inputs without changing any
  data bytes; 60 focused workflow/documentation tests Passed.
- Six direct representative files are pinned by URL, commit/record identity, license, byte size
  and SHA-256. All committed direct files are below 1 MiB except the 1,015,821-byte PDB file.
- The rMD17 container is range-read without being stored; only the 153,601,803-byte aspirin NPZ
  exists in ignored cache and will produce a small 32-frame extXYZ subset.
- Real parser checks found and fixed two source-backed bugs: official `qc_schema_output/1` is now
  accepted while the legacy alias remains compatible; APBS PQR zero radii and no-chain residue
  restarts now preserve all 998 atoms as two inferred segments.
- Direct-source acquisition and reader regressions Passed: 29 focused tests plus manifest sort,
  byte and runtime-dependency checks.
