# ChemBlender 2.3.0 Wave 4 Documentation and Final Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align all user/developer documentation, capability claims, migration notes, changelog and release evidence with the actual verified 2.3.0 product, then prepare RC and final exact-tag releases.

**Architecture:** Documentation is generated from or tested against reader descriptors, dependency inventory and schemas where possible. Claims use the maturity model and link to fixture/test evidence. Release notes come only from CHANGELOG and exact tag source.

**Tech Stack:** Markdown, JSON, Python standard-library documentation tests, GitHub Actions release workflow.

## Global Constraints

- No claim exceeds live verification evidence.
- “Supported” includes maturity/loss/dependency, not a bare boolean.
- RC documentation may only change for fixes/clarity, not new feature scope.
- Root README, manifest tagline, website-facing text and changelog are consistent.
- Publishing requires explicit authorization.

---

### Task 1: Replace the old product description and add user guides

**Files:**
- Modify: `README.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Create: `docs/user/quick-import.md`
- Create: `docs/user/project-browser.md`
- Create: `docs/user/project-sidecar.md`
- Create: `docs/user/data-quality.md`
- Create: `docs/user/scientific-editing.md`
- Create: `docs/user/formats.md`
- Modify: `docs/README.md`
- Modify: docs tests.

**Interfaces:**
- Produces: complete base user workflow and accurate tagline.

- [ ] **Step 1: Write documentation contract tests**

Assert root README contains program-neutral/result-first positioning, base format list, Windows/Blender requirements, sidecar warning and optional backend distinction. Assert manifest tagline length/format accepted by Blender.

- [ ] **Step 2: Write Quick Import and Browser guides**

Include single/multi/drop flows, Import Preview decisions, By Source/By Data, quality badges, default views and cancel behavior.

- [ ] **Step 3: Write sidecar/recovery guide**

Explain session project, save location, relative link, missing/mismatch/incompatible states, backup and cache clearing. Warn users to keep `.blend` and `.cbq` together.

- [ ] **Step 4: Write scientific editing/topology guide**

Distinguish view transforms and scientific edits, source vs derived structure, explicit/inferred topology and result validity.

- [ ] **Step 5: Run and commit**

Run docs links/no-BOM/content tests and commit.

### Task 2: Publish machine-derived format and dependency documentation

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Create: `ChemBlender/scripts/generate_format_docs.py`
- Create: `docs/user/format-capabilities.json`
- Create: `docs/user/dependencies.json`
- Modify: `docs/user/formats.md`
- Create: `tests/test_generated_docs_fresh.py`

**Interfaces:**
- Produces: deterministic docs generated from live descriptors and dependency inventory.

- [ ] **Step 1: Extend reader capability document**

Include plugin/execution mode, extensions/basenames, import capabilities, export maturity, loss policy, fixture families and Reader API version. Availability remains runtime, not baked as always true.

- [ ] **Step 2: Generate JSON and Markdown table**

Script writes canonical JSON and a marked section in formats.md. Running twice is byte-identical.

- [ ] **Step 3: Add freshness test**

Test regenerates in memory and compares tracked files. A reader change without docs update fails.

- [ ] **Step 4: Commit**

Commit generator, generated files and tests.

### Task 3: Complete developer and plugin documentation

**Files:**
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `.agents/README.md`
- Create: `docs/development/import-pipeline.md`
- Create: `docs/development/source-revisions.md`
- Create: `docs/development/testing-fixtures.md`
- Create: `docs/development/release-2.3.md`
- Finalize: `docs/reader-api-v1/`

**Interfaces:**
- Produces: current architecture, contribution and release documentation.

- [ ] **Step 1: Audit every source module responsibility**

Architecture guide's automated path set must exactly match all Python files. Document public entrypoints and dependency direction, not every helper.

- [ ] **Step 2: Document adding a built-in reader**

Reader manifest/descriptor, fixture provenance, diagnostics, public batch, exporter/loss, conformance, UI and capability docs.

- [ ] **Step 3: Document external reader and worker reader**

Use the example plugin and conformance CLI. Include security prohibitions and compatibility policy.

- [ ] **Step 4: Run and commit**

Run all docs tests and commit.

### Task 4: Write migration and upgrade documentation

**Files:**
- Create: `docs/migration/2.3.0.md`
- Create: `docs/user/legacy-migration.md`
- Modify: `docs/migration/2.2.0-extension.md`
- Create: `tests/test_migration_docs.py`

**Interfaces:**
- Produces: 2.2→2.3 installation, sidecar/schema and old-scene instructions.

- [ ] **Step 1: Cover extension upgrade**

Windows DLL lock/cold process, official ZIP/checksum, current project backup and rollback to 2.2.

- [ ] **Step 2: Cover sidecar schema**

Opening v0.1/v0.2, automatic in-memory migration, save-as v1, backup generation and incompatibility behavior.

- [ ] **Step 3: Cover legacy wizard**

Detection, preview, backup collection, source absence, diagnostics and rollback.

- [ ] **Step 4: Test and commit**

Docs tests assert required safety statements and links; commit.

### Task 5: Prepare RC changelog and release evidence

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Create: `.agents/completed/2.3.0-rc-readiness.md`
- Modify: active Wave 4 task.

**Interfaces:**
- Produces: exact RC version metadata and complete evidence record.

- [ ] **Step 1: Build changelog from verified features only**

Categories: Added, Changed, Fixed, Compatibility, Migration, Known Limitations, Verification. Include format maturity and optional dependency boundaries.

- [ ] **Step 2: Set RC version under proven scheme**

Manifest version, changelog heading, package metadata and intended tag agree. Do not tag yet.

- [ ] **Step 3: Run the full RC gate**

Native, optional, Blender, legacy, performance, size/license, docs and release dry-run. Record test counts, skipped tests, package hash/size, wheel inventory and exact commands.

- [ ] **Step 4: Commit RC metadata**

Commit only after local gates pass. Tag/push/package CI/pre-release publication need authorization.

### Task 6: Process RC feedback under scope freeze

**Files:**
- Modify: affected code/tests/docs only
- Modify: `CHANGELOG.md`
- Modify: RC readiness record.

**Interfaces:**
- Produces: release-blocker fixes with regression evidence.

- [ ] **Step 1: Triage by defined severity**

Data corruption, scientifically wrong mapping, crash, project loss/recovery failure and core workflow failure block final. Feature requests are queued for later.

- [ ] **Step 2: Apply systematic debugging and TDD**

Each fix begins with a reproducing test/fixture and focused commit. Do not bundle unrelated cleanup.

- [ ] **Step 3: Re-run impacted gates and full final gate**

Update evidence; no unresolved blocker remains.

### Task 7: Prepare and verify final 2.3.0 release

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Create: `.agents/completed/2.3.0-release-readiness.md`
- Update: roadmap and queued/active state.

**Interfaces:**
- Produces: exact final tag commit ready for authorized publication.

- [ ] **Step 1: Change RC metadata to final**

Use `2.3.0`, dated changelog entry and final known limits. Remove prerelease labels without adding features.

- [ ] **Step 2: Run full local release sequence**

All required tests and installs pass from a clean state. Verify package contents and hashes with the final version.

- [ ] **Step 3: Create annotated tag and obtain exact package CI only with authorization**

Wait for exactly one successful exact-tag package run and unexpired artifact.

- [ ] **Step 4: Run release workflow with `publish=false`**

Verify exact artifact, notes, digests, size/inventory/licenses and final tag ancestry.

- [ ] **Step 5: Publish only with separate authorization**

Dispatch `publish=true`; verify release is not draft/prerelease, is latest, has expected assets and matching digests.

- [ ] **Step 6: Record completion**

Move active task to completed, keep known limitations, update roadmap maturity to Release-qualified only where evidence exists, and run `git diff --check`/clean worktree confirmation.
