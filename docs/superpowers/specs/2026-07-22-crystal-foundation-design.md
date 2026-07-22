# Gemmi/spglib 晶体基础设施设计

## 目标

用 Gemmi 0.7.5 解析 CIF 语法与小分子/无机晶体站点，用 spglib 2.7.0 分析输入晶胞的空间群并生成可追溯的标准晶胞。两者只存在于独立 core/worker 环境，Blender Extension 继续只消费 normalized model。

## 职责边界

- Gemmi 负责 CIF block、pair、loop、quoted value、不确定度数值、site、occupancy、ADP 与声明的空间群信息。
- `CIFEnvelope` 保存精确 source bytes、block name 和完整 tag 名单；未知 tag 不被 normalized model 丢失。
- `PeriodicSiteData` 附着到 `Structure`，保存 fractional coordinates、site label、occupancy、Uiso/Uij、ADP type、disorder group、声明空间群和 symmetry-operation strings。
- spglib 只消费完整占位、无 disorder 的 periodic `Structure`，返回输入晶胞坐标系中的 operations，以及标准 setting 的 identity、Wyckoff、等价原子和变换。
- 标准晶胞是新的 derived `Structure`，不覆盖输入结构；`SymmetryResult` 同时引用输入和标准结构。

## 数据约定

### CIFEnvelope

| 字段 | 约束 | 作用 |
| --- | --- | --- |
| `id/revision` | UUID 与非空 revision | 项目身份与缓存版本 |
| `block_name` | 非空 | 选择的 CIF data block |
| `source_bytes` | 非空 bytes | 精确保留原输入与未知内容 |
| `tag_names` | 按 block 顺序展开的完整 tag | 快速能力/未知 tag 检查 |
| `provenance_ids` | UUID tuple | 来源追踪 |

当前 reader 明确要求一个 data block；多 block 文件在选择策略完成前报错，不静默只取第一个。

### PeriodicSiteData

- `fractional_coordinates`: `(atom, xyz)`, `dimensionless`；笛卡尔坐标由 `fractional @ cell` 得到。
- `occupancies`: `(atom,)`, `dimensionless`，范围 `0..1`。
- `isotropic_displacements`: 可选 `(atom,)`, `angstrom_squared`。
- `anisotropic_displacements`: 可选 `(atom, tensor_component=6)`, `angstrom_squared`，顺序 `U11,U22,U33,U12,U13,U23`。
- label、ADP type、disorder group 均保持 atom 顺序；声明的 H-M/IT number 与原始 symmetry operations 不等同于 spglib 派生结果。
- `cif_envelope_id` 对 CIF 来源为 UUID；POSCAR、ASE 或其他非 CIF 来源可为 `None`。

### SymmetryResult

- rotations/translations 使用 input fractional basis；对应 `x' = W x + w`。
- `transformation_matrix` 与 `origin_shift` 采用 spglib 2.7 定义：标准 basis 由输入 basis 与 `P^-1` 关联，标准 fractional coordinate 为 `P x + p (mod 1)`。
- 保存 Hall number、IT number、international/Hall symbol、choice、point group、Wyckoff、site symmetry、equivalent atoms、crystallographic orbits、primitive mappings 和 standard rotation。
- `symprec` 统一解释为 angstrom；bohr 输入在调用 spglib 前显式转为 angstrom。

## 失败与歧义

- Gemmi 缺失、语法错误、无晶胞、无 atom site、未知元素、非有限数值或多 block 直接失败。
- 部分占位与 disorder 可解析并进入 `ParserReport.warning`，但不自动交给 spglib，防止忽略占位后得到伪空间群。
- 缺失 Uiso/Uij 表达为 `None`，不伪造零值；Gemmi 默认值不能覆盖 tag-presence 判断。
- spglib 无结果、非法 tolerance、非周期结构或 atom count 不一致直接失败，不产生部分 `SymmetryResult`。

## Reader contract

`CIF_READER` 声明 `.cif`，并以 bounded prefix 中的 `data_`、cell tag 和 atom-site tag 组合 sniff。parse 返回一个 `Structure`、一个 `CIFEnvelope`、一个 `ProvenanceRecord` 与 `ParserReport`；reader 不直接执行 spglib 标准化。

## 打包与许可证

- `gemmi==0.7.5`（MPL-2.0）与 `spglib==2.7.0`（BSD-3-Clause）仅安装在开发/worker 环境。
- 参考源码固定为 Gemmi `5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e`、spglib `12355c77fb7c505a55f52cae36341d73b781a065`。
- Extension ZIP 不包含两个包或 submodule；未来分发 worker 时单独保留许可证与 notices。

## 非目标

- 本切片不删除现有 Blender `read_cif`/POSCAR/UI 路径，也不承诺无损格式化 round-trip。
- 不处理磁空间群、modulated CIF、多个 data block 选择、occupancy-aware symmetry 或 CIF dictionary validation。
- 不引入 ASE/pymatgen，也不把标准晶胞自动替换当前 Blender scene。
