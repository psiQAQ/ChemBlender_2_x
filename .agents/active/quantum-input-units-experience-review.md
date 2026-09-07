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

- 22b654d fixes stale cancellation summary and preview labels; its c5e438ae ZIP passes full isolated smoke (102.91 s). ENV final retest passed in isolation. IMP UI finished with six meshes, IMP/UI collection, .blend/.cbq and render.
- IMP MCP exposed stale forced dialogs after public cancel/confirm and explicit rows overwritten by defaults. Current repair adds read-only ephemeral preview_json and respects invoke vs execute plus explicit row choices; 159 related contracts pass after failing regressions. Rebuild/retest underway; remaining 12 cases not run yet.
- UI installer test setup accidentally created lab_blender_org/chemblender at 20:20. Exact newly-created directory quarantined after checking original process did not enable it. No existing MCP source moved. Both test repo configurations now point at copied MCP source within the run root. Original 9876 remains 1.blend, Cube/Light/Camera, dirty false.

- 87580c4 foreground preview fix qualified with 2,294 tests and isolated smoke. Live MCP then found missing inherited PropertyGroup.name in JSON collection conversion. Added actual JSON-to-Operator regression (old ZIP fails), fixed nested serialization; 2,294 tests / 26 skips / zero failures or errors and isolated smoke 103.44 s pass. Current ZIP 966dc8a7def7343fa29b1823ea72e2ea43a04015655bf32da0bd2f6c2a824daf; native UI install hash verified. Finish IMP MCP then remaining 12 cases.
