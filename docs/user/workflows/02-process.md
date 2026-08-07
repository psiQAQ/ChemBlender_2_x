# 处理数据

ChemBlender 把科学数据修改与 Blender 外观修改分开。移动对象、改材质、隐藏对象或调整 Geometry Nodes 都是 View 操作；它们不会改写 Project 中的 Structure、Topology 或属性。

## 要完成什么

- 从明确的网格编辑创建 derived Structure，不覆盖 imported Structure。
- 计算、接受、拒绝或切换 topology。
- 查看晶体的 declared/derived symmetry 与 selective dynamics。
- 按生物层级选择原子，并配置 PDB MODEL playback。
- 判断属性和计算结果是否仍对应当前 Structure revision。

## 示例

| 任务 | 示例 |
| --- | --- |
| 多帧与 revision | [carbon-trajectory.extxyz](../../../examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz) |
| MOL2 topology、charge、substructure | [substructure.mol2](../../../examples/user-workflows/inputs/mol2/substructure.mol2) |
| 晶体与 Selective Dynamics | [si.POSCAR](../../../examples/user-workflows/inputs/poscar/si.POSCAR)、[velocities.CONTCAR](../../../examples/user-workflows/inputs/poscar/velocities.CONTCAR) |
| PDB MODEL 播放与层级 | [model-trajectory.pdb](../../../examples/user-workflows/inputs/pdb/model-trajectory.pdb) |
| PDB MODEL 身份不一致诊断 | [multimodel.pdb](../../../examples/user-workflows/inputs/pdb/multimodel.pdb) |
| PQR charge/radius 与层级 | [with-chain.pqr](../../../examples/user-workflows/inputs/pqr/with-chain.pqr) |
| 32 帧 trajectory 与 force/energy | [aspirin-rmd17-32.extxyz](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz) |
| 大型 MOL2 与不支持键型 | [openbabel-5sun-protein.mol2](../../../examples/user-workflows/inputs/mol2/openbabel-5sun-protein.mol2) |
| 64 位点周期结构 | [cod-9012293-diamond-2x2x2.CONTCAR](../../../examples/user-workflows/inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR) |
| 真实 NMR MODEL 与生物层级 | [1d3z-ubiquitin-nmr.pdb](../../../examples/user-workflows/inputs/pdb/1d3z-ubiquitin-nmr.pdb) |
| 真实 PQR charge/radius 与推断 segment | [apbs-protein-rna-nb.pqr](../../../examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr) |

## 操作前检查

1. 在 Project Browser 中选中要处理的 Structure 或对应 View，记录 source revision、quality 和当前 topology source。
2. 如果要做科学编辑，先保存项目；重要数据同时备份 `.blend` 与 `.cbq/`。
3. 确认正在编辑 ChemBlender 的 Structure View，而不是普通 Blender mesh 或 legacy 对象。
4. `Partial`、`Ambiguous` 或 stale revision 先处理 Diagnostics。计算结果绑定旧 Structure 时，不要假定它对新几何仍有效。

## UI 操作

### 应用科学编辑

1. 在 3D View 中对 Structure View 的原子顶点、元素属性、边或 cell 做需要的修改。普通 Object transform 只改变显示。
2. 在 ChemBlender 控件中选择 `Apply Scientific Edits`。
3. 查看 atom、coordinate、element、bond 和 cell 变化预览。
4. 确认后让系统创建 derived Structure、必要的 derived topology 和指向 source Structure 的 provenance；若预览不符合意图，取消。

导出时要明确选择 derived Structure。原先计算结果仍绑定 source revision，除非重新计算或导入与 derived geometry 对应的结果。

### 处理 topology

1. 在 Project Browser 选中 Structure，查看当前 TopologyRecord 的 source、quality、parameters 和 edge count。
2. 缺少显式 topology 时选择 `Compute Topology`。距离推断只是 proposal，不是文件证据。
3. 检查 cutoff、周期 image shift、edge count 和诊断。
4. 选择 `Accept Topology` 或 `Reject Topology`。如果 Structure 有多个合法 topology，使用 `Switch Topology` 改变当前 View 的绑定。

