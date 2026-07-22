# TopologyGraph and critic2 JSON implementation plan

## Goal

实现中立拓扑模型、critic2 `cpreport JSON` adapter、sidecar round-trip 与 Blender point/path adapter。

## Plan

1. 用最小、注明来源的 JSON fixture 写 model/parser 失败测试。
2. 实现 critical points、connections、sampled paths 及 QCProject 引用校验。
3. 实现严格 critic2 JSON parser、stable identity、provenance 和 ParserReport。
4. 实现单 Mesh critical-point attributes；仅对真实 sampled paths 创建 Curve。
5. 更新 ADR/状态并运行 core、sidecar、Blender 实机验证。

## Verify

- `python -m unittest tests.test_critic2_topology`
- `python -m unittest discover -s tests`
- Blender Extension validate/build 与隔离 topology smoke
- `git diff --check`
