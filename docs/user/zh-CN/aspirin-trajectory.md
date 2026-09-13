# T06：阿司匹林轨迹与同帧原子力

本课只走一条路线：从固定 extXYZ 输入，经 Prepare、两个轨迹 View、逐帧检查、播放与渲染，得到可整体移动的配对工程。

![精细化后的源帧 15，Cycles 2400×1800、256 samples](../assets/2.5-tutorials/trajectory-refined-run009.png)

灰色为碳、红色为氧、白色为氢，黄色箭头表示原子力。输入没有准备好的键，因此显示原子和箭头。该投影下仍有部分箭头与原子重叠。光照和阴影会改变显示颜色，本图不是定量色标。

## 固定输入与前提

先完成[安装](installation.md)和[首课](first-aspirin.md)。使用 Blender 5.1.1、Prepare 0.1.0。下载 [aspirin-rmd17-32.extxyz](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz)、[来源与许可说明](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.md)和[冻结规格](../../../examples/tutorials/2.5.0/T06.case-spec.json)。来源说明含旧 Quick Import 操作，本课 2.5 使用下面的 CBQ 路线。

| 项目 | 参考 |
| --- | --- |
| 输入 SHA-256 | `95ad7342776441a9ce2d524a65351dad8b8e29ab40857b4ed858d17ab71a409a` |
| 来源 | CC0 rMD17 v3 阿司匹林；NPZ 行 0、100、…、3100 |
| 形状 | 32 帧 × 21 原子 × 3 分量 |
| 坐标 | angstrom |
| 力 | electron_volt_per_angstrom |
| 能量 | electron_volt |
| step | dimensionless，数组行标识 |
| source_index | 原索引；单位 unknown，语义状态 ambiguous |
| 物理时间间隔 | 未提供；使用 source frame，不标 ps |

## Prepare 转换

把输入放入新的教程目录。在 Prepare 中使用已安装的 Standard 运行环境 Python：

1. 操作选择 `inspect`，输入框粘贴 extXYZ 路径，Reader ID 填 `extxyz`，点击 `执行`。切换操作会改变表单布局，应重新定位按钮。预期返回 `success`、frame_count `32`、atomic_force 及 energy/source_index/step 逐帧属性。

![实际 Prepare inspect 结果](../assets/2.5-tutorials/trajectory-prepare-inspect.jpg)

2. 操作改为 `convert`，保留输入及 Reader ID，输入类型为 `files`，校验模式为 `balanced`。填写新的 CBQ 输出路径，点击 `执行`。预期返回 `success`；没有预制键的提示与下面的原子／箭头 View 一致。

![实际 Prepare convert 结果](../assets/2.5-tutorials/trajectory-prepare-convert.jpg)

预期成功，得到 `coordinates` FrameSet、`atomic_force` AtomFrameProperty，以及 `energy`、`step`、`source_index` FrameProperty。保存的全部坐标、力和逐帧数值属性均与独立解析的输入文本完全一致，32 帧的元素顺序保持相同。保留 source_index 的 ambiguous 状态；转换成功不能补出缺失单位。

## 创建并检查轨迹

1. 在新场景中设置并确认 `CBQ Package`，依次使用 `Preview CBQ`、`Import CBQ`。预期加入 9 个实体。
2. 在 Project Browser 选择 FrameSet。在 `Scientific Representation` 保持 `Automatic`、`Research`，说明显示 `Trajectory frame`，点击 `Create View`。
3. 选择 `atomic_force` 数据集，此时 `Automatic` 对应 `Trajectory with forces`。再次点击 `Create View`，创建绑定同一个 FrameSet 及其力属性的独立 View。
4. 关闭前一个普通轨迹 View 的视口与渲染可见性，同时保留该 View。也隐藏默认 Cube。选中力 View，用小键盘 `.` 取景。不同帧的多个 View 重叠会看起来像多出了原子。
5. 在力 View 控件中将 `Source Frame Index (0-based)` 设为 `15`，点击 `Apply Frame`；坐标和力箭头一起更新。用同样方法检查 `0`、`31`。下面的截图显示两个端点。

