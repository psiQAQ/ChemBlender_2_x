# ChemBlender 2.3.0 Wave 0 Source, Session and Sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stable source/revision identity, session projects, atomic solidification, manifest-hash scene links and recovery states.

**Architecture:** Source entities live in QCProject. Mutable session state lives in a service outside frozen dataclasses. Temporary and persistent sidecars share the existing content-addressed NPY format, with a generation publication layer and explicit schema migration.

**Tech Stack:** Python 3.13, dataclasses, pathlib, hashlib, JSON, NPY, Blender Scene properties and handlers.

## Global Constraints

- Preserve reads of `.cbq` manifest version 0.1.
- Source locator is not scientific identity.
- No online installation or new dependency.
- Windows directory publication behavior must be tested.
- Scene link errors never delete existing Blender objects.
- Update architecture guide and sidecar specification in the same commits.

---

### Task 1: Add source and revision model types

**Files:**
- Create: `ChemBlender/core/model/sources.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model_registry.py`
- Modify: `ChemBlender/core/__init__.py`
- Create: `tests/test_source_model.py`
- Modify: `tests/test_model_registry.py`
- Modify: `tests/test_model_public_surface.py`
- Modify: `tests/test_core_public_api.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `SourceRecord`, `SourceRevision` and `source_parse_identity()`.

- [ ] **Step 1: Write failing source identity tests**

```python
import unittest
from uuid import uuid4
from ChemBlender.core import SourceRecord, SourceRevision, source_parse_identity


class SourceModelTests(unittest.TestCase):
    def test_parse_identity_ignores_locator(self):
        first = source_parse_identity("a" * 64, "builtin", "xyz", "2", (("mode", "balanced"),))
        second = source_parse_identity("a" * 64, "builtin", "xyz", "2", (("mode", "balanced"),))
        self.assertEqual(first, second)

    def test_source_revision_requires_sha256_and_nonnegative_size(self):
        with self.assertRaises(ValueError):
            SourceRevision(
                id=uuid4(), source_id=uuid4(), content_hash="bad", byte_size=-1,
                locator="file.xyz", locator_kind="path", original_filename="file.xyz",
                reader_plugin_id="chemblender.builtin", reader_id="xyz",
                reader_version="2", reader_api_version="0.1",
                import_parameters_hash="b" * 64, parse_identity="c" * 64,
                created_entity_ids=(), diagnostic_ids=(),
            )
```

- [ ] **Step 2: Verify failure**

Run `tests.test_source_model`; expect missing imports.

- [ ] **Step 3: Implement canonical identity and validation**

Build a dict with content hash, plugin ID, reader ID/version and canonical parameter pairs, serialize it with `json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)`, then hash the UTF-8 bytes with SHA-256. Validate all hash fields and locator kind tokens.

- [ ] **Step 4: Register and export the source types**

Add the source types to the explicit sidecar registry and stable `ChemBlender.core` façade. Update the exact registry, public-surface and architecture documentation contracts. Do not add source fields to `QCProject` until Task 2 can migrate v0.1 documents before strict field decoding.

- [ ] **Step 5: Run and commit**

```powershell
& $pythonBin -m unittest tests.test_source_model tests.test_model_registry tests.test_model_public_surface tests.test_core_public_api tests.test_sidecar_storage tests.test_quantum_visualization_docs -v
```

```bash
git add ChemBlender/core/model/sources.py ChemBlender/core/model/__init__.py ChemBlender/core/model_registry.py ChemBlender/core/__init__.py tests/test_source_model.py tests/test_model_registry.py tests/test_model_public_surface.py tests/test_core_public_api.py .agents/reference/code-architecture-guide.md
git commit -m "feat: add source revision identity"
```

### Task 2: Migrate sidecar schema while preserving v0.1 reads

**Files:**
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/sidecar.py`
- Create: `ChemBlender/core/sidecar_migrations.py`
- Modify: `docs/quantum-visualization/specs/cbq-sidecar-v0.1.md`
- Create: `docs/quantum-visualization/2.3.0/architecture/cbq-sidecar-v0.2.md`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_source_model.py`
- Modify: `tests/test_sidecar_storage.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: QCProject source registries, manifest version `0.2`, v0.1→v0.2 in-memory migration and explicit generation metadata.

- [ ] **Step 1: Write migration tests**

```python
def test_v01_project_migrates_to_current_in_memory(self):
    project = open_project(V01_FIXTURE)
    self.assertEqual(project.schema_version, "0.2")
    self.assertEqual(project.sources, {})
    close_project(project)

def test_unknown_manifest_version_is_rejected(self):
    with self.assertRaises(SidecarCompatibilityError):
        open_project(UNKNOWN_VERSION_FIXTURE)
```

- [ ] **Step 2: Implement a document migration before decode**

Add `sources` and `source_revisions` dicts to `QCProject` and source groups to `ImportBatch`. `QCProject.commit()` verifies revision source IDs and created entities in the final combined ID set. Until the later diagnostics plan adds an ID-bearing diagnostic registry, non-empty `SourceRevision.diagnostic_ids` are rejected as dangling references rather than accepted without validation.

