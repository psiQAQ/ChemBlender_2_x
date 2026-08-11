# 水分子 Gaussian 输入样例

## 用途与选择理由

这是仓库自带的最小 Gaussian Cartesian 输入，用于验证 ChemBlender 能直接展示 `.gjf/.com` 中的内嵌分子结构，并保留 charge 与 multiplicity。它不执行 Gaussian，也不解析 route、method 或 basis。

## 来源与许可

- 取得日期：`2026-08-11`。
- 来源标识：`tests/fixtures/gaussian/water.gjf@72b6e849e0bd4582a7e6a8be0b095a9691cf103a`。
- 来源路径：仓库测试夹具 `tests/fixtures/gaussian/water.gjf`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与字段

- 3 个原子：O/H/H。
- Cartesian 坐标单位：angstrom。
- molecular charge：`0`。
- molecular multiplicity：`1`。
- Gaussian title：`water`。

## ChemBlender 支持边界

内置 `gaussian-input` reader 支持严格四列 `Element x y z` 坐标。Z-matrix、freeze code、ONIOM/fragment 修饰和 `--Link1--` 多任务会明确失败；坐标块之后的 basis/ECP 文本保留在原始来源中，但不进入结构语义。

## 操作流程

1. 用 `Quick Import` 选择 [`water.gjf`](water.gjf)。
2. 在 Preview 确认 selected reader 为 `gaussian-input`，并显示 `structure` capability。
3. 确认导入后，在 Project Browser 查看 Structure，并检查可见的 Structure View。

3 atoms、charge `0` 和 multiplicity `1` 会保存在项目语义中并由自动合同验证；当前通用 Preview/Project Browser 行不会单独显示这三个字段。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，使用公开的 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/gaussian/water.gjf。报告 Preview 中的 selected reader、capability、quality/diagnostics；确认后调用 bpy.ops.chemblender.confirm_import，并验证 Project Browser Structure 与可见 Structure View。3 atoms、charge 0、multiplicity 1 是自动合同预期，不得声称已由通用 UI 可见验证。不得执行 Gaussian，也不得声称已解析 route、method 或 basis。
```

## 完整性与验证

- SHA-256：`e13db766c139372297f73fa6ff3b56dfba3ca401d2ca5049ed142d9a961e51f2`
- 精确大小：`128` bytes
- 自动检查：严格 Cartesian、3 atoms、charge/multiplicity、Quick Import preflight/commit。

## 参考资料

- [Gaussian remote file conventions](https://gaussian.com/wp-content/uploads/dl/remote.pdf)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