`Switch Topology` 只改变该 View 使用哪个 TopologyRecord，不会重写 Structure，也不会替换其他 View。

### 晶体数据

1. 选中周期 Structure，查看 `Declared Symmetry`、`Derived Symmetry` 和 `Comparison Symmetry`。
2. Gemmi 可用时选择 `Derive Symmetry`。派生结果是新的结果实体，不会伪装成源文件声明。
3. 需要标准化显示时选择 `View Standardized Structure`。
4. 对含 Selective Dynamics 的 POSCAR/CONTCAR，查看 constrained atom count；`Toggle Selective Constraints` 只切换约束的 View 表现。

### 生物层级与 MODEL

1. 导入 PDB/PQR 后，在 Project Browser 选择 BiologicalHierarchy 或对应 Structure。
2. 用 model、chain、residue、atom name、altloc 或 occupancy 条件设置选择，再运行 `Select Biological Atoms`。
3. 需要默认生物视图时选择 `Create Biological Default View`。
4. 原子身份集合一致的多 MODEL PDB 使用 `Configure MODEL Playback`，核对帧数与当前 model。身份不一致时插件会建立独立 Structure 并给出诊断，不会伪造 trajectory；PQR 一般也没有 MODEL trajectory。

## 屏幕上应看到什么

- imported Structure 保留；科学编辑成功后出现新的 derived Structure 和 provenance。
- Project Browser 可同时列出多个 TopologyRecord，并区分 `explicit_file`、`rdkit_sanitized`、`distance_inferred` 或 `user_edited`。
- 晶体属性把 declared 与 derived 分开展示，comparison 不会把两者合并成一个“正确值”。
- Biological selection 改变 View 中的选择或可见范围，Project 中的 BiologicalHierarchy 保留。

## 成功判据

1. source revision、derived revision 和 View binding 能在 Project Browser 中区分。
2. topology 必须属于当前 Structure；跨 Structure 或 stale binding 应拒绝而不是继续显示。
3. 周期边记录 cell-image shift；不能把跨周期边假装成普通胞内键。
4. derived Structure 的计算或属性只有在其 provenance/revision 匹配时才用于解释或导出。
5. 取消 Apply Scientific Edits 或拒绝 topology 后，原 Project 与 source View 不变。

## Agent 提示词

### Apply Scientific Edits

```text
使用当前 Blender MCP，先查询 Blender 5.1/Extension/active file/dirty state，并从公开 UI/RNA 确认我选中的是 ChemBlender Structure View。检查 Operator RNA 与 poll 后调用 live `bpy.ops.chemblender.apply_scientific_edits`，先返回 atom/coordinate/element/bond/cell preview 和所有 confirmation；未经我确认不提交。提交后验证 source Structure 未变、derived Structure/provenance/revision/View binding 已创建。不得 import private modules、写 `.cbq`/cache/`cb_` state 或 bypass confirmation。
```

### topology proposal 与选择

```text
使用当前 Blender MCP 导入并选中 `examples/user-workflows/inputs/mol2/substructure.mol2` 的 Structure。预检 runtime 后检查 `bpy.ops.chemblender.compute_topology`、`accept_topology`、`reject_topology`、`switch_topology` 的 Operator RNA 与 poll。只调用当前 UI 允许的 Operator，先报告 existing topology source/quality/edge count 和 proposal parameters；任何 scientific confirmation 交给我。执行我指定的 accept/reject/switch 后验证 TopologyRecord 与 View binding，不能覆盖 explicit_file 证据。不得 import private modules、改 `.cbq` 或 bypass confirmation。
```

### 大型 MOL2 的 topology 边界

```text
使用当前 Blender MCP，读取 Operator RNA 后，通过 `bpy.ops.chemblender.quick_import` 导入 `examples/user-workflows/inputs/mol2/openbabel-5sun-protein.mol2`，停在 Import Preview confirmation。报告 6185 atoms、6248 declared bonds、390 substructures、`un` bond type、4 类 unknown sections、0 interpreted topologies 和 diagnostics。经我确认后再调用 `bpy.ops.chemblender.confirm_import`；只检查 Structure、原子属性、层级和原始记录，不自动调用 compute/accept topology，也不把显示连接称为来源 topology。不得 import private modules、写 `.cbq` 或 bypass confirmation。
```

