# CBQ Viewer、本地处理程序与科学可视化交付

日期：2026-09-09。状态：Completed。

## 结果

完成迁移收尾、纯 Mesh 编辑保留、CBQ 1.1 与完整回归后，按既定顺序交付统一 `chemblender-prepare` CLI / Worker v1、Blender 单一路径异步控制器、RDKit 分子操作闭环、QTAIM/NCI/phonon 专业操作和正式无 wheel Viewer。Blender 只负责 CBQ、本地编辑与可视化；第三方科学依赖及重计算保留在外部处理环境。

RDKit 删除前等价、性能、取消、信任边界和生命周期门槛全部通过。正式 manifest、依赖清单、staging 与 CI 已一致移除 RDKit、Gemmi 和其他科学 wheel，同时保留 SMILES/AddHs/ETKDG/Kekulé/MMFF/UFF/势能/导出与 Mesh→CBQ→新结果闭环。

## 最终证据

- Blender 5.1.1 / Python 3.13.9 私有 profile：validate/build、staging、安装、register/unregister/reload、冷启动、CBQ、纯 Mesh、保存重开、缓存重建和三个 `.blend` 资产全部 Passed。
- 最终 Extension：2,830,321 bytes、109 members、SHA-256 `9ea6adcb84ff8c3e576652d9c140d111d9d509039e5da40d57a5bd404ed06708`；0 wheels；artifact package/unpacked/code/resources/wheels/other 增长全部为 0。
- 外部包：`uv build --no-cache` Passed；wheel 559,417 bytes、SHA-256 `eca1dd6dcafc37a520af541cc7661a163046a5ed3932551a35213eaacc8093c9`；sdist 897,243 bytes、SHA-256 `82554df211cea58e2394f40f2824283d5a2292e89f59755e719ad1b76ad4c6f6`。
- 五层科学证据已覆盖模型、适配器/operation、真实文件、UI/Cycles 和保存重开。最后补齐项为 critic2 1.3.15 从 water HF/STO-3G WFX 生成的 ELF/LOL 40×40×40 网格；两项均通过安装态 Grid Volume、Research/Teaching Cycles、源移走、冷重开、Rebuild 与 Save As。
- 离线 SOP：17 anchors、157 local links、0 remote resources；专项 81 项 Passed。
- 最终全量：2526 tests、0 failures、0 errors、37 skips、147.228 s。

## 边界

本任务未修改共享 Blender 用户安装，未 push、未运行远端 CI、未发布 Release/PyPI；这些是未经授权的外部写入，不影响本地实施计划完成。最终报告见 [`VERIFICATION.md`](../../docs/quantum-visualization/scientific-visualization/VERIFICATION.md)，逐量 SOP 见 [`README.md`](../../docs/quantum-visualization/scientific-visualization/README.md)，完整执行轨迹保留在 `.planning/2026-09-08-physical-quantity-visualization-sop/`。
