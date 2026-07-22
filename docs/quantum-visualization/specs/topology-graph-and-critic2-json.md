# TopologyGraph 与 critic2 JSON contract

## 数据对象

`TopologyGraph` 是 `PropertyDataset(domain="topology")`：

- `data`：cell critical points 的 Cartesian positions，dims 为 `(critical_point, xyz)`；
- 每个 critical point 有稳定 UUID、name、kind、rank、signature 和 multiplicity；
- field value 带 `field_semantic_role`；Laplacian 与 Hessian eigenvalues 使用独立 `ArrayData` 和显式单位；
- `TopologyConnection` 保存 bond/ring CP 到 attractor/repulsor 的 cell CP identity、lattice vector、distance 与 path length；
- `TopologyPath` 仅在来源提供有序 samples 时存在，不能用端点直线冒充梯度路径。

kind 映射：nuclear attractor、non-nuclear attractor、bond、ring、cage 分别由 `is_nucleus`
和 rank-3 signature `-3/-1/+1/+3` 决定。

## critic2 JSON adapter

adapter 读取 `cpreport output.json` 的 `critical_points.nonequivalent_cps` 与 `cell_cps`。critic2
内部 JSON writer 直接输出 internal Cartesian coordinates；v1 要求调用者显式传入 coordinate、field、
Laplacian 单位，不从文件名猜测。

解析严格验证：

- 声明数量与数组长度；
- 唯一正整数 ID 和有效 nonequivalent mapping；
- rank/signature/kind；
- 所有数值 finite；
- attractor/repulsor endpoint 存在；
- connection 恰有两个分支。

source bytes、adapter/version 与单位参数进入 revision/provenance。解析结果可直接作为 `ImportBatch`
提交到 `.cbq`。

## Blender 映射

critical points 写入单一 Mesh points，并带 kind/signature/field/Laplacian named attributes。
只有 `TopologyPath.samples` 生成 Curve；仅有 connectivity 时不创建虚假的直线 bond path。

## 非目标

- 不解析 human-readable `.cro` 表格。
- 不实现 basin integration 或 basin surface。
- 不从 graph XYZ 猜测 path 分组。
