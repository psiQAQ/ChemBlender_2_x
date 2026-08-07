# Representative Example Corpus

- Goal ID: `CB-REPRESENTATIVE-EXAMPLE-CORPUS`
- State: `active`
- Branch: `codex/representative-example-corpus`
- Worktree: `D:\workspace\ChemBlender_2_x\.worktrees\representative-example-corpus`
- Baseline: `03786d497cf9c8a2021a7633fcbf3c67ecc81115`
- Design: `docs/superpowers/specs/2026-08-08-chemblender-representative-example-corpus-design.md`
- Current task: finalize the written design, then create the implementation plan.

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
