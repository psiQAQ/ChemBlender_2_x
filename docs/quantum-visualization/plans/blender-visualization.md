# Blender 可视化映射开发计划

## 范围

把 normalized datasets 映射为 Geometry Nodes attributes、Volume、Mesh、Curve、Material、动画和 2D plot，并保留 dataset ID 与显示参数。

## 非目标

- Blender datablock 不成为量子化学数据模型或大型数组仓库。
- 不为每个箭头、轨迹帧或轨道创建独立 Object 集合。
- 能带和 DOS 不强行全部用 Geometry Nodes 绘制。

## 优先级

| 优先级 | 内容 | 验证重点 |
| --- | --- | --- |
| P0 | 已完成原子标量、instanced-arrow、当前帧轨迹、周期 structure/grid 与 Volume/OpenVDB | 属性 ID 稳定；箭头数量不增加 Object；缓存可重建 |
| P1 | 已完成振动、IR/Raman、UV-Vis/ECD、stick selection、Spectrum/band/DOS Curve 与 property-on-surface | 光谱选择与三维对象使用同一 dataset/state ID |
| P2 | 已完成 versioned publication scene presets 与原子应用/回滚；linked brushing、比较视图按具体 UI 交互需求触发 | scene identity、binding 与 adapter metadata 可重放 |

## 依赖关系

依赖语义核心、`Grid3D`、缓存身份和边车恢复协议。节点组沿用当前 ChemBlender 组合方式；新增 adapter 不复制解析逻辑。

## 交付物

- structure、atom property、vector、grid、surface、spectrum、trajectory adapter 契约。
- Geometry Nodes 属性名、domain、dtype 与 ID 编码表。
- 原子标量、矢量、轨迹和表面的最小场景 fixture。
- `.blend` 中 project/dataset UUID、显示参数和缓存引用的保存规则。

## 验收标准

- `.blend` 只保留 ID、当前显示状态和可重建对象，不保存权威大型数组。
- 原子标量显示色标、单位、分析方法、范围和缺失值。
- 矢量用 instancing；长轨迹只更新当前帧位置属性。
- 轨道正负相位使用两个明确 dataset 或 surface，不依赖法向猜测。
- register/unregister/reload 和重开文件后 dataset 引用仍可恢复。

## 当前进度

基础 structure/dataset/vector/trajectory/vibration/electronic plot/topology/Fermi-surface adapters、
[scene preset v1](../specs/scene-preset-v1.md) 及其 Blender application 已完成。当前可原子地
重放 structure、vibration/electronic spectrum 和 band/DOS plan；stale plan 与 adapter
中途失败不会留下对象。signed isosurface 现使用两个明确相位的 OpenVDB，
property-on-surface 在同 affine grid 上采样 `cbq_surface_property` 并用 `coolwarm` 材质映射；
三者均受 scene render identity 和原子回滚约束。

## 参考仓库触发条件

- 轨迹、session、选择和整数标签编码进入实施时审阅 Molecular Nodes。
- ASE/周期结构映射和 volume 着色进入实施时审阅 Beautiful Atoms。
- Avogadro/CJSON 只在交换或 UI 工作流进入 P1 时审阅；不为界面灵感提前拉取仓库。
