# ChemBlender 2.5 real user tutorials

Implementation and correction are in progress. No case has independent human acceptance, and no final distribution claim is made.

The immutable design baseline remains in [the research package](../../../docs/chemblender25-research/README.md). The current per-case control state is [status.json](status.json); detailed receipts are versioned beside it, while large raw runs remain local under `.blend-analysis/2.5-real-user-tutorials/`.

## Current entry points

- Current candidate receipt: [run009-candidate-check.json](run009-candidate-check.json).
- Current-candidate P0 work: T04, T06 and T07 use run-009 receipts listed in `status.json`.
- Historical evidence: T00/T01/T02 use earlier candidates and require explicit current-candidate applicability checks before technical closure.
- Existing P0 evidence: T17 uses run-006 Prepare receipts; T18 uses run-007 Extension receipts. Neither is `not_run`, but both remain incomplete.
- First lesson: [English](../../../docs/user/en/first-aspirin.md) / [中文](../../../docs/user/zh-CN/first-aspirin.md).
- Offline guide: [English](../../../docs/offline/en/index.html) / [中文](../../../docs/offline/zh-CN/index.html).

Review ZIPs are local `review_only` handover packages. They are not final distribution artifacts and do not prove independent review. Technical status, direct GUI evidence, authorized replay, human review and distribution are tracked separately.

The execution checker accepts original GUI JPEG or PNG evidence with matching suffix, signature and hash; renders remain PNG. This verifies record integrity, not screenshot authenticity or human acceptance. The original research package remains byte-identical.

Example integrity check for the retained historical T01 run (its candidate scope remains historical):

```powershell
.venv\Scripts\python.exe examples\tutorials\2.5.0\validate_evidence.py .blend-analysis\2.5-real-user-tutorials\run-003\T01\run-manifest.json --spec examples\tutorials\2.5.0\T01.case-spec.json
```
