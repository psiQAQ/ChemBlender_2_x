# ChemBlender 2.4.0 Post-release Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave the published 2.4.0 repository with concise documentation
entrypoints, one human UX review guide, and only the Git refs/worktrees whose
content is not already recoverable from maintained history.

**Architecture:** Keep historical plan/spec files in place and add navigation
instead of rewriting provenance. Audit every Git deletion against live
`origin/main`, PR evidence, worktree cleanliness and ignored content. Runtime
code, release tags and public assets remain immutable.

**Tech Stack:** Markdown, Python standard-library `unittest`, Git, GitHub CLI,
PowerShell, Blender Extension CI.

## Global Constraints

- Runtime source, schemas, dependencies, manifest version, tags and Releases
  do not change.
- Historical plans/specs remain at their current paths and checkbox state.
- Preserve local/remote `main`, `archive/*`, remote `snapshot/*`, annotated
  tags and GitHub Releases.
- Never delete a non-ancestor prepared branch without semantic-equivalence
  evidence.
- Never treat ignored files as disposable before inventorying them.
- Do not use `reset --hard`, rebase, force-push or automatic `ours`/`theirs`.
- Stop after the human UX review handoff; product fixes require a new goal.

---

### Task 1: Persist the cleanup cursor and plan

**Files:**
- Create: `.agents/active/2.4.0-post-release-cleanup.md`
- Create: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-post-release-cleanup.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: approved cleanup design at
  `docs/superpowers/specs/2026-08-03-chemblender-2.4.0-post-release-cleanup-design.md`.
- Produces: a resumable task cursor with exact branch, baseline, scope and stop
  boundary.

- [ ] **Step 1: Create the in-progress cursor**

Record `Goal ID: CB240-POST-RELEASE-CLEANUP`, branch
`codex/2.4.0-post-release-cleanup`, baseline
`174e6c3691790362c500742f76aae76fb80d55aa`, current task `Documentation
routing and current capability boundary`, and the approved retention rules.
Set `NEXT_RELEASE_ACTIVE_FILES` to the new cursor filename so the single-active
task contract follows the live state.

- [ ] **Step 2: Check the plan and cursor**

Run:

```powershell
rg -n -i "TB[D]|TO[D]O|FIXM[E]|implement[ ]later" `
  docs/superpowers/plans/2026-08-03-chemblender-2.4.0-post-release-cleanup.md `
  .agents/active/2.4.0-post-release-cleanup.md
git diff --check
```

Expected: no placeholder match and no whitespace error.

- [ ] **Step 3: Commit the planning checkpoint**

```powershell
git add -- `
  .agents/active/2.4.0-post-release-cleanup.md `
  docs/superpowers/plans/2026-08-03-chemblender-2.4.0-post-release-cleanup.md `
  tests/test_quantum_visualization_docs.py
git commit -m "docs: plan post-release cleanup"
```

---

### Task 2: Add durable documentation routing and current capability text

**Files:**
- Create: `docs/superpowers/README.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `.agents/README.md`
- Modify: `.agents/reference/branch-architecture.md`
- Modify: `docs/user/formats.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: completed 2.4.0 release evidence and generated reader capability
  documents.
- Produces: one stable route to historical plan/spec provenance and accurate
  published 2.4.0 format wording.

- [ ] **Step 1: Write failing documentation-routing tests**

Add these methods to `QuantumVisualizationDocsTests`:

```python
def test_post_release_documentation_routes_current_and_historical_state(self):
    root = self.read_doc("README.md")
    docs = self.read_doc("docs/README.md")
    agents = self.read_doc(".agents/README.md")
    superpowers = self.read_doc("docs/superpowers/README.md")
    self.assertIn("superpowers/README.md", docs)
    self.assertIn("ChemBlender 2.4.0", root)
    self.assertIn("2.4.0-stable-release.md", agents)
    for term in (".agents/active/", ".agents/queued/", ".agents/completed/"):
        self.assertIn(term, superpowers)
    self.assertIn("historical", superpowers.lower())
    self.assertIn("2.4.0", superpowers)

