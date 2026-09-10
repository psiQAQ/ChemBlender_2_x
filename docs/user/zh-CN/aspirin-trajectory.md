# T06：阿司匹林轨迹与同帧原子力

## 当前候选：精细工程与已验证播放

下方早期操作记录与图片保留原候选绑定。当前本地审阅使用 `run-009/T06` 中的 `trajectory-refined.blend` 和完整同名 `.cbq` 目录。Extension SHA-256 为 `a1e2da79253d505b60daa42aa465eb725cdd1eba00e6c81ce4082102a62d0f28`；prepare wheel SHA-256 为 `b736bc61ecdbee77f61696576c98092afc7352a9af16b4367bfd3c2e3159af3a`。下文固定输入和科学单位不变；新候选已有 [Prepare GUI 检查](../../../examples/tutorials/2.5.0/T06-run009-gui-check.json)及[全帧 View 检查](../../../examples/tutorials/2.5.0/T06-run009-view-check.json)。大型产物目前仅供本地审阅，可分发下载包仍待完成。

![精细化后的源帧 15，Cycles 2400×1800、256 samples](../assets/2.5-tutorials/trajectory-refined-run009.png)

原子显示比例为 `0.3`，力箭头显示比例为 `0.35`，原子细分为 `5`，材质粗糙度为 `0.3`。功率 `14000` 的点光源和功率 `1800`、尺寸 `8` 的圆盘补光改善可见性。工程使用单条 Set Shade Smooth 原子分支，共 21,000 个平滑面，没有采用早期的 Smooth by Angle 修改器。自定义节点通过 MCP 编辑，其手动 GUI 搭建仍未验证。保留科学数组：这些修改改善显示表面，不会提高数据采样分辨率。当前投影仍有部分箭头被遮挡。

1. 将精细 `.blend` 与 `.cbq` 放在一起后打开。如果恢复的 Image Editor 遮住场景，关闭该辅助窗口。选中力 View `ChemBlender Structure.001`，在 `Scientific Representation` 下使用 `Load Selected View`。冷加载后科学播放默认暂停。
2. 在 Project Browser 选中坐标 FrameSet，点击 `Configure Trajectory Playback`。在 ChemBlender 侧栏内滚动至科学控件，保持 Animation Start Frame 为 `1`、Timeline Frames Per Source Frame 为 `1`。
3. 点击 `Apply Frame` 下方的 `Play`，再点 `Pause`。本候选的两个按钮均通过 Computer Use 实际点击。暂停截图的时间线为第 `30` 帧，对应源帧 `29`；坐标与缩放力均在 `1e-6` 容差内匹配该源帧。

![实际 Pause 后的时间线第 30 帧](../assets/2.5-tutorials/trajectory-pause-run009.jpg)

`Source Frame Index (0-based)` 是静态 Apply Frame 输入；本次播放中它保持 `0`，不是实时帧计数器。播放时使用时间线映射；静态 Apply Frame 预览可能与时间线不同。[GUI 播放记录](../../../examples/tutorials/2.5.0/T06-run009-playback-gui-check.json)区分 MCP 准备与实际点击。窄侧栏会截断部分标签，完整截图可读性和人工复做仍待验收。

精细工程原位及移动副本冷重开通过，源帧 15 和平滑设置保留，见[细化与恢复记录](../../../examples/tutorials/2.5.0/T06-run009-refined-check.json)。新 32 帧序列采用公开 FRAME 与渲染重放，再通过原生 VSE 装配。H.264/MPEG4 视频为 2400×1800、24 fps，在浏览器 CDP 离线模拟下播放到末尾，时长 1.333333 秒，见[动画记录](../../../examples/tutorials/2.5.0/T06-run009-animation-check.json)。这不是新的 Ctrl+F12 GUI 验证，也不是操作系统级断网测试。原视频装配保留绝对路径；审阅包中的装配使用 `//frames-refined/` 和相对 MP4 输出。移动副本冷重开、全部 32 帧哈希及重新编码通过，见[可移动视频记录](../../../examples/tutorials/2.5.0/T06-run009-portable-video-check.json)。保持装配工程与完整帧目录相邻；物理时间仍未知。

