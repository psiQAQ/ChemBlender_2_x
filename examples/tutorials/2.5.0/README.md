# ChemBlender 2.5 real user tutorials

Implementation and correction are in progress. No case has independent human acceptance, and no final distribution claim is made.

The immutable design baseline remains in [the research package](../../../docs/chemblender25-research/README.md). The current per-case control state is [status.json](status.json); detailed receipts are versioned beside it, while large raw runs remain local under `.blend-analysis/2.5-real-user-tutorials/`.

## Current entry points

- Current candidate receipt: [P6-current-extension-qualification.json](P6-current-extension-qualification.json); historical run receipts retain their original hashes.
- Environment qualification: [environment-qualification.json](environment-qualification.json). `development_reuse` is local evidence only, `isolated_install` requires the current wheel and no cross-environment path injection, and `distribution_ready` additionally requires every final delivery and independent-review gate.
- Current-candidate P0 work: T00, T04, T06 and T07 use current-candidate receipts listed in `status.json`.
- Current applicability: T00 now has a conforming current manifest backed by direct OS GUI reinstall, Test Processor and invalid-path recovery; its [technical receipt](T00-run010-technical-check.json) and [review-package receipt](T00-run010-package-check.json) classify the retained failed captures separately. T01, T02 and T04 also have conforming current manifests whose integrity and technical gates pass. T04's [technical receipt](T04-run010-technical-check.json), [supplement](T04.current-execution-supplement.json), [current-candidate receipt](T04-current-candidate-check.json) and [review-addendum receipt](T04-run010-package-check.json) keep historical direct GUI, current Operator replay/render/cold-open evidence and independent review separate. T00/T01/T02/T04 remain `ready_for_human_review`, not accepted. T07 has a [candidate-scope receipt](T07-current-candidate-check.json), [source/processor-unavailable recovery](T07-run010-offline-recovery-check.json), and a [review-package receipt](T07-run010-package-check.json). T18 has a [current recovery audit](T18-current-candidate-check.json). Historical direct-GUI events retain their original candidate identity. The [P0 checker summary](P4-p0-checker-summary.json) records every executed checker and every explicit no-manifest blocker.
- Existing P0 evidence: T17 retains run-006 direct-GUI receipts and now has a [current-candidate 13-format regression](T17-current-candidate-check.json) plus [review-package receipt](T17-run010-package-check.json). T18 uses run-007 Extension receipts. Neither independent human review is complete.
- Current Phase 5 evidence: T03 and T05 have current Standard receipts; T08–T14 retain current scientific receipts but still lack direct GUI/manifests; T15 has a [current CLI/Worker science receipt](T15-current-candidate-check.json) for real QTAIM/NCI output through the retained WSL critic2 route; T16 now has a [current MIT-input and isolated Fermi receipt](T16-current-candidate-check.json), while POTCAR/WAVECAR/pickle remain excluded; T19 has an [external Python Reader API receipt](T19-current-candidate-check.json); T20 has a [real compute receipt](T20-current-candidate-check.json); B01 has a [negative provider-boundary receipt](B01-current-candidate-check.json). B01 performed no network fetch, and its passed negative checks are not positive provider success. None of these receipts substitutes for missing direct GUI, Blender lifecycle, tutorial package or independent review.
- First lesson: [English](../../../docs/user/en/first-aspirin.md) / [中文](../../../docs/user/zh-CN/first-aspirin.md).
- Offline guide: [English](../../../docs/offline/en/index.html) / [中文](../../../docs/offline/zh-CN/index.html).

Review ZIPs are local `review_only` handover packages. They are not final distribution artifacts and do not prove independent review. Technical status, direct GUI evidence, authorized replay, human review and distribution are tracked separately.

Standard, scientific, wavefunction and fermi routes have current isolated-install receipts, but none is distribution-ready while independent review and final delivery gates remain open. The retained critic2 WSL route is still `development_reuse`. No `.pth`, `PYTHONPATH` or source injection is accepted as deployment qualification.

The execution checker accepts original GUI JPEG or PNG evidence with matching suffix, signature and hash; renders remain PNG. This verifies record integrity, not screenshot authenticity or human acceptance. The original research package remains byte-identical.

`validate_evidence.py` reports evidence integrity, technical completion, independent review and acceptance separately. A non-passed run is still fully audited for every record it declares; missing gates return `incomplete`, while malformed records, broken links, unsafe paths and wrong hashes return `invalid`.

Execution supplement v1 is optional. [T01.execution-supplement.json](T01.execution-supplement.json) records the first approved GUI-to-MCP reuse chain. Each replay links the prior direct-GUI run and captures, the user authorization, the candidate difference check and a hash-linked public Operator receipt. It is classified as `authorized_mcp_replay`, never as a new `os_gui` or `human_gui` event. A changed button, new panel or previously unverified step still requires direct GUI evidence.

Example check for the current T01 run (exit 2 means only independent human review remains incomplete):

```powershell
.venv\Scripts\python.exe examples\tutorials\2.5.0\validate_evidence.py .blend-analysis\2.5-real-user-tutorials\run-010\T01\run-manifest.json --spec examples\tutorials\2.5.0\T01.case-spec.json --publish --expected-extension-sha256 73fe2c248a7c1ad939018ce21a4ae44c52855abbdaff124af581bd34ffe469c8 --expected-prepare-sha256 3ca42c26be19aebc5444d5df5a0490a15d3da6c370f2c4ec6883921a3e8880e3 --execution-supplement examples\tutorials\2.5.0\T01.current-execution-supplement.json
```
