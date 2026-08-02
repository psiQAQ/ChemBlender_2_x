# ChemBlender 2.4.0 Deterministic Native PQR Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and `superpowers:executing-plans`
> task by task.

**Goal:** Add a dependency-free deterministic native PQR core exporter with
explicit loss confirmation, atomic destination publication, cancellation
cleanup and Semantic native re-import verification.

**Architecture:** Reuse the frozen `pqr_export_readiness()` contract,
`Structure`, `BiologicalHierarchy`, charge/radius datasets, `ExportReport`,
`MolecularExport` and `atomic_write_chunks`. Add one focused writer module that
emits the two whitespace dialects already accepted by the native PQR reader.
Do not create another molecular model, generic serializer framework or PDB/PQR
writer hierarchy.

**Tech Stack:** Python 3.13, Blender-bundled NumPy, standard-library
`unittest`, native `ChemBlender.core.formats.pqr`, Blender Extensions tooling.

## Global Constraints

- Start only after `.agents/queued/2.4.0-pqr-export.md` is explicitly activated.
- Preserve `Structure`, `BiologicalHierarchy`, `AtomicProperty`, Reader API
  `1.0-rc1` and sidecar schema 1.0.
- Reuse `pqr_export_readiness()`; do not fork its association, field-budget,
  charge/radius or single-Structure rules.
- Use only existing dependencies. Importing the exporter must not load `bpy`,
  RDKit, Gemmi, ASE, Open Babel, cclib, IOData, GBasis or spglib.
- The normalized slice is **No UI**, **No FrameSet**, **No Cube**, **No MODEL**,
  **No CONECT** and **No CRYST1**.
- Omitted scientific/source semantics must appear in a stable loss report and
  block destination publication until `confirm_loss=True`.
- Do not modify manifest version, CHANGELOG release entries, workflows, tags or
  Releases.

---

### Task 1: Activate and freeze the public PQR writer contract

**Files:**
- Move: `.agents/queued/2.4.0-pqr-export.md` to `.agents/active/2.4.0-pqr-export.md`
- Create: `tests/test_pqr_exporter.py`
- Create: `docs/quantum-visualization/2.4.0/pqr-export-contract.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**

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

- [ ] **Step 1: Activate only the queued cursor**

Set goal `CB240-PQR-EXPORT-T5`, state `in_progress`, and current task
`Task 1 — Freeze native PQR export contract`. Keep PQR UI, Cube and Reader API
stable unstarted.

- [ ] **Step 2: Write the public contract RED**

Tests must require:

- `preview_pqr_export` and `export_pqr` are public from
  `ChemBlender.core.exporters`;
- ready with-chain and no-chain fixtures emit deterministic ASCII/LF text;
- unsupported readiness raises `ValueError` containing the exact stable tokens;
- a loss report blocks text and destination creation until `confirm_loss=True`;
- `confirm_loss` is exact `bool`;
- cancellation before validation raises `ExportCancelled` and publishes nothing.

Run:

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pqr_exporter -v
```

Expected RED: `tests.test_pqr_exporter` cannot import the two writer functions.

---

### Task 2: Implement the minimum deterministic 10/11-field writer

**Files:**
- Create: `ChemBlender/core/exporters/pqr.py`
- Modify: `ChemBlender/core/exporters/__init__.py`
- Modify: `ChemBlender/core/exporters/pdb_readiness.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_pdb_export_readiness.py`
- Modify: `tests/test_pqr_exporter.py`

**Interfaces:** Consume Task 1 signatures, `PDBPQRExportStatus`,
`ExportReport`, `ExportReportEntry`, `MolecularExport`, `atomic_write_chunks`,
`ExportCancelled` and the native PQR element-inference rule. Produce normalized
ASCII PQR records.

- [ ] **Step 1: Resolve one authoritative entity projection**

Resolve exactly one Structure, one matching BiologicalHierarchy, one complete
`partial_charge` AtomicProperty in `elementary_charge`, and one complete
positive `radius` AtomicProperty in `angstrom`. Use the readiness result as the
first gate, then re-read the live arrays at serialization time. Do not accept a
FrameSet or a second Structure.

- [ ] **Step 2: Validate native re-import element identity before publication**

Add readiness and writer RED cases for an atom name whose native PQR inference
does not match the Structure atomic number. For every atom, reuse the existing
`ChemBlender.core.formats.pqr._infer_pqr_element` rule with the preserved atom
name, `ATOM`/`HETATM` kind and residue name. Return the stable readiness token
`identity.element.mismatch` before serialization; repeat the guard at the
writer trust boundary. Do not copy the periodic-table heuristic.

