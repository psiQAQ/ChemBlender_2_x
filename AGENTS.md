# ChemBlender Repository Instructions

## Communication

- Use Chinese by default. Keep code, commands, paths, APIs, and errors in English.
- Lead with conclusion, evidence, plan, and verification. Separate confirmed facts, inference, and recommendation.

## Session Recovery

After a new conversation or context compaction:

1. Read this file.
2. Read `.agents/README.md`.
3. Read the relevant `.agents/active/` or `.agents/queued/` document.
4. Read only the referenced decision or reference documents needed for the task.
5. Verify Git, Blender, dependency, test, and CI state live.

Do not infer current status from this file, completed work, archived evidence, or old conversations.

## Release Boundaries

- `78c2d8d` is the imported 2.1.0 baseline.
- 2.1.1 is the final legacy add-on release and changes only the version plus two compressed `.blend` files.
- 2.2.0 is the first extension release and uses `ChemBlender/` as its extension root.
- The repository root is the development workspace, not the packaged extension root.
- `CHANGELOG.md` is the canonical Release-notes source. A version bump and its dated changelog entry belong in the same pre-tag commit; the Release workflow extracts that entry instead of generating or duplicating notes.

## Branch Roles

- `origin/main` is the maintained release line.
- `upstream/main` is the upstream reference.
- `archive/*` is immutable investigation history and never a release base.
- `release/*` contains focused release preparation.
- `feat/*` contains maintained downstream features.
- Formal `upstream-pr/*` branches start from freshly fetched `upstream/main` and exclude downstream governance, packaging, and extension history.

## Repository Layout

- `ChemBlender/`: packaged extension source and manifest.
- `tests/`: repository contracts and Blender runtime smoke checks.
- `docs/`: durable human-facing development, migration, and release documentation.
- `.agents/active/`: current task authority.
- `.agents/queued/`: approved work not yet started.
- `.agents/reference/`: stable operational rules.
- `.agents/decisions/`: numbered decision rationale.
- `.agents/completed/`: finished summaries used only for provenance.
- `.agents/skills/`: repository-local skills and templates.

## Task Execution

- Before editing, state Goal, Success Criteria, Constraints, and Verification.
- Inspect `git status`, the current branch, affected source, callers, tests, and recent commits before modifying files.
- Use the smallest change that solves the confirmed problem. Reuse existing code and standard-library/platform features.
- Do not add speculative abstractions, dependencies, compatibility layers, or unrelated cleanup.
- Protect user changes and preserve existing file encoding and line endings.

## Python Environment

- Prefer project `.venv`, then an existing `uv` environment, then Blender bundled Python returned by MCP.
- Do not install or change Python dependencies without explicit approval.
- Do not install packages into Blender's global `site-packages`.

## Blender Extension Workflow

- Before Blender operations, run `blender-mcp --help` and query Blender version, executable, bundled Python, runtime system, and extension repositories together.
- Require Blender 5.1.0 or newer for the supported release.
- Build and install through Blender Extensions; never copy 2.2.0 source into a legacy add-on directory.
- Verify the enabled key `bl_ext.user_default.chemblender`.
- Validate register, unregister, repeated reload, scene properties, `.blend` assets, and RDKit import in the real runtime.

## Dependency Policy

- Use Blender's bundled NumPy.
- RDKit is an offline manifest wheel downloaded by developers or CI.
- Never track `.whl` files or install packages during import, `register()`, or add-on enable.
- Pin dependency filenames, sources, versions, and SHA-256 values in the dependency reference and CI.

## Git and External Writes

- One complete logical phase per commit; commit messages describe the actual change.
- Use independent branches for risky work and prefer `git revert` over history destruction.
- Never use `git reset --hard` without explicit approval.
- Do not push, alter remotes, open or change PRs/issues, or publish releases without explicit approval.

## Verification

- Run the narrowest relevant unit test first, then static package checks, Blender extension validate/build, and real install smoke tests when applicable.
- Report results as Passed, Failed, or Not Run with a reason.
- A ZIP existing, a manifest parsing, or CI being green is not sufficient by itself; inspect package contents and runtime behavior.
- Run `git diff --check` and confirm the final worktree before claiming completion.

## Release Testing Policy

- Keep release contracts on Python's standard library until pytest features are demonstrably needed.
- A release gate includes repository contracts, native extension validate/build, ZIP-content audit, isolated Blender install, real `user_default` install, and an actual GitHub Actions run.
- Use a temporary `BLENDER_USER_RESOURCES` directory for isolated runtime tests so an existing extension installation cannot satisfy missing dependencies.
- Manifest permissions must describe actual runtime file and network behavior; network access is never used for package installation.
- Pin GitHub-owned actions to reviewed full commit SHAs, not mutable version tags.

## Documentation and Agent Memory

- Update docs only for features, architecture, installation, release flow, or explicit requests.
- Root `AGENTS.md` contains stable rules and routing only, never live commit/run status or chat transcripts.
- Update `.agents/active/` only after a material state change. Polling without change produces no edit.
- Record branch-role, release-boundary, dependency-source, and packaging-policy changes in the same commit.
- Append decisions instead of rewriting old rationale. Move finished work to `completed/` with concise evidence.

## Windows Files

- Preserve UTF-8 BOM state and line endings. Do not use Windows PowerShell 5.1 `Set-Content`, `Out-File`, `>`, or `>>` for UTF-8 source files.
- `.bat` files use UTF-8 without BOM and CRLF, starting with `@echo off` and `chcp 65001 >nul`.
- Sort paths ordinally, not with culture-sensitive `Sort-Object`.

## Knowledge Entrypoints

- Quantum visualization roadmap: `docs/quantum-visualization/roadmap.md`
- Quantum visualization data boundary: `docs/quantum-visualization/architecture/data-boundary.md`
- Latest release readiness evidence: `.agents/completed/2.2.0-release-readiness.md`
- Branch architecture: `.agents/reference/branch-architecture.md`
- Dependency and release policy: `.agents/reference/dependencies-and-release.md`
- Version roadmap decision: `.agents/decisions/0001-version-and-extension-roadmap.md`
- Release testing decision: `.agents/decisions/0002-release-testing-and-pillow-scope.md`
- Completed 2.1 history: `.agents/completed/2.1.0-import-and-2.1.1-slimming.md`
