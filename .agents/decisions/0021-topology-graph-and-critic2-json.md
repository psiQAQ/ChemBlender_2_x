# 0021：TopologyGraph 与 critic2 JSON

## Status

Accepted for Phase 4 topology ingestion and Blender mapping.

## Context

critic2 可输出 human-readable report、JSON 和 graph structure 文件。JSON writer 提供稳定字段与
connectivity，但不包含梯度路径的逐点采样；从端点生成直线会错误表达 bond path 几何。

## Decision

- `TopologyGraph` 作为 dataset 保存 critical-point positions、stable IDs、kind/rank/signature、
  multiplicity、field semantic/unit、Laplacian、Hessian eigenvalues 和 connectivity。
- `TopologyPath` 只接受至少两个 finite xyz samples；critic2 JSON adapter 不生成 path。
- signature `-3/-1/+1/+3` 映射 attractor/bond/ring/cage，`is_nucleus` 区分 nuclear 与 non-nuclear attractor。
- adapter 只读取 `cpreport JSON`，coordinate/field/Laplacian units 由调用者显式提供。
- nonequivalent mapping 和 connection endpoint 必须有效；未知 signature 或 dangling endpoint 失败。
- 当前 critic2 JSON writer 的 cell-count 字段可能与实际 `cell_cps` list 不同；adapter 报 warning 并以 list 为准。
- Blender 用一个 Mesh 保存 CP points 与 named attributes；只有真实 `TopologyPath` 创建 Curve。

## Consequences

- QTAIM/NCI 等不同标量场共享拓扑容器，同时保留 field semantic role。
- connectivity 可用于选择与关系查询，但没有 samples 时不冒充真实 gradient path。
- basin integration 和 surface mesh 仍需独立、带 fixture 的 schema。

## Verification Contract

1. 最小 critic2 JSON schema fixture 产生稳定 graph/point/connection identity。
2. invalid signature、dangling mapping/endpoint、非有限数值和错误 shape 被拒绝。
3. `TopologyGraph` 通过 `.cbq` lazy sidecar round-trip。
4. Blender 隔离安装验证 CP attributes、bohr-to-angstrom 和真实 sampled Curve。
