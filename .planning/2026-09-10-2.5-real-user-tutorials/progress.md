# Progress
2026-09-10: Implementation authorized. Created feat/2.5-real-user-tutorials. M0 in progress. No case GUI execution yet; human acceptance Not Run.
Errors: PowerShell rg wildcard paths are not expanded; use directory plus -g. Python read_text defaults to GBK here; use explicit UTF-8. Existing private-viewer/export.cbq has denied traversal; do not modify old evidence.

2026-09-10 M0: Computer Use installed final baseline ZIP in run-001 isolated profile. All 109 installed files matched ZIP. GUI Test Processor result 10/21 operations,16/22 readers,Standard complete. Confirmed UI defect: completion did not redraw until another click. Added redraw on terminal/cancelling transitions and native Blender regression (Passed). New build Passed; old build launcher loaded unrelated user addons, so repeat build with explicit isolated profile before accepting build evidence. run-001 retained as defect evidence; final screenshots require new artifact hash.
