# ChemBlender 2.4.0 Native MOL2 Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dependency-free, deterministic native MOL2 core exporter with explicit loss confirmation and semantic re-import verification.

**Architecture:** Reuse `mol2_export_readiness`, the existing exchange entities and the shared `MolecularExport`/`ExportReport`/atomic-write contracts. Add one focused writer module; do not add a second molecular model or pass parser objects into the project. This Task 1 ends at the core API and generated capability documents: **No UI**, PDB/PQR work or dependency change belongs here.

**Tech Stack:** Python 3.13, NumPy already supplied by Blender, standard-library `unittest`, native `ChemBlender.core.formats.mol2`, Blender Extensions tooling.

## Global Constraints

- Baseline is the Scope Discovery checkpoint containing `docs/quantum-visualization/2.4.0/candidate-intake.md`.
- Keep `Mol2ExportReadiness`, `Structure`, `TopologyRecord`, `MolecularRecord`, `AtomicProperty` and `ChemicalAnnotation` as the only scientific inputs.
- Add no dependency and never import RDKit, Gemmi, ASE, Open Babel or Blender from the new writer module.
- Preserve the existing `1.0-rc1` Reader API token and sidecar schema.
- Do not modify Blender export UI or registration in this task.
- Do not claim byte-identical or lossless Tripos round-trip. Raw-only omissions require explicit confirmation.
- Do not modify manifest version, CHANGELOG release entries, tags or Releases.
- No push, PR or remote operation is part of the local implementation checkpoint.

---

### Task 1: Activate and lock the native writer contract

**Files:**
- Move: `.agents/queued/2.4.0-mol2-export.md` to `.agents/active/2.4.0-mol2-export.md`
- Create: `docs/quantum-visualization/2.4.0/mol2-export-contract.md`
- Create: `tests/test_mol2_exporter.py`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `mol2_export_readiness(project_entities) -> Mol2ExportReadiness` and the existing entity groups on `ImportBatch` or `QCProject`.
- Produces: the public signatures `preview_mol2_export(project_entities) -> ExportReport` and `export_mol2(project_entities, *, confirm_loss=False, destination=None, is_cancelled=None) -> MolecularExport`.

- [ ] **Step 1: Activate the queued cursor**

Move the queued cursor to `.agents/active/2.4.0-mol2-export.md`, set `State` to
`in_progress`, set `Current task` to `Core writer contract`, and record the exact
Scope Discovery checkpoint SHA as its baseline. Update the documentation inventory
test so this is the only active task and `.agents/queued/` is empty.

- [ ] **Step 2: Write the contract before the implementation**

Create `mol2-export-contract.md` with these exact rules:

- `Unsupported` readiness raises `ValueError` containing the ordinally sorted tokens;
- `Partial` readiness returns a preview with one `missing:<token>` entry per token;
- raw-only information that a normalized writer omits produces stable loss entries;
- no destination is created until `confirm_loss=True` when confirmation is required;
- atom and bond IDs are allocated `1..N` in emitted order;
- records sort by `(source_record_index, record_key, structure UUID)` rather than container order;
- numeric text uses finite, locale-independent `.17g` formatting with negative zero normalized;
- semantic round-trip compares scientific entities, not UUIDs, whitespace or provenance;
- unsupported periodic shifts, non-angstrom coordinates, malformed token fields and non-finite values fail closed.

- [ ] **Step 3: Write the first failing exporter tests**

Create `tests/test_mol2_exporter.py` with real parser fixtures. The initial tests must
import the wished-for public API and cover the following behavior:

