# ChemBlender 2.3.0 Wave 2 Bundled Gemmi and CIF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle a pinned Gemmi wheel and make robust CIF import, raw-envelope preservation, block selection, occupancy/ADP handling and controlled export available in the base Windows extension.

**Architecture:** Gemmi owns CIF lexical/structural parsing. A ChemBlender adapter maps selected blocks to internal periodic models and preserves original bytes/envelope. Optional spglib is not imported by the reader. Export patches known fields in a copy of the source envelope or creates an explicitly normalized new document.

**Tech Stack:** Gemmi, Python 3.13, NumPy, Blender 5.1 Extension wheels, existing PeriodicSiteData/CIFEnvelope/import pipeline, standard-library tests and Blender smoke.

## Global Constraints

- Gemmi is the only new required scientific wheel in this Wave.
- Gemmi imports only during CIF availability/parse operations, not extension enable.
- CIF import must work with spglib absent.
- Raw source bytes and unknown tags/loops are preserved.
- File-declared symmetry is not replaced by derived symmetry.
- Wheel version, URL, SHA-256, license, size and lifecycle evidence are mandatory.

---

### Task 1: Approve and lock the Gemmi wheel

**Files:**
- Modify: `.agents/decisions/0030-native-dependency-and-gemmi-boundary.md` (or its renumbered equivalent selected during document integration)
- Modify: `.agents/reference/dependencies-and-release.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `.github/workflows/extension-package.yml`
- Modify: `ChemBlender/scripts/validate_extension.py`
- Create: `tests/test_gemmi_dependency_contract.py`

**Interfaces:**
- Produces: exact Gemmi wheel metadata and package contract.

- [ ] **Step 1: Select the official CPython 3.13 Windows x64 wheel**

Download from the official PyPI file URL in a temporary developer/CI location. Record distribution version, filename, URL, SHA-256, compressed bytes, unpacked bytes and MPL-2.0 notice. Do not commit the wheel.

- [ ] **Step 2: Add dependency contract tests**

```python
def test_manifest_declares_inventory_gemmi_wheel(self):
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    inventory = tomllib.loads(DEPENDENCIES.read_text(encoding="utf-8"))
    gemmi = inventory["packages"]["gemmi"]
    self.assertIn(f"./wheels/{gemmi['filename']}", manifest["wheels"])
    self.assertRegex(gemmi["sha256"], r"[0-9a-f]{64}")
    self.assertTrue(gemmi["url"].startswith("https://"))
```

Also assert Git ignores `.whl` and the dependency reference repeats the inventory source and license boundary.

- [ ] **Step 3: Add CI download and hash verification**

Use the recorded URL/SHA. Download RDKit and Gemmi to `ChemBlender/wheels/`. The package audit expects exactly the approved wheel list, not any `.whl` glob.

- [ ] **Step 4: Extend validator and ZIP audit**

Validate wheel filenames against manifest and dependency inventory. Reject missing, extra or duplicate wheels.

- [ ] **Step 5: Run package preflight and commit**

Run dependency contract tests and local validator with both wheels present. Commit metadata/workflow/manifest, not wheel bytes.

### Task 2: Move CIF reader to the built-in Reader API

**Files:**
- Move or adapt: `ChemBlender/core/gemmi_adapter.py` → `ChemBlender/core/formats/cif.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `ChemBlender/reader_api/registry.py`
- Modify: `tests/test_gemmi_adapter.py`
- Create: `tests/test_cif_reader.py`

**Interfaces:**
- Produces: built-in reader ID `cif`, execution mode built-in, availability based on bundled Gemmi.

- [ ] **Step 1: Add import isolation tests**

`import ChemBlender.core` and extension enable do not load `gemmi`. Calling CIF availability may use `find_spec`; parsing loads Gemmi. Simulated missing Gemmi marks reader unavailable without breaking registry.

- [ ] **Step 2: Preserve old public functions**

`parse_cif` and `sniff_cif` remain re-exported from `ChemBlender.core`. `CIF_READER` points to the new built-in public descriptor.

- [ ] **Step 3: Convert output to PublicImportBatch**

SourceRecord/Revision and diagnostics are produced through the import pipeline, not embedded ad hoc. Reader returns structure/site/envelope entities and parser report.

- [ ] **Step 4: Run and commit**

Run old Gemmi tests, reader conformance and catalog/capability tests; commit.

### Task 3: Support multiple blocks and robust source envelopes

**Files:**
- Modify: `ChemBlender/core/formats/cif.py`
- Modify: `ChemBlender/core/model/structure.py`
- Modify: `ChemBlender/core/model/project.py`
- Create: `tests/fixtures/cif/multi-block.cif`
- Create: `tests/fixtures/cif/quoted-loop.cif`
- Create: `tests/test_cif_blocks.py`

**Interfaces:**
- Produces: one CIFEnvelope per source document and block-local structure records with stable block keys.

- [ ] **Step 1: Write block-selection tests**

A two-block file produces two SourcePreview records. Quick default selects the first block containing a valid atom-site loop; no valid block yields a blocking diagnostic but preserves source metadata.

- [ ] **Step 2: Preserve raw document and block identity**

CIFEnvelope stores original bytes, source hash, block names and complete tag names. Each structure references envelope ID and block name/index. Duplicate block names receive deterministic source-local keys with diagnostics.

- [ ] **Step 3: Exercise quoting and loops**

Fixtures include quoted values, multiline text, uncertainty notation and loop values containing spaces. Tests assert Gemmi-derived values rather than hand-tokenized results.

