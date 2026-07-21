# Reader 与格式能力开发计划

## 范围

建立 reader registry、内容探测、capability matrix 与 `ParserReport`，把第三方 parser 输出转换为 ChemBlender 语义对象。

## 非目标

- 不让扩展名白名单继续充当格式能力声明。
- 不把 cclib `ccData`、IOData 或 ASE 对象直接交给 Blender。
- 不在 import、`register()` 或 enable 时安装 parser 依赖。

## 优先级

| 优先级 | 内容 | 主要验证 |
| --- | --- | --- |
| P0 | registry、extensions + sniffing、capability 状态、`ParserReport`、MOL2 声明回归、cclib/IOData/Gemmi/spglib adapter 边界 | 真实 fixture 能区分 supported、partial、unsupported、ambiguous |
| P1 | ASE、QCSchema v1/v2、CJSON、Cube 与周期体数据 adapter | round-trip 或字段级对照不静默丢数据 |
| P2 | phonopy、critic2、Multiwfn、MD trajectory 和数据库 connector | 对应 Phase 已批准，且外部输出有稳定 fixture |

## 依赖关系

本主题依赖语义核心、单位与 `Grid3D` ADR。Gemmi/spglib 的落地还依赖现有 CIF、POSCAR 和空间群路径的回归测试。新增第三方包必须先完成依赖与打包决策。

## 交付物

- reader 注册和选择契约。
- 格式与物理量 capability matrix。
- cclib、IOData、Gemmi/spglib 等 adapter 的字段映射表。
- golden fixtures、错误输出和不完整计算样本。
- MOL2 声明与真实 reader 能力保持一致的回归测试。

## 验收标准

- `.log`、`.out` 等模糊扩展名通过内容探测选择 reader。
- 每次解析返回 reader/version、parsed、missing、ambiguous、warnings 和终止状态。
- capability matrix 由测试生成或校验，不由文档手工猜测。
- parser 可在普通 CPython 中测试；Blender adapter 只消费 normalized model。
- 非标准输入、失败计算和不完整文件有明确错误，不产生伪完整记录。

## 参考仓库触发条件

- 设计 registry、Cube 契约和 fixture 结构时审阅 xyzrender。
- Gaussian/ORCA/Q-Chem 等输出进入实施时审阅 cclib parser coverage。
- FCHK/Molden/WFN/WFX 进入实施时审阅 IOData convention handling。
- CIF/空间群替换进入实施时审阅 Gemmi 与 spglib；只在需要固定代码证据时添加 submodule。