```python
from ChemBlender.core.exporters import export_mol2, preview_mol2_export
from ChemBlender.core.formats.mol2 import parse_mol2


def test_aromatic_fixture_exports_deterministically(self):
    batch = parse_mol2(AROMATIC_FIXTURE)
    first = export_mol2(batch)
    second = export_mol2(batch)
    self.assertEqual(first.text, second.text)
    self.assertFalse(first.report.requires_confirmation)
    self.assertIn("@<TRIPOS>MOLECULE\n", first.text)
    self.assertIn("  ar\n", first.text)


def test_loss_preview_blocks_the_destination_until_confirmed(self):
    batch = parse_mol2(SMALL_FIXTURE)
    with TemporaryDirectory() as directory:
        destination = Path(directory) / "normalized.mol2"
        blocked = export_mol2(batch, destination=destination)
        self.assertEqual(blocked.text, "")
        self.assertTrue(blocked.report.requires_confirmation)
        self.assertFalse(destination.exists())
```

Also assert that missing topology raises `ValueError` with `topology`, and that the
small fixture reports source-ID/unknown-section loss rather than silently dropping it.

- [ ] **Step 4: Run RED**

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest tests.test_mol2_exporter -v
```

Expected: import failure because `preview_mol2_export` and `export_mol2` are not yet
public.

- [ ] **Step 5: Commit the activated contract after it is GREEN in Task 2**

Do not commit a failing test. Task 1 and Task 2 form one reviewable implementation
commit after the writer passes.

---

### Task 2: Implement deterministic normalized MOL2 text

**Files:**
- Create: `ChemBlender/core/exporters/mol2.py`
- Modify: `ChemBlender/core/exporters/__init__.py`
- Test: `tests/test_mol2_exporter.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: Task 1's two public signatures and existing `Mol2ExportStatus`, `MolecularExport`, `ExportReport`, `ExportReportEntry`, `atomic_write_chunks` and `ExportCancelled`.
- Produces: deterministic UTF-8 MOL2 text and a report whose `frame_count` is the number of emitted MOL2 records.

- [ ] **Step 1: Add the minimal public module**

Create `ChemBlender/core/exporters/mol2.py`. The public flow must have this shape:

```python
def preview_mol2_export(project_entities):
    readiness = mol2_export_readiness(project_entities)
    if readiness.status is Mol2ExportStatus.UNSUPPORTED:
        raise ValueError(
            "MOL2 export is unsupported: " + ", ".join(readiness.missing_fields)
        )
    entries = tuple(
        ExportReportEntry(f"missing:{token}", f"MOL2 field is missing: {token}")
        for token in readiness.missing_fields
    ) + _raw_loss_entries(project_entities)
    return ExportReport(
        "mol2",
        False,
        len(_ordered_structures(project_entities)),
        bool(entries),
        tuple(sorted(set(entries), key=lambda entry: (entry.code, entry.message))),
    )


def export_mol2(
    project_entities,
    *,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
):
    if type(confirm_loss) is not bool:
        raise TypeError("confirm_loss must be bool")
    preview = preview_mol2_export(project_entities)
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    text = "".join(_normalized_record(entry) for entry in _ordered_entries(project_entities))
    if destination is not None:
        atomic_write_chunks(destination, (text,), is_cancelled=is_cancelled)
    return MolecularExport(
        text,
        ExportReport("mol2", destination is not None, preview.frame_count,
                     preview.requires_confirmation, preview.entries),
    )
```

Use a tuple or frozen dataclass only if it removes repeated association work; do not
introduce a public planning model. `_ordered_entries` must resolve exactly one selected
topology, record, role property and Tripos annotation for each structure using the same
association rules as readiness, then sort independently of dict/tuple insertion order.

- [ ] **Step 2: Emit only the supported normalized sections**

`_normalized_record` must emit, in order:

```text
@<TRIPOS>MOLECULE
<title>
<atom_count> <bond_count> <substructure_count> 0 0
<molecule_type>
<charge_type>
@<TRIPOS>ATOM
...
@<TRIPOS>BOND
...
@<TRIPOS>SUBSTRUCTURE
...
```

Rules:

- title comes from the unique bound `MolecularRecord`, otherwise the structure UUID;
- missing molecule type becomes `SMALL` only after loss confirmation;
- missing/inconsistent charge metadata becomes `NO_CHARGES` only after loss confirmation;
- omit optional atom substructure/charge columns when their complete property is absent;
- emit `SUBSTRUCTURE` only when complete ID and name properties exist;
- emit bond types as `ar`, `amide`, `1`, `2` or `3` from the already validated topology;
- use the atom order from `Structure` and canonical bond order from `TopologyRecord`;
- reject whitespace/newlines in token fields and reject invalid array shape/unit/value at the writer trust boundary.