旧 `trajectory-view.blend` 草稿含重叠的平面／平滑显示分支，请使用精细工程。Rebuild 可能移除自定义外观节点，需要重新设置。在副本上清空派生几何后，REBUILD 恢复保存配方的源帧 0。依次使用 `Load Selected View`、将 Source Frame Index 设为 `15`、点击 `Apply Frame`，再保存以恢复该静态预览。坐标与力、View 标识、科学数组不变及随后冷重开均通过，见[重建记录](../../../examples/tutorials/2.5.0/T06-run009-rebuild-check.json)。自定义平滑已被移除，需要重新设置。完整手动渲染说明、剩余 GUI 覆盖及人工独立验收仍未完成。

本地 `T06-review.zip` 含 92 个文件（121,561,147 bytes）：输入及许可、精细配对工程、静态图、32 帧、相对路径视频装配、MP4、双语交接及证据。SHA-256 为 `8eea79a46ea7967bda201619dbb066e6a2908315bdc9c884c1c4844284c8003a`。新解压目录中的科学工程冷重开和视频帧路径／哈希检查通过，见[审阅包记录](../../../examples/tutorials/2.5.0/T06-run009-package-check.json)。这是本地审阅包，不是最终验收通过，也未把大包嵌入本离线页面。

本课为执行中草稿。输入转换、全帧科学对照、实际 Create View／Apply Frame／Play／Pause 操作及静态渲染已有证据。32 帧 PNG 序列、H.264 编码、原位／移动后冷重开及派生几何重建也已通过。连续录屏、剩余 GUI 留证和人工独立复做仍待完成。

![源帧 15 的阿司匹林与缩放力箭头](../assets/2.5-tutorials/trajectory-frame15.png)

灰色为碳、红色为氧、白色为氢，黄色箭头表示原子力。输入没有准备好的键，因此显示原子和箭头。该投影下仍有部分箭头与原子重叠。光照和阴影会改变显示颜色，本图不是定量色标。

## 固定输入与前提

先完成[安装](installation.md)和[首课](first-aspirin.md)。使用 Blender 5.1.1、prepare 0.1.0；候选 Extension SHA-256 为 `963b905f3e5ee3c5fc1fa53a1ccefd5c60616d89ac77977efe4afdbed066426a`。下载 [aspirin-rmd17-32.extxyz](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz)、[来源与许可说明](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.md)和[冻结规格](../../../examples/tutorials/2.5.0/T06.case-spec.json)。来源说明含旧 Quick Import 操作，本课 2.5 使用下面的 CBQ 路线。

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

把输入放入新的教程目录。在 Prepare 中使用已安装的 Standard 运行环境 Python，按以下实测步骤操作：

1. 操作选择 `inspect`，输入框粘贴 extXYZ 路径，Reader ID 填 `extxyz`，点击 `执行`。切换操作会改变表单布局，应重新定位按钮。预期返回 `success`、frame_count `32`、atomic_force 及 energy/source_index/step 逐帧属性。

![实际 Prepare inspect 结果](../assets/2.5-tutorials/trajectory-prepare-inspect.jpg)

2. 操作改为 `convert`，保留输入及 Reader ID，输入类型为 `files`，校验模式为 `balanced`。填写新的 CBQ 输出路径，点击 `执行`。预期返回 `success`；没有预制键的提示与下面的原子／箭头 View 一致。本次 GUI 输出使用 `gui-converted.cbq`，以保留已有工程。

![实际 Prepare convert 结果](../assets/2.5-tutorials/trajectory-prepare-convert.jpg)

[GUI 产物科学检查](../assets/2.5-tutorials/trajectory-gui-science-check.json)独立核对了全部 32 帧与原始输入。以下等价公开命令也已通过，运行时替换示例路径。

