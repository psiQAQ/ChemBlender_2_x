# ChemBlender 用户工作流

本目录按真实操作顺序说明 ChemBlender 2.4.0。第一次使用时，从[导入数据](01-import.md)开始；准备发布或交付项目前，再走一遍[项目保存与恢复](05-project-lifecycle.md)。

## 相对 2.1.0，用户实际得到什么

2.1.0 主要把分子或晶体直接做成 Blender 对象。当前版本先把来源、结构、拓扑、属性、计算结果和修订写入 Project，再从这些科学实体生成 Blender View。对象仍可调整材质、变换和显示，但它不再是科学数据的唯一副本。

完整版本变化以根目录的 [CHANGELOG](../../../CHANGELOG.md) 为准。下面只列 UI 中能够完成的用户任务。

| 能力 | UI 入口 | 用户可完成的事项 |
| --- | --- | --- |
| 多格式导入与预检 | `Quick Import`、`Import Preview` | 选择单个或多个文件、拖放、输入 SMILES，检查 reader、质量、冲突、归组和默认 View 后再提交 |
| 科学项目浏览 | `Project Browser` | 按 Source 或 Data 查找 Structure、Topology、Grid3D、属性、结果、诊断和 View |
| 可追溯编辑 | `Apply Scientific Edits`、拓扑控件 | 从 View 的明确修改创建 derived Structure；计算、接受、拒绝或切换 topology |
| 晶体与生物数据 | Structure 属性、biological controls | 查看 declared/derived symmetry、selective dynamics、层级选择和 PDB MODEL 播放 |
| 三维场展示 | Grid3D controls | 创建 `Volume`、`Signed Surface`，或把兼容属性映射到 surface |
| 有损失预览的导出 | `Export Selected Data` | 导出 XYZ、extXYZ、MOL、MOL2、PDB、PQR、Cube、SDF、SMILES、CIF、POSCAR/CONTCAR |
| 保存、重开和恢复 | `Save Project`、Project Browser recovery | 保存 `.blend`/`.cbq` 配对，验证或重连 sidecar，重建自有缓存 |
| 旧场景迁移 | `Legacy Migration` | 预览 2.1/2.2 对象，显式迁移到 Project，并保留原对象备份 |

## 三类能力边界

| 类别 | 当前边界 |
| --- | --- |
| 基础安装可用 | Windows x64 Release 安装包内的 built-in readers、RDKit、Gemmi，以及上表列出的 Project/UI 工作流 |
| 需要可选 runtime | cclib、IOData、ASE、pymatgen 等 adapter 只有在单独管理的 Python runtime 通过 availability check 后可选；它们不属于本教程的基础成功条件 |
| 开发接口或条件能力 | CJSON/QCSchema 的 core exporter、Reader API、缓存维护和第三方 reader 扩展没有通用 Project Browser 操作；Agent 也不能把这些接口描述成现成 UI |

不要只凭扩展名判断能力。导入内容、依赖、View、导出成熟度和已知损失见[格式与支持范围](formats.md)。

## 样例层级与“分辨率”

每种格式至少保留一个 `contract` 样例。它通常只有几百 bytes，用来锁定语法分支、字段映射和错误路径；文件小不等于坐标精度不足，但它不能证明大型数据的交互体验。需要观察规模、轨迹、层级或体数据时，改用 `representative` 样例。代表样例来自 COD、wwPDB CCD/PDB、APBS、Open Babel、Avogadro、MolSSI 和 rMD17，或由这些固定来源按公开规则确定性派生。

“分辨率”要按数据类型读：坐标文件看原子数、单位和有效小数；trajectory 看帧数、每帧原子数和属性；Cube 看 `Nx×Ny×Nz`、步长和空间范围；晶体看位点、晶胞、symmetry/supercell；生物结构看 atom/residue/chain/model。文件 bytes 只说明编码大小。

每个输入旁边都有同名 Markdown，记录来源 ID、取得日期、许可证、规范链接、字段、ChemBlender 支持边界、SHA-256 和 Agent 提示词。完整选择表见[格式样例矩阵](formats.md#样例矩阵)；输入文件保持不可变。自动检查通过后，仍要完成[人工插件使用体验检阅](reviews/README.md)，才能把候选版本视为可发布。

## 推荐路线

```text
准备环境 → 导入 → Import Preview → 处理 → 展示 → 导出
                         ↓
                 保存 / 重开 / 恢复 / 迁移
```

1. [导入数据](01-import.md)
2. [处理数据](02-process.md)
3. [展示数据](03-visualize.md)
4. [导出数据](04-export.md)
5. [保存、重开、恢复与迁移](05-project-lifecycle.md)
6. [Agent 与 Blender MCP](06-agent-and-mcp.md)
7. [Agent 辅助的插件能力外案例](07-agent-beyond-plugin.md)
8. [格式与支持范围](formats.md)
9. [人工插件使用体验检阅](reviews/README.md)

细节事实仍以现有的 [Quick Import](../quick-import.md)、[Project Browser](../project-browser.md)、[数据质量](../data-quality.md)、[科学编辑](../scientific-editing.md)和[项目 sidecar](../project-sidecar.md)指南为准。教程输入集中在[用户流程样例目录](../../../examples/user-workflows/README.md)，输入文件不要原地覆盖；基础流程实测见 [`local-2.4.0.json`](../../../examples/user-workflows/results/local-2.4.0.json)，代表样例实测见 [`local-representative-2.4.0.json`](../../../examples/user-workflows/results/local-representative-2.4.0.json)。

## 开始前

- 使用 Blender 5.1 或更高版本，并把 Release ZIP 安装为 Blender Extension。更新后关闭并重新启动 Blender，再确认 RDKit/Gemmi；开发验证另见[Windows 冷依赖检查](../../development/windows-extension-cold-check.md)。
- 确认 3D View 右侧边栏中有 `ChemBlender` 标签页。
- 先复制待处理文件；本教程的 `examples/user-workflows/inputs/` 是不可变输入。
- 重要项目先准备一个新的、可写目录，保存时让 `.blend` 与 `.cbq/` 位于同一层。
- 遇到 `Partial`、`Ambiguous`、`Incomplete` 或 `Invalid` 时先读 Diagnostics，不要为了继续而忽略科学含义。
