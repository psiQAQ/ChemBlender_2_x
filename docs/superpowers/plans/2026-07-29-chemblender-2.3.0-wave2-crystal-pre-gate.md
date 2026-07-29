# ChemBlender 2.3.0 Wave 2 Crystal Pre-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the unified native crystal model and periodic contracts
without starting a Wave 2 reader, dependency or Blender UI path.

**Architecture:** Reuse `Structure`, `PeriodicSiteData`, `TopologyRecord` and
`SymmetryResult` as the persisted authority. Add only pure model helpers and
validation required by future adapters; derived cell parameters never become
a second persisted authority.

**Tech Stack:** Python 3.13, NumPy, frozen dataclasses, standard-library
`unittest`, `.cbq` sidecar, canonical Reader API documents, Blender 5.1.2.

## Global Constraints

- Base the Wave 2 branch on Wave 1
  `1bbab2101c71b9954b198678f6a1026e9eb2a440`.
- Keep exactly one active Wave.
- Do not add `CrystalStructure`, `PeriodicTopology` or a crystal registry.
- Do not change project schema or sidecar versions.
- Do not implement/import CIF, Gemmi, POSCAR, crystal UI or symmetry expansion.
- Do not add or upgrade dependencies.
- Every runtime change follows observed RED, minimal GREEN and focused review.
- Push only after the completed checkpoint and final verification; do not
  create a PR, tag or Release.

---

### Task 1: Activate the Crystal Pre-Gate

**Files:**

- Move: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`
  to `.agents/completed/2.3.0-wave-1-native-molecular-and-grid.md`
- Move: `.agents/queued/2.3.0-wave-2-native-crystal.md`
  to `.agents/active/2.3.0-wave-2-native-crystal.md`
- Create: `.agents/decisions/0042-native-crystal-contract-reuse.md`
- Create:
  `docs/superpowers/specs/2026-07-29-chemblender-2.3.0-wave2-crystal-pre-gate-design.md`
- Create:
  `docs/superpowers/plans/2026-07-29-chemblender-2.3.0-wave2-crystal-pre-gate.md`
- Modify: `.agents/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**

- Consumes: completed Wave 1 gate at `1bbab210...`.
- Produces: one active Wave 2 cursor and one accepted model decision.

- [x] **Step 1: Update the active/queued documentation test**

Set `WAVE_230_ACTIVE_FILE` to `2.3.0-wave-2-native-crystal.md` and keep only
Wave 3 and Wave 4 in `WAVE_230_QUEUE_FILES`.

- [x] **Step 2: Run the documentation contract**

Run:

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
```

Expected: all documentation tests pass with exactly one active Wave.

- [x] **Step 3: Commit activation and plan**

```powershell
git add .agents docs/superpowers tests/test_quantum_visualization_docs.py
git commit -m "docs: activate Wave 2 crystal pre-gate"
```

**Commit boundary:** Documentation, decision and in-progress cursor only.

**Stop boundary:** No runtime model edit before this commit.

---

### Task 2: Add Pure Unit-Cell and Coordinate Contracts

**Files:**

- Modify: `ChemBlender/core/model/structure.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/__init__.py`
- Create: `tests/test_crystal_model_contract.py`
- Modify: `tests/test_core_public_api.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**

- Produces:
  `unit_cell_parameters(cell)`,
  `fractional_to_cartesian(fractional_coordinates, cell)`,
  `cartesian_to_fractional(coordinates, cell)` and
  `validate_periodic_coordinate_consistency(structure,
  absolute_tolerance=1e-9)`.

- [x] **Step 1: Write the failing cell/coordinate tests**

Cover known/unknown units, non-finite values, cell lengths/angles, skew-cell
round trips, bohr retention, invalid shapes, mismatched units and explicit
coordinate inconsistency.

- [x] **Step 2: Run RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_crystal_model_contract -v
```

Expected: import errors for the four missing public helpers and failures for
currently accepted non-length/non-finite Structure coordinates.

- [x] **Step 3: Implement the minimum pure-core helpers**

Use row-vector algebra only:

```python
cartesian = fractional @ cell
fractional = cartesian @ numpy.linalg.inv(cell)
```

Derive angles with clipped normalized dot products and `degrees(acos(...))`.
Do not store derived parameters.

- [x] **Step 4: Run GREEN**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_crystal_model_contract `
  tests.test_periodic_model `
  tests.test_periodic_topology_inference `
  tests.test_core_public_api -v
```

Expected: all tests pass and legacy inconsistent fractional data remains
loadable until an adapter explicitly calls the consistency validator.

**Commit boundary:** Public pure model contract, tests and architecture guide.

**Stop boundary:** No reader/catalog/registration/UI change.

---

### Task 3: Harden Structured Symmetry and Periodic Topology

**Files:**

- Modify: `ChemBlender/core/model/structure.py`
- Modify: `tests/test_crystal_model_contract.py`
- Reuse: `ChemBlender/core/model/molecular_topology.py`
- Reuse: `ChemBlender/core/model/project.py`

**Interfaces:**

- Consumes: existing `SymmetryResult` and `TopologyRecord`.
- Produces: integer unimodular rotation validation and explicit conformance
  evidence for periodic edge/project rollback behavior.

- [x] **Step 1: Write failing symmetry tests**

Reject float rotations, singular/non-unimodular rotations, malformed
translations and non-finite values; accept identity and inversion operations.

- [x] **Step 2: Run RED**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_crystal_model_contract.CrystalSymmetryContractTests -v
```

Expected: invalid float and non-unimodular rotations are currently accepted.