def test_user_format_summary_matches_published_240_capabilities(self):
    formats = self.read_doc("docs/user/formats.md")
    self.assertIn("ChemBlender 2.4.0 format scope", formats)
    self.assertNotIn("Base 2.3.0 format scope", formats)
    self.assertIn("Cube export", formats)
    self.assertIn("PQR export", formats)
    self.assertIn("Project Browser", formats)
```

- [ ] **Step 2: Run the RED tests**

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_post_release_documentation_routes_current_and_historical_state `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_user_format_summary_matches_published_240_capabilities -v
```

Expected: failures for the missing superpowers index, missing UX-review links
and stale format wording.

- [ ] **Step 3: Implement the minimum routing changes**

Create `docs/superpowers/README.md` with four sections: `Current authority`,
`Historical provenance`, `Released baseline`, and `Starting new work`.

Update the existing indexes without enumerating all 141 historical files:

- root `README.md`: name the current 2.4.0 product boundary;
- `docs/README.md`: add the Superpowers provenance index;
- `.agents/README.md`: add the 2.4.0 Stable completion record and route detailed
  2.4.0 task history through `.agents/completed/`;
- branch architecture: replace stale statements about retired feature refs
  with the retained-ref policy and published 2.4.0 boundary;
- formats guide: name the current 2.4.0 scope and accurately distinguish
  semantic export from bitwise source reproduction for Cube and PQR.

- [ ] **Step 4: Verify generated documents remain current**

```powershell
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
& $pythonBin -m unittest `
  tests.test_generated_docs_fresh `
  tests.test_quantum_visualization_docs -v
```

Expected: generated files are unchanged/current and all documentation tests
pass.

- [ ] **Step 5: Commit the documentation routing**

```powershell
git add -- `
  README.md docs/README.md docs/superpowers/README.md docs/user/formats.md `
  .agents/README.md .agents/reference/branch-architecture.md `
  tests/test_quantum_visualization_docs.py
git commit -m "docs: organize post-release navigation"
```

---

### Task 3: Add the 2.4.0 human UX review handoff

**Files:**
- Create: `docs/user/2.4.0-experience-review.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`
- Modify: `.agents/active/2.4.0-post-release-cleanup.md`

**Interfaces:**
- Consumes: existing Quick Import, Project Browser, format, data-quality,
  project-sidecar and scientific-editing user guides.
- Produces: one human review script and one issue-observation schema; it does
  not produce product findings.

- [ ] **Step 1: Write the failing review-guide contract**

Add:

```python
def test_240_human_experience_review_is_complete_and_observational(self):
    guide = self.read_doc("docs/user/2.4.0-experience-review.md")
    for index_path in ("README.md", "docs/README.md"):
        self.assertIn("2.4.0-experience-review.md", self.read_doc(index_path))
    for workflow in (
        "Install", "First launch", "Quick Import", "Import Preview",
        "Project Browser", "Structure", "Volume", "Surface", "Export",
        "save", "reopen", "Cancel", "recover",
    ):
        self.assertIn(workflow, guide)
    for field in (
        "Environment", "Severity", "Reproducibility", "Expected result",
        "Actual result", "Evidence",
    ):
        self.assertIn(field, guide)
    self.assertIn("do not implement", guide.lower())
```

- [ ] **Step 2: Run the RED test**

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_human_experience_review_is_complete_and_observational -v
```

Expected: failure because the guide does not exist.

- [ ] **Step 3: Write the human review guide**

Use existing public documentation links and define:

- prerequisites and a clean-profile recommendation;
- nine ordered workflows from install through recovery;
- observation prompts focused on discoverability, comprehension, feedback,
  interruption and recovery;
- severity values `Blocker`, `Major`, `Minor`, `Suggestion`;
- a copyable Markdown finding template;
- an explicit boundary that findings are recorded but not fixed in this task.

- [ ] **Step 4: Run GREEN verification**

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs `
  tests.test_generated_docs_fresh -v
git diff --check
```

Expected: all tests and diff check pass.

- [ ] **Step 5: Update the cursor and commit**

Record the Task 2/3 commits and set current task to `Prepared branch and
ignored-evidence audit`.

```powershell
git add -- `
  README.md docs/README.md docs/user/2.4.0-experience-review.md `
  tests/test_quantum_visualization_docs.py `
  .agents/active/2.4.0-post-release-cleanup.md
git commit -m "docs: add 2.4.0 human experience review"
```

