# ADR 0041：Cube 结构引用与派生视图边界

## Status

Accepted for the Wave 1 Cube pre-gate.

## Context

Cube 同时携带原子信息和连续三维场。项目已经有 `Structure`、`Grid3D`、`.cbq`
权威存储以及可删除重建的 OpenVDB/Blender 视图；为 Cube 再定义结构、原子或缓存
模型会造成同一科学实体的多套权威表示。

## Decision

### 原子与连续场

- Cube 的 atomic number 与坐标进入现有 `Structure`。
- 原子 nuclear charge 等逐原子科学量进入引用同一结构的
  `AtomicProperty`，不进入 `Grid3D`，具体保留属于 Cube Task 1。
- 连续场的 origin、完整 step vectors、shape、values、value unit 和语义进入
  现有 `Grid3D`。
- 同一 Cube 产生的 `Grid3D.structure_id` 必须引用该文件产生的
  `Structure.id`。
- 不创建 `CubeAtom`、`CubeStructure` 或第二套项目注册表。

`Grid3D.structure_id` 保持可选，以允许不含或尚未绑定结构的通用派生网格；只要
reader 同时创建了结构，就必须写入该引用。`QCProject` 继续在事务边界拒绝悬空
引用。

### 单位和 provenance

`Structure.coordinates.unit` 与 `Grid3D.coordinate_unit` 分别声明结构坐标和
网格几何使用的长度单位；`Grid3D.data.unit` 单独声明场值单位。`bohr` 与
`angstrom` 是不同 token，不允许仅修改 token 而不转换数值。

来源单位、格式约定和任何数值换算记录在 `ProvenanceRecord.parameters`。发生
换算时继续遵守 ADR 0004 的 `from_unit`、`to_unit`、`scale`、`offset`
契约。不增加 `native_unit`/`display_unit` 字段或单位依赖。

### 科学数据与派生视图

`QCProject` 中的 `Grid3D` 和 provenance 是权威科学数据。OpenVDB、Blender
Volume、Geometry Nodes 输出和等值面 Mesh 是可删除的派生视图：

- 不进入权威 grid values；
- 不作为重新导出或恢复科学数据的来源；
- cache identity 继续包含输入 UUID/revision、dataset index、操作版本和参数；
- cache 丢失后由 sidecar 中的 `Grid3D` 重建，不改变科学实体 revision。

现有 `SurfaceProperty` 仅表示 `FermiSurfaceMesh` 上的 vertex/face 属性，不扩展
成 Cube 等值面的第二套科学实体。若未来需要持久化科学表面，必须有独立数据与
可逆性需求后另行决策。

### Source calculation

已有 `PropertyDataset.source_calculation` 和 `provenance_ids` 表达来源计算和
解析链路。Cube reader 不增加格式专用 calculation 字段；有真实 calculation
记录时使用现有引用。

## Consequences

- Cube、XYZ、MOL/SDF、QCSchema 和计算派生网格共享同一结构模型。
- `.blend` 或 VDB 损坏不会破坏权威场数据。
- Cube Task 1 只需保留 nuclear charge 和 dataset/source metadata，无需迁移
  当前 `Grid3D` 或新增格式专用结构类型。

## Rejected Alternatives

- **格式专用 Cube 结构/原子类型**：重复 `Structure` 与 `AtomicProperty`。
- **把 VDB 作为科学数据**：无法可靠恢复单位、完整数组和 provenance。
- **保存 mesh 后删除 Grid3D**：表面采样不可逆，无法重新导出或复验。
- **新增单位对象或双 unit 字段**：现有 token 与 provenance 已覆盖本阶段需求。

## Verification Contract

1. Cube import 的 grid 立即引用同 batch 的 structure。
2. 悬空 grid 引用在项目事务提交时被拒绝。
3. `structure_id`、coordinate unit 和 value unit 经过 canonical document 与
   `.cbq` save/reopen 后不变。
4. `bohr` 与 `angstrom` 不被静默混用；显示换算不改权威 Grid3D。
5. 删除 ChemBlender-owned VDB 后可从 sidecar Grid3D 重建。
6. `ChemBlender.core` 在普通 CPython 中导入时不加载 `bpy`。
