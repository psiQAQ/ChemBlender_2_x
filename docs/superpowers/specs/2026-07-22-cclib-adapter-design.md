# cclib 最小解析闭环设计

## Goal

将 Gaussian 与 ORCA 输出中的结构、SCF 能量和原子布居从 cclib `ccData` 转换为 ChemBlender normalized model，同时保持 Blender Extension 与第三方解析依赖隔离。

## Success Criteria

- `.log`/`.out` 通过内容识别进入 cclib reader，不依赖扩展名猜测程序。
- 单点和多步坐标分别生成最终 `Structure` 与可选 `FrameSet`。
- `scfenergies`、`atomcharges` 和 `atomspins` 转换为带单位、维度和计算来源的 `PropertyDataset`。
- `metadata.success` 决定 `CalculationRecord.status`；缺失或未映射内容进入 `ParserReport` 或 provenance，不静默伪造完整数据。
- adapter 模块导入不要求 cclib、SciPy 或 NumPy；真实解析只在独立 core 环境中加载 cclib。
- 官方 Gaussian 与 ORCA fixture 均通过真实 cclib 1.8.1 解析和项目提交验证。

## Dependency Boundary

支持并验证 `cclib==1.8.1`。cclib 及其 NumPy、SciPy、periodictable、packaging 依赖属于独立 `chemblender-qc-core` 环境，不加入 `ChemBlender/blender_manifest.toml`，也不在 Blender import、`register()` 或 enable 时安装。

`submodules/cclib` 固定在官方 `v1.8.1` commit `07260dd0394cb1a2381d4d897746d727a12ad6ce`，用途仅为：

- 审阅 parser 字段和 capability；
- 保存固定版本源码证据；
- 复用上游 Gaussian/ORCA 测试数据进行可选 integration test。

运行时通过正常 Python 环境安装 `cclib==1.8.1`。submodule 不是 Extension 包内容，也不是运行时 import path。

## Public API

`ChemBlender.core.cclib_adapter` 提供两个入口：

```python
adapt_ccdata(data, source, *, cclib_version="unknown") -> ImportBatch
parse_cclib_output(source) -> ImportBatch
```

`adapt_ccdata` 是可直接测试的纯转换边界；`parse_cclib_output` 延迟导入 `cclib`，调用 `cclib.io.ccread`，并将实际 cclib 版本写入 provenance。依赖缺失或 cclib 无法识别文件时抛出明确错误，不返回空 batch。

reader descriptor：

| 字段 | 值 |
| --- | --- |
| `reader_id` | `cclib_output` |
| `reader_version` | adapter schema `2`（schema 1 为 structure/energy/atomic property；schema 2 增加 vibration） |
| extensions | `.log`, `.out` |
| priority | `80`，低于明确格式 reader |
| capabilities | structure、trajectory、energy、atomic_property |

首版 sniff 只对 Gaussian 与 ORCA 强标记返回 `EXACT`，普通 `.log`/`.out` 不返回可能匹配。以后增加程序时必须先提供稳定 token fixture。

## Field Mapping

| cclib 字段 | normalized object | 语义、维度与单位 |
| --- | --- | --- |
| `atomnos`, `atomcoords[-1]` | `Structure` | coordinates `(atom, xyz)`, `angstrom` |
| 多帧 `atomcoords` | `FrameSet` | coordinates `(frame, atom, xyz)`, `angstrom` |
| `scfenergies` | `PropertyDataset` | `scf_energy`, domain `calculation_step`, `(step,)`, `electron_volt` |
| `atomcharges[name]` | `PropertyDataset` | `<name>_charge`, domain `atom`, `(atom,)`, `elementary_charge` |
| `atomspins[name]` | `PropertyDataset` | `<name>_spin_population`, domain `atom`, `(atom,)`, `dimensionless` |
| `metadata.success` | `CalculationRecord.status` | true=`success`、false=`failed`、缺失=`incomplete` |
| package/version/method/basis/charge/mult | `ProvenanceRecord.parameters` | 保留来源计算上下文 |

最终结构是 `CalculationRecord.result_structure_ids`。cclib 输出没有可靠的独立输入结构语义时，不伪造 `input_structure_ids`。

## Report Rules

- 缺少 `atomnos` 或 `atomcoords`：解析失败，因为无法建立最小结构闭环。
- 没有 `scfenergies`：产生 `missing` issue，且不声明本次已解析 `energy`。
- 没有原子 charge/spin：产生 `missing` issue，且不创建空数据集。
- `metadata.success` 缺失：计算状态为 `incomplete`，产生 `ambiguous` issue。
- adapter 当前未转换但 cclib 已解析的字段名，排序后写入 provenance 的 `unmapped_attributes`，并产生一个 `unsupported` issue。
- 所有数组验证 rank、atom 维度与有限值；无效 shape 直接失败。

## Fixture and Verification

真实 integration fixture 直接引用固定 submodule：

- Gaussian 16: `data/Gaussian/basicGaussian16/water_hf_solvent_cpcm.log`
- ORCA 4.1: `data/ORCA/basicORCA4.1/water_mp2.out`

标准测试不强制安装可选依赖；adapter 单元测试覆盖转换、状态、缺失字段和 sniff。安装 cclib 且初始化 submodule 后，integration test 必须真实解析两份输出并提交到 `QCProject`。

## Non-goals

- 本阶段不映射 MP/CC energy、收敛数组、振动、激发态、MO 或基组。
- 不把所有 cclib parser 的理论 capability 宣称为 ChemBlender 已实现 capability。
- 不复制上游量化输出 fixture 到本仓库。
- 不建立 worker、IPC、sidecar backend 或新的发行包。
