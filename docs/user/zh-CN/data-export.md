# T17：明确损失后导出科学数据

工作草稿。13 种格式已有安装版 CLI 导出与回读、实际 Prepare GUI 导出证据；每份 GUI 输出均与科学检查通过的 CLI 输出逐字节一致。下述选项以外的高级设置、工程恢复及人工独立复做仍待完成。本课尚不构成 Blender 工程交接验收。

## 固定输入与处理器

先完成 [Standard prepare 安装](installation.md)。本次使用 prepare 0.1.0 候选 wheel，SHA-256 为 `cdb056514b7b9eed068aa96cd95dd2d12c8b183e753350b7fc6b424fd513c56b`。旧版同名 0.1.0 wheel 不含分子手性与 PQR 修复；候选包仅完成本地专项验证，未发布。

下载 [Ligand.mol2](../../../examples/tutorials/2.5.0/inputs/mdanalysis-2w73/Ligand.mol2)、[来源说明](../../../examples/tutorials/2.5.0/inputs/mdanalysis-2w73/README.md)、[LICENSE](../../../examples/tutorials/2.5.0/inputs/mdanalysis-2w73/LICENSE) 和 [案例规格](../../../examples/tutorials/2.5.0/T17-mol2-2w73.case-spec.json)。输入 SHA-256 为 `d8e8c7c3435ebd6922c6e9907979e55f7729763c64333b6384ffbf5424a80d48`，包含 297 个原子、297 条键、17 个 substructure。来源标注为 2W73 配体、GAST_HUCK 电荷；这是已有准备结果，并非本次新计算。

将输入放入新的工作目录，执行公开命令。保留完整 `ligand.cbq` 目录。

```powershell
chemblender-prepare convert Ligand.mol2 --reader mol2 -o ligand.cbq --json
chemblender-prepare inspect ligand.cbq --json
```

从结果复制 Structure 的 UUID；使用自己的实际返回值，不照抄截图 UUID。以上转换与查看是 CLI 步骤，不计为 MOL2 GUI 验证。

## 实际 Prepare 导出步骤

1. 打开 Prepare，将 **操作** 设为 `export`，**运行环境 Python** 指向候选安装环境中的 Python。这里需要 Python 路径，不是 `chemblender-prepare.exe`。
2. 用选择器选中 `ligand.cbq`，或在 **输入文件 / CBQ** 填入其绝对路径；输出填写新文件 `ligand-exported.mol2` 的绝对路径；**结构 / 导出实体 UUID** 填 Structure UUID，**导出格式** 选 `mol2`。**Cube dataset index** 留空。
3. 保持 **导出先预览** 勾选，点击 **执行**。预期出现 `success` 和 preview 报告，但不生成输出文件。

![实际预览及损失列表](../assets/2.5-tutorials/export-preview.jpg)

预览列出原子状态位、注释、非规范 substructure 字段、未知 section 的省略，以及 bond ID 重新编号。全部 17 个 substructure 的 root 会规范化为组内首个原子，并输出为 GROUP；组编号、名称和原子归属保留。这不是无损导出。

4. 取消 **导出先预览**，暂不勾选 **已阅读并确认导出损失**，点击 **执行**。应明确拒绝，而且不生成文件。

![未确认损失时拒绝导出](../assets/2.5-tutorials/export-rejected.jpg)

5. 阅读损失后，勾选 **已阅读并确认导出损失**，再次点击 **执行**。预期 `success` 并生成文件。

![确认损失后导出成功](../assets/2.5-tutorials/export-success.jpg)

6. 用公开 CLI 重新导入另一个新目录：

```powershell
chemblender-prepare convert ligand-exported.mol2 --reader mol2 -o reopened.cbq --json
chemblender-prepare validate reopened.cbq --json
```

实际 GUI 输出与科学检查通过的 CLI 输出逐字节一致：坐标和来源电荷最大误差为 0，原子名称、类型、组引用与按端点比较的键类型一致。详见 [科学检查](../../../examples/tutorials/2.5.0/T17-mol2-2w73-check.json) 和 [GUI 记录](../../../examples/tutorials/2.5.0/T17-gui-mol2-check.json)。

## 格式覆盖与边界

