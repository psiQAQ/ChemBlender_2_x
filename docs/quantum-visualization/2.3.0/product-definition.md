# ChemBlender 2.3.0 产品定义

## 产品声明

ChemBlender 是 Blender 原生、计算程序中立的化学、量子化学与材料数据兼容、管理和科学可视化平台。基础扩展优先读取已有数据，并在统一语义、单位、来源、质量和版本模型下创建可重建的 Blender 视图。计算、复杂波函数求值、大型周期电子结构后端和外部数据库均为可选增强。

## 成功标准

2.3.0 不是以新增多少 dataclass、adapter 或后端判断成功，而以以下完整用户任务判断：

```text
安装官方 Windows x64 ZIP
→ Quick Import 单个或多个文件
→ 自动识别并展示预检结果
→ 用户确认重复、歧义和归组建议
→ 数据原子提交到会话 QCProject
→ 自动创建结构、轨迹、晶体或场数据默认视图
→ 在 Project Browser 中按来源或数据查看
→ 保存 .blend 时固化 .cbq
→ 重开后恢复项目和可重建视图
→ 对承诺格式进行受控导出与 round-trip
```

## 资源比例

| 方向 | 比例 | 发布价值 |
| --- | ---: | --- |
| Native Compatibility | 70% | 降低安装和格式门槛，形成大规模真实用户入口 |
| Platform Foundation | 30% | 让格式、数据、视图、质量和插件可持续扩展 |

## 第一优先级：基础安装直接可用

- XYZ/extXYZ
- MOL V2000/V3000
- SDF
- MOL2
- PDB/PQR
- SMILES
- CIF（Gemmi 随包）
- POSCAR/CONTCAR
- Cube
- CJSON

RDKit 已经作为基础 wheel，因此其格式和化学拓扑能力属于第一优先级。Gemmi 在 2.3.0 升级为基础 wheel。spglib、cclib、IOData、GBasis、ASE、pymatgen、phonopy、PyProcar 与外部程序继续可选。

## 非目标

- 不在 2.3.0 建设完整量子化学计算平台。
- 不要求用户为基础格式配置 Conda、外部 Python 或独立程序。
- 不在 2.3.0 实现蛋白质 ribbon/cartoon、二级结构或大型生物轨迹系统。
- 不承诺 Cube 无损重写，因为文件通常不可靠声明标量场语义和单位。
- 不把所有可选后端暴露到 UI 作为正式产品承诺。
- 不把 Blender Mesh、Curve、Volume 或 custom properties 当作权威科学数据。
- 不在未测量前引入 Zarr、HDF5、GPU 或远程 worker。

## 科学可信原则

1. 原始导入实体不可变。
2. 用户科学编辑产生派生结构、派生拓扑或新 revision。
3. 显式文件数据与推断数据分开保存。
4. Partial、Ambiguous、Incomplete 与 Invalid 不得被 UI 隐藏。
5. reader 未实现字段与源文件缺失字段必须区分。
6. 所有自动归组和拓扑推断必须可解释并由用户确认。
7. 报告默认排除未解决的 Ambiguous 数据。
