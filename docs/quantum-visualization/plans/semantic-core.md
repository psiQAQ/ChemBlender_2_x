# 语义核心开发计划

## 范围

建立不依赖 `bpy` 的最小量子化学语义层，使 parser、worker 和 Blender adapter 共享相同的数据身份、数组维度、单位与来源记录。

## 非目标

- 本主题不实现文件 parser、Blender UI 或数值求值后端。
- 不一次定义全部轨道、激发态和周期电子结构字段。
- ADR 完成前不决定独立 Python 包或 Extension 内子包的最终位置。

## 优先级

| 优先级 | 内容 | 进入下一优先级的条件 |
| --- | --- | --- |
| P0 | `Structure`、`CalculationRecord`、`PropertyDataset`、`Grid3D`、`ParserReport`、`Provenance`；统一 `dtype/shape/dims/unit/source` | 两种结构格式归一化一致；普通 CPython 测试通过；core 无 `bpy` |
| P1 | `OrbitalSet`、`VibrationalModeSet`、`ExcitedStateSet`、`Spectrum`、周期数据专用容器 | Phase 1 有真实 fixture，通用 `PropertyDataset` 已不足以清晰表达 |
| P2 | `TopologyGraph`、数据库记录、跨项目 provenance graph | critic2/数据库 connector 已进入获批任务 |

## 依赖关系

P0 依赖五项数据边界 ADR。reader、Blender adapter、存储和 worker 都依赖 P0 对象身份与数组契约。第三方库只能由 adapter 使用，不能改变内部模型的权威字段。

## 交付物

- 版本化的最小 schema 与字段说明。
- 对象构造、数组 shape 和单位验证规则。
- 缺失、歧义与 partial 数据的表示方法。
- 普通 CPython contract tests 和小型序列化示例。

## 验收标准

- core import 不触发 `bpy`、RDKit 或 Blender runtime。
- 数组维度名与 shape 一致；数值有单位或 dimensionless 标记。
- 未支持字段和失败计算不会被转换为空数组后静默继续。
- 来源文件、parser version 和派生关系可追踪。
- 同一结构从两个 reader 进入后得到等价的 normalized representation。

## 参考仓库触发条件

- 需要校对单位、计算记录和 provenance 时审阅 QCElemental/QCSchema。
- 需要比较最小结构容器时审阅 xyzrender 与 ASE。
- 只有逐行审阅或运行对照测试时才添加 submodule；API 文档足够时不拉仓库。