- [x] **Step 3: Add minimal `SymmetryResult` validation**

Require integer rotation dtype and determinant magnitude one for every
operation. Retain the existing dimensionless/finiteness checks.

- [x] **Step 4: Verify topology and rollback**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_crystal_model_contract `
  tests.test_topology_record `
  tests.test_periodic_topology_inference `
  tests.test_periodic_model -v
```

Expected: canonical shifts, duplicate rejection, atom-index validation and
failed-batch registry rollback all pass.

**Commit boundary:** Fold into the same crystal contract implementation
commit as Task 2.

**Stop boundary:** No symmetry derivation backend.

---

### Task 4: Prove Persistence, Canonical and Import Isolation

**Files:**

- Modify: `tests/test_crystal_model_contract.py`
- Modify: `tests/test_core_public_api.py`
- Modify: `tests/test_mol_reader.py`
- Modify: `tests/test_sdf_reader.py`

**Interfaces:**

- Consumes: current `.cbq` v0.2 and canonical PublicImportBatch schemas.
- Produces: compatibility evidence without a schema change.

- [x] **Step 1: Add persistence tests**

Save/open a periodic project and canonicalize/decode its public batch. Assert
structure UUID, lattice, fractional coordinates, PBC, topology shifts and
lazy array integrity.

- [x] **Step 2: Add optional-import audit**

In a fresh process import `ChemBlender.core`; fail if `bpy`, `gemmi`,
`spglib`, `ase` or `pymatgen` appears in `sys.modules`.

- [x] **Step 3: Stabilize Windows fixture bytes**

Normalize the shared in-memory MOL fixture to LF before constructing CRLF and
10k synthetic test inputs. This removes checkout `core.autocrlf` from
scientific hash expectations without altering production parsing.

- [x] **Step 4: Run focused persistence verification**

```powershell
& $pythonBin -m unittest `
  tests.test_crystal_model_contract `
  tests.test_sidecar_storage `
  tests.test_reader_canonical_document `
  tests.test_model_registry `
  tests.test_mol_reader `
  tests.test_sdf_reader -v
```

Expected: all pass; committed v0.1 sidecar/canonical fixtures remain
unchanged.

**Commit boundary:** Commit all model/test/docs changes as
`feat: freeze native crystal data contracts`.

**Stop boundary:** No file-format implementation.

---

### Task 5: Full Verification, Review and Checkpoint

**Files:**

- Modify: `.agents/active/2.3.0-wave-2-native-crystal.md`
- Modify:
  `docs/superpowers/plans/2026-07-29-chemblender-2.3.0-wave2-crystal-pre-gate.md`

**Interfaces:**

- Consumes: final implementation commit.
- Produces: completed gate evidence and next-task cursor.

- [x] **Step 1: Run repository verification**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
git diff --check
```

Expected: zero failed/error tests and only accepted optional skips.

- [x] **Step 2: Run Blender package verification**

Run native extension validate/build and ZIP path/CRC/wheel audit with Blender
5.1.2. No CIF/POSCAR/UI product smoke belongs to this gate.

- [x] **Step 3: Review the final diff twice**

First compare every requirement in ADR 0042 and this plan to tests and code.
Then review the diff for public API drift, duplicated authorities, accidental
optional imports and unrelated changes. Resolve every gate-related finding
and rerun Steps 1–2.

- [x] **Step 4: Commit the completed cursor**

```powershell
git add `
  .agents/active/2.3.0-wave-2-native-crystal.md `
  docs/superpowers/plans/2026-07-29-chemblender-2.3.0-wave2-crystal-pre-gate.md
git commit -m "chore: checkpoint crystal pre-gate"
```

- [x] **Step 5: Push the verified Wave 2 branch**

Require clean worktree, fast-forward remote ancestry and a successful
`git push --dry-run` before:

```powershell
git push -u origin feat/2.3.0-wave2-native-crystal
```

Verify `git ls-remote` matches local HEAD. Do not push tags or create a PR.

**Commit boundary:** Checkpoint only.

**Stop boundary:** Stop after push. The next task is Wave 2 Task 1, beginning
with Gemmi dependency approval; CIF/Gemmi/POSCAR/UI remain unstarted.

## Completion Evidence

- Planning commit:
  `7314e03239e9f6c67fa6bc9ef54e3d13a054f82a`.
- Implementation commit:
  `f5ed327413bec04deb5f2cf92b43e45035ecf630`.
- RED:
  the initial 13-test crystal contract run reported six failures and six
  errors for missing helpers and accepted invalid data; the fresh-checkout
  baseline reported `1411 Ran / 28 Skipped / 1 Failed / 1 Error` from
  checkout-dependent MOL fixture line endings.
- GREEN:
  focused `166/166 Passed`; full `1424 Passed / 28 Skipped / 0 Failed`;
  compileall, docs `15/15`, optional-import audit and `git diff --check`
  Passed.
- Persistence:
  `.cbq` and canonical Reader API round-trips, lazy coordinate/cell ownership,
  project rollback, periodic topology shifts and legacy sidecars Passed.
- Blender 5.1.2:
  native preflight, extension validate/build and 154-entry ZIP
  CRC/path/manifest/wheel audit Passed. Package SHA-256:
  `63f4412d342ea8eef3eb36e94dd33699a9c1511987507c8df87e8ee22f5e937c`.
- Reviews:
  specification compliance and code-quality passes completed; lazy sidecar
  ownership and unsafe dtype compatibility findings were fixed before final
  verification.
- Remote CI: `Not Run`.
