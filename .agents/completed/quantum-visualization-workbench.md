# 量子化学可视化首期工作流

2026-09-08，首期 A-D 在本地 `feat/quantum-visualization-workbench` 完成。起点为 `ca5ce98`；后续专业分析、周期、比较/动画和 GPU 工作保留在路线图中。

[实施计划](../../.planning/2026-09-08-quantum-visualization-workbench/task_plan.md) · [操作说明](../../docs/user/quantum-workbench.md) · [真实示例](../../examples/quantum-workbench/README.md)

## 完成内容

- 属性表面只从 density 生成几何；property_surface_v2 显式重建旧视图，失败保留原对象，派生网格携带 structure_id。
- Orbital Set 列表与 α/β、前线轨道选择；有界 MO、RDM 密度/自旋密度与 ESP worker；严格核电荷和可求值状态校验，原子发布与取消。
- 独立 dataset/色域、正确零点色标、全仿射三线性采样、平面切片、线剖面和科学坐标 CSV。
- 顺序轨道图片与原生报告导出，固定相机和显示参数，失败/取消不发布半份图片包；View 保存、重开、Save As、搬移和删缓存重建。
- 原有 14 个参考子模块固定版本保持不变；新增 MolecularNodes、MOrbVis、PySCF 固定版本，仅作源码参考，不进入扩展或运行时依赖。

## 验证

| 层次 | 实际证据 | 结果 |
| --- | --- | --- |
| 全量单测 | Blender bundled Python 3.13.9：2,410 项，2,379 通过、31 可选/环境跳过，零失败/错误 | Passed |
| 科学模型与适配器 | 已批准缓存环境 Python 3.12.13、既有八项 pinned constraints；Cartesian/pure、FCHK/Molden/UHF、RDM/ESP、取消和发布回归 | Passed |
| 独立数值 | PySCF 2.13.1 RHF/STO-3G，12 固定点，MO/密度/ESP 最大绝对差 9.60e-9 以下 | Passed |
| Blender 几何/UI | 5.1.1 密度专用几何、实际输入计算、数据切换、旧视图事务重建、照明无关切片/色标、导出失败/取消清理 | Passed |
| 完整生命周期 | 保存重开、两种 Save As remap、整体搬移、删除五份 VDB 后重建；15 个数组哈希与科学 CSV 不变 | Passed |
| 本地扩展 | Native validate/build、197 条 ZIP 字节审计、隔离与真实 user_default 安装、启停重载、RDKit/Gemmi | Passed |
| 远端 CI / 发布 | 未获当前授权，未 push、PR、tag 或发布 | Not Run |

最终本地 ZIP：`ChemBlender/chemblender-2.4.0.zip`，30,029,960 字节，SHA-256 `e076d7b0b177ef06aa5492eacfc7b9e7ec534b441bea0f6661ea205aa7a8e2fb`。版本未变更；这是功能分支构建，不是新 Release。

示例保留 .blend + .cbq、总览、HOMO/LUMO PNG、切片/剖面 CSV、来源和独立数值对照。Git 保留生成物原始字节；缓存、验证副本和运行日志不入库。

## 环境与限制

测试曾误用后台 read_factory_settings，触发 Blender 原生共享 wheel 清理。已用原启用扩展的现有 wheel 原版本恢复；最终 4,888 个唯一文件哈希、八包导入和数值 smoke 全通过。旧恢复计数 5,834 包含两份 manifest 共同引用的 946 个 RDKit 文件。Windows 锁定库的原生 stale 清理项留给 Blender 正常退出处理。

最终实际安装内容逐字节匹配 ZIP，原 userpref.blend 与扩展启用集合不变；交互 Blender 仍为原始未保存的 Camera/Cube/Light 场景。当前进程中已加载的旧模块未强制重载，正常重启 Blender 后使用已安装的新代码。

参考记录在项目 `.agents/cache/`：qwb-final-unittest.log、qwb-final-isolated-install.log、qwb-final-actual-install.log、qwb-zip-audit.json、qwb-final-environment-audit.json。实际用户后台会记录其他已启用插件的既有 keymap/torch 提示；ChemBlender gate 均通过。

逐点数值对照不表示积分已收敛。复数轨道/自旋器、隐式重采样与无明确有效核电荷的 ESP 保持拒绝；每张原生图片渲染期间不能中途取消，取消在阶段之间生效。专业分析、周期与大规模优化按后续阶段推进。
