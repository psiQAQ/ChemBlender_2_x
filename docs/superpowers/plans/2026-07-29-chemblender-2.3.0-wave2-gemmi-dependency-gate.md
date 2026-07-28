# ChemBlender 2.3.0 Wave 2 Gemmi Dependency Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Approve and lock the official Gemmi CPython 3.13 Windows x64 wheel
as the lazy CIF-adapter dependency without starting CIF product work.

**Architecture:** Reuse Blender Extension manifest wheels, the existing
package workflow and artifact inventory verifier. Gemmi stays behind the
existing function-local adapter import; no Gemmi object enters the project,
sidecar, canonical document or public Reader API.

**Tech Stack:** Python 3.13, Blender 5.1.2 Extensions, TOML, GitHub Actions,
standard-library `unittest`.

## Global Constraints

- Start from reviewed Wave 2 Pre-Gate SHA
  `b211ddc0316f854b5c960ba83cea7b35d7d84f00`.
- Pin one official, non-yanked `cp313-cp313-win_amd64` wheel and its SHA-256.
- Do not track wheel files, install into Blender's global Python or build from
  source.
- Do not add Gemmi to `pyproject.toml` or import it during extension enable,
  `ChemBlender.core` import or `ChemBlender.reader_api` import.
- Do not change scientific models, project/sidecar/canonical schemas, CIF
  parsing, POSCAR, crystal UI, symmetry expansion or export.
- Keep spglib optional and outside the extension ZIP.
- No push, PR, tag or Release without new explicit authorization.

---

### Task 1: Activate the Gemmi Dependency Gate

**Files:**

- Create:
  `docs/superpowers/plans/2026-07-29-chemblender-2.3.0-wave2-gemmi-dependency-gate.md`
- Modify: `.agents/active/2.3.0-wave-2-native-crystal.md`

**Interfaces:**

- Consumes: completed `W2-CRYSTAL-PRE-GATE`.
- Produces: one durable in-progress dependency-gate cursor.

- [x] **Step 1: Record live dependency evidence**

Record the exact official wheel filename, URL, SHA-256, compressed/unpacked
size, license file and Python/platform tags.

- [x] **Step 2: Commit plan and cursor**

```powershell
git add `
  docs/superpowers/plans/2026-07-29-chemblender-2.3.0-wave2-gemmi-dependency-gate.md `
  .agents/active/2.3.0-wave-2-native-crystal.md
git commit -m "docs: start Gemmi dependency gate"
```

**Commit boundary:** Plan and in-progress cursor only.

**Stop boundary:** No manifest, workflow or test change before this commit.

---

### Task 2: Lock the Official Wheel Contract

**Files:**

- Create: `tests/test_gemmi_dependency_contract.py`
- Modify: `tests/test_repository_contract.py`
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `ChemBlender/scripts/validate_extension.py`
- Modify: `.github/workflows/extension-package.yml`
- Modify: `.agents/decisions/0030-native-dependency-and-gemmi-boundary.md`
- Modify: `.agents/reference/dependencies-and-release.md`
- Modify:
  `docs/quantum-visualization/2.3.0/dependency-tier-matrix.md`

**Interfaces:**

- Declares:
  `./wheels/gemmi-0.7.5-cp313-cp313-win_amd64.whl`.
- Verifies:
  `ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d`.
- Preserves: exact manifest-declared wheel inventory and ignored binary policy.

- [x] **Step 1: Write RED contract tests**

Test the exact manifest entry, workflow URL/SHA, missing/extra/duplicate local
wheel rejection and absence of tracked wheels.

- [x] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest `
  tests.test_gemmi_dependency_contract `
  tests.test_repository_contract -v
```

Expected RED: Gemmi is absent from the manifest/workflow and local preflight
does not reject undeclared or duplicate wheel inventory.

- [x] **Step 3: Implement the minimum lock**

Add the exact wheel to the manifest, download and hash it in the existing
package job, make local preflight compare declared and present wheels, and
record the accepted supply-chain/license boundary. Do not add another
dependency configuration source.

- [x] **Step 4: Run focused GREEN**

Run the RED command plus validator and release-artifact tests.

**Commit boundary:** Wheel declaration, supply-chain policy and executable
packaging contracts.

**Stop boundary:** Do not edit the CIF adapter or reader catalog.

---

### Task 3: Prove Lazy Import and Blender Runtime Compatibility

**Files:**

- Modify: `tests/test_gemmi_dependency_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**

