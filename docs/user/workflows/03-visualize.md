# 展示数据

Project 中的 Structure、Grid3D、属性和结果是科学实体；Blender Object、material、Volume 和 surface 是 View。View 可以重建，也可以有多个。不要从“场景里看得见”推断数据已经写回 Project。

## 要完成什么

- 创建或检查 Structure View。
- 从 Cube 的 Grid3D 创建 Volume 或 Signed Surface。
- 把兼容的 property grid 映射到 surface。
- 播放 trajectory 或 PDB MODEL frames。
- 在缓存缺失时从已验证 Grid3D 重建 View。

## 示例

用 [two-datasets.cube](../../../examples/user-workflows/inputs/cube/two-datasets.cube)练习多 dataset Grid3D。结构与轨迹可用 [carbon-trajectory.extxyz](../../../examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz)和 [multimodel.pdb](../../../examples/user-workflows/inputs/pdb/multimodel.pdb)。轻量结果展示可用 [water-results.cjson](../../../examples/user-workflows/inputs/cjson/water-results.cjson)和 [atomic-result.json](../../../examples/user-workflows/inputs/qcschema/atomic-result.json)。

## 操作前检查

1. 在 Project Browser 选中目标科学实体，核对 source revision、单位、semantic role、shape 和 quality。
2. Cube 有多个 dataset 时必须明确 dataset index；不要把第一个 dataset 当作自动正确选择。
3. `Ambiguous` Grid3D 先检查 preset、value unit 和诊断。未解决语义时，`Signed Surface` 可能被禁用。
4. 保存或导出截图前，确认当前 View binding 指向预期 Structure/Grid revision。

## UI 操作

### Structure View

1. Quick Import 的 Default View 选择 `Structure`，或在 Project Browser 选择目标 Structure 的可用 View 操作。
2. 检查 atom count、cell、topology binding 和 quality。
3. 可以调整 Blender transform、visibility 和 material。这些操作只改 View。

### Grid Volume 与 Signed Surface

1. 导入 Cube 并在 Project Browser 选中 Grid3D。
2. 如果状态是 `Ambiguous`，选择 dataset index、preset 和 value unit，再运行 `Resolve Grid Semantics`。
3. 设置 isovalue。
4. 选择 `Volume` 创建体渲染，或选择 `Signed Surface` 创建正负等值面。按钮被禁用时先查看 availability/quality，而不是绕过检查。
5. 如果存在兼容 property Grid，选择 `Map <Property>` 把它映射到 surface。

### trajectory 与 MODEL playback

1. 选中 extXYZ FrameSet 或 PDB multi-model 数据对应的 View。
2. 核对 frame/model count 与起止帧。
3. PDB 使用 `Configure MODEL Playback`。播放时观察几何变化，并确认 Project Browser 中仍是同一 source revision。

### 缓存重建

ChemBlender 自有的 Volume/Surface cache 位于 sidecar 的 derived cache 范围。冷重开时，如果 cache 缺失但 `.cbq` 中 Grid3D 完整，系统可以重建。外部 Volume 路径不会被 ChemBlender 接管。不要删除 sidecar manifest 或 authoritative arrays 来测试重建。

## 屏幕上应看到什么

- Structure View 有与 Project Structure 对应的原子，并记录 View binding。
- Volume/Signed Surface 创建期间有进度；完成后报告创建的 Grid view object 数量。
- `two-datasets.cube` 的 dataset 选择是显式状态，改变 index 后得到对应 dataset 的 View。
- trajectory/MODEL 播放改变 View 帧，不会产生新的 source revision。

## 成功判据

1. Project Browser 中的科学实体在删除 View 后仍存在。
2. 重建 View 后，绑定的 entity/revision、dataset index、unit 和 isovalue 与原设置一致。
3. Volume/Surface 使用的是 ChemBlender 自有 cache 路径；缺失 cache 可从 Grid3D 重建。
4. 关闭并重开 `.blend` 后，代表性 View 或其可重建状态仍可验证。
5. Blender material 或灯光变化不会修改 `.cbq` 的科学 revision。

## Agent 提示词

> 在 Blender 5.1 中通过 ChemBlender 公开 Operator 导入 `examples/user-workflows/inputs/cube/two-datasets.cube`。在 Import Preview 后从 Project Browser 选中 Grid3D，读取公开 RNA 的 status、dims、dataset count 和 unit；显式选择一个 dataset，必要时运行 Resolve Grid Semantics，再创建 Volume 或 Signed Surface。完成后验证 View binding、dataset index、isovalue 和对象存在。不要直接调用私有 cache/service 函数。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `Signed Surface` 灰色 | 先解决 Grid semantic、dataset index、unit 和 signed-data 条件；不要直接用 `bpy.data` 伪造 View binding |
| 重开后 Volume 路径失效 | 先验证 `.blend`/`.cbq` link，再让插件从 authoritative Grid3D 重建自有 cache |
| 修改 material 后导出科学文件没有变化 | 正常。材质是 View；科学导出从 Project entity 读取 |
| 播放帧数不对 | 核对 extXYZ FrameSet 或 PDB MODEL count，以及 View 绑定的 source revision |
| CJSON/QCSchema 没有自动专用 View | 先看导入到哪些实体与属性。当前 UI 只为可支持的 Structure/Grid/属性创建 View，不为每种 envelope 建独立面板 |

继续：[导出数据](04-export.md)。
