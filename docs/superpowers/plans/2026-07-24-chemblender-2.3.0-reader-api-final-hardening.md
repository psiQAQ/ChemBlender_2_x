# ChemBlender Reader API Tasks 3–7 Final Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`
> and apply test-driven development.

**Goal:** Close every Critical, Important, and directly related Minor finding
from the frozen Tasks 3–7 review before the authorized branch push.

**Architecture:** Keep the existing canonical-document, public-batch, worker,
Blender-handle, and conformance boundaries. Expose the exact sniff result types
required by the public protocol, reject non-canonical nested public data,
require honest source-identity evidence, and make filesystem publication
failures atomic and API-stable.

**Tech Stack:** Python 3.13 standard library, existing Reader API 0.x and worker
protocol, `unittest`.

## Constraints

- Do not add dependencies, pickle, dynamic source-tree imports, or a second
  scientific model/enum class.
- Do not enter Registration/UI, Release Groundwork, or Wave 1–4.
- Do not change the Reader API version or canonical document schema.
- Write a failing regression test before each implementation change.
- Preserve the existing successful XYZ/Cube conformance and worker lifecycle.

## Task 1: Close the public protocol and public-batch trust boundary

**Files:**
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `ChemBlender/reader_api/public_model.py`
- Modify: `ChemBlender/reader_api/builtin_bridge.py`
- Modify: `tests/test_reader_plugin_manifest.py`
- Modify: `tests/test_public_import_batch.py`

- [x] Re-export the exact core `SniffMatch` and `SniffResult` classes from the
  dynamically resolved Reader API facade.
- [x] Prove a synthetic installed-namespace plugin can implement `sniff()`
  using only the resolved public module.
- [x] Recursively reject callable, mutable, or unregistered nested values at
  the public-to-internal batch boundary while preserving approved immutable
  scientific values and no-copy array behavior.

## Task 2: Require complete conformance identity evidence

**Files:**
- Modify: `ChemBlender/reader_api/conformance.py`
- Modify: `tests/test_reader_conformance.py`
- Modify: `docs/quantum-visualization/2.3.0/reader-api-0.x.md`

- [x] Reject incomplete or contradictory provenance when a reader returns no
  `SourceRevision`.
- [x] Preserve built-in XYZ/Cube conformance only for identity evidence that
  actually binds the selected reader, version, source hash, validation mode,
  and canonical parameters.
- [x] Document the exact source-identity evidence required by alpha
  conformance.

## Task 3: Make artifact publication failures atomic and stable

**Files:**
- Modify: `ChemBlender/reader_api/canonical_document.py`
- Modify: `worker/reader_operation.py`
- Modify: `worker/runner.py`
- Modify: `tests/test_reader_canonical_document.py`
- Modify: `tests/test_worker_reader_operation.py`
- Modify: `tests/test_worker_protocol.py`

- [x] Convert post-write hashing and cleanup filesystem errors to stable
  canonical-document errors.
- [x] If worker result publication fails after creating the operation bundle,
  remove only that operation-created bundle and preserve the original failure.
- [x] Prove a retry is not blocked by a stale bundle.

## Task 4: Review, verify, checkpoint, and push

- [x] Update the exact public `__all__` contract, architecture guide, and
  execution cursor where responsibilities or public entry points changed.
- [x] Run focused tests, full discovery, compileall, optional-import isolation,
  `git diff --check`, and final worktree inspection.
- [x] Obtain independent specification and code-quality approval.
- [x] Commit implementation and checkpoint separately.
- [x] Push the feature branch once and verify the remote SHA equals local HEAD
  `32b26bb4508a29d3ac0763256869fb9e8daac5f4`.