![实际应用源帧 15](../assets/2.5-tutorials/trajectory-apply-frame.jpg)

![FRAME 重放后的源帧 0](../assets/2.5-tutorials/trajectory-frame0.jpg)

![FRAME 重放后的源帧 31](../assets/2.5-tutorials/trajectory-frame31.jpg)

[端点检查](../assets/2.5-tutorials/trajectory-first-last-check.json)确认坐标与缩放后的力满足显示容差。

逐个检查全部 32 帧时，显示顶点与向量应在 `1e-6` 显示精度内对应正确源帧，权威数组保持不变。Vector Display Scale 不为 1 时，应将显示向量与“源力乘显示比例”比较。

| 源帧 | 能量，eV | step | source_index |
| --- | --- | --- | --- |
| 0 | -17617.8287419 | 0 | 161596 |
| 15 | -17617.4879446 | 1500 | 26491 |
| 31 | -17617.7618802 | 3100 | 151469 |

这些是数据集参考值，不是 Blender 重新计算的能量。`source_index` 仍明确标成 `unit unknown; ambiguous`。

## 播放与暂停

在侧栏内滚动到 `Apply Frame` 下方的 `Play`、`Pause`。保持 Animation Start Frame 为 `1`，Timeline Frames Per Source Frame 为 `1`。点击 `Play`：时间线范围变为 1–32，源帧等于时间线帧减一。点击 `Pause` 后，时间线与科学播放均停止。

`Apply Frame` 预览一个静态源帧。暂停时场景时间线可以显示另一个数值，应以源帧控件和 View 保存的元数据识别静态预览。24 fps 显示速度不能证明缺失的物理采样间隔，也不能证明所选构型统计独立。

## 细化与渲染

1. 选中力 View，使用 `Load Selected View`，将 Vector Display Scale 设为 `0.35`，启用 `Light Quantitative Colors`，再点 `Update Style / Parameters`。缩短箭头是显示选择，不是力单位转换。
2. 打开力 View 的 `ChemBlender Ball and Stick` Geometry Nodes 修改器。在现有 `CH_Ball and Stick` 组中将 `Subdivision` 设为 `5`，不要改源坐标与力。
3. 在同一节点编辑器按 `Shift+A`，搜索并添加 `Set Shade Smooth`，放在 `ChemBlender Scientific Atom Material` 后。按 `Group.001: Ball and Stick` → `ChemBlender Scientific Atom Geometry` → `ChemBlender Scientific Atom Material` → `Set Shade Smooth: Mesh` → `Join Geometry` 接线；保留 `ChemBlender Vector Instances` 到 `Join Geometry` 的独立连接。删除原先 Atom Material 直连 Join 的线，否则平面与平滑原子分支会重叠，面数会从 21,000 翻倍到 42,000。

4. 在 Camera 属性中选择 `Orthographic`，Location 设为 `(0, -16, 11)`，Rotation X 为 `0.968509` 弧度、Y/Z 为 `0`，Orthographic Scale 为 `11`。Point Light 位于 `(0, -16, 11)`，Power `14000`、Radius `3`。添加名为 `Tutorial Fill` 的 Area light，位置 `(5, 4, 8)`、Shape `Disk`、Power `1800`、Size `8`，朝向原点。World 属性中将 Background 线性 RGB 设为 `(0.18, 0.18, 0.18)`、Strength `1`。
5. 在 Render Properties 选择 Cycles、Device `CPU`、Render Samples `256` 并启用降噪；Output Properties 设为 `2400×1800`、`100%`、`PNG`。应用源帧 15，按 `F12`，再用 `Image → Save As…`；将配对 `.blend` 保存到完整 `.cbq` 目录旁。
6. 动画前先配置播放，按 `Pause` 停止视口但不要关闭科学播放标志；Start/End 设为 `1`/`32`，新输出路径设为 `//frames-refined/frame_`、格式 PNG，再用 `Render → Render Animation`（`Ctrl+F12`）。另建 Video Editing 场景，用 `Add → Image/Sequence` 按文件名顺序选择 32 张 PNG；设 24 fps、同样的 2400×1800，输出选择 `FFmpeg Video`、容器 `MPEG-4`、编码 `H.264`、路径 `//trajectory-refined.mp4`，然后渲染动画。

