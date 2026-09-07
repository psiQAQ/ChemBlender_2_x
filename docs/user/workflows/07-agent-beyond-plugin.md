# Agent 辅助的 Blender 操作：插件能力外

以下案例允许 Agent 使用一般 `bpy`。它们只改变场景呈现或 Blender 文件组织，不是 ChemBlender 的产品能力，也不能把 Object transform、material、visibility 或 render settings 写成科学数据修改。

开始前先确认选择的是 ChemBlender 已创建的 View，而不是让 Agent 凭名称猜对象。渲染前还要通过 depsgraph 检查该 View 的 `evaluated geometry` 或 Volume bounds 确实包含可渲染内容；只有点、没有面或实例的 View 可能在视口可选，却不能直接渲染。不得改 mesh 顶点、科学 attributes、Geometry Nodes 中承载结构语义的输入、ChemBlender custom properties 或 `.cbq`。

## 材质样式

这不是 ChemBlender 插件能力。材质只影响 View 外观。

对象材质槽不一定控制最终原子颜色。Geometry Nodes 生成的实例可能使用自己的材质（如 CH_Molecule）；先检查 evaluated geometry/instances 的实际材质，再用渲染验证。仅修改对象材质槽时，应明确报告其作用范围，不能根据槽值宣称画面已变色，也不要为套用展示材质而改写科学节点输入。

```text
在当前 Blender 中使用一般 bpy，为我已明确选中的 ChemBlender View 准备展示材质。先读取 selected objects、现有 material slots 和 node RNA；不要按名称猜对象。有现有材质时复制后修改，没有材质时创建新的展示材质并说明此前 material slot 为空。只调整 Base Color、Roughness、Metallic、Alpha 等材质参数，不改 mesh、Geometry Nodes、custom properties、Object transform 或任何 scientific entity。完成后返回对象、材质、修改前后参数和渲染视口截图状态；不要声称化学元素、键级或属性发生变化。
```

## 世界、灯光与相机

这不是 ChemBlender 插件能力。它是普通场景布光。

```text
使用一般 bpy 为当前展示场景设置 world background、一盏 Area light 和一台 Camera。先报告现有 world/light/camera，复用可用对象；只有缺失时才创建。根据当前可见 View 的 evaluated world-space bounds 构图；若 evaluated geometry 没有可渲染面、实例或有效 Volume bounds，停止并要求用户明确选择另一个 View，不得按名称代选。不得修改这些 View 的 transform、mesh、materials、Geometry Nodes 或 custom properties。完成后返回相机位置、焦距、灯光能量、背景颜色和 framing 证据。这些变化只属于 Blender scene。
```

## Collection 与可见性

这不是 ChemBlender 插件能力。Collection 组织不改变 Project entity。

```text
使用一般 bpy 创建或复用名为 `Presentation` 的 collection，把我明确选择的 View 额外 link 到该 collection，并保留原 collection membership。只设置 collection/view-layer visibility，不删除、不重命名 ChemBlender owned collection/object，不改对象数据、transform、custom properties 或 `.cbq`。返回每个对象操作前后的 collection membership 和可见性；说明这是 scene organization，不是 scientific grouping。
```

## Eevee / Cycles 渲染设置

这不是 ChemBlender 插件能力。渲染参数不会改变 Structure 或 Grid3D。

```text
使用一般 bpy 配置当前 scene 的渲染。先检查 Blender 5.1 live RenderSettings RNA 和可用 engine enum，再按我的选择设置 Eevee 或 Cycles、分辨率、samples、透明背景和输出格式；不要猜旧版本 enum。不得修改 ChemBlender View 的科学 geometry、attributes、bindings、custom properties 或 `.cbq`。执行一次低分辨率测试渲染并实际打开图像或返回截图；只有文件存在或 Operator 返回 `FINISHED` 不算通过。画面空白、全黑、严重裁切时，检查 evaluated geometry、相机投影、render visibility 和材质后重新构图；仍不可渲染就停止并说明原因。返回 engine、分辨率、samples、输出路径、文件大小和图像可读性；不要把渲染结果描述成科学导出。
```

## 保存展示副本

这不是 ChemBlender 插件能力。普通 Blender Save As 不能替代 ChemBlender 项目的配对备份。

```text
使用一般 bpy 检查当前 filepath、dirty state 和 `bpy.ops.wm.save_as_mainfile` Operator RNA。若当前文件连接 ChemBlender Project 或存在 `.cbq` 配对要求，停止并转用用户工作流的 Save Project/冷重开流程；不要直接复制或改 sidecar。只有我确认这是普通、无 Project link 的展示文件时，才保存到一个全新 `.blend` 路径，禁止覆盖当前文件。完成后重开副本，验证 camera、lights、materials、collections 和 render settings，并返回路径、SHA-256、大小与重开结果。
```

## 判定边界

- 能否改变颜色、灯光或相机，是 Blender/Agent 能力，不是插件格式支持。
- 能否保存一张图，不代表 source、quality、revision 或 export round-trip 已通过。
- 如果展示需求必须改变原子坐标、元素、cell 或 topology，回到[处理数据](02-process.md)，通过 `Apply Scientific Edits` 等公开流程创建 derived entity。

返回 [Agent 与 Blender MCP](06-agent-and-mcp.md)或[工作流总览](README.md)。
