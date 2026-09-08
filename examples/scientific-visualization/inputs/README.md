# 真实科学输入

这些文件用于验证 reader、科学量含义和可视化流程。`../input-manifest.json` 逐文件记录原始 URL、固定 commit、许可、bytes 和 SHA-256；`../licenses/` 保留原始分发许可。所有输入均保持原始 Git blob 或 HTTP 响应字节，未截取、改值、转换换行或解压重写。

| 目录 | 来源与用途 | 必须保留的边界 |
| --- | --- | --- |
| `wavefunction/` | IOData 固定测试语料：water / CH3 FCHK、water Molden / WFX、nitrogen MP2 FCHK | MO、密度、ESP、spin 与 RDM 差分依其真实方法、单位和基组；Molden 的密度层级须显式指定。WFX 是 critic2 待生成输出的输入。 |
| `cclib/Gaussian/basicGaussian16/` | cclib 原始 Gaussian 16 dvb IR、Raman、TD 输出 | Raman 原始量是 activity；TD 输出不等同实验光谱。 |
| `cclib/Gaussian/basicGaussian09/` | dvb TD 输出，包含非零 signed rotatory strengths | 单位明确为 `10**-40 erg-esu-cm/Gauss`；cclib 读取 length gauge。不可误用 velocity 列或声称已转换成实验 molar ECD。 |
| `cclib/ORCA/basicORCA5.0/` | ORCA 5.0 dvb IR、Raman、TD 输出 | 保留程序差异、禁阻跃迁和原始单位；不同输出之间不得拼接成同一 Calculation。 |
| `silicon/bands/` | pymatgen Si Band fixture：VASP 5.2.11，160 个高对称路径点，配套 KPOINTS | 配套路径用于 Band，不能当作 Fermi 或 DOS 均匀网格。 |
| `silicon/dos/` | pymatgen Si static fixture：VASP 5.2.12，4×4×4 Monkhorst-Pack，10 个不可约点，含 PDOS | 与 Band 是独立计算，分别记录 E_F / Calculation / provenance，不宣称同一自洽或收敛结果。 |
| `phonopy/NaCl/` | phonopy 真实 NaCl 有限位移：两份 VASP 4.6.35 XML、FORCE_SETS、位移 YAML、BORN 和原胞 | 原始 XML 各 64 原子。从文件建立 Phonopy 并生成 q 点特征向量后再作动画；现有对象适配器不代表文件工作流已接通。 |

Fermi 输入因归档中包含 POTCAR、pickle 且完整数据许可仍待核定，不放在这里。经批准取回的原包与六个必要文本只保留在忽略的项目缓存；脚本不会提取、解析或执行 POTCAR/pickle。数据来源和文本哈希也记在 manifest。

从仓库根目录运行：

```powershell
& .agents/cache/gbasis-py312/Scripts/python.exe -B examples/scientific-visualization/prepare_inputs.py --verify
& .agents/cache/gbasis-py312/Scripts/python.exe -B examples/scientific-visualization/prepare_inputs.py --verify --fermi
```

移除 `--verify` 可按固定 manifest 补齐缺失输入；已有文件的哈希不符时拒绝覆盖。脚本只用 Python 标准库，不安装依赖。`--verify` 不写文件、不联网。
