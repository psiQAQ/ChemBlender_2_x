# 0012：周期能带与 DOS 数据边界

## Status

Accepted for Phase 2 band structure, DOS and projection ingestion.

## Context

VASP/pymatgen 将能带、占据数、投影和 DOS 使用不同轴顺序与容器表达；绘图时又常把
能量平移到费米能。ChemBlender 需要保留权威数值，同时让结构、能带、DOS 和后续
费米面共享稳定 identity。

## Decision

- 权威能量始终保存为 absolute eV，`fermi_energy` 独立保存；`E-E_F` 只属于 view。
- band 轴固定为 `(spin, kpoint, band)`，projection 固定为 `(spin, kpoint, band, atom, orbital)`。
- DOS 轴固定为 `(spin, energy)`，PDOS 固定为 `(spin, energy, atom, orbital)`。
- spin 顺序只允许 `alpha` 或 `alpha, beta`；缺失 occupation/projection 进入 `ParserReport`，不创建伪数组。
- reciprocal lattice 使用包含 `2π` 的 pymatgen physics convention，单位为 `inverse_angstrom`。
- `CompleteDos(normalize=True)` 的 total DOS 和原始 PDOS 同时除以 cell volume。
- Blender 使用轻量 Curve：能带默认显示 `E-E_F`，β-DOS 可镜像；对象保留 dataset/structure UUID 和 selection indices。
- pymatgen-core 只在独立 core/worker 环境 late import，不进入 Extension ZIP。

## Consequences

- `vasprun.xml` 可以生成共享同一 `Structure` UUID 的 band/DOS datasets。
- publication styling、PyProcar Fermi surface 与 sumo layout 不进入本阶段。
- linked selection 后续可依据 atom/orbital/dataset ID 连接结构与倒空间视图。

## Verification Contract

1. synthetic `BandStructureSymmLine` 数值证明 band/projection transpose 正确。
2. synthetic `CompleteDos` 数值证明 spin/order、稀疏 PDOS 补零和 volume normalization。
3. project 拒绝 dangling structure 和 projection atom-axis mismatch。
4. Blender Curve 精确执行 Fermi shift、β-DOS mirror 和 selection metadata。
5. Extension ZIP 不包含 pymatgen、matplotlib 或 submodules。
