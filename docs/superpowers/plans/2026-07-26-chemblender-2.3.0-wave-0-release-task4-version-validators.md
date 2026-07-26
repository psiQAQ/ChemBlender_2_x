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

- [x] **Step 1: Add parser RED cases**

Test the four valid examples and invalid grammar including `2.3.0-alpha`,
`2.3.0-alpha.`, `2.3.0-alpha.0`, `2.3.0-preview.1`, `v2.3.0`,
`02.3.0`, whitespace, control and separators.

- [x] **Step 2: Run RED**

Run release metadata tests; expect import/attribute failures for the absent parser.

- [x] **Step 3: Implement one anchored parser**

Use one compiled regex and return the parsed immutable value. Make
`read_release_metadata()` call it after filename-safety validation.

---

### Task 2: Changelog extraction consumes shared parser

**Files:**
- Modify: `ChemBlender/scripts/extract_release_notes.py`
- Modify: `tests/test_release_notes.py`

- [x] **Step 1: Add prerelease heading RED tests**

Accept exactly one dated `## [2.3.0-alpha.1] - YYYY-MM-DD` entry and reject
invalid/duplicate/missing/empty entries.

- [x] **Step 2: Replace local version regex**

Use direct/module dual-mode import of `parse_release_version`; retain exact
escaped heading matching and UTF-8/LF output.

---

### Task 3: Extension validator consumes shared parser

**Files:**
- Modify: `ChemBlender/scripts/validate_extension.py`
- Create or modify: `tests/test_validate_extension.py`

- [x] **Step 1: Add valid/invalid manifest RED tests**

Call the local validator boundary with stable and three prerelease examples;
invalid grammar must be a validation error, not only a warning.

- [x] **Step 2: Remove `SEMVER_PATTERN`**

Import the shared parser in direct/module modes. Convert parser failure into
one precise manifest-version validation error while preserving all unrelated
preflight/native validation behavior.

---

### Task 4: Artifact verifier consumes shared parser

**Files:**
- Modify: `ChemBlender/scripts/verify_release_artifact.py`
- Modify: `tests/test_release_artifact.py`

- [x] **Step 1: Add prerelease tag RED cases**

Accept `v2.3.0-alpha.1` when metadata matches and reject leading/missing `v`,
unsupported/malformed prerelease tags and tag/manifest mismatch.

- [x] **Step 2: Remove duplicate tag regex**

Require a leading `v`, parse the remainder with `parse_release_version`, and
compare its exact value with metadata. Keep checksum/ZIP contracts unchanged.

---

### Task 5: Regression, review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

- [x] **Step 1: Run focused/full verification**

Run metadata, notes, local validator and artifact tests, full `unittest`,
`compileall` and `git diff --check`.

- [x] **Step 2: Stable and disposable prerelease verification**

Re-run stable metadata/artifact fixtures and the disposable Blender prerelease
probe. Production manifest must remain unchanged.

- [x] **Step 3: Independent review and commit**

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

- State: `completed`
- Baseline: `584486c5397b06e086da41515462b293697b242f`
- Planning commit: `e06293e040716c03cf6115a8017a680e51085309`
- Implementation commit: `4b2d26509b09c1f233dc64e8727b3de2c48fa8c4`
- Review-fix commit: `c16680af5fea9705d6b93ab42c710d31a7ce0ad1`
- Shared parser source: `ChemBlender/scripts/release_metadata.py`
- RED evidence:
  focused 20 tests produced 9 failures and 3 errors for missing shared APIs and
  legacy consumer behavior; review regression then produced 6 Unicode-digit
  subtest failures.
- GREEN evidence:
  focused 62 Passed and 1 Skipped; full 985 Passed, 28 Skipped and 0 Failed;
  review-fix targeted 3/3 and consumer 39/39 Passed; compileall/diff-check
  Passed.
- Stable regression: `Passed`
- Prerelease probe regression: `Passed`; Blender 5.1.2 exit 0.
- Duplicate parser audit:
  one shared anchored ASCII regex; legacy metadata/notes/validator/tag regexes
  removed.
- Independent review:
  Unicode-digit Important fixed and scoped re-review `ADDRESSED`; no remaining
  findings.
- Remote CI: `Not Run`
- Next task: `Task 5 — Add prerelease-aware release workflow behavior`
