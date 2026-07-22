# IOData 波函数语义与 adapter 设计

## Goal

以 IOData 1.0.1 解析 FCHK 与 Molden，将结构、Gaussian basis 和分子轨道转换为 ChemBlender 自有、可验证且不依赖 IOData 生命周期的语义对象。

## Success Criteria

- restricted、unrestricted、generalized 轨道在内部模型中保持不同通道语义，不把 generalized 强行压成 alpha/beta。
- basis shell 保留中心原子、角动量、Cartesian/pure 类型、primitive exponent、contraction coefficient、basis function convention 与 primitive normalization。
- FCHK 与 Molden fixture 均生成 `Structure`、`BasisSet`、`OrbitalSet`，并可原子提交到 `QCProject`。
- 轨道系数、能量和 occupation 的 shape、单位与 basis function 数严格一致。
- IOData 及其 NumPy/SciPy/attrs 依赖只在外部 core 环境加载，不加入 Blender Extension wheel。

## Dependency Boundary

支持并验证 PyPI 包 `qc-iodata==1.0.1`。`submodules/iodata` 固定官方 `v1.0.1` commit `adab5813713ba64641565eb2a8c11803a4e9bba6`，用于源码审阅和固定 integration fixture。IOData 是 GPL-3.0-or-later，与本仓库 GPL-3.0 代码边界兼容；submodule 不进入 Extension ZIP。

IOData 以 atomic units 返回数据：坐标使用 bohr，轨道能量使用 hartree。adapter 不做无必要的单位换算，只将单位显式写入 normalized model。

## Semantic Model

### BasisShell

每个 shell 保存：

- `center_atom`：零基原子索引；
- `angular_momenta`：每个 contraction 的角动量；
- `kinds`：`cartesian` 或 `pure`；
- `exponents`：`(primitive,)`，单位 `inverse_square_bohr`；
- `coefficients`：`(primitive, contraction)`，dimensionless。

generalized contraction 不拆成多份重复 shell。`BasisShell.basis_function_count` 按 Cartesian `(l+1)(l+2)/2` 或 pure `2l+1` 计算。

### BasisConvention

保存 `(angular_momentum, kind, functions)`。`functions` 的顺序和可选负号原样保留，例如 pure harmonic 的 `c0`、`s1`、`-c3`。这使后续 GBasis/Grid 求值器能显式转换 convention，而不是假设 Gaussian 或 Molden 顺序。

### BasisSet

实体字段包括 UUID/revision、`structure_id`、名称、shell、convention、`primitive_normalization` 和 provenance。`QCProject.commit()` 验证中心原子索引、结构引用和 UUID 唯一性。

### OrbitalChannel

一个 channel 保存：

- label：`restricted`、`alpha`、`beta` 或 `generalized`；
- coefficients：普通 channel 为 `(orbital, basis_function)`；generalized 为 `(orbital, spin_basis_function)`；
- energies：可选 `(orbital,)`，hartree；
- occupations：可选 `(orbital,)`，dimensionless；
- irreps：可选、每轨道一个字符串。

### OrbitalSet

`kind` 使用 `restricted`、`unrestricted`、`generalized` 枚举：

| kind | channels | 系数宽度 |
| --- | --- | --- |
| restricted | 一个 `restricted` | `nbasis` |
| unrestricted | `alpha`、`beta` 各一个 | 各 `nbasis`，轨道数可不同 |
| generalized | 一个 `generalized` | `2 * nbasis` |

这种表示避免为了建立规则三维数组而填充不同数量的 alpha/beta 轨道，也避免丢失 generalized spinor 的两倍 basis 维度。

## IOData Mapping

| IOData 字段 | ChemBlender | 处理规则 |
| --- | --- | --- |
| `atnums`, `atcoords` | `Structure` | `(atom, xyz)`, bohr |
| `obasis.shells` | `BasisShell` | 数组复制并验证 |
| `obasis.conventions` | `BasisConvention` | key 排序，函数顺序原样保留 |
| `obasis.primitive_normalization` | `BasisSet` | `L2`/`L1` 规范化为小写 token |
| restricted `mo` | 一个 restricted channel | IOData `(basis, orbital)` 转置 |
| unrestricted `mo` | alpha/beta channel | 按 `norba`/`norbb` 切列并转置 |
| generalized `mo` | generalized channel | `(2*basis, orbital)` 转置，不拆 spin |
| `mo.energies` | channel energies | hartree |
| `mo.occs` | channel occupations | restricted 保留 spin-summed occupation |
| `mo.irreps` | channel irreps | 字符串化，不编码进数值数组 |

adapter 不通过 IOData 的 `coeffsa`/`coeffsb` 属性处理 generalized，因为上游明确对 generalized 抛出 `NotImplementedError`。

## Public API and Reader

```python
adapt_iodata(data, source, *, iodata_version="unknown") -> ImportBatch
parse_iodata_wavefunction(source) -> ImportBatch
```

`parse_iodata_wavefunction` 延迟 import `iodata.load_one`。reader ID 为 `iodata_wavefunction`，首版扩展名为 `.fchk`、`.fch`、`.molden`、`.input`，capability 为 structure、basis_set、orbital。sniff 只接受 FCHK 的 typed record 标记或 `[Molden Format]`。

缺少结构、basis、MO 或 coefficient 时解析失败。可选 energies、occupations、irreps 缺失时创建部分 `OrbitalSet` 并产生 `missing` issue，不制造零数组。未映射 IOData 属性名写入 provenance 和一个 `unsupported` issue。

## Fixture Strategy

固定 upstream fixture：

- restricted FCHK：`water_sto3g_hf_g03.fchk`；
- unrestricted FCHK：`ch3_hf_sto3g.fchk`；
- Molden：`h2o.molden.input`。

标准测试使用 synthetic IOData-like objects 验证模型和转换；可选 integration 环境安装 submodule 后真实解析三份 fixture。generalized 由 synthetic model/adapter test 覆盖，因为 FCHK/Molden 通常不携带 generalized spinor。

## Non-goals

- 本阶段不映射 RDM、gradient、Hessian、优化轨迹、WFX/WFN/MWFN。
- 不实现 AO/MO 数值求值、密度网格、ESP 或等值面。
- 不建立 lazy array store；当前小型 fixture 数组复制到 normalized entity。
- 不将 basis shell 展开为逐 basis-function 大表。