```powershell
chemblender-prepare inspect "D:\ChemBlenderLessons\T06\aspirin-rmd17-32.extxyz" --reader extxyz --json
chemblender-prepare convert "D:\ChemBlenderLessons\T06\aspirin-rmd17-32.extxyz" --reader extxyz -o "D:\ChemBlenderLessons\T06\aspirin-trajectory.cbq" --json
chemblender-prepare validate "D:\ChemBlenderLessons\T06\aspirin-trajectory.cbq" --json
```

预期成功，得到 `coordinates` FrameSet、`atomic_force` AtomFrameProperty，以及 `energy`、`step`、`source_index` FrameProperty。保存的全部坐标、力和逐帧数值属性均与独立解析的输入文本完全一致，32 帧的元素顺序保持相同。保留 source_index 的 ambiguous 状态；转换成功不能补出缺失单位。

## 创建并检查轨迹

1. 在新场景中设置并确认 `CBQ Package`，依次使用 `Preview CBQ`、`Import CBQ`。本次加入 9 个实体。导入通过 MCP 复用了已验证 Operator；下面的轨迹控件则经过实际 GUI 操作。
2. 在 Project Browser 选择 FrameSet。在 `Scientific Representation` 保持 `Automatic`、`Research`，说明显示 `Trajectory frame`，点击 `Create View`。
3. 选择 `atomic_force` 数据集，此时 `Automatic` 对应 `Trajectory with forces`。再次点击 `Create View`，创建绑定同一个 FrameSet 及其力属性的独立 View。
4. 关闭前一个普通轨迹 View 的视口与渲染可见性，同时保留该 View。也隐藏默认 Cube。选中力 View，用小键盘 `.` 取景。不同帧的多个 View 重叠会看起来像多出了原子。
5. 在力 View 控件中将 `Source Frame Index (0-based)` 设为 `15`，点击 `Apply Frame`；坐标和力箭头一起更新。用同样方法检查 `0`、`31`。下面的截图记录了经授权公开 FRAME 重放后的两个端点。

![实际应用源帧 15](../assets/2.5-tutorials/trajectory-apply-frame.jpg)

![FRAME 重放后的源帧 0](../assets/2.5-tutorials/trajectory-frame0.jpg)

![FRAME 重放后的源帧 31](../assets/2.5-tutorials/trajectory-frame31.jpg)

[端点检查](../assets/2.5-tutorials/trajectory-first-last-check.json)确认坐标与缩放后的力满足显示容差。这些截图证明可见结果，不代表重新手动点击了 Apply Frame。

后续公开 `FRAME` 重放检查了全部 32 帧，显示顶点与向量在 `1e-6` 显示精度内对应正确源帧，权威数组不变。Vector Display Scale 不为 1 时，应将显示向量与“源力乘显示比例”比较。[全帧检查记录](../assets/2.5-tutorials/trajectory-force-check.json)使用的是外观细化之前的比例 1。

| 源帧 | 能量，eV | step | source_index |
| --- | --- | --- | --- |
| 0 | -17617.8287419 | 0 | 161596 |
| 15 | -17617.4879446 | 1500 | 26491 |
| 31 | -17617.7618802 | 3100 | 151469 |

这些是数据集参考值，不是 Blender 重新计算的能量。该表不表示实际界面已在动态结构旁显示每个字段。

## 播放与暂停

在侧栏内滚动到 `Apply Frame` 下方的 `Play`、`Pause`。保持 Animation Start Frame 为 `1`，Timeline Frames Per Source Frame 为 `1`。点击 `Play`：实测时间线范围变为 1–32，源帧等于时间线帧减一。点击 `Pause` 后，时间线与科学播放均停止。实际播放期间采集了 12 张带时间戳的截图，这不是连续录屏。

`Apply Frame` 预览一个静态源帧。暂停时场景时间线可以显示另一个数值，应以源帧控件和 View 保存的元数据识别静态预览。24 fps 显示速度不能证明缺失的物理采样间隔，也不能证明所选构型统计独立。

## 细化与渲染