### 晶体属性

```text
使用当前 Blender MCP 通过公开导入流程打开 `examples/user-workflows/inputs/poscar/velocities.CONTCAR`。确认 Blender >= 5.1 和 Extension key，检查 Operator RNA 后读取 declared/derived/comparison symmetry、Selective Dynamics 和 velocity 的公开 UI 状态。Gemmi availability 和 cell 完整时才允许调用 live `bpy.ops.chemblender.derive_crystal_symmetry` 或 `toggle_selective_constraints`；先报告 confirmation 与 dependency reason。验证 derived result 或 constraint View，不把它写成源文件事实。不得 import private modules、编辑 `.cbq` 或 bypass confirmation。
```

### 代表性周期结构

```text
使用当前 Blender MCP，先检查 Blender 5.1、Extension key、`bpy.ops.chemblender.quick_import`、`confirm_import` 和 `derive_crystal_symmetry` 的 Operator RNA/poll。导入 `examples/user-workflows/inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR`，在 Preview 报告 64 个 C sites、7.1338 Å cell、Direct coordinates、64 行零 atomic velocity、quality 和 confirmation；经我确认后提交。需要 symmetry 时只调用公开 `bpy.ops.chemblender.derive_crystal_symmetry`，并把结果标为从 POSCAR 派生，不能写成源声明。不得 import private modules、编辑 `.cbq` 或 bypass confirmation。
```

### biological hierarchy 与 MODEL

```text
使用当前 Blender MCP 导入 `examples/user-workflows/inputs/pdb/1d3z-ubiquitin-nmr.pdb`，在 Import Preview confirmation 后报告 10 MODEL、每模型 1231 atoms、chain A、76 residues 和 trajectory，再等我确认提交。选中 BiologicalHierarchy/Structure 后检查 `bpy.ops.chemblender.select_biological_atoms`、`play_biological_models`、`create_biological_view` 的 Operator RNA 与 poll，再按我给的 model/chain/residue 条件调用，返回 selection、frame change 和 View binding。可另行用 `examples/user-workflows/inputs/pdb/multimodel.pdb` 确认身份不一致会拆成独立 Structure。不得 import private modules、改 mesh/scientific attributes、写 `.cbq` 或 bypass confirmation。
```

### 代表性 PQR 层级

```text
使用当前 Blender MCP，读取公开 Operator RNA 后，通过 `bpy.ops.chemblender.quick_import` 导入 `examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr`。停在 Preview，报告 998 atoms、41 residues、998 charge/radius、22 个 zero radius、无来源 chain 和 2 个 inferred segments；经我确认后调用 `bpy.ops.chemblender.confirm_import`。可用 `bpy.ops.chemblender.select_biological_atoms` 检查 segment/residue 选择，但不得把 inferred segment 改称来源 chain。任何 confirmation 都不绕过；不得 import private modules 或编辑 `.cbq`。
```

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 移动对象后坐标没有变化 | 这是预期行为。Object transform 是 View 状态；要改科学坐标必须使用 `Apply Scientific Edits` |
| `Compute Topology` 结果与文件键不同 | 比较 source token 与参数。文件 topology 和 distance proposal 可并存；不要用推断结果覆盖显式证据 |
| `Derive Symmetry` 不可用 | 查看 dependency reason 和周期 cell 完整性；不要手填空间群来消除 unavailable 状态 |
| 结果在 derived Structure 上看似可见 | 检查数据集绑定的 Structure revision。可见不等于科学上仍有效 |
| PDB 选择少了原子 | 检查 model、altloc、occupancy、chain/residue filter 和质量诊断 |

详见[科学编辑与 topology](../scientific-editing.md)和[数据质量](../data-quality.md)。继续：[展示数据](03-visualize.md)。