Rebuild 或 Update 可能替换显示对象，替换后需重新设置 Subdivision 5 和单条 Set Shade Smooth 节点分支；渲染前检查节点连接。更多显示多边形或更平滑的法线不会增加科学采样点。

## 工程交接与恢复边界

工作工程是 `trajectory-refined.blend` 加完整 `trajectory-refined.cbq` 目录；静态 PNG 与完整 PNG 序列另行保留。复制或移动时同时携带工程对与帧目录，正常退出 Blender，再用新进程打开副本 `.blend`。加载后科学播放关闭，需要显式重新启动。派生几何缺失时，从本地 CBQ 执行 Rebuild，再重新应用显示细化；不要把权威 `.npy` 数组当作显示缓存删除。大型帧序列、MP4 和配对工程保存在本地案例产物目录，不进入 Extension ZIP。

## 验证附录

已接纳的 run-009 证据使用 Extension SHA-256 `a1e2da79253d505b60daa42aa465eb725cdd1eba00e6c81ce4082102a62d0f28` 和 Prepare wheel SHA-256 `b736bc61ecdbee77f61696576c98092afc7352a9af16b4367bfd3c2e3159af3a`。[Prepare GUI](../../../examples/tutorials/2.5.0/T06-run009-gui-check.json)、[GUI 输出科学检查](../assets/2.5-tutorials/trajectory-gui-science-check.json)、[全帧 View](../../../examples/tutorials/2.5.0/T06-run009-view-check.json)、[力检查](../assets/2.5-tutorials/trajectory-force-check.json)、[播放](../../../examples/tutorials/2.5.0/T06-run009-playback-gui-check.json)、[重建](../../../examples/tutorials/2.5.0/T06-run009-rebuild-check.json)及[离线恢复](../../../examples/tutorials/2.5.0/T06-run010-offline-recovery-check.json)记录保持单独候选绑定。等价 CLI inspect/convert/validate 路线也已通过，但只属于审计证据，不是第二条教程路线。只读当前帧行已由脚本核对源帧 0、15、31，但仍缺直接 GUI 截图。

本地 `T06-review.zip` 含配对工程、静态图、32 帧序列、相对路径 VSE 装配、MP4、双语交接与证据；SHA-256 为 `8eea79a46ea7967bda201619dbb066e6a2908315bdc9c884c1c4844284c8003a`。[审阅包记录](../../../examples/tutorials/2.5.0/T06-run009-package-check.json)只证明 review-only 交接，不是最终分发。[动画](../../../examples/tutorials/2.5.0/T06-run009-animation-check.json)、[视频完整性](../assets/2.5-tutorials/trajectory-video-check.json)、[可移动视频](../../../examples/tutorials/2.5.0/T06-run009-portable-video-check.json)、[冷重开](../assets/2.5-tutorials/trajectory-cold-recovery.json)、[缓存重建](../assets/2.5-tutorials/trajectory-cache-recovery.json)、保留的 [Smooth by Angle 实验](../assets/2.5-tutorials/trajectory-smooth.jpg)及[媒体来源](../assets/2.5-tutorials/provenance.json)属于审计材料。一次取消的渲染前审计是采集时机问题；`render_post` 与显式静态对照匹配正确源帧。连续 GUI 录屏、新标量行的直接截图和人工独立复做仍待完成。

最终本地候选适用性：Extension SHA-256 `73fe2c248a7c1ad939018ce21a4ae44c52855abbdaff124af581bd34ffe469c8`; Prepare wheel SHA-256 `3ca42c26be19aebc5444d5df5a0490a15d3da6c370f2c4ec6883921a3e8880e3`. 上述历史回执保留真实执行字节；[最终差异映射](../../../examples/tutorials/2.5.0/P6-final-candidate-applicability.json)不会把它们换标为新的 GUI 事件。