---

### Task 4: Audit non-ancestor branches and ignored worktree content

**Files:**
- Modify: `.agents/active/2.4.0-post-release-cleanup.md`

**Interfaces:**
- Consumes: live refs, worktree state, completed cursors, changed paths,
  patch IDs and fixture hashes.
- Produces: literal `remove` or `retain` decisions for every non-ancestor or
  detached target.

- [ ] **Step 1: Refresh the Git inventory**

```powershell
git fetch origin --prune
git status --short
git worktree list --porcelain
git for-each-ref --format="%(refname:short) %(objectname)" refs/heads
git ls-remote --heads origin
gh pr list --repo psiQAQ/ChemBlender_2_x --state all --limit 100
```

Expected: cleanup branch is the only new development ref and every mapped
worktree is clean.

- [ ] **Step 2: Audit prepared non-ancestor branches**

Audit these live branch names when present:

```text
docs/2.3.0-prepared-worktree-integration
feat/2.3.0-wave2-poscar-syntax
feat/2.3.0-wave4-legacy-fixtures
```

For each branch run:

```powershell
$base = git merge-base $branch origin/main
git log --oneline "$base..$branch"
git diff --name-status "$base..$branch"
git cherry origin/main $branch
```

For every `+` commit, compare patch IDs or final file bytes with `origin/main`.
For the legacy fixtures, compare SHA-256 values. Record exact evidence and do
not delete a branch with unmatched content.

- [ ] **Step 3: Audit detached worktrees**

For `pqr-ui-budget-audit` and `w4-ci-exact-verify`, require clean status,
HEAD ancestry in `origin/main`, and no unique ignored evidence.

- [ ] **Step 4: Inventory ignored content for every removal candidate**

Use `git status --short --ignored` and classify ignored paths as cache,
downloaded wheel, build artifact, test output or unique evidence. Record any
preserved path and hash in the cursor before cleanup.

- [ ] **Step 5: Commit the audit decision**

```powershell
git add -- .agents/active/2.4.0-post-release-cleanup.md
git commit -m "docs: record post-release cleanup audit"
```

---

### Task 5: Remove verified redundant worktrees and local branches

**Files:**
- Modify: `.agents/active/2.4.0-post-release-cleanup.md`

**Interfaces:**
- Consumes: Task 4 literal removal set.
- Produces: root worktree plus the active cleanup worktree and any explicitly
  retained archive/unmatched worktrees.

- [ ] **Step 1: Revalidate each target immediately before removal**

