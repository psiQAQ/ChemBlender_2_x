# ChemBlender 2.5 用户指南

[English](../en/index.md)

ChemBlender 是 CBQ Viewer。原始化学与模拟文件先在 Blender 外由 prepare 转为经过校验的 CBQ，再交给 Viewer。processor 或原始文件移走后，已保存项目仍可编辑、显示、动画和渲染。

## 指南

- [安装、更新与卸载](installation.md)
- [Blender 完整联动 SOP](blender-workflow.md)
- [首课：阿司匹林与实际 GUI 截图](first-aspirin.md)——已完成 Agent 实操，待人工复做。
- [T02：乙醇构象、MMFF94 与网格 Apply](ethanol-conformers.md)——已有实际 GUI 与科学检查，待人工复做。
- [T04：晶胞、占位与金刚石](crystal-cells.md) — 草稿；科学与恢复验证通过，GUI 和人工验收待完成。
- [能力与项目生命周期](capabilities-and-projects.md)
- [错误与恢复](troubleshooting.md)
- [发布状态与已知限制](release-status.md)

固定顺序：安装 Standard prepare → 定位 executable → 配置 Blender → Test Processor → CLI/GUI 生成 CBQ → 导入/编辑/Apply → 外部 operation → View/Cycles → 保存/移动/冷重开 → 取消与故障恢复。