Use the existing `atomic_write_chunks`; do not add a second temporary-file helper.

- [ ] **Step 3: Expose the two functions**

Import and add `preview_mol2_export` and `export_mol2` to
`ChemBlender/core/exporters/__init__.py::__all__`. Importing
`ChemBlender.core.exporters` must not load `rdkit`, `gemmi`, `ase`, `bpy` or another
optional stack.

- [ ] **Step 4: Verify GREEN and semantic re-import**

Add assertions that write to a temporary `.mol2`, call `parse_mol2(destination)`, and
compare these literal scientific fields:

- atomic numbers, coordinates and atom names;
- canonical bond endpoints, orders, aromatic flags and `amide` labels;
- `atom_type`, complete `partial_charge`, `substructure_id` and `substructure_name`;
- Tripos `molecule_type` and `charge_type` annotations;
- multi-record count and deterministic order.

UUIDs, revisions, provenance IDs, source hashes, raw whitespace and comments are not
semantic equality fields.

```powershell
& $pythonBin -m unittest `
  tests.test_mol2_export_readiness `
  tests.test_mol2_exporter -v
```

Expected: all tests pass with zero errors/failures.

- [ ] **Step 5: Commit the core writer**

```powershell
git add -- `
  .agents/active/2.4.0-mol2-export.md `
  .agents/reference/code-architecture-guide.md `
  ChemBlender/core/exporters/mol2.py `
  ChemBlender/core/exporters/__init__.py `
  docs/quantum-visualization/2.4.0/mol2-export-contract.md `
  tests/test_mol2_exporter.py `
  tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "feat: add deterministic native MOL2 export"
```

---

### Task 3: Qualify cancellation, multi-record ordering and loss boundaries

**Files:**
- Modify: `tests/test_mol2_exporter.py`
- Modify: `ChemBlender/core/exporters/mol2.py`

**Interfaces:**
- Consumes: Task 2's public API.
- Produces: proof that writer failure/cancellation never publishes a partial destination and that container ordering cannot change bytes.

- [ ] **Step 1: Write failing boundary tests**

Add tests for:

1. reversed `ImportBatch` entity tuples and reversed `QCProject` dict insertion order
   produce identical bytes;
2. `tests/fixtures/mol2/multi.mol2` emits the source record-index order;
3. a cancellation callback before and during output raises `ExportCancelled` and leaves
   no destination or sibling temporary file;
4. non-finite coordinates/charge, non-angstrom coordinates, nonzero periodic shifts,
   whitespace token fields and unsupported bond mapping fail without a destination;
5. `confirm_loss` must be exact `bool`;
6. unknown `SET` and raw status/comment fields create stable, duplicate-free loss codes.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_mol2_exporter -v
```

Expected: at least the reversed-container or cancellation-mid-stream test fails before
the minimal ordering/validation fix.

- [ ] **Step 3: Make only the failing boundaries GREEN**

Use ordinal tuple keys and the shared cancellation callback. Do not add concurrency,
streaming classes or a configuration object: fixture-scale normalized records fit the
existing chunk writer.

- [ ] **Step 4: Verify and commit**

```powershell
& $pythonBin -m unittest `
  tests.test_mol2_export_readiness `
  tests.test_mol2_exporter `
  tests.test_mol2_reader `
  tests.test_mol2_syntax -v
git add -- ChemBlender/core/exporters/mol2.py tests/test_mol2_exporter.py
git diff --cached --check
git commit -m "test: qualify native MOL2 export boundaries"
```

---

### Task 4: Publish the core export capability

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `docs/quantum-visualization/2.3.0/format-maturity-matrix.md`
- Regenerate: `docs/quantum-visualization/reader-capability-matrix.json`
- Regenerate: `docs/user/format-capabilities.json`
- Regenerate: `docs/user/formats.md`
- Verify unchanged unless generator requires it: `docs/user/dependencies.json`

