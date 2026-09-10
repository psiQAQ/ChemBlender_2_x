# ChemBlender 2.5 User Guide

[简体中文](../zh-CN/index.md)

ChemBlender is a CBQ Viewer. Prepare raw chemistry and simulation files outside Blender, then import the validated CBQ project. The Viewer remains usable after the processor or original source file is moved.

## Guides

- [Install, update and uninstall](installation.md)
- [End-to-end Blender workflow](blender-workflow.md)
- [First lesson: aspirin with actual GUI captures](first-aspirin.md) — Agent run completed; human replay pending.
- [T02: ethanol conformers, MMFF94 and mesh Apply](ethanol-conformers.md) — actual GUI and science checks; human replay pending.
- [Capabilities and project lifecycle](capabilities-and-projects.md)
- [Errors and recovery](troubleshooting.md)
- [Release status and limitations](release-status.md)

The normal sequence is: install Standard prepare → locate the executable → configure Blender → Test Processor → create CBQ in CLI/GUI → import/edit/Apply → run an external operation → create Views/Cycles output → save/move/cold reopen → test cancellation and recovery.
