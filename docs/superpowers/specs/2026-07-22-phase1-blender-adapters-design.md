# Phase 1 Blender adapters 收口设计

## 目标

把 Phase 1 normalized `Structure`、`AtomicProperty`、`FrameSet`、`VibrationalModeSet`、`ExcitedStateSet` 与 stick `Spectrum` 映射到同一 Blender Mesh 身份，同时保持 core 为权威数据源。

## 已确认边界

- Blender Mesh 顶点顺序对应 zero-based atom index；`cbq_atom_id` 是稳定 POINT-domain integer attribute。
- `.blend` 只保存 structure/dataset UUID、revision、当前 frame/selection 和显示参数；完整 trajectory、spectrum 或量化数组不写入 custom properties。
- 一个对象只有一个当前原子矢量视图，统一使用 `cbq_vector`、`cbq_vector_magnitude` 和 `vector_arrow_v1` Geometry Nodes contract。
- `FrameSet` 留在 Python 内存 binding 中；`frame_change_post` 只更新现有 Mesh 顶点坐标。重开恢复和 lazy sidecar 属于 Phase 3。
- broadened spectrum 的 sample 不等价于单一 state/mode；只有 stick spectrum 可以直接建立 source entity selection。

## Structure view

`create_structure_view` 从 normalized `Structure` 创建一个无键 Mesh 点集，并写入：

- `atomic_num`：兼容现有 ChemBlender 节点；
- `cbq_atom_id`：`0..N-1`；
- object custom properties：structure UUID/revision、source/display coordinate unit 与 contract version。

坐标统一显示为 angstrom；bohr 使用固定换算。拓扑和球棍 Geometry Nodes 沿用现有系统，不在本切片重建键。

## Atomic scalar

`apply_atomic_scalar` 只接受 `(atom,)` `AtomicProperty`：

- 数值写入 `cbq_atom_scalar`；NaN 作为 missing，写 `0` 占位并由 `cbq_atom_scalar_valid` mask 标记；无穷和复数拒绝；
- 同步写 `colour` POINT color 供现有节点消费；缺失值为中性灰；
- 自动或显式 display range、symmetric range、unit、semantic role、dataset UUID/revision 写入 object metadata。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `obj` | 必填 | 已绑定同一 `structure_id` 的 Mesh object |
| `dataset` | 必填 | `(atom,)` `AtomicProperty` |
| `display_min` | 自动 | 与 `display_max` 同时提供的色域下界 |
| `display_max` | 自动 | 与 `display_min` 同时提供的色域上界 |
| `symmetric` | `False` | 以零为中心扩展为对称色域 |

## Atomic vector 与 vibration

`apply_atomic_vector` 接受 `(atom, xyz)` `AtomicProperty`，按 display scale 写入通用 vector attributes，并挂载一个 instanced-cone node modifier。`vibration_view` 复用同一 helper，只额外保存 reference positions、mode identity 和 phase 动画状态。

箭头采用 instancing，不为每个原子创建 Object。重复应用更新属性和 metadata，不叠加 modifier。

## Trajectory

`configure_trajectory_view` 绑定 Mesh 与 `FrameSet`：

- `frame_start` 与正整数 `frame_step` 将 Blender frame 映射到 trajectory index，范围外 clamp；
- handler 只写当前帧坐标并记录 `cb_trajectory_frame_index`；
- bindings 只在内存中存在，disable/unregister 时清空并移除 handler；
- object 删除或失效时自动清理 binding。

## Selection

- `apply_atom_selection` 将 atom index 集合编码为 `cbq_selected` boolean named attribute。
- `link_stick_spectrum_selection` 验证 `SpectrumProfile.STICK`、source UUID、kind/source 类型和 sample count，再记录 spectrum UUID、source dataset UUID、domain 与 zero-based entity index。
- UI 可以显示 one-based state/mode label，但内部 index 不变。

## cclib identity 修正

cclib schema 4 将 charge/spin datasets 变为带 `structure_id` 的 `AtomicProperty`，使真实 Gaussian/ORCA 输出可直接进入 scalar adapter。`grads` 仍由 capability report 明确标为 unsupported，直到 frame-aligned vector dataset 语义完成；本切片不静默截取最后一个 gradient。

## 验证

- 普通 Python tests 验证 cclib schema 4 的 typed atom identity 与项目引用。
- Blender package smoke 创建 normalized structure view，检查标量/missing mask/color/range、通用箭头实例、trajectory handler 更新和 stick selection identity。
- 重复 enable/disable 后 handler 与 node group 不重复。
- Extension ZIP 不包含 cclib、fixture、submodule 或测试。

## 非目标

- 最终面板、2D plot widget、色标对象、键重建、长轨迹插值/缓存和 `.blend` 重开恢复；
- 从 broadened peak 猜测单一 transition；
- 截断或伪装 cclib 多帧 force/gradient history。
