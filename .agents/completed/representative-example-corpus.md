# Representative Example Corpus

- Goal ID: `CB-REPRESENTATIVE-EXAMPLE-CORPUS`
- State: `completed` for corpus preparation, automated qualification and local integration
- Date: 2026-08-08, Asia/Shanghai
- Baseline: `03786d497cf9c8a2021a7633fcbf3c67ecc81115`
- Qualified branch: `codex/representative-example-corpus` at `07022082726ca8c9ef2b28ddcb02660a769c5217`
- Local `main` merge: `6c693ebe5d6ff8616eaf95f3e619b79ed7c18bf1`
- Manual release gate: `Not Run` / `Blocked`; this completion does not authorize a tag or Release

## Result

- Preserved all 17 small contract fixtures and added 15 representative inputs across CIF,
  CJSON, Cube, extXYZ, MOL V2000/V3000, MOL2, PDB, POSCAR/CONTCAR, PQR, QCSchema,
  SDF, SMILES and XYZ.
- Every one of the 32 inputs has an adjacent user-facing Markdown file with format fields,
  source identity, retrieval/derivation, redistribution license, specification links,
  ChemBlender support boundaries, UI workflow and a copyable Agent/Blender MCP prompt.
- Direct bytes are pinned to COD, OpenChemistry/Avogadro, Open Babel, RCSB PDB, APBS and
  MolSSI/QCSchema identities. Derived bytes use the CC0 rMD17 dataset, wwPDB CCD records,
  COD diamond data or the documented analytic H2 LCAO generator. No source with unclear
  redistribution terms was committed.
- No submodule, runtime dependency or Blender global-package install was added. The optional
  `spglib` worker boundary remains documented and absent from the base Extension install.
- The largest input is the `64x64x64` H2 Cube at 3,932,577 bytes. The five retained
  `.blend/.cbq` projects contain 119 files totaling 9,008,581 bytes; their largest file is
  2,097,280 bytes. No committed input/output reaches 50 MiB or exceeds 100 MiB.

## Product defects fixed

1. Official QCSchema `qc_schema_output/1` is accepted while the legacy alias remains compatible.
2. APBS PQR preserves 998 atoms, source zero radii, residue restarts and two inferred segments;
   Preview summarizes record-level element inference without discarding low-level diagnostics.
3. Open Babel MOL2 `un` bonds remain explicitly unsupported without fabricated topology, and
   topology-less records no longer crash conformer preview.
4. Project Browser exposes public `bpy.ops.chemblender.configure_trajectory_playback` for the
   32-frame representative extXYZ trajectory.
5. The workflow runner uses the optional-spglib boundary and public object View-kind contract.
6. The exact verified product-code growth is locked into artifact baselines while every
   unexplained-growth allowance remains zero.

## Verification

- `prepare_representative_inputs.py --stage verify`: Passed for every reproducible derived file.
- Final feature-branch suite on Blender bundled Python 3.13.9: 2,257 tests, 26 skipped,
  0 failed in 224.380 seconds.
- Post-merge representative/workflow suite on local `main`: 38 tests, 0 failed.
- Blender 5.1.2 native extension validate/build: Passed.
- Package: `ChemBlender/chemblender-2.4.0.zip`, 29,977,165 bytes, SHA-256
  `5555bbd3ebc6b8cc4066af78d5ffc929a70c72bae76b797a4cffded7a428e321`,
  189 members and 32,066,803 unpacked bytes. CRC, duplicate, safe-path, exact-wheel and
  zero-unexplained-growth budget checks Passed.
- Blender MCP live query: exact Blender 5.1.2 executable, Python 3.13.9, Windows AMD64,
  `user_default`, enabled key `bl_ext.user_default.chemblender`, RDKit 2026.03.3,
  Gemmi 0.7.5, public Operators and Scene RNA Passed.
- Public-Operator representative runner: molecular, trajectory, biological, crystal, grid and
  save/reopen preparation Passed with `deferred=[]`.
- Five tracked bundles were cold-opened in fresh Blender 5.1.2 processes. A final Grid reopen
  confirmed 11 Project Browser rows, four Volume datablocks, eight sidecar files and the public
  `grid_volume` / `signed_isosurface` View kinds.
- `git diff --check`: Passed before and after the local merge. No remote write, push, PR, tag,
  release or remote change was performed.
- After the green merge, the dedicated feature worktree and merged feature branch were removed.
  This deleted 253,131,041 bytes of regenerable download/build caches and left the unrelated
  `codex/user-workflow-experience-gate` worktree untouched. The task-owned Blender 5.1 process
  was stopped by verified PID/executable; the user's pre-existing Blender process was not touched.

## Human release gate

The versioned record
`docs/user/workflows/reviews/local-2.4.0-representative-corpus.md` keeps all 14 required
UI and Agent/MCP cases at `Not Run` / `Incomplete`; the final result is `Blocked` until the
user executes the documented experience review. Automated evidence cannot override a human
failure or an unexecuted case.

The existing `mesh.py:513` invalid-escape warning is non-blocking. RDKit intentionally emits
diagnostics for malformed test records. Neither requires user action for this corpus task.
