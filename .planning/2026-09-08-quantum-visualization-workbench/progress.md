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

- User explicitly approved the independent project-cache environment. Installed managed CPython 3.12.13 and the eight unchanged gbasis-py312 constraints under .agents/cache; uv pip check passed. No global Blender packages changed. B real-file and UI success checks resumed.

- B real numerical gate passed (44 tests, 42 passed, 2 expected environment-specific skips). Fixed valid CH3 FCHK sniff with paired typed records. Blender revealed a 261-character canonical artifact path: shortened owned task prefix and checked complete Windows UTF-16 path length before launch.
- B Blender success gate passed: same session imports water FCHK, water Molden and CH3 UHF; 729-point MO, density and ESP via real operators, RDM/spin checks, Browser source switching without losing selected orbital, two register/unregister and missing-dependency/cancel cycles. UUID-backed selections prevent enum position aliasing.
- Phase C started: core sampling/export, Blender sample views and UI/cache ownership delegated; root integrates preset contracts, common color mapping and documentation.

- C passed: 12 affine sampling/CSV tests on NumPy 1.26.4 and 2.3.4; root 69 related unit/docs contracts passed. Real Blender adapter and full UI regressions passed: multi-dataset property binding, scientific zero colorbar, valid-only slice faces and profile segments, transform-independent CSV, load parameters, failure rollback and explicit rebuild retaining root and user grandchild transforms. The sampled values are display data, not a new .cbq schema.
- C committed as a local logical phase. D begins with report provenance, sequential orbital image export, and a real-file example/lifecycle gate.

- D report ancestry fixed without schema/API changes: scientific parent UUIDs now resolve through their actual entities and provenance; source revision ownership remains a leaf. Ten tests passed in the numerical environment, including real FCHK MO/RDM-density/ESP report bundles.
- Full bundled-Python suite: 2,392 tests, one subprocess Gemmi-path failure and 30 optional skips. Passing existing library paths through PYTHONPATH fixed the launch environment; all nine affected crystal qualification tests then passed. Full final suite will run after D is stable.
- Real example exposed Windows sharing violation replacing optional worker progress.json during polling; a focused progress-publication fix and failure-injection regression are in progress.

- D image/lifecycle QA found two display issues: modifier custom contracts do not persist reliably, so rebuild/cleanup now inspect durable node-group contracts; legacy actual save/open/rebuild and user-resource retention passed. Slice/colorbar lighting is now independent emission; actual unlit/strong-light pixel tests passed.
- A background test called read_factory_settings and triggered native cleanup of the shared user extension wheels. Root restored all eight original packages from the already-enabled extension manifests through the native wheel manager, without download/version changes. 5,834 wheel-entry hash checks matched; fresh-process imports and numeric/chemistry smoke passed. Interactive scene remained unsaved with its original three objects. Subsequent scene tests use private BLENDER_USER_RESOURCES.

- D passed: sequential orbital image export and atomic report package, all real example lifecycle stages, both Save As remap modes and moved project pair. Fifteen scientific arrays and scientific CSV remain unchanged under display moves and cache recovery.
- Independent PySCF 2.13.1 RHF/STO-3G comparison passed at twelve fixed grid points: MO, density and ESP maximum absolute differences below 9.60e-9; this is a pointwise check, not integration convergence.
- Final native validate/build/ZIP (197 entries) and isolated extension lifecycle passed. Full 2,410-test run found one obsolete modifier-contract mock; corrected it and the narrow runner FloatVectorProperty stub. Final rerun and actual-user install follow.

- Final bundled-Python unittest: 2,410 ran, 2,379 passed, 31 optional/environment skips, zero failures/errors (119.967 s). The isolated 74-test import-preview suite and its formerly failing case also passed in fresh processes.
- First actual-user install/lifecycle passed with the original enabled extension set preserved. Final line-ending-only normalization required rebuilding the ZIP; the byte-exact final package has 197 entries, 30,029,960 bytes, SHA-256 e076d7b0b177ef06aa5492eacfc7b9e7ec534b441bea0f6661ea205aa7a8e2fb. Final artifact installation checks are running.

- Final artifact isolated and actual-user native install/lifecycle both passed (exit 0); actual enabled extension set and userpref.blend bytes stayed unchanged. Installed package matches every final ZIP entry.
- Final environment audit passed: 4,888 unique files across eight original wheels, zero hash mismatches and fresh imports/numerical smoke. Earlier 5,834 checks included the same 946 RDKit files through both manifests. Interactive MCP confirmed the original unsaved Camera/Cube/Light scene and enabled extensions.
- Independent delivery review passed: 15 array hashes, 21 planned view identities, 9,590 CSV data rows, report schema/Markdown/artifact hashes, image dimensions and README links. Generated orbital directory inherited Python's private temporary ACL; enabled its parent inheritance so the actual user can read the delivered files. Artifact bytes are preserved with Git -text and CR-at-EOL handling.
- First-release A-D and all authorized local qualification are complete. Remote CI, push and release were not run.
