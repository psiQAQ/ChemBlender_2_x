# Quantum input units and dual-path experience review

- State: active
- Branch: fix/quantum-input-units-experience-review
- Baseline: 76c7cbc8e7bbadfe578ffb95380b025bb7762856
- Authorization: user-approved implementation plan, 2026-09-07.
- Scope: correct units and stale task tests; provision only pinned RDKit/Gemmi wheels; validate/build/install; 14 UI and MCP cases with immediate fixes and retests.
- Preserve: user-created untracked 1.blend and existing Blender process/unsaved scene.
- Current: unit/reimport repairs committed as bed5cab; exact initial package budget as 03604d3. Genuine UI exposed Project Browser.draw writing forbidden Scene RNA. Deferred refresh fix passes 2,290 tests (26 documented skips), new ZIP audit passes; clean UI/MCP retest underway.
- Wheel hashes and inventory verified; isolated test-site provisioned under .blend-analysis/2026-09-07-review/.
- Next: finish Browser fix UI retest and commit, requalify final ZIP, continue IMP and remaining 12 cases. UI-only and MCP-only visible test profiles are separate; original user MCP 9876 is untouched.
- Actual user_default first install smoke failed when Blender wheel manager cleaned a pre-existing NumPy while loaded. Auto-review rejected reinstall/cleanup retry due possible impact on existing MCP. Do not bypass; continue isolated work and report actual-user verification Blocked pending safe read-only findings or explicit approval.
- Current candidate ZIP: 7579c1541eb242cb9220d3c7ff40296446d3f083641cf5c0c50c3f1fb9dc2112; package-browser-fix/ preserves audit; package/ preserves first 63bc260e build.
- Evidence root: .blend-analysis/2026-09-07-review/ (ignored); final report will be tracked under docs/user/workflows/reviews/.
- Reviewer: Agent simulating a user; preserve historical human Not Run records.
- No push, tag, release, dependency upgrades or unrelated optional backend installations.