| 格式 | 固定输入与检查 |
| --- | --- |
| xyz、extxyz | 阿司匹林：21 原子，坐标与顺序完全一致 |
| mol | 阿司匹林：坐标、身份与按端点比较的分子图一致 |
| mol2 | 2W73：297 原子与键；需确认上述损失 |
| pdb | 泛素：10 帧 × 1231 原子，全部坐标、occupancy、B factor 和层级一致；确认后省略晶胞 |
| pqr | APBS 蛋白–RNA：998 个电荷与半径一致，22 个零半径、41 个残基和两段推断分段保留 |
| sdf | 选定 CCD 分子：坐标、身份、分子图及标题一致；该记录属性列表为空，不代表非空 SDF 属性验证 |
| smiles | 紫杉醇：规范异构图一致；不保留坐标 |
| cif、poscar | 共晶 / 金刚石：坐标及晶格矩阵完全一致 |
| cube | 解析 H2：262144 个采样、原点与步进一致；回读后需重新指定物理语义 |
| cjson、qcschema | JSON 值与原始 envelope 一致 |

参阅 [13 格式规格](../../../examples/tutorials/2.5.0/T17.case-spec.json)、[安装运行记录](../../../examples/tutorials/2.5.0/prepare-run006-check.json) 和 [补充科学检查](../../../examples/tutorials/2.5.0/T17-science-run006-check.json)。MOL2 正向补充使用上面的 2W73 规格。[原生元数据检查](../../../examples/tutorials/2.5.0/T17-metadata-run006-check.json) 覆盖 PDB/PQR 层级和选定 SDF 记录。格式正向覆盖不等于每个高级选项均已验证。

## 已验证的 GUI 设置

沿用预览 → 阅读报告 → 导出的顺序。以下记录将实际截图与候选包哈希关联。

| 格式 / GUI 记录 | 实际设置或边界 |
| --- | --- |
| [xyz](../../../examples/tutorials/2.5.0/T17-gui-xyz-check.json) | 确认拓扑、身份和元数据省略 |
| [extxyz](../../../examples/tutorials/2.5.0/T17-gui-extxyz-check.json) | 高级缺失值标记留空；面板多一行 |
| [mol](../../../examples/tutorials/2.5.0/T17-gui-mol-check.json) | 该样本无需损失确认 |
| [mol2](../../../examples/tutorials/2.5.0/T17-gui-mol2-check.json) | 确认上述损失 |
| [pdb](../../../examples/tutorials/2.5.0/T17-gui-pdb-check.json) | 全部 10 个 model；确认晶胞省略 |
| [pqr](../../../examples/tutorials/2.5.0/T17-gui-pqr-check.json) | 确认分段索引省略；保留来源电荷 |
| [sdf](../../../examples/tutorials/2.5.0/T17-gui-sdf-check.json) | 仅选定记录；无需损失确认 |
| [smiles](../../../examples/tutorials/2.5.0/T17-gui-smiles-check.json) | 确认坐标、顺序、标题、原始记录及属性省略 |
| [cif](../../../examples/tutorials/2.5.0/T17-gui-cif-check.json) | 高级 CIF 模式：preserve |
| [poscar](../../../examples/tutorials/2.5.0/T17-gui-poscar-check.json) | 高级字段留空使用默认值；非默认值未验证 |
| [cube](../../../examples/tutorials/2.5.0/T17-gui-cube-check.json) | 单 dataset、索引留空；确认语义和单位省略 |
| [cjson](../../../examples/tutorials/2.5.0/T17-gui-cjson-check.json) | 保留原始 envelope 的 JSON 值 |
| [qcschema](../../../examples/tutorials/2.5.0/T17-gui-qcschema-check.json) | 仅原始 envelope，不加入工程派生字段；未重新计算 |

## 恢复与科学边界

更换输入后再次核对实体 UUID：实际 SDF 操作曾保留上一个输入的 UUID，因此被拒绝。复制当前输入的 UUID，重新预览后再导出。切换格式会改变可见控件，应按标签操作，不照抄固定屏幕坐标。

分开保留来源文件、来源 CBQ 和导出文件。输出已存在时换用新名称。需要确认损失时先阅读报告；确认只接受列出的省略，不代表允许任意科学数据变化。

5SUN 含未知 `un` 键，没有完整解释拓扑，导出拒绝符合预期。Open Babel mol24 引用了未声明的 substructure，导入被拒绝。两个拒绝均不抵消正向覆盖要求，也未人为补造缺失层级或键。

规范化 MOL2 是交换文件，不能替代配对的 `.blend` / `.cbq` 工程。交接时保留权威 CBQ。渲染材质和显示网格细分不会提高科学分辨率，也不能修复不完整拓扑。
