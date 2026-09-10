# ChemBlender 2.5 real user tutorials

Implementation in progress. No completed tutorial acceptance is claimed.

The original design remains in [the research package](../../../docs/chemblender25-research/README.md). Case status is tracked in [status.json](status.json). Raw run evidence and large outputs are local under `.blend-analysis/2.5-real-user-tutorials/`. Human independent acceptance is required.

- First lesson: [English](../../../docs/user/en/first-aspirin.md) / [中文](../../../docs/user/zh-CN/first-aspirin.md).
- Offline guide: [English](../../../docs/offline/en/index.html) / [中文](../../../docs/offline/zh-CN/index.html).
- T01 local run: `.blend-analysis/2.5-real-user-tutorials/run-002/T01/run-manifest.json`.
- Paired project: `run-002/T01/aspirin.blend` and the complete adjacent `aspirin.cbq/` directory. Render: `aspirin-cycles.png`.

T00 diagnostics and T01 GUI conversion/import/View/render/save/cold reopen have run. Scientific checks and offline browser checks passed. The checker still reports `incomplete`: final visual review is pending, and no human independent replay has occurred. T02–T20 and B01 remain Not Run; this checkpoint does not close the overall plan.

On 2026-09-10 the user approved native GUI JPEG evidence. [The execution checker](validate_evidence.py) is a copy of the original research checker with only GUI image format handling changed: original JPEG or PNG with matching suffix, signature and hash; renders remain PNG. The result schema, scientific checks, lifecycle and independent review gates are unchanged. Signature checks are not image decoding or proof of authenticity. The original research files remain byte-identical.

```powershell
.venv/Scripts/python.exe examples/tutorials/2.5.0/validate_evidence.py .blend-analysis/2.5-real-user-tutorials/run-002/T01/run-manifest.json --spec examples/tutorials/2.5.0/T01.case-spec.json
```
