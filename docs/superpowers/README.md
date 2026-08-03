# Design and implementation provenance

## Current authority

Current Agent work is recorded in `.agents/active/`. Approved work that has
not started is recorded in `.agents/queued/`. If both directories contain no
tracked task, no repository plan is active.

## Historical provenance

Files under `specs/` and `plans/` are historical design and execution
records. They stay at stable paths so commits, reviews and completed evidence
can link to them. An unchecked box in an old plan is not current work; use the
Agent state directories to determine live status.

Completed execution evidence belongs in `.agents/completed/`. Stable rules and
architectural decisions belong in `.agents/reference/` and
`.agents/decisions/`.

## Released baseline

The current maintained release is ChemBlender 2.4.0. Its exact local, CI, tag,
asset and public Release evidence is recorded in
[`2.4.0-stable-release.md`](../../.agents/completed/2.4.0-stable-release.md).

## Starting new work

Do not reopen a historical checklist. Define a new goal, write a new approved
specification when behavior or policy changes, create a new implementation
plan, and register its cursor in `.agents/active/` or `.agents/queued/`.
