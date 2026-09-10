# T06：阿司匹林轨迹与同帧原子力

本课为执行中草稿。输入转换、全帧科学对照、实际 Create View／Apply Frame／Play／Pause 操作及静态渲染已有证据。完整动画、连续录屏、配对工程冷重开和人工独立复做仍待完成。

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

把输入放入新的教程目录。以下公开命令已通过，运行时替换示例路径。该输入专用的 Prepare GUI 留证仍待完成。

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
5. 在力 View 控件中将 `Source Frame Index (0-based)` 设为 `15`，点击 `Apply Frame`；坐标和力箭头一起更新。用同样方法检查 `0`、`31`。本草稿专门的首／末帧 GUI 截图仍待补齐。

![实际应用源帧 15](../assets/2.5-tutorials/trajectory-apply-frame.jpg)

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
6. 正在验证的动画路线会在停止视口播放后保留科学播放驱动，将场景范围设为 1–32，再用 `Ctrl+F12` 渲染到新的 PNG 目录。该快捷键已实际尝试。最终帧序列与视频验收待完成，此段还不是已完成的交付路线。

Rebuild 或 Update 可能替换显示对象，替换后需重新设置自定义细分及 Smooth by Angle，渲染前检查修改器列表。更多显示多边形或更平滑的法线不会增加科学采样点。

## 工程交接与恢复边界

工作工程是 `aspirin-trajectory.blend` 加完整 `aspirin-trajectory.cbq` 目录。另行保留静态 PNG 及后续完整 PNG 序列。本案例的原位／移动后冷重开、缓存重建和离线重建仍待执行。不要把权威 `.npy` 数组当作显示缓存删除。

一次动画尝试因渲染前审计错位而取消。两帧对照证明 `render_pre` 早于源帧更新，`render_post` 对应正确源帧；动画第 2 帧与显式设置同源帧的静态渲染逐像素一致。这是证据采集时机问题，并未证明产品输出错帧。最终验收必须检查完成的图像和渲染后审计。

人工复做、连续 GUI 录屏、完整首／中／末帧截图及案例打包仍待完成。[媒体来源](../assets/2.5-tutorials/provenance.json)分别记录原始截图和渲染图。
