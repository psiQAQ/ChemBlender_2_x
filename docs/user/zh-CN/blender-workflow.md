# Blender 完整联动 SOP

1. 运行 `chemblender-prepare doctor --json`；Standard 必需项必须 Passed。未配置可选后端时出现 warning 是正常结果。
2. 用 `uv tool dir --bin` 定位 launcher，在 Blender 填入 `chemblender-prepare.exe` 绝对路径并运行 **Test Processor**。确认 processor `0.1.0`、协议 `1`、Standard complete 和 operation/reader 数量。
3. 用 CLI 或 GUI 检查原始文件并生成新的 `.cbq` 目录。GUI 的 **derive** 保留 operation ID 与 JSON 参数，属于专家入口。
4. 在 ChemBlender 中 Preview 并导入 CBQ，在 Project Browser 选择科学实体。
5. 修改几何时编辑生成的 Mesh，再执行 **Apply** 创建新 derived Structure；imported Structure 与旧 View 不被覆盖。
6. 运行支持的外部 operation。modal 任务应显示进度、支持 Cancel、校验 project revision/hash，并追加新结果而不是替换旧结果。
7. 仅在实体能力允许时创建 Structure、Surface、Volume、trajectory、spectrum 等 View；配置 Cycles 并从 View 渲染。
8. 让 `project.blend` 与 `project.cbq/` 相邻保存。Save As 或移动时两者一起移动，冷重开后复核链接、实体、View 与 hash。
9. 删除 derived render cache 后从 CBQ 本地重建。移动 processor 或源文件不应破坏已有编辑、View、动画和渲染。
10. 测试取消和无效 processor 路径；恢复 launcher 路径，重新 **Test Processor**，再显式重试。

Blender 只暴露高频 Viewer 操作。转换或专业计算类 operation 留在 CLI/Worker；没有面板按钮不等于功能缺失。
