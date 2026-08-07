# COD 4503272 咖啡因共晶 CIF 代表样例

## 用途与选择理由

这个 `representative` 样例用于检查真实 CIF 中的非对称单元、部分占位、disorder group 和原始实验元数据。它比 NaCl 合同样例更接近日常晶体数据，但 64 个非对称位点仍属于适合交互检阅的规模。

## 来源与许可

- 来源标识：`COD 4503272`；2026-08-08 从 [Crystallography Open Database 原始 CIF](https://www.crystallography.net/cod/4503272.cif) 逐字节取得。
- 记录描述 caffeine–succinic acid–chloroform 4/1/2 共晶，文献 DOI 为 `10.1021/cg700929e`。
- 许可：`CC0-1.0`，见 [COD 数据提交与公共领域说明](https://www.crystallography.net/cod/new.html)。

## 规模与分辨率

文件大小 `14996` bytes，含 1 个 block、64 个非对称位点，其中 23 个 occupancy 小于 1，9 个带 disorder group；空间群编号为 64。晶胞参数带实验不确定度，坐标精度来自 COD 原记录，不能用文件 KB 数推断实验分辨率。

## 字段说明

| 字段组 | 本文件内容 | 含义 |
| --- | --- | --- |
| `_cell_*` | `a=6.64390(10)`、`b=23.2514(4)`、`c=33.5615(7) Å` | 晶胞与标准不确定度 |
| `_space_group_*` | `C m c a`、IT 64 | 声明空间群 |
| `_atom_site_fract_*` | 64 行 | 非对称单元分数坐标 |
| `_atom_site_occupancy` | 23 个部分占位位点 | 混占或无序的占位信息 |
| `_atom_site_disorder_group` | 9 个位点 | 无序组关系 |
| `_publ_*` / `_diffrn_*` | 文献、温度、辐射与反射数据 | 原始实验和发表元数据 |

## ChemBlender 支持边界

ChemBlender 2.4.0 保留 `CIFEnvelope`，把晶胞、位点、occupancy、disorder 和声明 symmetry 映射到项目。Gemmi 负责 CIF 语法；可选的 symmetry 派生不会覆盖文件声明。一般 CIF tag 会保留在 envelope，但并非每个实验字段都有独立 UI 控件；导出前必须检查逐项 loss preview。

## 操作流程

1. 用 `Quick Import` 选择 [`cod-4503272-caffeine-cocrystal.cif`](cod-4503272-caffeine-cocrystal.cif)，在 Preview 核对 occupancy/disorder 诊断。
2. 确认导入，在 Structure 属性查看 declared symmetry，并按需调用 `derive_crystal_symmetry` 做比较。
3. 建立周期 View；若导出 Normalized CIF，逐项确认 envelope 字段变化。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，读取 Operator RNA 后，用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/cif/cod-4503272-caffeine-cocrystal.cif 的绝对路径。只走 UI 等价的 bpy.ops.chemblender.*；先报告 64 个非对称位点、部分 occupancy、disorder、声明空间群、Import Preview 诊断和项目实体，再等我确认 bpy.ops.chemblender.confirm_import。若比较 symmetry，可调用公开的 bpy.ops.chemblender.derive_crystal_symmetry，但不得覆盖源声明。任何有损导出停在确认界面；保存 .blend 时把 .cbq 放在旁边并报告路径。
```

## 完整性与验证

- SHA-256：`0ab8afbcc0f931327a5cba664df8317bf557f3b6f06b1fe5b27908676b89c5f5`
- 精确大小：`14996` bytes
- 自动检查：1 block、64 asymmetric sites、23 partial-occupancy sites、9 disorder-group sites、IT number 64。

## 参考资料

- [COD 4503272 原始记录](https://www.crystallography.net/cod/4503272.cif)
- [IUCr CIF 1.1 语法规范](https://www.iucr.org/resources/cif/spec/version1.1/cifsyntax)
- [COD 数据库说明](https://www.crystallography.net/cod/)