1. 选中力 View，使用 `Load Selected View`，将 Vector Display Scale 设为 `0.35`，启用 `Light Quantitative Colors`，再点 `Update Style / Parameters`。缩短箭头是显示选择，不是力单位转换。
2. 按[乙醇课程](ethanol-conformers.md)的方法，将现有 `CH_Ball and Stick` 节点的 Subdivision 设为 `5`，保持源坐标与力不变。
3. 在 Object Mode 选中 View，鼠标置于视口，按 F3 搜索 `Smooth by Angle` 并确认。在 Modifiers Properties 中启用新修改器的 `Ignore Sharpness`，Angle 保持 30°。该 GUI 步骤已消除原子棱面。未选中对象时命令不会添加修改器；不启用 Ignore Sharpness 时，已有锐边标记仍会保留棱面。

![实际启用 Ignore Sharpness](../assets/2.5-tutorials/trajectory-smooth.jpg)

4. 实测相机为正交相机，位置 `(0, -16, 11)`，朝向原点，Orthographic Scale 为 `11`。Point Light 位置 `(0, -8, 9)`，Power `6500`，Radius `3`；World Background 线性 RGB 为 `(0.18, 0.18, 0.18)`，Strength `1`。这些构图参数通过 MCP 重放设置，完整手动面板说明仍待验证。
5. 使用 Cycles、CPU、256 samples、降噪，输出 `2400×1800`、100%、PNG。渲染源帧 15 并单独保存 PNG；同时保留 `.blend` 与完整同名 `.cbq` 目录。
6. 本次记录的动画路线会在停止视口播放后保留科学播放驱动，将场景范围设为 1–32，再用 `Ctrl+F12` 渲染到新的 PNG 目录。该快捷键已实际尝试。全部 32 张完成的 PNG 均通过解码及渲染后同帧检查。独立 Blender VSE 装配将它们编码为 H.264/MPEG4，尺寸 2400×1800、24 fps、32 个视频样本、时长 1.333333 秒；实际断网浏览播放到末尾。装配使用原生 API 重放，完整手动装配及保留驱动的 GUI 路线仍待验证。

Rebuild 或 Update 可能替换显示对象，替换后需重新设置自定义细分及 Smooth by Angle，渲染前检查修改器列表。更多显示多边形或更平滑的法线不会增加科学采样点。

## 工程交接与恢复边界

工作工程是 `aspirin-trajectory.blend` 加完整 `aspirin-trajectory.cbq` 目录。另行保留静态 PNG 及后续完整 PNG 序列。原工程与移动副本冷重开通过，源帧 15、两个 View、力比例及启用 Ignore Sharpness 的 Smooth by Angle 均保留。加载后科学播放关闭，需要显式重新启动播放。在另一个副本中清空力 View 网格后，公开 REBUILD Operator 恢复了同帧坐标与力，科学数组未变；再次冷重开也通过。重建后自定义 Smooth by Angle 不再存在，需重新设置外观细化。这些检查尚不能证明源文件／处理器不可用时的离线重建。不要把权威 `.npy` 数组当作显示缓存删除。

一次动画尝试因渲染前审计错位而取消。两帧对照证明 `render_pre` 早于源帧更新，`render_post` 对应正确源帧；动画第 2 帧与显式设置同源帧的静态渲染逐像素一致。这是证据采集时机问题，并未证明产品输出错帧。最终验收必须检查完成的图像和渲染后审计。

可查看 [32 帧审计](../assets/2.5-tutorials/trajectory-animation-check.json)、[视频完整性记录](../assets/2.5-tutorials/trajectory-video-check.json)、[原位／移动后冷重开](../assets/2.5-tutorials/trajectory-cold-recovery.json)及[显示重建记录](../assets/2.5-tutorials/trajectory-cache-recovery.json)。大型帧序列、MP4 和配对工程保存在本地案例产物目录，不进入 Extension ZIP。

人工复做、连续 GUI 录屏、逐帧数值面板检查及案例打包仍待完成。[媒体来源](../assets/2.5-tutorials/provenance.json)分别记录原始截图和渲染图。