- [ ] **Step 3: Emit only the accepted whitespace records**

Use one ASCII line per atom:

```text
ATOM serial atom_name residue_name chain residue_id x y z charge radius
ATOM serial atom_name residue_name residue_id x y z charge radius
```

The first form has 11 fields and is used only for non-empty chain IDs. The
second has 10 fields. Uppercase `ATOM`/`HETATM`; combine residue sequence number
and optional insertion code into one token. Format coordinates with exactly
three decimal places, charge and radius with exactly four, normalize negative
zero, and terminate each record with one LF. Preserve valid source serials only
for `Ready`; otherwise allocate `1..atom_count` in Structure order.

Reject non-ASCII/control labels, live-array mutation, non-finite values,
non-positive radii, element mismatch and field overflow before destination
publication. Do not emit headers, `MODEL`, `END`, `TER`, `CONECT` or comments.

- [ ] **Step 4: Preview only actual omissions**

Use stable sorted loss codes for serial renumbering and real omitted semantics:
topology, periodic cell, isotope, formal charge, atom-map number, stereo label
and molecular charge/multiplicity.
Do not report UUID, revision, provenance or whitespace normalization as loss.

- [ ] **Step 5: Publish atomically and expose the functions**

Use `atomic_write_chunks()` and its short sibling temporary path. Check
cancellation before validation and between record chunks. Cancellation or any
error leaves no destination or temporary sibling. Add both functions to
`ChemBlender.core.exporters.__all__` and document the new module in the code
architecture guide.

- [ ] **Step 6: Run GREEN and commit**

```powershell
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pqr_exporter -v
git diff --check
git add -- .agents/active/2.4.0-pqr-export.md .agents/reference/code-architecture-guide.md ChemBlender/core/exporters/pqr.py ChemBlender/core/exporters/pdb_readiness.py ChemBlender/core/exporters/__init__.py docs/quantum-visualization/2.4.0/pqr-export-contract.md tests/test_pdb_export_readiness.py tests/test_pqr_exporter.py tests/test_quantum_visualization_docs.py
git commit -m "feat: add deterministic native PQR export"
```

Add only files actually modified.

---

### Task 3: Qualify dialect, loss, cancellation and Semantic native re-import

**Files:**
- Modify: `ChemBlender/core/exporters/pqr.py`
- Modify: `tests/test_pqr_exporter.py`

**Interfaces:** Consume the Task 2 writer. Produce executable evidence for the
normalized PQR boundary.

- [ ] **Step 1: Add focused RED cases**

Cover:

1. with-chain output has exactly 11 fields; no-chain output has exactly 10;
2. `ATOM`/`HETATM`, residue, chain and insertion-code tokens round-trip;
3. reversed tuple/dict insertion order produces identical bytes;
4. duplicate/out-of-range serials renumber predictably;
5. charge and radius use exact units, finite values and 4-decimal formatting;
6. coordinate, serial, label, residue, charge and radius overflow fails closed;
7. atom-name context that infers the wrong element fails before publication;
8. FrameSet and multiple Structures remain unsupported through readiness;
9. cancellation before validation and mid-write leaves no destination/temp;
10. topology/cell/identity omissions produce sorted stable loss codes.

- [ ] **Step 2: Implement only missing shared boundaries and run GREEN**

```powershell
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pqr_exporter -v
```

Each RED must name one absent boundary. Do not refactor the working PDB writer
or create a general fixed-field/exporter base class.

- [ ] **Step 3: Prove Semantic native re-import**

Export to a temporary `.pqr`, parse with native `parse_pqr()`, and compare:

- atomic numbers and coordinates within the written 0.001 angstrom precision;
- atom names, record kinds, chain IDs, residue names/numbers and insertion codes;
- charge and radius values within the written 0.0001 precision.

Do not compare UUIDs, revisions, provenance, raw lines or whitespace.

- [ ] **Step 4: Commit the boundary proof**

```powershell
git add -- ChemBlender/core/exporters/pqr.py ChemBlender/core/exporters/pdb_readiness.py tests/test_pdb_export_readiness.py tests/test_pqr_exporter.py
git diff --cached --check
git commit -m "test: qualify native PQR export boundaries"
```

Add only files actually modified.

---

### Task 4: Publish the core capability

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `docs/quantum-visualization/2.3.0/format-maturity-matrix.md`
- Regenerate: `docs/quantum-visualization/reader-capability-matrix.json`
- Regenerate: `docs/user/format-capabilities.json`
- Regenerate: `docs/user/formats.md`

