# 能力与项目生命周期

Standard processor 提供核心 CBQ 操作、22 个注册 reader（按声明依赖决定可用性）和 13 种公开导出格式。精确清单见源码生成的 [public-surface.json](../../prepare/public-surface.json) 与 [format-capabilities.json](../format-capabilities.json)。

`capabilities` 是当前机器的实时事实源。`doctor` 在 Standard NumPy/RDKit/Gemmi 不完整时失败，并对未配置的专业 route、critic2、QCEngine/provider operation 或 reader 给出具体 warning。

保存后的项目由两部分组成：

- `project.blend`：Scene、Blender View、呈现状态和 project link。
- `project.cbq/`：权威科学实体、provenance、revision、数组和可重建缓存。

两者必须一起移动。导入与外部 operation 追加带 provenance 的实体；Mesh Apply 创建 derived Structure，不改写 imported 坐标。View 的外观变化不会自动变成科学数据。
