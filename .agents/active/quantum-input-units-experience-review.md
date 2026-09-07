# Quantum input units and dual-path experience review

- State: active
- Branch: fix/quantum-input-units-experience-review
- Baseline: 76c7cbc8e7bbadfe578ffb95380b025bb7762856
- Authorization: user-approved implementation plan, 2026-09-07.
- Scope: correct units and stale task tests; provision only pinned RDKit/Gemmi wheels; validate/build/install; 14 UI and MCP cases with immediate fixes and retests.
- Preserve: user-created untracked 1.blend and existing Blender process/unsaved scene.
- Current: unit/provenance regressions pass; reimport regression exposed same-locator reader-version detection and Windows lazy-array locks, both fixed and focused checks pass.
- Wheel hashes and inventory verified; isolated test-site provisioned under .blend-analysis/2026-09-07-review/.
- Next: complete full qualification, then run genuine UI and public MCP paths separately in a dedicated visible test instance.
- Evidence root: .blend-analysis/2026-09-07-review/ (ignored); final report will be tracked under docs/user/workflows/reviews/.
- Reviewer: Agent simulating a user; preserve historical human Not Run records.
- No push, tag, release, dependency upgrades or unrelated optional backend installations.
