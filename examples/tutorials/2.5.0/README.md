# ChemBlender 2.5 real user tutorials

Implementation in progress. No completed tutorial acceptance is claimed.

The original design remains in [the research package](../../../docs/chemblender25-research/README.md). Case status is tracked in [status.json](status.json). Raw run evidence and large outputs are local under `.blend-analysis/2.5-real-user-tutorials/`. Human independent acceptance is required.

- First lesson: [English](../../../docs/user/en/first-aspirin.md) / [中文](../../../docs/user/zh-CN/first-aspirin.md).
- Offline guide: [English](../../../docs/offline/en/index.html) / [中文](../../../docs/offline/zh-CN/index.html).
- T01 local run: `.blend-analysis/2.5-real-user-tutorials/run-002/T01/run-manifest.json`.
- Paired project: `run-002/T01/aspirin.blend` and the complete adjacent `aspirin.cbq/` directory. Render: `aspirin-cycles.png`.

T00 diagnostics and T01 GUI conversion/import/View/render/save/cold reopen have run. Scientific checks and offline browser checks passed. The research checker still reports `incomplete`: GUI captures are native JPEG rather than the specified PNG, final visual review is pending, and no human independent replay has occurred. T02–T20 and B01 remain Not Run; this checkpoint does not close the overall plan.