- [ ] **Step 4: Run and commit**

Run block, envelope, sidecar and import preview tests; commit.

### Task 4: Map sites, occupancy, disorder and ADP comprehensively

**Files:**
- Modify: `ChemBlender/core/formats/cif.py`
- Modify: `ChemBlender/core/model/structure.py`
- Create: `tests/test_cif_site_data.py`
- Add: public fixtures for partial occupancy, disorder and mixed Uiso/Uij.

**Interfaces:**
- Produces: complete `PeriodicSiteData`, atom/site categorical identities and quality diagnostics.

- [ ] **Step 1: Add numeric uncertainty tests**

Values such as `1.234(5)` normalize to 1.234 and preserve the original token/uncertainty in envelope metadata or diagnostic detail. Missing `.`/`?` maps to missing values, not zero.

- [ ] **Step 2: Map coordinate alternatives**

Prefer fractional coordinates when cell exists. If only Cartesian coordinates exist, store them and derive fractional coordinates with provenance when cell is non-singular. Conflicting coordinate sets produce Ambiguous diagnostic.

- [ ] **Step 3: Map occupancy/disorder**

Occupancy defaults are applied only when CIF convention permits and the action is diagnosed. Disorder group/assembly values use categorical/integer data; partial occupancy remains source data.

- [ ] **Step 4: Map ADP**

Support Uiso/Ueq and complete Uij rows. Partial six-component rows are Invalid for that atom's anisotropic dataset and represented as missing; structure remains. B factors are converted to U only through an explicit conversion operation and provenance.

- [ ] **Step 5: Run and commit**

Run site/ADP and legacy CIF fixture regression tests; commit.

### Task 5: Separate declared and derived symmetry in UI/data

**Files:**
- Modify: `ChemBlender/core/model/structure.py`
- Modify: `ChemBlender/core/spglib_adapter.py`
- Create: `ChemBlender/core/symmetry_comparison.py`
- Create: `tests/test_symmetry_comparison.py`
- Modify: `ChemBlender/ui/properties.py`

**Interfaces:**
- Produces: `DeclaredSymmetry`, `compare_symmetry()` and optional spglib action.

- [ ] **Step 1: Preserve declared fields independently**

Declared name, IT number, Hall symbol and operations are source fields. They remain even when inconsistent or incomplete, with diagnostics.

- [ ] **Step 2: Update spglib derivation**

Optional action takes explicit symprec/angle tolerance and returns SymmetryResult + standardized Structure. It never changes the source structure/envelope.

- [ ] **Step 3: Implement comparison**

Return match, equivalent-after-setting, different or insufficient-data status plus details. Do not claim setting equivalence without an explicit transformation.

- [ ] **Step 4: UI and tests**

Properties show Declared and Derived sections. With spglib missing, Derive button is disabled with dependency reason while all CIF data remains usable.

- [ ] **Step 5: Commit**

Run optional/no-optional paths and commit.

### Task 6: Implement controlled CIF export

**Files:**
- Create: `ChemBlender/core/exporters/cif.py`
- Create: `tests/test_cif_exporter.py`
- Create: `tests/test_cif_controlled_roundtrip.py`
- Create: `docs/quantum-visualization/2.3.0/specs/cif-export-policy.md`

**Interfaces:**
- Produces: `plan_cif_export()`, `export_cif()` and field-level ExportReport.

- [ ] **Step 1: Write unchanged-envelope test**

Exporting an unchanged source structure in Preserve mode yields semantically equivalent blocks and preserves unknown custom loop/tag values.

- [ ] **Step 2: Implement patch plan**

Known patchable fields: cell, selected atom-site coordinates, element/label, occupancy, Uiso/Uij and declared symmetry when explicitly edited. The plan lists preserve/replace/add/omit before writing.

- [ ] **Step 3: Implement normalized-new mode**

A derived structure without envelope exports a new documented minimal CIF. It does not fabricate source uncertainty, disorder or symmetry.

- [ ] **Step 4: Round-trip tests**

Parse exported files with Gemmi and compare patched semantics. Unknown source content remains in Preserve mode.

- [ ] **Step 5: Commit**

Commit exporter, tests and policy.

### Task 7: Add CIF product flow and lifecycle smoke

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/`
- Modify: `tests/blender_smoke.py`
- Create: `tests/test_cif_product_flow.py`
- Create: `docs/quantum-visualization/2.3.0/benchmarks/gemmi-package-baseline.md`

**Interfaces:**
- Produces: CIF block selection, site/ADP view controls, save/reopen/export and wheel evidence.

- [ ] **Step 1: Add Preview details**

Display blocks, atom/site counts, cell, occupancy/ADP quality and declared symmetry. Multiple valid blocks require explicit selection or default confirmation.

- [ ] **Step 2: Add browser/property controls**

Site labels, occupancy, disorder and ADP datasets are visible. The default crystal view uses source asymmetric unit and cell.

- [ ] **Step 3: Extend Blender smoke**

Official ZIP imports a partial-disorder CIF with Gemmi, creates crystal view, saves/reopens, exports controlled CIF and verifies no spglib import.

- [ ] **Step 4: Measure wheel/package**

Record Gemmi import time, parse time, compressed/unpacked wheel size and total artifact delta. Run enable/disable twice.

- [ ] **Step 5: Commit and update Wave evidence**

Commit UI/smoke/benchmark and record the base dependency gate.
