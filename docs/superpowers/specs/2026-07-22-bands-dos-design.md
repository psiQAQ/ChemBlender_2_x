# Phase 2 Band Structure 与 DOS 设计

## Scope

本阶段建立 ChemBlender 自有 periodic electronic-structure schema，并用
pymatgen-core 2026.7.16 归一化 `BandStructure`/`BandStructureSymmLine` 与
`CompleteDos`。Blender 只消费归一化数组并生成轻量 Curve；pymatgen-core 不进入
Extension。

## Energy and spin contract

权威数组保存来源的 absolute energy（eV），Fermi energy 作为独立标量保存。
`energy_reference="absolute"` 是数据含义；`E - E_F` 只在 plot adapter 中按显示
参数派生，不能覆盖原数组。spin 轴顺序固定为 `("alpha",)` 或
`("alpha", "beta")`，不通过正负 DOS 值编码 spin。

## BandStructure

`BandStructure` 继承 `PropertyDataset`：

- `data`: energies，`(spin, kpoint, band)`，eV；
- `occupations`: 可选，同 shape，dimensionless；
- `kpoints`: fractional reciprocal coordinates，`(kpoint, reciprocal_axis)`；
- `reciprocal_lattice`: pymatgen physics convention（含 2π），`inverse_angstrom`；
- `distances`: path distance，`(kpoint,)`，`inverse_angstrom`；
- `labels`: 每个 kpoint 的 label 或 `None`；
- `branches`: start/end index 与 endpoint labels；
- `projections`: 可选 `(spin, kpoint, band, atom, orbital)`，dimensionless；
- `orbital_labels`: 与 projection orbital axis 一一对应；
- `structure_id` 与 `fermi_energy`。

pymatgen 原 projection 顺序为 `(band, kpoint, orbital, ion)`，adapter 必须显式
transpose。没有 occupations/projections 时保持 `None` 并报告 missing，不填零伪造。

## DensityOfStates

`DensityOfStates` 继承 `PropertyDataset`：

- `data`: total DOS，`(spin, energy)`；
- `energies`: `(energy,)`，eV；
- `projections`: 可选 `(spin, energy, atom, orbital)`；
- `orbital_labels`、`spin_channels`、`structure_id`、`fermi_energy`；
- unit 为 `states_per_electron_volt`，或已按体积归一化时为
  `states_per_electron_volt_per_cubic_angstrom`。

PDOS orbital axis 取所有 site orbital 的稳定 union；缺少某个 site-orbital-spin
组合表示物理上的零贡献，可以填零。`CompleteDos.norm_vol` 非空时 total DOS 已由
pymatgen 除以体积，但原 `pdos` mapping 未同步归一化，adapter 对 PDOS 显式除以同一
volume 并记录 provenance。

## VASP adapter

首版 parser 使用 `Vasprun(..., parse_projected_eigen=parse_projections)`，可分别或
同时输出 band/DOS。`Vasprun.eigenvalues` 的 occupation 只在与最终 band kpoint/band
shape 严格一致时映射；hybrid slicing 或其他不一致场景报告 ambiguous/missing，不猜测。
结构、band 和 DOS 共享一个 normalized structure UUID。

## Blender contract

- band plot：每个 spin-band 一条 poly spline，x 为 reciprocal path distance，y 可
  选择 absolute 或 `E-E_F`；
- DOS plot：每个 spin 一条 poly spline，x 为 density（beta 可仅显示时取负），y 为
  energy；
- Curve object 保存 dataset UUID、revision、display energy reference；
- selection API 只写 spin/kpoint/band 或 spin/energy/component index metadata，供
  后续 structure/projection linked selection 使用。

## Failure policy

- 非有限 energy、Fermi level、kpoints、density 或 projection 直接失败；
- shape、spin key 或 structure atom count 不一致直接失败；
- 未知 orbital count 不映射成错误标签；
- generic `BandStructure` 没有 branches 时使用空 tuple；
- parser 缺字段进入 `ParserReport`，不以默认值冒充来源数据。