**Interfaces:** Consume the qualified core writer. Produce PQR export capability
`F5 / core / preview_confirmation`.

- [ ] **Step 1: Add capability RED**

Require the generated PQR export object to equal:

```python
{
    "execution_mode": "core",
    "format_id": "pqr",
    "loss_policy": "preview_confirmation",
    "maturity": "F5",
}
```

Run `tests.test_generated_docs_fresh` and observe the current F0 result.

- [ ] **Step 2: Change the single capability source and regenerate**

Add only:

```python
"pqr": ("pqr", "F5", "core", "preview_confirmation"),
```

to `_READER_EXPORTS`, then run:

```powershell
& $pythonBin ChemBlender/scripts/generate_format_docs.py --write
& $pythonBin -m unittest tests.test_pqr_exporter tests.test_generated_docs_fresh -v
```

Only PQR export capability documentation may change. PQR must not appear in
Project Browser format choices in this No UI task.

- [ ] **Step 3: Commit capability publication**

```powershell
git add -- ChemBlender/core/reader_catalog.py docs/quantum-visualization/2.3.0/format-maturity-matrix.md docs/quantum-visualization/reader-capability-matrix.json docs/user/format-capabilities.json docs/user/formats.md tests/test_generated_docs_fresh.py
git diff --cached --check
git commit -m "docs: publish native PQR export capability"
```

---

### Task 5: Full local qualification, reviews and checkpoint

**Files:**
- Move: `.agents/active/2.4.0-pqr-export.md` to `.agents/completed/2.4.0-pqr-export.md`
- Modify: `ChemBlender/benchmarks/budget.json` only from a fresh-checkout exact
  package measurement when zero-unexplained-growth verification requires it
- Modify: `tests/test_quantum_visualization_docs.py`
- Verify: every Task 1–4 file

**Interfaces:** Produce a clean local PQR core-export checkpoint; no PQR UI is
activated.

- [ ] **Step 1: Run focused and full Python verification**

```powershell
& $pythonBin -m unittest tests.test_pdb_export_readiness tests.test_pqr_exporter tests.test_pqr_reader tests.test_generated_docs_fresh tests.test_quantum_visualization_docs -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
```

- [ ] **Step 2: Run package and real Blender verification**

Using Blender 5.1.2, run native extension validate/build, ZIP
path/duplicate/CRC/two-wheel/hash and zero-unexplained-growth audit, isolated
install, repeated register/unregister/reload, and an installed core PQR
export/native re-import smoke. Importing the writer must not load optional
stacks. If the new tracked code changes the package baseline, update only the
exact fresh-checkout package/member/code baselines; unexplained allowances,
wheel and safety limits remain unchanged.

- [ ] **Step 3: Run two independent reviews**

Run specification-compliance and code-quality reviews. Fix every Critical,
Important and task-related Minor finding, then rerun Steps 1–2.

- [ ] **Step 4: Complete the cursor and checkpoint**

Record commits, RED/GREEN evidence, focused/full counts, deterministic bytes,
loss confirmation, Semantic native re-import, package/Blender results, reviews
and `Remote CI: Not Run`. Move the cursor to completed and leave no active or
queued PQR implementation.

```powershell
git diff --check
git status --short
git add -- .agents/completed/2.4.0-pqr-export.md tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "chore: checkpoint native PQR export"
```

Stop before PQR UI, Cube, Reader API stable, version or Release work.

---

### Task 6: Exact-head remote integration gate

**Files:**
- Modify: `.agents/completed/2.4.0-pqr-export.md` only after remote state changes

**Interfaces:** Consume the clean local checkpoint. Produce exact-head CI and an
ordinary merge only under explicit remote authorization.

- [ ] **Step 1: Push and open a ready PR only when authorized**

Push normally without force/rebase. Open one PR to `main` that lists the PQR
core scope, local test counts, Blender/package evidence and No UI boundary.

- [ ] **Step 2: Require exact-head CI**

Wait for `extension-package` and `optional-qc-core`; each run `headSha` must
equal the pushed feature head and every required job must reach `success`. A new
commit invalidates older CI evidence.

- [ ] **Step 3: Merge only when authorized**

Use an ordinary merge commit, never squash or rebase merge. Fetch and verify the
exact feature head is an ancestor of `origin/main`; record PR URL/number, run
IDs/URLs, exact head and merge SHA.

Stop after integration. PQR UI remains a separate later scope-discovery choice.
