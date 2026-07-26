# 2.3.0 外部参考项目与标准

本清单用于设计、测试对照和许可证审查。存在 submodule 不等于运行时依赖。实际版本、commit和许可证在执行前由 Codex live-verify，并同步 `.agents/reference/dependencies-and-release.md`。

| 项目/标准 | 2.3.0 用途 | 边界 | 许可证/来源 |
| --- | --- | --- | --- |
| Blender Extensions | wheel、自包含包、manifest、build/validate、FileHandler/Workspace API | 官方平台规则为准 | https://docs.blender.org/manual/en/latest/advanced/extensions/ |
| RDKit | MOL/SDF/SMILES、化学拓扑、stereo、writers | 基础wheel；不暴露Mol为权威模型 | BSD-3-Clause, https://www.rdkit.org/docs/ |
| Gemmi | CIF 1.1词法、block/loop、small structure、raw envelope | 基础wheel；late import | MPL-2.0, https://gemmi.readthedocs.io/ |
| spglib | 空间群、Hall、Wyckoff、standardized cell | 可选派生，不覆盖CIF声明 | BSD-3-Clause, https://spglib.readthedocs.io/ |
| libAtoms extxyz | Properties语法和测试对照 | 只作规范/fixture参考，基础reader原生实现 | https://github.com/libAtoms/extxyz |
| wwPDB PDB v3.30 | ATOM/HETATM/MODEL/CONECT/CRYST1固定列规范 | 2.3只做atom-level | https://www.wwpdb.org/documentation/file-format-content/format33/v3.3.html |
| APBS PQR | PQR atom fields、charge/radius dialect参考 | 原生parser，多dialect显式诊断 | https://apbs.readthedocs.io/en/latest/formats/pqr.html |
| Avogadro/CJSON | 轻量结构、拓扑、轨迹、结果交换 | 大数组仍用`.cbq` | BSD-style project, https://github.com/OpenChemistry/avogadrolibs |
| xyzrender | reader sniff、Cube/格式测试、显示参数配置 | 不复用2D renderer为Blender后端 | MIT, https://github.com/aligfellow/xyzrender |
| Molecular Blender | Molden/Cube轨道、adaptive isosurface、Blender集成经验 | 保持Priority 3 wavefunction后端 | GPL-3.0+, https://github.com/smparker/molecular-blender |
| Beautiful Atoms | ASE/Blender、periodic、volumetric/property surface | 不用隐藏Mesh保存权威数组 | GPL family, https://github.com/beautiful-atoms/beautiful-atoms |
| Molecular Nodes | trajectory session、selection、workspace和GN属性契约 | 不扩大2.3到完整结构生物学 | MIT, https://github.com/BradyAJohnston/MolecularNodes |
| cclib | 多量化输出和属性capability matrix | 外部core/worker，真实integration CI | BSD-3-Clause, https://github.com/cclib/cclib |
| IOData | FCHK/Molden/WFN/WFX与basis/orbital/RDM | 外部core/worker | GPL-3.0+, https://github.com/theochem/iodata |
| GBasis | AO/MO/density/ESP求值 | Python 3.12 worker基线 | GPL-3.0+, https://github.com/theochem/gbasis |
| ASE | 结构/轨迹/periodic I/O对照 | 可选adapter，不做基础extXYZ/POSCAR前提 | LGPL-2.1+, https://gitlab.com/ase/ase |
| pymatgen | VASP field/band/DOS数据 | Priority 3 | MIT, https://github.com/materialsproject/pymatgen |
| phonopy | qpoint/frequency/complex eigenvector | Priority 3 | BSD-3-Clause, https://github.com/phonopy/phonopy |
| PyProcar | Fermi surface/projection/spin texture | Priority 4 | GPL-3.0, https://github.com/romerogroup/pyprocar |
| critic2 | QTAIM/topology/NCI外部结果 | Priority 4固定进程/JSON | GPL-3.0, https://github.com/aoterodelaroza/critic2 |
| quantum-chem-skills | recipe和工作流分类 | 不作为parser/数值核心 | MIT, https://github.com/silico-quantum/quantum-chem-skills |

## 固定审阅快照

本规划审阅的 ChemBlender commit：

```text
https://github.com/psiQAQ/ChemBlender_2_x/commit/1cf492f40d5fa8799fa964b8dfc914ab5ecbec4c
```

引用具体实现时优先使用 commit permalink，而不是移动的 `main` URL。
