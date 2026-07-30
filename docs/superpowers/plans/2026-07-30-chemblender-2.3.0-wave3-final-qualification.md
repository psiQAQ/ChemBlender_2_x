# ChemBlender 2.3.0 Wave 3 Final Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` task by task. Track completion with the
> checkbox steps below.

**Goal:** Freeze the completed Wave 3 exchange and Reader Extension boundary,
qualify fixed MOL2/PDB/PQR/CJSON project lifecycles, record reproducible scale
evidence and close the Wave before Wave 4 starts.

**Architecture:** Qualification reuses the frozen exchange models,
`ReaderPluginRegistry`, canonical document and sidecar. It adds executable
contracts and benchmark evidence only. Runtime changes are permitted solely
when a new RED test exposes a real Wave 3 regression.

**Tech Stack:** Python 3.13, NumPy, repository-pinned Gemmi/RDKit wheels,
standard-library `unittest`, Blender 5.1.2 Extensions and PowerShell.

## Global Constraints

- Start from Wave 3 checkpoint
  `4d193cf32ddefabac04cfa5644da748ed40e83f3`.
- Keep sidecar schema `1.0` and Reader API `1.0-rc1`.
- Do not change the manifest version, dependencies, workflows, changelog,
  tags or releases.
- Do not implement MOL2/PDB/PQR export, ribbon/cartoon, assembly expansion or
  another exchange model.
- Optional wheels may be unpacked into temporary test paths; do not install
  or upgrade dependencies.
- Do not activate Wave 4.
- Do not push without a new explicit authorization.

---

### Task 1: Persist the final qualification gate

**Files:**
- Create:
  `docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave3-final-qualification.md`
- Modify: `.agents/active/2.3.0-wave-3-exchange-mol2-pdb-pqr.md`

**Interfaces:**
- Consumes: completed MOL2, PDB/PQR and CJSON/Reader API plan checkpoints.
- Produces: one in-progress `W3-FINAL-QUALIFICATION-GATE` cursor.

- [x] **Step 1: Record the live baseline**

Record branch, worktree, exact baseline SHA, Blender executable/Python/runtime
and the completed plan checkpoints.

- [x] **Step 2: Record scope and stop boundary**

Required subgoals are `exchange-capability-freeze`,
`fixed-exchange-roundtrip`, `reader-extension-lifecycle`,
`wave3-scale-baseline`, `full-product-verification` and
`independent-final-review`. Wave 4 remains queued.

- [x] **Step 3: Verify and commit**

Run documentation contracts and `git diff --check`, then commit the plan and
cursor:

```text
docs: start Wave 3 final qualification
```

### Task 2: Freeze exchange and Reader API qualification contracts

**Files:**
- Create: `tests/test_wave3_exchange_qualification.py`
- Modify only if a real mismatch is found:
  `docs/quantum-visualization/reader-capability-matrix.json`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: live built-in reader descriptors, exchange model public surface,
  fixed Wave 3 fixtures and Reader API conformance.
- Produces: executable capability, dependency and lifecycle qualification.

- [ ] **Step 1: Write the RED qualification contract**

Require exact capability-matrix entries for `mol2`, `pdb`, `pqr` and `cjson`;
public exchange entities without parser/vendor objects; and imports of
`ChemBlender.core`/`ChemBlender.reader_api` that do not load RDKit, Gemmi,
OpenBabel, Biopython, ASE or pymatgen.

Use the existing fixtures:

```text
tests/fixtures/mol2/{small,aromatic,substructure,multi}.mol2
tests/fixtures/pdb/{atom-hetatm,altloc,conect,cryst1,multimodel}.pdb
tests/fixtures/pqr/{with-chain,no-chain,padded}.pqr
tests/fixtures/cjson/water-results.cjson
```

For every format, parse, commit, save sidecar schema `1.0`, reopen and compare
the format-specific scientific identity. CJSON additionally exports and
reparses semantically. MOL2/PDB/PQR use their P1 readiness reports and do not
pretend that an exporter exists.

