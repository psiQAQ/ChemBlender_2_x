# ChemBlender 2.5 real user tutorials

Implementation and correction are in progress. No case has independent human acceptance, and no final distribution claim is made.

The immutable design baseline remains in [the research package](../../../docs/chemblender25-research/README.md). The current per-case control state is [status.json](status.json); detailed receipts are versioned beside it, while large raw runs remain local under `.blend-analysis/2.5-real-user-tutorials/`.

## Current entry points

- Current candidate receipt: [run009-candidate-check.json](run009-candidate-check.json).
- Environment qualification: [environment-qualification.json](environment-qualification.json). `development_reuse` is local evidence only, `isolated_install` requires the current wheel and no cross-environment path injection, and `distribution_ready` additionally requires every final delivery and independent-review gate.
- Current-candidate P0 work: T00, T04, T06 and T07 use current-candidate receipts listed in `status.json`.
- Current applicability: T00 has a [current-candidate applicability receipt](T00-current-candidate-check.json). T01 has a [current-candidate receipt](T01-current-candidate-check.json), a separately classified [execution supplement](T01.current-execution-supplement.json), and a [review-package receipt](T01-run010-package-check.json). T02 has its own [current-candidate receipt](T02-current-candidate-check.json), [execution supplement](T02.current-execution-supplement.json), and [current review-addendum receipt](T02-run010-package-check.json). T07 has a [candidate-scope receipt](T07-current-candidate-check.json), [source/processor-unavailable recovery](T07-run010-offline-recovery-check.json), and a [review-package receipt](T07-run010-package-check.json). T18 has a [current recovery audit](T18-current-candidate-check.json). Historical direct-GUI events retain their original candidate identity. The [P0 checker summary](P4-p0-checker-summary.json) records every executed checker and every explicit no-manifest blocker.
- Existing P0 evidence: T17 retains run-006 direct-GUI receipts and now has a [current-candidate 13-format regression](T17-current-candidate-check.json) plus [review-package receipt](T17-run010-package-check.json). T18 uses run-007 Extension receipts. Neither independent human review is complete.
- First lesson: [English](../../../docs/user/en/first-aspirin.md) / [中文](../../../docs/user/zh-CN/first-aspirin.md).
- Offline guide: [English](../../../docs/offline/en/index.html) / [中文](../../../docs/offline/zh-CN/index.html).

Review ZIPs are local `review_only` handover packages. They are not final distribution artifacts and do not prove independent review. Technical status, direct GUI evidence, authorized replay, human review and distribution are tracked separately.

The current Standard environment is an isolated current-wheel install but is not distribution-ready. The scientific route remains `development_reuse` because it uses cross-environment `.pth` paths. The dependency-self-contained wavefunction and fermi caches contain eight Prepare/Core files that differ from the current wheel and are not configured in run-009. Replaying any of these as a current professional route therefore requires authorization to update the environment; no `.pth`, `PYTHONPATH` or source injection is permitted.

The execution checker accepts original GUI JPEG or PNG evidence with matching suffix, signature and hash; renders remain PNG. This verifies record integrity, not screenshot authenticity or human acceptance. The original research package remains byte-identical.

`validate_evidence.py` reports evidence integrity, technical completion, independent review and acceptance separately. A non-passed run is still fully audited for every record it declares; missing gates return `incomplete`, while malformed records, broken links, unsafe paths and wrong hashes return `invalid`.

Execution supplement v1 is optional. [T01.execution-supplement.json](T01.execution-supplement.json) records the first approved GUI-to-MCP reuse chain. Each replay links the prior direct-GUI run and captures, the user authorization, the candidate difference check and a hash-linked public Operator receipt. It is classified as `authorized_mcp_replay`, never as a new `os_gui` or `human_gui` event. A changed button, new panel or previously unverified step still requires direct GUI evidence.

Example integrity check for the retained historical T01 run (its candidate scope remains historical):

```powershell
.venv\Scripts\python.exe examples\tutorials\2.5.0\validate_evidence.py .blend-analysis\2.5-real-user-tutorials\run-003\T01\run-manifest.json --spec examples\tutorials\2.5.0\T01.case-spec.json
```

To include the approved replay chain, append:

```powershell
--execution-supplement examples\tutorials\2.5.0\T01.execution-supplement.json
```
