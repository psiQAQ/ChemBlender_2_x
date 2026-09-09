# 科学量可视化示例

真实计算文件、科学数组、显示参数和 Cycles 输出共同组成可复现示例。按[中文 SOP](../../docs/quantum-visualization/scientific-visualization/README.md)从导入到面板操作逐步执行，也可打开[离线网页](../../docs/quantum-visualization/scientific-visualization/index.html)查看实图。

| 内容 | 入口 | 验证边界 |
| --- | --- | --- |
| 固定来源的输入 | [输入说明](inputs/README.md)、[来源及哈希](input-manifest.json) | 文件存在不表示相应可选计算后端已运行 |
| MO、密度、自旋、差分、ESP | [22 张分子实图清单](output/molecular/images/render-manifest.json) | Research / Teaching；2400×1800、Cycles 256 samples |
| 分子工作台 | [场景清单](output/molecular/scenes/scene-manifest.json)、[生命周期验证](output/molecular/scenes/lifecycle-verification.json) | water、CH₃、N 原子；保留配套 `.cbq` 文件夹 |
| 原子电荷、轨迹、逐帧力 | [实图与动画清单](output/atom-trajectory/manifest.json) | 6 张静图、128 帧 PNG、4 段 MP4；rMD17 未声明物理时间间隔 |
| PQR / rMD17 工作台 | [场景清单](output/atom-trajectory/scenes/scene-manifest.json)、[生命周期验证](output/atom-trajectory/scenes/lifecycle-verification.json)、[PQR](output/atom-trajectory/scenes/pqr.blend)、[rMD17](output/atom-trajectory/scenes/rmd17.blend) | 2 + 4 个 View；Save As、整体移动、独立进程重开、公开 Load / Rebuild、全部 32 帧和 14 个科学数组哈希检查通过；保留相邻 `.cbq` |
| 外部科学后端 | [依赖提案](dependencies/PROPOSAL.md) | 已批准的隔离环境完成 wavefunction、Fermi、QTAIM、NCI、phonon 真实操作；critic2 1.3.15 另从 water WFX 生成并验收 40×40×40 ELF/LOL；运行能力以 `chemblender-prepare capabilities --json` 为准 |

原始文件和输出均保持字节不变，来源、单位、显示设置以各 manifest 和报告为准。渲染输出不进入 Extension ZIP。

分子报告位于 `output/molecular/images/reports/<case>/`，其中 `artifact.path` 相对于 `output/molecular/images/`；原子 / 轨迹报告的 `artifact.path` 则相对于各自 case 输出目录。解析路径时使用对应根目录，不从报告文件所在位置推断。

重放脚本不会安装依赖；先按 SOP 配置已批准的环境。`prepare_inputs.py --verify` 只检查输入，`prepare_molecular.py` 生成缓存中的科学项目，`render_molecular.py` 与 `render_atom_trajectory.py` 生成新输出目录；`save_molecular.py`、[save_atom_trajectory.py](save_atom_trajectory.py) 发布对应工作台，后者以 `--verify` 在另一进程重开并检查全部 View。Blender 脚本要求项目缓存中的独立 `BLENDER_USER_RESOURCES`；启动前创建并显式设置对应 `BLENDER_USER_CONFIG`、`BLENDER_USER_SCRIPTS`、`BLENDER_USER_DATAFILES`，避免新目录尚未存在时读取用户启动配置。`save_atom_trajectory.py --existing-libraries` 指向已经通过隔离安装检查的缓存 wheel 库目录，不安装或修改该目录。

`save_atom_trajectory.py --lifecycle-cache .agents/cache/your-new-lifecycle` 对缓存副本测试 Save As 与整体移动；在另一 Blender 进程保留相同参数并加 `--verify`，完成独立冷启动核验并发布 `lifecycle-verification.json`。测试不重渲、不修改正式 `.blend` / `.cbq` 或原有图片和视频。