**Interfaces:**
- Consumes: the verified public core writer.
- Produces: MOL2 export capability `("mol2", "F5", "core", "preview_confirmation")`; no Project Browser claim.

- [ ] **Step 1: Write the failing capability assertion**

In `tests/test_generated_docs_fresh.py`, assert:

```python
self.assertEqual(
    by_id["mol2"]["export"],
    {
        "execution_mode": "core",
        "format_id": "mol2",
        "loss_policy": "preview_confirmation",
        "maturity": "F5",
    },
)
```

Run the single test and confirm it fails because current MOL2 export maturity is F0.

- [ ] **Step 2: Update the single runtime source**

Add this exact entry to `_READER_EXPORTS` in `reader_catalog.py`:

```python
"mol2": ("mol2", "F5", "core", "preview_confirmation"),
```

Do not add MOL2 to `ui.export._FORMAT_ITEMS`; Task 1 has no UI.

- [ ] **Step 3: Regenerate and verify the documents**

```powershell
& $pythonBin ChemBlender/scripts/generate_format_docs.py --write
& $pythonBin -m unittest tests.test_generated_docs_fresh -v
```

Inspect the diff. Only the MOL2 export row/JSON object may change; dependency inventory
bytes must remain unchanged. Update the static maturity row to describe `F5 core` with
explicit loss confirmation rather than a Project Browser workflow.

- [ ] **Step 4: Commit the capability**

```powershell
git add -- `
  ChemBlender/core/reader_catalog.py `
  docs/quantum-visualization/2.3.0/format-maturity-matrix.md `
  docs/quantum-visualization/reader-capability-matrix.json `
  docs/user/format-capabilities.json `
  docs/user/formats.md `
  tests/test_generated_docs_fresh.py
git diff --cached --check
git commit -m "docs: publish native MOL2 export capability"
```

---

### Task 5: Full verification, independent review and checkpoint

**Files:**
- Move: `.agents/active/2.4.0-mol2-export.md` to `.agents/completed/2.4.0-mol2-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`
- Verify: all Task 1 files

**Interfaces:**
- Consumes: Tasks 1–4 and their commits.
- Produces: a clean local branch with the MOL2 core exporter complete and no UI task started.

- [ ] **Step 1: Run focused and full Python verification**

```powershell
& $pythonBin -m unittest `
  tests.test_mol2_export_readiness `
  tests.test_mol2_exporter `
  tests.test_mol2_reader `
  tests.test_mol2_syntax `
  tests.test_generated_docs_fresh `
  tests.test_quantum_visualization_docs -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
```

- [ ] **Step 2: Run package verification**

Using Blender 5.1.2, run native extension validate/build, ZIP inventory audit and an
isolated install/import smoke that imports `ChemBlender.core.exporters`, exports the
aromatic fixture, reparses it and confirms no optional dependency was loaded by the
writer. No Blender UI export smoke belongs to this task.

- [ ] **Step 3: Request two independent reviews**

Run specification-compliance and code-quality reviews against the Scope Discovery
checkpoint. Fix every Critical/Important and directly related Minor finding, then rerun
Steps 1–2. Record review-fix SHAs or `none`.

- [ ] **Step 4: Complete the cursor and contract**

Record exact commits, RED/GREEN evidence, focused/full counts, Blender package result,
semantic round-trip, loss confirmation, optional-import audit and `Remote CI: Not Run`.
Move the cursor to completed and update the documentation inventory test so no later
task is silently active.

- [ ] **Step 5: Final static checks and checkpoint commit**

```powershell
git diff --check
git show --check --stat --oneline origin/main..HEAD
git status --short
git add -- `
  .agents/completed/2.4.0-mol2-export.md `
  tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "chore: checkpoint native MOL2 export"
git status --short
```

Stop with a clean worktree. Do not start MOL2 UI, PDB/PQR export, a version bump or any
remote operation.
