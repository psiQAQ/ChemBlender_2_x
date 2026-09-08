# 真实界面截图复核

11 张 PNG 均由 Blender 5.1.1 的 `bpy.ops.screen.screenshot` 直接保存，尺寸为 1600 × 1001，没有拼接、补画或修改像素。截图使用独立的 `BLENDER_USER_RESOURCES`，包 SHA-256 为 `eb92e88ee056d9cb62ffe57f45e37fcb360cd609212d158332b0835125094279`。这组截图记录 qualification05；最终安装包可以包含后续不改变界面的修复。

[manifest.json](manifest.json) 保存每张截图的哈希、实际 View 名称、项目 UUID 和持久化参数。[operations.json](operations.json) 保存公开操作、三个真实输入的哈希、播放观察、渲染和保存重开结果。

| 文件 | 已执行操作与画面内容 |
| --- | --- |
| 01 | 真实水 FCHK 的 restricted HOMO 5；公开创建、加载、更新 signed isosurface，阈值 0.06 |
| 02 | 总电子密度等值面，阈值 0.08；坐标和值单位分别显示 |
| 03 | Grid volume 参数和本次公开导出的 Research PNG；density scale 5 是显示传递参数 |
| 04 | 同 affine 的密度与 ESP 绑定；密度阈值 0.002，ESP 色域 ±0.06，Teaching 模板 |
| 05 | ESP 切片，原点及两条完整跨度、129 × 129 个含端点样本 |
| 06 | ESP profile，从 (-4, 0.7, 0.6) 到 (5, 0.7, 0.6) bohr，共 257 点；曲线横轴为真实距离 |
| 07 | 实际轨道能量、占据数和 HOMO 5 缓存；0.25 bohr 步长、56 × 49 × 60 网格及密度、ESP 入口 |
| 08 | 原始 PQR 的 998 个原子全部用于 charge View；Coolwarm、对称 ±1.2 色域和模板参数 |
| 09 | rMD17 的 32 个源构型；第 31 个源索引、力绑定、scale 0.5、Apply Frame、Play/Pause 和 Timeline |
| 10 | 公开 Cycles 导出设置及实际 PNG：960 × 720、64 samples、Research + Teaching |
| 11 | 公开 Rebuild、Save、Open 后的 Connected/clean 状态；13 个 dataset revision 与 10 个 View 完整恢复 |

03/10 的中央图像是本次公开导出产生的 PNG，在 Blender Image Editor 内打开。它们是界面操作预览；SOP 的正式图片使用另行记录的 2400 × 1800 / 256 samples 参数。没有把预览冒充正式质量输出。

09 使用 Material Preview 的 `forest.exr` studio world，`use_scene_world=False`、`use_scene_lights=False`。中性单色 World 会让白色 H 球难以辨认，因此进行了只读几何核验：21 个原子球各有 338 个 evaluated vertices，8 个 H 的半径属性均为 0.32 Å。切换视口环境后 8 个白球可读；科学数组与球体材质未因此改写。rMD17 文件没有物理时间通道，32 帧仅表示源构型次序。

## 从原始数据复核

1. 按上级 SOP 启动独立 Blender profile，通过 Wavefunction Import 读取 `examples/scientific-visualization/inputs/wavefunction/water_sto3g_hf_g03.fchk`。使用已经批准的 worker 环境，计算 restricted MO 5、SCF total density 与 ESP。
2. 对 ESP 显式使用 `origin=(-5.9075,-5.9275,-6.7025)` bohr、`step=0.25` bohr、`shape=(56,49,60)`。密度必须使用同一 affine 才能绑定到 property surface。最初 Fit 网格经过核位置，ESP 正确拒绝且未发布半成品。
3. 用 Quick Import 分别导入 `examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr` 和 `examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz`；确认导入时关闭默认 View。再通过 Scientific Representation 创建 charge、trajectory 和 trajectory_force。
4. 从 `manifest.json` 读取所需 View 的 settings，通过面板的 Defaults、Create、Load、Update、Rebuild 重建。轨迹 Play 已观察到 Timeline 从 1 推进到 12；Pause 后 Apply Frame 31，并通过 Update 保存静帧。`frame_start=1`、`frame_step=1`。
5. 选择 density cloud，用图 10 的公开参数导出到新的空目录。成功后检查 PNG、display.json 和 manifest.json；保存 `.blend`，重开并检查 Project Connected、clean 与 View 参数。

## 本机缓存重放

本次缓存项目为 `.agents/cache/scientific-gui-all-quantities.blend`，其 `.cbq` 位于同目录；缓存没有作为正式输入或分发包提交。已保存的独立窗口布局与源数据是下面命令的前提。原始 GUI helper 及哈希列在 `operations.json` 中。

```powershell
# 工作目录为仓库根；仅连接本任务独立 MCP 9884，不使用共享 9876。
& 'C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe' `
  .agents/cache/scientific_gui_client.py `
  .agents/cache/scientific-gui-reopen-verify.py
```

`scientific_gui_water_screenshots.py` 用原生 `LOAD`、视口参数和定时器重放水分子的参数界面，允许 Blender 在截图前完成布局。面板折叠和滚动位置依赖已保存的窗口布局；重新安排窗口后需人工调整，不能只凭脚本返回值断言截图可读。03/10 要再次打开这次实际导出的 PNG；09 要保留上述 studio world 设置。
