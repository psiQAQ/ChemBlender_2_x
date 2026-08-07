# 水分子 CJSON 结果合同样例

## 用途与选择理由

这是一个 `contract` 夹具，用很小的文件覆盖 CJSON 的结构、多个坐标集、原子属性、振动、光谱、轨道和 3D 标量网格。数值是测试数据，不应当当作真实量化计算结果引用。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/cjson/water-results.cjson@3e1d02e046851c6c89a81ac8dce42b435bb25509`
- 平台：ChemBlender repository；从测试夹具逐字节复制。
- 许可：`GPL-3.0`，见 [仓库许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)。

## 规模与分辨率

文件为 `1539` bytes，主体只有 3 个原子和 2 条键。`3dSets` 有 2 组几何，内嵌 Cube 为 `2 × 2 × 2` 共 8 个值；它适合检查字段映射，不足以评价轨迹播放或体数据展示性能。

## 字段说明

| 字段 | 内容 | ChemBlender 映射 |
| --- | --- | --- |
| `chemicalJson` | `1` | CJSON envelope 版本标记 |
| `atoms.elements.number` | `[8,1,1]` | 原子序数 |
| `atoms.coords.3d` / `3dSets` | 1 个主几何、2 组坐标 | Structure 与附加坐标数据 |
| `partialCharges` / `forces` | Mulliken 电荷与力 | 逐原子属性 |
| `vibrations` / `spectra` / `orbitals` | 频率、强度、电子跃迁、轨道能 | 受支持的结果数据 |
| `cube` | origin、spacing、dimensions、scalars | 小型 Grid3D |
| `customProjectField` | `preserve=true` | 由 CJSONEnvelope 保留的扩展字段 |

## ChemBlender 支持边界

ChemBlender 2.4.0 可恢复 Structure、Topology、CJSONEnvelope 及一部分结果数据。CJSON 可容纳的任意 JSON 扩展并不等于都有专门 UI；未知字段应留在 envelope。导出是 controlled envelope 路径，不能把重新序列化视作逐字节回写。

## 操作流程

1. 用 `Quick Import` 选择 [`water-results.cjson`](water-results.cjson)，在 Preview 查看 reader 和结果实体。
2. 确认后从 Project Browser 分别选择 Structure、振动/光谱数据和 Grid3D。
3. 若创建 Grid View，先核对 scalar semantic 与 unit；不要把测试值标为真实电子密度。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，读取 Operator RNA 后，用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/cjson/water-results.cjson 的绝对路径。只使用公开 bpy.ops.chemblender.* 和 UI RNA。先报告 Import Preview 中的 Structure、Topology、CJSONEnvelope、振动、光谱、轨道与 2x2x2 Grid3D，并明确这些是合同测试值；等我确认后再调用 bpy.ops.chemblender.confirm_import。创建网格视图前先用公开的 resolve_grid_semantics 流程，不猜单位；导出有损时停下请求确认。保存 .blend 与相邻 .cbq，并报告路径。
```

## 完整性与验证

- SHA-256：`82221e1b98092ccc05c74fd27ad5d52f63fef7d37d988516b2d2542dcbfae3ce`
- 精确大小：`1539` bytes
- 自动检查：3 atoms、2 bonds、1 CJSON result record，原字节受 manifest 约束。

## 参考资料

- [OpenChemistry Chemical JSON 说明](https://github.com/OpenChemistry/chemicaljson)
- [Chemical JSON schema](https://github.com/OpenChemistry/chemicaljson/blob/main/cjson.schema)
