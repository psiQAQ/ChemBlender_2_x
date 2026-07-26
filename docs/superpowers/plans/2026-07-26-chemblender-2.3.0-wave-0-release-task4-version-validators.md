# ChemBlender 2.3.0 Wave 0 Release Task 4 Version Validators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one strict parser own the Blender-proven stable/alpha/beta/rc version scheme across metadata, changelog extraction, extension validation and artifact verification.

**Architecture:** `release_metadata.py` exposes a frozen parsed-version value and one `parse_release_version()` function for the supported SemVer subset. Metadata validation, release-note extraction, local extension validation and tag artifact verification import it; duplicate version regexes are removed.

**Tech Stack:** Python 3.13 standard library, `re`, `dataclasses`, `unittest`.

## Global Constraints

- Baseline: `584486c5397b06e086da41515462b293697b242f`.
- Blender 5.1.2 native probe proved `2.3.0-alpha.1`.
- Valid examples: `2.3.0`, `2.3.0-alpha.1`, `2.3.0-beta.2`, `2.3.0-rc.1`.
- Supported prerelease channels are exactly `alpha`, `beta`, `rc`.
- Numeric identifiers use canonical decimal form: `0` or a nonzero digit followed by digits; prerelease sequence starts at 1.
- Reject missing numeric prerelease sequence, spaces, leading `v`, control/path-unsafe characters, unsupported channels and leading-zero numeric identifiers.
- Do not modify the production manifest, changelog content or workflows in this task.
- No tag, Release, publish, remote CI or push during this task.

---

### Task 1: Shared parsed release version

**Files:**
- Modify: `ChemBlender/scripts/release_metadata.py`
- Modify: `tests/test_release_metadata.py`

**Interfaces:**
- Produce: frozen, slotted `ParsedReleaseVersion`.
- Produce: `parse_release_version(value: str) -> ParsedReleaseVersion`.
- Parsed fields: exact `value`, `major`, `minor`, `patch`, `channel`,
  `channel_number`, `is_prerelease`.

- [ ] **Step 1: Add parser RED cases**

Test the four valid examples and invalid grammar including `2.3.0-alpha`,
`2.3.0-alpha.`, `2.3.0-alpha.0`, `2.3.0-preview.1`, `v2.3.0`,
`02.3.0`, whitespace, control and separators.

- [ ] **Step 2: Run RED**

Run release metadata tests; expect import/attribute failures for the absent parser.

- [ ] **Step 3: Implement one anchored parser**

Use one compiled regex and return the parsed immutable value. Make
`read_release_metadata()` call it after filename-safety validation.

---

### Task 2: Changelog extraction consumes shared parser

**Files:**
- Modify: `ChemBlender/scripts/extract_release_notes.py`
- Modify: `tests/test_release_notes.py`

- [ ] **Step 1: Add prerelease heading RED tests**

Accept exactly one dated `## [2.3.0-alpha.1] - YYYY-MM-DD` entry and reject
invalid/duplicate/missing/empty entries.

- [ ] **Step 2: Replace local version regex**

Use direct/module dual-mode import of `parse_release_version`; retain exact
escaped heading matching and UTF-8/LF output.

---

### Task 3: Extension validator consumes shared parser

**Files:**
- Modify: `ChemBlender/scripts/validate_extension.py`
- Create or modify: `tests/test_validate_extension.py`

- [ ] **Step 1: Add valid/invalid manifest RED tests**

Call the local validator boundary with stable and three prerelease examples;
invalid grammar must be a validation error, not only a warning.

- [ ] **Step 2: Remove `SEMVER_PATTERN`**

Import the shared parser in direct/module modes. Convert parser failure into
one precise manifest-version validation error while preserving all unrelated
preflight/native validation behavior.

---

### Task 4: Artifact verifier consumes shared parser

**Files:**
- Modify: `ChemBlender/scripts/verify_release_artifact.py`
- Modify: `tests/test_release_artifact.py`

- [ ] **Step 1: Add prerelease tag RED cases**

Accept `v2.3.0-alpha.1` when metadata matches and reject leading/missing `v`,
unsupported/malformed prerelease tags and tag/manifest mismatch.

- [ ] **Step 2: Remove duplicate tag regex**

Require a leading `v`, parse the remainder with `parse_release_version`, and
compare its exact value with metadata. Keep checksum/ZIP contracts unchanged.

---

### Task 5: Regression, review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

- [ ] **Step 1: Run focused/full verification**

Run metadata, notes, local validator and artifact tests, full `unittest`,
`compileall` and `git diff --check`.

- [ ] **Step 2: Stable and disposable prerelease verification**

Re-run stable metadata/artifact fixtures and the disposable Blender prerelease
probe. Production manifest must remain unchanged.

- [ ] **Step 3: Independent review and commit**

Review grammar consistency, duplicate parser removal, direct-script imports and
error classification. Implementation commit:

```text
feat: validate proven prerelease versions consistently
```

Next task:

```text
Task 5 — Add prerelease-aware release workflow behavior
```

---

## Completion checkpoint

- State: `in_progress`
- Baseline: `584486c5397b06e086da41515462b293697b242f`
- Planning commit: pending
- Implementation commit: pending
- Shared parser source: pending
- RED evidence: `Not Run`
- GREEN evidence: `Not Run`
- Stable regression: `Not Run`
- Prerelease probe regression: `Not Run`
- Remote CI: `Not Run`
- Next task: `Task 5 — Add prerelease-aware release workflow behavior`