`migrate_manifest(document)` accepts only known versions. For v0.1, add empty source registries to the encoded QCProject field set before strict dataclass decoding and change the manifest version. Do not invent diagnostic or view fields that are not present in the current `QCProject` model. Preserve project UUID and arrays.

- [ ] **Step 3: Add generation fields**

Manifest root includes `generation_id`, `created_at_utc`, `manifest_sha256` outside the hashed document or computed after canonicalization using a clearly documented two-pass method. `open_project` verifies the stored manifest hash.

- [ ] **Step 4: Verify and commit**

Run all sidecar, project link, cache and worker tests. Commit migration docs with code.

### Task 3: Implement ProjectSession and temporary roots

**Files:**
- Create: `ChemBlender/core/session.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `docs/quantum-visualization/2.3.0/public-core-api.md`
- Create: `tests/test_project_session.py`
- Modify: `tests/test_core_public_api.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `ProjectSession`, `create_session()`, `close_session()` and dirty-state operations.

- [ ] **Step 1: Write session lifecycle tests**

```python
def test_session_creates_and_removes_owned_temporary_root(self):
    session = create_session(temp_parent=self.tempdir)
    root = session.temporary_root
    self.assertTrue(root.is_dir())
    close_session(session, remove_temporary=True)
    self.assertFalse(root.exists())

def test_dirty_state_changes_only_after_project_mutation(self):
    session = create_session(temp_parent=self.tempdir)
    self.assertFalse(session.dirty)
    session.mark_dirty("import")
    self.assertTrue(session.dirty)
```

- [ ] **Step 2: Implement the service**

Use a mutable dataclass with project, temporary root, persistent sidecar path, dirty reasons, active IDs and link status. Temporary root names include a UUID and are always beneath the provided/Blender temp parent.

- [ ] **Step 3: Add cleanup protection**

`close_session` refuses to delete a path not marked with a session ownership file containing the matching UUID.

- [ ] **Step 4: Run and commit**

Run session, sidecar, public API, documentation and path traversal tests, then
commit the new module together with its architecture and façade contracts.

### Task 4: Implement atomic session solidification

**Files:**
- Create: `ChemBlender/core/storage/publication.py`
- Modify: `ChemBlender/core/sidecar.py`
- Create: `tests/test_sidecar_publication.py`

**Interfaces:**
- Produces: `solidify_session(session, destination) -> PublishedProject`.

- [ ] **Step 1: Write success and rollback tests**

Use a temporary destination. Patch the final verification function to fail and assert the previous destination manifest and arrays remain unchanged. On success, assert the reopened project UUID and manifest hash.

- [ ] **Step 2: Implement staged directory publication**

Write to a sibling hidden temp directory. Verify. On Windows, publish using a backup rename sequence with recovery in `finally`. Restrict destination suffix to `.cbq` and require same-volume staging.

- [ ] **Step 3: Add orphan recovery**

A helper detects `.tmp` and `.backup` siblings and returns an explicit recovery report; it never deletes them without user action unless ownership and completed publication prove safety.

- [ ] **Step 4: Run and commit**

Run publication tests repeatedly to catch file-handle issues. Commit separately.

### Task 5: Store and verify manifest hash in Scene links

**Files:**
- Modify: `ChemBlender/project_link.py`
- Modify: `tests/blender_smoke.py`
- Create: `tests/test_project_link_pure.py`

**Interfaces:**
- Produces: `MANIFEST_HASH_KEY`, extended `write_project_link()` and hash-aware `resolve_project_link()`.

- [ ] **Step 1: Add pure link data tests**

Refactor locator/hash computation into pure helpers. Test relative locator and hash mismatch without importing `bpy`.

- [ ] **Step 2: Add Scene key**

```python
MANIFEST_HASH_KEY = "cbq_manifest_sha256"
```

`write_project_link` requires a verified sidecar and stores its manifest hash. `resolve_project_link` compares the current manifest before returning CONNECTED; mismatch returns `MISMATCH` with no scene mutation.

- [ ] **Step 3: Update Blender smoke**

Assert the key exists, resolves after save, and tampering returns INVALID/MISMATCH while marker objects remain.

- [ ] **Step 4: Verify and commit**

Run pure link, sidecar and Blender smoke before commit.

### Task 6: Add session save/relink/verify service operations

**Files:**
- Create: `ChemBlender/core/project_service.py`
- Create: `tests/test_project_service.py`
- Modify: `ChemBlender/core/__init__.py`

**Interfaces:**
- Produces: `save_project_session()`, `relink_project_session()`, `verify_project_session()`, `clear_derived_cache()`.

- [ ] **Step 1: Write operation tests**

Cover unsaved, connected, missing, mismatch, incompatible and invalid states. `clear_derived_cache` may remove only render/derivation caches, never source arrays or manifest.

- [ ] **Step 2: Implement operations using existing storage primitives**

Return typed result objects with status/message/path/hash; do not raise for expected missing/incompatible states.

- [ ] **Step 3: Verify and commit**

Run project service, sidecar, project link and cache tests. Update architecture guide and commit.
