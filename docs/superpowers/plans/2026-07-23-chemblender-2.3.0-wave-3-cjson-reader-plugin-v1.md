# ChemBlender 2.3.0 Wave 3 CJSON and Reader API v1 Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete lightweight CJSON exchange, publish Reader API v1 documentation/conformance, and prove the API with a separately installable example reader extension.

**Architecture:** Existing CJSON adapter migrates to the public Reader API and current project models while preserving raw envelope. The example reader lives as a separate extension source under examples/release artifacts and is not part of the base runtime. Its Blender registration bootstrap resolves the versioned API handle from `bpy.app.driver_namespace`; its reader business module imports no `bpy` and receives the dynamically resolved public API module.

**Tech Stack:** Python 3.13 JSON, Blender Extension manifest, Reader API v1, standard-library `unittest`, Blender lifecycle tests.

## Global Constraints

- No breaking Reader API change after beta.1 freeze.
- CJSON is lightweight exchange; large arrays remain in `.cbq` or are explicitly omitted/referenced.
- Example plugin cannot import private `ChemBlender.core` modules.
- Plugin errors or missing plugin cannot block ChemBlender registration or sidecar reopening.
- Conformance results are machine-readable and documented.

---

### Task 1: Adapt CJSON reader/exporter to the current public model

**Files:**
- Modify: `ChemBlender/core/cjson_adapter.py` or split into `ChemBlender/core/formats/cjson.py` and `ChemBlender/core/exporters/cjson.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `tests/test_cjson_adapter.py`
- Create: `tests/test_cjson_product_flow.py`

**Interfaces:**
- Produces: built-in Reader API v1 CJSON reader and lightweight exporter.

- [ ] **Step 1: Lock supported CJSON field matrix**

Tests cover atoms, coordinates, bonds/orders, charges, unit cell, trajectories/conformers, scalar atom properties, vibrations/spectra references supported by current implementation and raw unknown envelope fields.

- [ ] **Step 2: Map to new entities**

Use TopologyRecord, ConformerSet/FrameSet, categorical identity and SourceRevision. Existing envelopes migrate and remain readable.

- [ ] **Step 3: Define large-data export behavior**

CJSON export may include small arrays under a configured byte threshold. Larger Grid3D/orbital arrays are omitted with stable artifact references only when the receiving contract supports them; otherwise ExportReport lists omission. Never embed NPY/base64 silently.

- [ ] **Step 4: Product flow test**

Import CJSON, create view, save/reopen, export, parse export and compare lightweight semantics.

- [ ] **Step 5: Commit**

Run CJSON, sidecar, reader conformance and flow tests; commit.

### Task 2: Finalize Reader API v1 public documentation

**Files:**
- Modify: `ChemBlender/reader_api/version.py`
- Create: `docs/reader-api-v1/README.md`
- Create: `docs/reader-api-v1/manifest.md`
- Create: `docs/reader-api-v1/python-api.md`
- Create: `docs/reader-api-v1/worker-api.md`
- Create: `docs/reader-api-v1/diagnostics.md`
- Create: `docs/reader-api-v1/compatibility.md`
- Modify: `docs/README.md`

**Interfaces:**
- Produces: stable v1 imports, manifest schema, execution modes and compatibility policy.

- [ ] **Step 1: Generate the public symbol list**

Source-tree tests import every documented symbol from `ChemBlender.reader_api` and assert `__all__` exactness. Installed-extension documentation uses the API-handle bootstrap and never hardcodes `bl_ext.user_default` or imports `ChemBlender.core.model.*`.

- [ ] **Step 2: Document lifecycle**

Explain discovery, availability, sniff, parse, progress/cancel, diagnostics, canonical artifacts, exception isolation and sidecar behavior when plugins are missing.

- [ ] **Step 3: Document compatibility**

Same major preserves required fields and behavior; optional fields may be added; deprecations last at least two formal minor releases; incompatible plugin is disabled with diagnostic.

- [ ] **Step 4: Run docs tests and commit**

Add local-link/no-BOM tests and commit.

### Task 3: Build a standalone example Reader Extension

**Files:**
- Create: `examples/reader-extension/README.md`
- Create: `examples/reader-extension/blender_manifest.toml`
- Create: `examples/reader-extension/__init__.py`
- Create: `examples/reader-extension/reader.py`
- Create: `examples/reader-extension/LICENSE`
- Create: `examples/reader-extension/tests/test_reader.py`
- Create: `tests/test_example_reader_boundary.py`

**Interfaces:**
- Produces: `org.chemblender.example.simplecoords` plugin reading `.cbsimple`.

- [ ] **Step 1: Define the example format**

```text
CBSIMPLE 1
units angstrom
atoms 3
O 0.0 0.0 0.0
H 0.7 0.0 0.5
H -0.7 0.0 0.5
```

The reader returns one Structure and source diagnostic report.

- [ ] **Step 2: Implement only public imports**

Static tests walk AST and reject imports whose module starts with `ChemBlender.core`, `ChemBlender.ui` or `ChemBlender.views`. `reader.py` cannot import `bpy`; only `__init__.py`/bootstrap may import `bpy` and `importlib` to obtain `bpy.app.driver_namespace["chemblender.reader_api.v1"]`, import `handle.module_name`, and call the official registration callback.

- [ ] **Step 3: Add manifest and fixture tests**

Run API manifest validation, sniff, parse, canonical round-trip and cancellation tests.

- [ ] **Step 4: Build/install in Blender**

Package the example separately, install after ChemBlender, import fixture, disable/uninstall plugin, reopen saved `.cbq` and confirm view/data remain accessible while reparse is unavailable.

- [ ] **Step 5: Commit**

Commit example and tests; base ChemBlender ZIP excludes examples.

### Task 4: Publish the Reader API v1 conformance kit

**Files:**
- Modify: `ChemBlender/reader_api/conformance.py`
- Create: `ChemBlender/reader_api/conformance_cli.py`
- Create: `tests/test_reader_conformance_v1.py`
- Create: `docs/reader-api-v1/conformance.md`

**Interfaces:**
- Produces: CLI and JSON result schema.

- [ ] **Step 1: Define conformance result document**

Fields: API version, plugin ID/version, reader ID/version, case IDs, pass/fail/skip, duration, fixture hashes, diagnostics and environment. Skips require an explicit optional-case reason; required cases cannot skip.

- [ ] **Step 2: Extend checks**

Validate deterministic sniff, prefix bound, source identity, quality/diagnostics, reference integrity, canonical round-trip, artifact security, progress monotonicity, cancellation, exception isolation and declared capabilities.

- [ ] **Step 3: Add CLI**

```text
python -m ChemBlender.reader_api.conformance_cli --plugin-path examples/reader-extension --fixtures examples/reader-extension/fixtures --output conformance-result.json
```

The CLI imports the plugin in a subprocess for isolation and returns nonzero if a required case fails.

- [ ] **Step 4: Run built-in and example suites**

All built-in Wave 1–3 readers and the example plugin produce passing results. Store summary in beta.2 evidence, not generated runtime artifacts in Git unless stable fixtures are intended.

- [ ] **Step 5: Commit**

Commit conformance implementation/docs/tests.

### Task 5: Verify plugin discovery and failure isolation in Blender

**Files:**
- Modify: `ChemBlender/reader_api/discovery.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `tests/blender_smoke.py`
- Create: `tests/test_plugin_discovery.py`

**Interfaces:**
- Produces: discovery refresh, plugin state UI and isolated failures.

- [ ] **Step 1: Write discovery tests**

Discover built-in readers and registered extension plugins by explicit hook/registry, not scanning arbitrary `sys.path`. Duplicate plugin/reader IDs are rejected per plugin and reported.

- [ ] **Step 2: Add refresh lifecycle**

Extension enable registers its reader; disable unregisters it. ChemBlender refreshes registry without re-registering Blender classes. A failing plugin callback becomes an unavailable plugin diagnostic.

- [ ] **Step 3: Blender smoke**

Install good and intentionally failing test plugins. Main extension remains enabled, good reader works, failing reader is visible/unavailable, all unregister cleanly.

- [ ] **Step 4: Commit and beta.2 gate**

Run full Reader API v1, example plugin, Blender lifecycle and Wave 3 format tests. Commit final compatible API additions.
