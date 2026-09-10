# ChemBlender 2.5 real user tutorials

Goal: Deliver bilingual, real GUI and scientifically checked T00-T20 plus B01 tutorials and portable projects. Human independent acceptance remains mandatory.
Goal tracking: The user explicitly activated the remaining M0-M5 scope as a persistent goal on 2026-09-10. Keep the goal active while executable work remains; update this plan and the active record after material progress. Human acceptance and mandatory blockers cannot be self-certified.
Success: Required scientific, GUI, render, persistence and distribution checks pass; human review is recorded separately.
Constraints: Preserve the current unsaved Blender scene and installed environments. Reuse existing backends; ask before installing dependencies. No external publication. Research source package stays byte-identical.
Verification: Per-case frozen specs, event/screenshot records, public CLI validation, cold reopen/move, offline browser QA, relevant regression, package audit and git diff --check.

## Plan
- [ ] M0: Freeze artifacts, isolated profile, evidence specifications and GUI capability.
- [ ] M1: T00/T01 GUI, Cycles, save/cold reopen and first offline lesson.
- [ ] M2: T02, T04, T06, T07, T17, T18 required core scenarios.
- [ ] M3: T03/T05, T08-T10, T11/T12, T13/T14, T15, T19/T20/T16/B01.
- [ ] M4: Bilingual offline documentation and human blind replay.
- [ ] M5: Local candidate, regression and distribution evidence.

## Defaults
Computer Use first; native input only if unavailable. One GUI operator and at most one Agent-owned Blender process at a time, including background replay/audit. Preserve the user's pre-existing unsaved Blender process. Save and exit the tutorial process before cold reopen or background checks; verify its exact PID has exited before launching the next one. Reuse the isolated tutorial profile serially. Human independent reviewer. New profile and per-run directories. No scientific source or sidecar arrays deleted during recovery tests.