- [ ] **Step 2: Qualify Reader API v1 and plugin-missing recovery**

Run the 12 required built-in conformance cases and the standalone example
case. Verify a saved example-reader project opens from sidecar after the
example business module is absent, while reparse is explicitly unavailable.
Do not scan arbitrary `sys.path`.

- [ ] **Step 3: Run GREEN and commit**

Run the new qualification test plus Wave 3 parser, sidecar, conformance,
plugin discovery and documentation modules. Commit:

```text
test: qualify Wave 3 exchange boundaries
```

### Task 3: Record a reproducible Wave 3 scale baseline

**Files:**
- Create: `ChemBlender/scripts/benchmark_exchange.py`
- Create: `docs/performance/wave3-exchange-baseline.md`
- Modify: `tests/test_wave3_exchange_qualification.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: native MOL2/PDB/PQR/CJSON parsers and existing preview projection.
- Produces: canonical benchmark JSON with environment, workload, warmup,
  sample count, median, p95 and peak Python memory.

- [ ] **Step 1: Write the benchmark RED contract**

Require a small in-process API and CLI using only the standard library plus
existing ChemBlender APIs. Metrics are `mol2_parse`, `pdb_parse`,
`pqr_parse`, `cjson_parse` and `preview_projection`. Each metric records cold,
median, p95, peak bytes and workload size. Disabled Blender-only work is
reported `Not Run`, never fabricated.

- [ ] **Step 2: Implement the minimum deterministic benchmark**

Generate bounded synthetic files directly to a temporary directory; do not
build nested full-project copies or Blender objects. Use stable numeric text,
one warmup and at least five measured samples. Output sorted compact UTF-8
JSON with one trailing LF.

- [ ] **Step 3: Measure the reference workloads**

Measure small product preview latency and 50,000-atom native parsing for
MOL2/PDB/PQR/CJSON on the reference machine. Record whether quick feedback is
within 0.5 seconds, whether peak memory is bounded relative to source bytes
and whether work exceeding one second remains outside the Blender draw path.
Do not turn one desktop timing into a cloud-CI absolute threshold.

- [ ] **Step 4: Run GREEN and commit**

Run the benchmark contract, CLI, compileall and `git diff --check`. Commit:

```text
perf: record Wave 3 exchange baseline
```

### Task 4: Run the final product gate and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-3-exchange-mol2-pdb-pqr.md`
- Modify:
  `docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave3-final-qualification.md`

**Interfaces:**
- Consumes: Tasks 1–3 commits and all three completed Wave 3 plans.
- Produces: completed Wave 3 evidence and a clean branch stopped before Wave 4.

- [ ] **Step 1: Run focused and full Python verification**

Run Wave 3 format/model/UI/export-readiness, sidecar, Reader API,
conformance, example, registration, qualification and documentation modules,
then:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests examples/reader-extension
git diff --check
```

- [ ] **Step 2: Run Blender 5.1.2 product qualification**

Run native validate/build, exact ZIP safe-path/duplicate/CRC/wheel audit and
isolated install. Qualify MOL2, PDB, PQR and CJSON import/view/save/reopen;
base + good + duplicate-ID failing Reader Extensions; missing-plugin reopen;
register/unregister/reload x2; and the repository product smoke.

- [ ] **Step 3: Request two independent reviews**

One review checks specification/scientific compliance. A second checks code
quality, benchmark honesty, resource ownership, packaging and
over-engineering. Fix all Critical, Important and gate-related Minor findings,
then rerun affected and full verification.

- [ ] **Step 4: Complete the cursor and checkpoint**

Record commits, RED/GREEN counts, benchmark metrics, Blender/package evidence,
`Remote CI: Not Run`, worktree status and:

```text
Next plan: Wave 4 migration and release qualification
Stop boundary: Wave 4 has not started
```

Commit:

```text
chore: checkpoint Wave 3 final qualification
```
