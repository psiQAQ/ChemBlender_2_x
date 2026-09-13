# 科学案例合集

本章覆盖当前本地候选的 T03、T05、T08–T16、T19、T20 和 B01。下载 [review package](../../offline/artifacts/scientific-viewer-review.zip)（SHA-256 `4d921d21c475c0ae11acd25cc5f76d9552643d8a98f7a791968d5b7d1827483e`）。包内有 22 个目录，每个目录都让 `project.blend` 与完整 `project.cbq/` 相邻，并附原生 PNG 渲染。导入源被刻意排除；所有工程对均在独立进程冷重开，并在无 processor 时通过 `Rebuild Selected View`。

统一的精确 Viewer 步骤：完整解压且不要改成员名，打开 `project.blend`，确认 Project Browser 显示 connected，选择实体或 View，然后在 `Scientific Representation` 中选择下表 preset、模板 `Research`，点击 `Create View`。恢复时选择 View 并点击 `Rebuild Selected View`；不得删除 `project.cbq/arrays/*.npy`。这些是 Blender 原生后台结果，不是鼠标键盘直录，也不是独立人工验收。

| 案例 | 固定输入与准确路线 | 可见结果与科学边界 | 证据 |
| --- | --- | --- | --- |
| T03 | SMILES `CCO`；Prepare GUI `derive`，operation `molecule.conformers`，参数 `{"count":3,"force_field":"MMFF94"}`，再执行 `validate`；每个 Structure 用 `Structure publication`。 | 保留三个构象。MMFF94 只排序本次构象，不是电子能。 | [回执](../../../examples/tutorials/2.5.0/T03-current-candidate-check.json) |
| T05 | 固定 PDB/PQR/MOL2；Prepare GUI `convert`；PDB 用 `Trajectory frame`，PQR/MOL2 charge 用 `Atomic scalar`。 | PDB model 顺序、PQR charge/radius、MOL2 hierarchy 分开保留；同为 atom-indexed 不代表同义。 | [回执](../../../examples/tutorials/2.5.0/T05-current-candidate-check.json) |
| T08 | 固定 FCHK/Molden，经 `python.wavefunction`；记录的 `33³`、`0.25 bohr` HOMO/LUMO grid；`Signed scalar isosurface`，`+0.03/-0.03`。 | 正负相位均可见。有限盒归一化不是全空间证明。 | [回执](../../../examples/tutorials/2.5.0/T08-current-candidate-check.json) |
| T09 | 固定 water/CH3/N2 FCHK；选择 CH3 spin density 与 `Signed scalar isosurface`。 | 自旋密度保留正负；total、spin、post-SCF-minus-SCF 是不同数据集。 | [回执](../../../examples/tutorials/2.5.0/T09-current-candidate-check.json) |
| T10 | 固定 water density/ESP，必须同 Structure、同 affine grid；`Property on surface`。 | ESP 给 density 等值面着色，ESP 不是等值阈值；核奇点探针会被拒绝。 | [回执](../../../examples/tutorials/2.5.0/T10-current-candidate-check.json) |
| T11 | 固定 Gaussian/ORCA，经 `python.scientific`；`Vibration mode`、selection index `1`、`Apply Phase`；光谱另用 `Spectrum plot`。 | IR/Raman 字段不混用；phase 是动画相位，不是物理时间。 | [回执](../../../examples/tutorials/2.5.0/T11-current-candidate-check.json) |
| T12 | 固定 Gaussian/ORCA TD；UV–Vis/ECD 用 `Spectrum plot`；只有完整 Gaussian state 用 `Electronic spectrum linked`。 | Gaussian ECD 保留 length gauge/unit；ORCA 缺失项保持 unknown，使用 spectrum-only View。 | [回执](../../../examples/tutorials/2.5.0/T12-current-candidate-check.json) |
| T13 | 固定 silicon band + KPOINTS 与独立 DOS，经 `python.scientific`；`Band structure`/`Density of states`；reference `absolute`。 | 保留声明的 k path；不同 Structure/Fermi level 不静默对齐合并。 | [回执](../../../examples/tutorials/2.5.0/T13-current-candidate-check.json) |
| T14 | 固定 NaCl phonopy 六文件；`Phonon mode`、q-point index `1`、mode index `0`，再预览 phase。 | 展示周期复模式相位，不是时间。 | [回执](../../../examples/tutorials/2.5.0/T14-current-candidate-check.json) |
| T15 | 固定 critic2 JSON/NCI；`Topology graph` 与 `NCI surface`。 | 展示 5 个 critical point、4 条有序 path 与配对 40³ field；不虚构路径或键能。 | [回执](../../../examples/tutorials/2.5.0/T15-current-candidate-check.json) |
| T16 | MIT 声明的 SrVO3 六个文本文件，经 `python.fermi`；`Fermi surface`。 | 声明的 21³ Gamma mesh 上 bands 16–18；排除 POTCAR/WAVECAR/CHG/HDF5/pickle。 | [回执](../../../examples/tutorials/2.5.0/T16-current-candidate-check.json) |
| T19 | 显式 external Python register/discover/conformance；Viewer `Structure publication`。 | Reader API 可用，但不加入普通 GUI 的 22 个 reader。 | [回执](../../../examples/tutorials/2.5.0/T19-current-candidate-check.json) |
| T20 | 通过 `python.qcschema` 执行 `qcschema.compute@1`；选择 gradient 与 `Atomic vector`。 | 实际 PySCF 2.13.1 RHF/cc-pVDZ 能量 `-76.0214183672713 Eh`；交换成功不等于计算成功。 | [回执](../../../examples/tutorials/2.5.0/T20-current-candidate-check.json) |
| B01 | 无 provider credential/live transport 时，Prepare GUI 先 `capabilities` 后 `doctor`，并测试 Cancel。 | provider unavailable，无网络请求、无输出；负向边界按设计无科学 render/project。 | [回执](../../../examples/tutorials/2.5.0/B01-current-candidate-check.json) |

