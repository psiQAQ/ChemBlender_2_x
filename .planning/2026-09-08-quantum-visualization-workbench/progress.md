# Progress

## 2026-09-08 implementation start
- User approved first-release implementation and staged reference submodules.
- Verified clean main at ca5ce98 and read repository/Blender guidance.
- Created owned planning files; no implementation changes yet.
- Runtime preflight: blender-mcp help failed inside sandbox; checking existing launcher outside sandbox.
- Tests: Blender bundled Python baseline passed 23 surface/grid/preset tests. my_base Python remains unusable (exit 1 without output); no package was installed.
- MCP confirmed Windows Blender 5.1.1, bundled Python 3.13.9, NumPy 2.3.4, enabled bl_ext.user_default.chemblender. Active scene is unsaved/dirty; use a separate background Blender for validation.
- Created feat/quantum-visualization-workbench. Phase A parent structure identity and version updates started. Assigned old-view migration and independent Blender regression to separate agents.
- Actual Blender 5.1.1 reproduction: fixed density plus zero property yields 176 vertices / 174 faces; linear property yields 744 / 740 before fix. Density-only GridToMesh implementation is now under runtime retest.
- Root core regression: 21 tests passed, 3 optional scientific integrations skipped (no IOData/GBasis environment). Updated version expectation after property preset v2.
- Existing environments were checked: no Python 3.12 with IOData/GBasis remains. Asked user to restore the existing pinned optional test environment; package install remains pending approval. RDKit/Gemmi release wheels already exist with correct hashes.
- References complete: three clean fixed-commit submodules; existing 14 unchanged; docs tests 37/37 passed; committed as one local phase.
- Surface geometry retest passed: all three property variants have 176 vertices / 174 faces; affine coordinates and signed branches preserved. Sampling max errors 5.36e-8 / 1.97e-6.
- Related UI tests initially had five RDKit-dependent failures with no RDKit on CPython path. Reused the existing MCP-discovered extension library path outside sandbox (no install); all 105 tests then passed, using bundled NumPy.
- Phase A complete: real v1 View (744 vertices) explicitly rebuilt to v2 (176), preserving original Object/transform/collections/user modifier. Old resources reclaimed; injected preparation failure rolled back without leaks. A stale view does not prevent another current Volume cache repair. Unit suites and live regression passed.
- Saved Phase A as local commit ad1c42d. Phase B now implements bounded numeric/worker operations, orbital metadata/UI, and explicit external-worker wavefunction import in separate owned files.
- Added pure orbital browser metadata with conservative frontier labels, current scientific-cache identity, scientific grid bounds and memory preflight. Six focused tests passed with bundled NumPy.
- Existing IOData/GBasis source submodules were empty; initialized only their recorded gitlink revisions to recover authoritative FCHK/Molden fixtures. No package installation.
- Found a real UI boundary: Quick Import probes IOData inside Blender and cannot use the optional external environment. A dedicated worker import entry will reuse the existing parse/transaction machinery.
- Molden commonly lacks a source RDM. Its density matrix must be explicitly derived from orbital occupations with a user-selected SCF/post-SCF level and recorded provenance; integer occupations alone do not establish SCF origin.
- Phase B Blender UI gate passed twice in a separate Blender 5.1.1: full register/unregister, alpha/beta orbital selection, grid fit, real worker missing-dependency failure with unchanged project, and task cancellation/workspace cleanup. Successful real-file numerical/UI gate remains pending the optional environment.
- Phase B review complete: input UUID closure is detached on the main thread; closing/replacing the source sidecar cannot invalidate worker arrays, and unrelated grids are not copied. Late cancellation and source replacement reject publication; closed modal handlers exit.
- Root verification: 147 core/worker/A-regression/docs tests ran, 144 passed and 3 optional numerical tests skipped. Final UI/import/launcher/docs run: 62 ran, 58 passed and 4 skipped (three optional scientific checks plus one Blender-only check separately passed). These suites overlap and are not additive.
- Final Blender 5.1.1 two-cycle regression passed after snapshot/cancel fixes, including actual FCHK worker import failure with a named qc-iodata diagnostic. An earlier assertion exposed the generic reader_unavailable message; the diagnostic is now fixed and reverified.
- Native Extension validate/build and ZIP audit passed: 194 entries, current source bytes, existing RDKit/Gemmi wheels only; no source submodules, worker package or planning files. ZIP SHA-256: 973d7f06b2c039459f6fde9896906a4d957f5fc7e43efbee3218ccea60b1844d. Existing legacy NumPy/import and mesh escape warnings were not changed.
- No dependency package was installed, interactive scene changed or remote write performed. B real numerical/UI success, C/D, isolated/user installation and full example lifecycle remain outstanding. Await permission for the required pinned environment before continuing the sequential B gate.
