# Molecular Quantum Chemistry Ingestion

## Result

Phase 1 的最小读取与 Blender grid 闭环已完成：

- Cube reader 保留多 dataset、斜 step vectors、bohr 坐标和语义/单位歧义。
- OpenVDB adapter 将 `Grid3D` 写入显式 cache path，以完整 affine transform 建立 Blender Volume，并保留 dataset identity。
- cclib 1.8.1 adapter 将 Gaussian/ORCA 输出转换为结构、SCF 能量、原子布居、计算状态、provenance 和 `ParserReport`。
- `BasisSet`/`OrbitalSet` 表达 restricted、unrestricted、generalized 轨道和 basis convention；IOData 1.0.1 adapter 支持 FCHK/Molden。
- cclib 与 IOData 仅存在于外部 core 环境；Blender Extension 延迟加载 adapter 依赖，ZIP 不包含两个第三方栈或 submodule。

## Evidence

- Cube/OpenVDB 合并提交：`25459f7`、`61cd0ee`。
- cclib 设计/实现提交：`d58855d`、`ccd9e76`。
- IOData 设计/实现提交：`247f4f0`、`a87d985`。
- cclib integration：Gaussian 16 与 ORCA 4.1 固定 fixture 全通过。
- IOData integration：restricted FCHK、unrestricted FCHK 与 Molden 固定 fixture 全通过。
- 主分支标准测试：91 项通过，2 项可选 integration 在未安装外部依赖的 Blender Python 中按设计跳过。
- Blender 5.1.2 extension validate/build、隔离 lifecycle smoke 和 ZIP 边界审计通过。

## Known Limits

- 尚未从 basis/orbital 数值求值 MO、density、spin density 或 ESP。
- cclib 的 vibration、excited state、convergence 和高阶 energy 尚未映射。
- 大型数组仍为内存对象，未进入 Zarr/HDF5 sidecar。
