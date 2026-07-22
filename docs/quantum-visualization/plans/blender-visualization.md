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
| P0 | 已完成单一 instanced-arrow node contract 与 Volume/OpenVDB；继续原子标量、当前帧轨迹、mesh fallback、色标与单位 | 属性 ID 稳定；箭头数量不增加 Object；缓存可重建 |
| P1 | 已完成振动 phase adapter 与 IR/Raman 数据；继续 UV-Vis、激发态、轨道选择、linked selection、表面顶点着色 | 光谱选择与三维对象使用同一 dataset/state ID |
| P2 | publication templates、linked brushing、比较视图和高级交互 | 有明确工作流和维护成本预算 |

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

## 参考仓库触发条件

- 轨迹、session、选择和整数标签编码进入实施时审阅 Molecular Nodes。
- ASE/周期结构映射和 volume 着色进入实施时审阅 Beautiful Atoms。
- Avogadro/CJSON 只在交换或 UI 工作流进入 P1 时审阅；不为界面灵感提前拉取仓库。
