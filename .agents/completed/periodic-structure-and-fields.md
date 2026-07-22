# Phase 2 Periodic Structure and Scalar Fields

## Result

- 固定 ASE 3.29.0 与 pymatgen-core 2026.7.16 的 reviewed submodules。
- 完成 POSCAR/CONTCAR、extXYZ、selective-dynamics、PBC 和未知 array/constraint 报告。
- 完成 CHGCAR/PARCHG、ELFCAR、LOCPOT 的 structure-linked `Grid3D` 映射、单位归一化与 spin/SOC 语义。
- `PeriodicSiteData` 增加 PBC，`Grid3D` 增加可验证的 structure reference。
- Blender structure/Volume 保存 periodic cell、PBC 与 structure UUID。
- 将 `qc-gbasis==0.1.0` 的安装名、求值职责、非目标和后续导数/积分方向补入波函数计划。

## Verification Evidence

- Blender Python：165 tests passed，22 skipped（外部 parser 依赖未安装）。
- ASE/pymatgen-core Python 3.13 环境：165 tests passed，18 skipped。
- CHGCAR density integral、triclinic step vectors、spin/SOC、ELFCAR、LOCPOT 与真实 write/read fixture 通过。
- Blender 5.1.2 extension validate/build 通过；ZIP 41 entries，只有固定 RDKit wheel，不含外部周期依赖。
- 短路径隔离 profile 的安装、OpenVDB、周期 structure metadata、register/unregister/reload 与 RDKit runtime 通过。
- `user_default` 的实际安装在修复一次由已加载 DLL 导致的不完整 wheel 后，经两个独立 Blender 进程验证 enabled state、RDKit 2026.03.3、benzene parse、core import 与 late-import boundary。

## Known Operational Constraint

Windows 上不能在已加载共享 NumPy/RDKit DLL 的 Blender 进程中覆盖安装 wheel。
真实安装验证必须采用 disable-and-exit、cold install、fresh-process persistence check
三段式流程；单进程内成功不足以证明退出后的共享 dependency 完整。
