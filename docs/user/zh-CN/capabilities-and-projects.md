# 能力与项目生命周期

Standard processor 提供核心 CBQ 操作、22 个注册 reader（按声明依赖决定可用性）和 13 种公开导出格式。精确清单见源码生成的 [public-surface.json](../../prepare/public-surface.json) 与 [format-capabilities.json](../format-capabilities.json)。

`capabilities` 是当前机器的实时事实源。`doctor` 在 Standard NumPy/RDKit/Gemmi 不完整时失败，并对未配置的专业 route、critic2、QCEngine/provider operation 或 reader 给出具体 warning。

保存后的项目由两部分组成：

- `project.blend`：Scene、Blender View、呈现状态和 project link。
- `project.cbq/`：权威科学实体、provenance、revision、数组和可重建缓存。

两者必须一起移动。导入与外部 operation 追加带 provenance 的实体；Mesh Apply 创建 derived Structure，不改写 imported 坐标。View 的外观变化不会自动变成科学数据。

## 保存、移动与恢复工程（T18）

选择 **File > Save As**，输入新的 `.blend` 文件名，再点击 **Save As**。ChemBlender 会写入同名 `.cbq` 文件夹。移动时携带两者；退出 Blender 后重新打开移动后的 `.blend`，检查工程交接。文件对话框中的 **Cancel** 会保留当前工程。

如果只移动了 `.blend`，已有对象可能仍然可见，但科学数据不可用。在 3D Viewport 按 **N**，选择 **ChemBlender**，找到 **Project Browser**。**Project link: Missing** 与 **No project data** 表示科学数据链接需要恢复；仅能看到模型不能证明工程完整。

![Project Browser 显示科学项目链接缺失](../assets/2.5-tutorials/project-link-missing.jpg)

点击 **Relink**。在文件对话框中进入正确的 `.cbq` 文件夹，文件名保留 **manifest.json**，点击 **Recover Project Link**。选错项目会提示 `sidecar project UUID or manifest hash does not match scene link`，已有 View 保留。关闭错误提示，再点击 **Relink** 选择正确的 manifest。不要用 **Detach** 绕过不匹配提示。

![选错 CBQ 被拒绝，已有 View 保留](../assets/2.5-tutorials/project-link-mismatch.jpg)

恢复后保存 `.blend`，生成位于其旁边的配对 `.cbq`。退出后用新 Blender 进程重新打开，检查预期实体和 View。通过前保留原始配对工程。

T18 阿司匹林实测已核对 21 个原子、未变的实体 UUID/revision、9 份一致的科学数组、GUI Save As/Cancel、错误重链接拒绝后正确恢复，以及两份已保存工程的独立进程冷重开。截图绑定候选 ZIP `a1e2da79…`；这些是 Agent 证据，独立人工验收仍待完成。完整记录：[GUI 另存](../../../examples/tutorials/2.5.0/T18-run007-gui-save-check.json)、[GUI 恢复](../../../examples/tutorials/2.5.0/T18-run007-gui-relink-check.json)、[冷重开](../../../examples/tutorials/2.5.0/T18-run007-gui-pairs-cold-check.json)。