## 原生渲染图库

![T03 构象](../assets/2.5-tutorials/scientific/t03-conformers.png)

![T05 PDB models](../assets/2.5-tutorials/scientific/t05-pdb-models.png)

![T08 FCHK HOMO 正负相位](../assets/2.5-tutorials/scientific/t08-fchk-homo.png)

![T09 有符号自旋密度](../assets/2.5-tutorials/scientific/t09-spin-density.png)

![T10 density surface 上的 ESP 着色](../assets/2.5-tutorials/scientific/t10-density-esp.png)

![T11 振动模式](../assets/2.5-tutorials/scientific/t11-vibration.png)

![T11 Gaussian IR linked View](../assets/2.5-tutorials/scientific/t11-gaussian-ir.png)

![T12 UV–Vis](../assets/2.5-tutorials/scientific/t12-gaussian-uvvis.png)

![T12 ECD](../assets/2.5-tutorials/scientific/t12-gaussian-ecd.png)

![T13 绝对能量能带](../assets/2.5-tutorials/scientific/t13-bands.png)

![T14 NaCl 声子模式](../assets/2.5-tutorials/scientific/t14-phonon.png)

![T15 QTAIM](../assets/2.5-tutorials/scientific/t15-qtaim.png)

![T15 NCI](../assets/2.5-tutorials/scientific/t15-nci.png)

![T16 SrVO3 Fermi surface](../assets/2.5-tutorials/scientific/t16-fermi.png)

![T19 外部 Reader API 结果](../assets/2.5-tutorials/scientific/t19-reader-api.png)

![T20 QCSchema gradient](../assets/2.5-tutorials/scientific/t20-qcschema-gradient.png)

linked spectrum 的标签小于专用 plot render。当前本章所有案例仍缺直接 GUI 直录，独立人工验收仍未签署。