For each target, resolve the absolute worktree path and require it to be under
`D:\workspace\ChemBlender_2_x\.worktrees\`, clean, and matched to the audited
SHA. Ancestor targets must still pass:

```powershell
git merge-base --is-ancestor $sha origin/main
```

- [ ] **Step 2: Remove mapped worktrees one at a time**

```powershell
git worktree remove -- "$literalWorktreePath"
```

Do not use `--force` unless the superproject and initialized submodules are
clean and the only obstacle is verified disposable submodule state. Stop on a
Windows path-lock error rather than terminating unknown processes.

- [ ] **Step 3: Delete the audited local branches**

Use `git branch -d -- $branch` for ancestor branches. Use `git branch -D` for a
prepared non-ancestor branch only when Task 4 recorded full semantic
equivalence and the corresponding worktree has already been removed.

- [ ] **Step 4: Verify local cleanup**

```powershell
git worktree list --porcelain
git worktree prune --dry-run --verbose
git for-each-ref --format="%(refname:short) %(objectname)" refs/heads
```

Expected: no stale worktree metadata and only the approved retained local refs
plus the active cleanup branch.

---

### Task 6: Remove verified redundant remote branches

**Files:**
- Modify: `.agents/active/2.4.0-post-release-cleanup.md`

**Interfaces:**
- Consumes: PR head SHAs and `origin/main` ancestry.
- Produces: remote `main`, immutable `archive/*`, `snapshot/*`, and any target
  that fails revalidation.

- [ ] **Step 1: Build the literal remote candidate set**

Select only live branches with merged PR evidence or release evidence. Exclude
`main`, `archive/*`, `snapshot/*` and the active cleanup branch.

- [ ] **Step 2: Validate and delete one remote ref at a time**

For each candidate require:

```powershell
$live = git ls-remote --heads origin "refs/heads/$branch"
git merge-base --is-ancestor $auditedSha origin/main
gh pr list --repo psiQAQ/ChemBlender_2_x --state merged --head $branch `
  --json headRefOid,mergeCommit,url
```

The live SHA must equal the audited PR/release head. Then run:

```powershell
git push origin --delete $branch
git fetch origin --prune
```

- [ ] **Step 3: Verify remote cleanup**

```powershell
git ls-remote --heads origin
git remote prune origin --dry-run
```

Expected: only approved retained refs and the active cleanup branch remain;
no stale tracking ref is reported.

- [ ] **Step 4: Record exact retained and removed refs**

Update the active cursor with counts, names, SHAs, any retained blocker and the
remote cleanup result.

---

### Task 7: Qualify and checkpoint the cleanup

**Files:**
- Move: `.agents/active/2.4.0-post-release-cleanup.md` to
  `.agents/completed/2.4.0-post-release-cleanup.md`
- Modify: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-post-release-cleanup.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: documentation commits and final Git inventory.
- Produces: a clean, reviewable checkpoint ready for PR integration.

- [ ] **Step 1: Run focused verification**

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs `
  tests.test_generated_docs_fresh `
  tests.test_repository_contract -v
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

- [ ] **Step 2: Verify immutable release evidence**

```powershell
git rev-parse "v2.4.0^{}"
gh release view v2.4.0 --repo psiQAQ/ChemBlender_2_x `
  --json tagName,isDraft,isPrerelease,assets,url
```

Expected: tag still peels to
`302b6efec366f1f1657663659b89e8ce526877a5`, public asset names and digests
are unchanged.

- [ ] **Step 3: Complete the cursor and plan**

Record commits, tests, retained refs, removed refs, worktree count, remote count,
the human review guide path and `Product UX fixes: Not Started`.
Reset `NEXT_RELEASE_ACTIVE_FILES` to `()` after moving the cursor to completed.

- [ ] **Step 4: Commit the cleanup checkpoint**

```powershell
git add -A -- `
  .agents/active/2.4.0-post-release-cleanup.md `
  .agents/completed/2.4.0-post-release-cleanup.md `
  docs/superpowers/plans/2026-08-03-chemblender-2.4.0-post-release-cleanup.md `
  tests/test_quantum_visualization_docs.py
git commit -m "chore: checkpoint post-release cleanup"
```

---

### Task 8: Integrate and remove the cleanup branch

**Files:** None after the checkpoint; this task changes Git/GitHub state only.

**Interfaces:**
- Consumes: clean Task 7 checkpoint.
- Produces: ordinary merge in `main`, exact merge-head CI, and no remaining
  cleanup branch/worktree.

- [ ] **Step 1: Push and create a ready PR**

```powershell
git push -u origin codex/2.4.0-post-release-cleanup
gh pr create --repo psiQAQ/ChemBlender_2_x --base main `
  --head codex/2.4.0-post-release-cleanup `
  --title "chore: organize ChemBlender 2.4.0 post-release state" `
  --body-file $prBodyPath
```

- [ ] **Step 2: Require exact-head CI**

Wait for `extension-package` and `optional-qc-core`; verify every run's
`headSha` equals the PR head and every required job succeeds.

- [ ] **Step 3: Merge normally and verify merge-head CI**

```powershell
gh pr merge $prNumber --repo psiQAQ/ChemBlender_2_x --merge
git fetch origin --prune
```

Require the checkpoint to be an ancestor of `origin/main`, then wait for both
workflows on the exact merge SHA.

- [ ] **Step 4: Fast-forward the clean root main worktree**

```powershell
git -C D:\workspace\ChemBlender_2_x pull --ff-only origin main
```

- [ ] **Step 5: Remove the merged cleanup ref and worktree**

From the root worktree, verify the cleanup checkpoint is an ancestor of
`origin/main`, remove the cleanup worktree, delete the local cleanup branch,
delete its remote branch, fetch/prune and run the final worktree/ref audit.

Expected final state: clean root `main`, no open PR, no active/queued task,
only approved retained local/remote refs, and the human UX review guide ready
for the user's manual inspection.