- `import ChemBlender.core` does not load `gemmi`.
- `import ChemBlender.reader_api` does not load `gemmi`.
- Extension enable does not load `gemmi`.
- Explicit post-enable `import gemmi` resolves version `0.7.5` from the
  manifest wheel under Blender bundled Python.

- [x] **Step 1: Add import-isolation tests**

Use fresh Python processes and `sys.modules` assertions; no source inspection
substitute.

- [x] **Step 2: Extend package smoke**

Require exactly the RDKit and Gemmi wheels, retain the enable-time optional
stack audit, then explicitly import Gemmi and verify version after install.

- [x] **Step 3: Run focused GREEN**

Run the dependency, core public API and repository contract tests.

**Blender verification:** Run native preflight, extension validate/build, ZIP
inventory/CRC audit and isolated install/lifecycle with Blender 5.1.2.

**Commit boundary:** Fold into the dependency implementation commit.

**Stop boundary:** Import/version smoke only; no CIF parse or UI operation.

---

### Task 4: Full Verification, Review and Checkpoint

**Files:**

- Modify: `.agents/active/2.3.0-wave-2-native-crystal.md`
- Modify:
  `docs/superpowers/plans/2026-07-29-chemblender-2.3.0-wave2-gemmi-dependency-gate.md`

**Interfaces:**

- Produces: reproducible local evidence and the next-task cursor.

- [x] **Step 1: Run full verification**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
git status --short
```

- [x] **Step 2: Request independent review**

Review specification compliance and code quality. Fix all gate-related
findings and rerun affected verification.

- [x] **Step 3: Commit implementation**

```powershell
git commit -m "feat: lock gemmi crystal reader dependency"
```

- [x] **Step 4: Complete cursor and checkpoint**

Record exact RED/GREEN counts, wheel metadata, Blender results, review
findings and `Remote CI: Not Run`.

```powershell
git commit -m "chore: checkpoint gemmi dependency gate"
```

**Commit boundary:** Completed plan/cursor evidence only.

**Stop boundary:** Stop with Wave 2 Task 2 — Gemmi adapter implementation
unstarted. Do not push.

## Completion Evidence

- Planning commit:
  `263421b017be8946a5e316ee65b5bff5b139a5a6`.
- Implementation commit:
  `9735c517407eb7e5cbc0970098fab7ff13d606e3`.
- Manifest byte-lock test commit:
  `80a68d99e979591ab7878a5cd3c748597b640ca3`.
- Review-fix commit:
  `1d7cf9503256cb3764ec7833072bca7c421fb1e8`.
- RED:
  initial dependency contracts `21 Ran / 5 Failed`; canonical alias
  regression `6 Ran / 1 Failed`.
- GREEN:
  final dependency/release focused `72 Ran / 1 privilege-related Skipped /
  0 Failed`; full `1430 Ran / 28 Skipped / 0 Failed`.
- Official wheel:
  `gemmi-0.7.5-cp313-cp313-win_amd64.whl`,
  SHA-256
  `ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d`.
- Wheel size:
  `2,270,352` compressed / `5,345,458` unpacked bytes.
- License:
  `gemmi-0.7.5.dist-info/licenses/LICENSE.txt`, MPL-2.0.
- Blender 5.1.2:
  native preflight, extension validate/build, exact ZIP inventory/CRC,
  isolated lifecycle and `gemmi==0.7.5` import Passed.
- Package:
  `chemblender-2.3.0-alpha.1.zip`, `29,832,390` bytes, SHA-256
  `71fc5a890f36da4fba78bfabf77db757d6498fc559e5654801c807baab603de3`.
- Reviews: `SPEC PASS`; `QUALITY PASS`.
- Remote CI: `Not Run`.
