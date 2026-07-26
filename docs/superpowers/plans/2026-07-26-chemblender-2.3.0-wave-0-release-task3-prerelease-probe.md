# ChemBlender 2.3.0 Wave 0 Release Task 3 Prerelease Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove with Blender 5.1.2 native validation whether `2.3.0-alpha.1` is an accepted extension manifest version without editing the production manifest.

**Architecture:** A standard-library probe copies the extension into a temporary directory, excludes local build outputs, changes exactly one manifest version assignment, invokes Blender native `extension validate`, captures deterministic evidence and removes the copy. A committed development note records the actual executable, version, command and result.

**Tech Stack:** Python 3.13 standard library, `tempfile`, `shutil`, `subprocess`, `tomllib`, Blender 5.1.2 native extension CLI, `unittest`.

## Global Constraints

- Baseline: `75e2fa01e4a50b33fabdaec37a4202d2da24c12f`.
- Probe version exactly `2.3.0-alpha.1`.
- The production `ChemBlender/blender_manifest.toml` stays byte-identical.
- Do not modify workflows, changelog, production manifest version or release validators.
- Do not create a tag, artifact publication, Release or push during this task.
- Do not add dependencies.
- If the real native probe fails, stop Tasks 4–6 and record the observed failure before selecting a replacement scheme.

---

### Task 1: Safe disposable manifest copy

**Files:**
- Create: `ChemBlender/scripts/probe_prerelease_version.py`
- Create: `tests/test_prerelease_probe_script.py`

**Interfaces:**
- Produce: `probe_prerelease_version(extension_root, blender, version) -> dict[str, object]`.
- Produce CLI accepting `--extension-root`, `--blender`, and optional `--version`.

- [ ] **Step 1: Write copy-safety RED tests**

Assert the script is missing, then cover:

- production manifest bytes remain exact;
- temporary manifest changes exactly one `version = "..."` assignment;
- source build ZIP/checksum, `__pycache__`, `.git` and local wheel directory are excluded;
- malformed/multiple/missing version assignments fail before subprocess;
- temporary root is removed on success and failure.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_prerelease_probe_script -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the minimal safe probe**

Use `TemporaryDirectory`, `shutil.copytree`, an anchored text replacement and
`subprocess.run(..., capture_output=True, text=True, check=False)`. Invoke:

```text
<blender> --command extension validate <temporary-extension-root>
```

Return the command, version, exit code, stdout and stderr. CLI emits sorted JSON
and returns Blender's nonzero status as failure.

---

### Task 2: Real Blender 5.1.2 probe

**Files:**
- Create: `docs/development/2.3.0-prerelease-version-probe.md`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

- [ ] **Step 1: Run Blender preflight**

Confirm Blender `5.1.2`, Windows executable and native CLI availability.

- [ ] **Step 2: Run the real probe**

Use the MCP-confirmed executable:

```text
C:\Program Files\Blender Foundation\Blender 5.1\blender.exe
```

Record exact command, exit code, stdout/stderr, source manifest SHA-256 before
and after, and whether the temporary directory was cleaned.

- [ ] **Step 3: Commit observed evidence**

The document must say `Passed` only if native exit code is 0. It must clearly
separate local evidence from Remote CI (`Not Run`).

---

### Task 3: Regression, review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

- [ ] **Step 1: Run focused/full verification**

Run probe/release metadata/documentation tests, full `unittest`, `compileall`
and `git diff --check`.

- [ ] **Step 2: Independent review**

Review source immutability, copy exclusions, command construction, temp cleanup,
exit propagation and evidence accuracy. Fix all Critical, Important and
task-related Minor findings.

- [ ] **Step 3: Commit and checkpoint**

Implementation commit:

```text
test: probe Blender prerelease manifest support
```

If native probe passes, next task is:

```text
Task 4 — Extend changelog and release validators for the proven scheme
```

---

## Completion checkpoint

- State: `in_progress`
- Baseline: `75e2fa01e4a50b33fabdaec37a4202d2da24c12f`
- Planning commit: pending
- Implementation commit: pending
- Probe version: `2.3.0-alpha.1`
- Native Blender result: `Not Run`
- Production manifest unchanged: `Not Run`
- Remote CI: `Not Run`
- Next task: conditional on native probe
