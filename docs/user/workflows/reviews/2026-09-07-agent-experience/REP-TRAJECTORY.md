# REP-TRAJECTORY — 32×21 extXYZ 与逐帧属性

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：32×21 数据重开与重配置、帧 1/32 坐标及 force、播放/暂停；energy/step/source_index 数组完整性。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-TRAJECTORY-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-TRAJECTORY-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-TRAJECTORY/UI/REP-TRAJECTORY-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-TRAJECTORY-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-TRAJECTORY-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-TRAJECTORY/MCP/REP-TRAJECTORY-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI **Passed**；MCP **Passed**。Blender5.1.1/Python3.13.9，source `1c290eec5d98a6f0cbbb5d6749069c3cc1872dca`，R22 ZIP SHA-256 `82529f5564f8b4f9b319785c35094700c431747ff2daa3b438312c6a2b3a8e56`。最终全轮同包复核仍待完成。

前置：独立空文件、独立profile；UI完成后MCP才开始。输入为不可变`aspirin-rmd17-32.extxyz`副本，61621bytes，SHA-256 `95ad7342776441a9ce2d524a65351dad8b8e29ab40857b4ed858d17ab71a409a`，[来源清单](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-input.json)。32帧演示子集，不能作为统计独立训练样本。

| 检查 | UI原生步骤与可见结果 | MCP公开操作与结果 |
| --- | --- | --- |
| 导入 | N侧栏 → Select Files → 文件选择器；Preview显示32frames、atomic_force、energy/source_index/step、Complete；OK产生21原子View | 读RNA/poll，quick_import → preview_json → confirm_import；32帧摘要一致，committed、21vertices |
| 绑定播放 | Outliner选View；Browser By Data搜索coordinates、选Coordinates、Configure Trajectory Playback；结束帧变32 | 从公开Browser行选择frame_set、激活匹配View；configure_trajectory_playback(frame_start=1,frame_step=1)返回FINISHED |
| 力属性 | Browser搜索force，选择Atomic Force → Show Force Vectors；出现箭头和current frame状态 | 选择atom_frame_property，apply_frame_force(display_scale=1.0)返回FINISHED；单位electron_volt_per_angstrom |
| 抽帧 | 在时间轴数字框输入1/16/32；分别读取状态并从同一相机保存渲染 | public scene.frame_set(1/16/32)，逐次核对公开向量属性并render.render |
| 播放与暂停 | 空格播放，公开is_animation_playing=true、可见播放截图；再空格暂停，停在11帧 | public screen.animation_play，再animation_cancel(restore_frame=False)；true→false，32帧之后实际循环到5帧 |
| 能量与保存 | Browser搜索并选Energy，显示Complete；恢复32帧，原生Save As生成配对 | 读取Energy/Step/Source Index行；保存前恢复32帧，public save_as_mainfile生成配对 |

两路线分别保存`REP-TRAJECTORY/UI`和`REP-TRAJECTORY/MCP`集合，内含真实绑定View和证据相机。相机/集合由展示脚本整理，不改写科学数组；UI的产品导入、播放配置、属性选择、时间轴、播放暂停和保存均使用真实鼠标键盘。

科学验证：所有32×21坐标和力都与extXYZ文本一致；energy、step、source_index逐帧相等，两个sidecar的五个数据集数组hash相同。抽查Blender1/16/32对应数组0/15/31，顶点与力属性匹配同一帧，状态均为current frame。首末坐标不同。能量单位electron_volt、力electron_volt_per_angstrom、坐标angstrom。Source Index仍标Ambiguous，因为来源没有单位声明；不擅自补科学语义。三组能量和索引数值见[科学检查](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-science-check.json)。

入口/文案：Browser搜索与Configure/Show Force按钮可找到，需要先选对数据行及匹配View；选择后有32frames和force状态反馈。Preview显示帧数和属性名，未显示全部单位或21atoms/frame，已修正文档要求。Energy当前可列为数据集但没有数值显示按钮，本项从保存项目核对数值，不声称UI画出了能量曲线。等待均短，UI原生输入累计44.88秒；MCP导入至保存的各操作累计5.28秒，不含观察间隔。Preview有Cancel；本项没有重复执行导入取消，原生播放暂停与MCP animation_cancel均实测。恢复播放后仍能抽帧和保存。

操作问题：第一次点击时间轴数字框左侧箭头，将帧减为0而没有输入16；状态断言立即停止，随后准确点击数字中心并输入16/32，重测通过。该问题属于Agent输入定位，不是插件错误，没有源码修复commit。本项未发现新的可复现产品缺陷；沿用R22对以前轨迹/箭头修复的实际重测，未混用R13画面。六张渲染全部实际打开检查，原子形变与力箭头可见，没有空白或裁切。

| 帧 | UI渲染 | MCP渲染 |
| --- | --- | --- |
| 1 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-UI-sample1-render.png) | [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-MCP-sample1-render.png) |
| 16 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-UI-sample16-render.png) | [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-MCP-sample16-render.png) |
| 32 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-UI-sample32-render.png) | [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-MCP-sample32-render.png) |

- [Preview](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-01-preview.png) / [配置入口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-03-playback-entry.png) / [播放窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-09-playing.png)
- [Energy与末帧](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-TRAJECTORY-R22-11-energy-selected.png) / [MCP公开行](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-MCP-rows.json)
- [UI配对](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-UI/REP-TRAJECTORY-UI.blend) / [MCP配对](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-MCP/REP-TRAJECTORY-MCP.blend)
- [UI播放](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-UI-playing.json) / [暂停](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-UI-paused.json) / [MCP播放](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-MCP-playing.json) / [暂停](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-TRAJECTORY-R22-MCP-paused.json)

配对保存与全部文件hash已核对；本项未冷重开或删除缓存，不把保存等同冷重开。R22完整自动验证2313tests/26有理由skips、隔离smoke104.33秒及原生构建审计通过记录保持不变；本项只新增文档与证据。
