# CBQ Viewer、本地编辑与外部处理模块

## 当前 authority

执行用户批准的CBQ共享核心/外部准备工具改造，并按2026-09-08追加方案保留Blender纯Mesh编辑和高频交互，通过单一本地可执行文件异步重计算。新增方案取代“Blender仅查看、立即删除RDKit wheel”的旧边界。

完整接口、操作、流程、阶段及门槛：[本地处理模块方案](../../docs/quantum-visualization/architecture/local-processor.md)。主Agent维护[task_plan.md](../../.planning/2026-09-08-physical-quantity-visualization-sop/task_plan.md)、[findings.md](../../.planning/2026-09-08-physical-quantity-visualization-sop/findings.md)、[progress.md](../../.planning/2026-09-08-physical-quantity-visualization-sop/progress.md)。恢复时核查Git和运行环境。

## 当前实态

- 分支治理已完成：main 54ecf4c、两项远端CI成功、完整bundle及附注归档标签已核验、旧工作分支已退役，当前feat/cbq-only-viewer。
- cbq_core／chemblender_prepare迁移已按用户要求保存开发检查点：27f67c9（共享核心/外部工具）、85ab235（Viewer）、8244d12（回归）、9eebdd7（文档/示例）；C2最终收尾已补齐测试迁移和legacy View恢复，并由full20关闭。
- 用户明确批准缓存科学/Fermi/critic2环境及本仓库uv init/venv安装。根.venv/uv.lock已建立；科学环境、Fermi兼容锁及critic2工具链探测完成。科学数值/完整UI验收并未因此自动完成。
- 候选无wheel Blender验证见 .blend-analysis/cbq-viewer-ui-smoke-03/qualification.json。基础注册、视图、保存重开/源移走/缓存重建通过，不代表RDKit功能等价、纯Mesh编辑、响应时间或正式瘦身完成。
- 旧分子/原子图像与SOP为既有交付证据，见[验证记录](../../docs/quantum-visualization/scientific-visualization/VERIFICATION.md)；新架构逐物理量验收单独记录。

## 下一步及硬门槛

1. 先完成当前模块迁移、测试迁移和架构导览；审计整文件删除中的纯编辑功能；形成干净逻辑提交，才接入新增控制器。
2. 共享Worker v1、capabilities/worker/doctor、单exe路由，再接Blender全局路径、异步任务和节流预览。路径不进入.blend或CBQ。
3. 顺序迁移既有wavefunction/Fermi/reader、RDKit编辑闭环、QTAIM/phonon/NCI；结果新UUID追加，旧结果保留，过期或不可信结果不提交。
4. RDKit wheel正式保留直至功能等价、100ms modal/1秒运行/两秒取消/两秒小分子冷启动额外开销及数据一致性全部通过。任一失败则修复或延期，不发布降级版本。无wheel候选验证不关闭此门槛。
5. 最后做正式无wheel隔离安装、完整科学可视化/Cycles/生命周期、窗口截图及目录可跳转SOP、Python wheel/sdist和Extension审计。

保持项目缓存环境隔离，不改共享Blender profile或全局Python。不复制RDKit源码，不做HTTP/常驻服务，不在Blender安装依赖。独立模块为未来PyPI发布做构建准备；本次不发布Release/PyPI，GUI由用户负责发布。后续新依赖及未获授权外部写入仍遵循仓库审批规则。

2026-09-09 回归快照更新：migration-full-09为最新完整回归（2565项，7 failures/124 errors/36 skips，89.714秒，Failed）。主要剩余旧import-preview/quick-import、wavefunction任务安全、legacy路由/恢复测试迁移。GUI校验模式漏传已修复；多文件/未知扩展名实际CLI→CBQ与Tk验证通过。full09后修复benchmark字符串检索误报，相关59项通过，但未标全量通过。详见规划progress.md，C2稳定提交及所有后续门槛仍未关闭。

2026-09-09 最新全量改为migration-full-10：2569项、6 failures/116 errors/36 skips、93.344秒，Failed。新增Tk SMILES进度文件Windows共享冲突已修复，CLI定向28项27 Passed/1 skipped；未重跑全量。其余失败集中旧导入UI、wavefunction和legacy路由/恢复迁移。详见规划progress.md及full10日志；C2仍未稳定提交。

2026-09-09 最新全量full11：2571项、5 failures/116 errors/36 skips、100.141秒，Failed。Mesh Apply安装版生命周期通过cbq-mesh-apply-lifecycle-02（标准preset、相对core import、保存后Apply/冷重开/显式重建/SaveAs），旧UI/任务/legacy迁移仍待完成，C2未提交。详见规划progress.md。

2026-09-09 最新完整回归为full12：2571项、3 failures/107 errors/36 skips、100.079秒，Failed。外部GUI取消超时/进程所有权和文件选择迁移已有针对性证据，旧preview/quick UI、wavefunction与legacy恢复门槛仍待关闭，C2尚未稳定提交。详见规划progress.md和migration-full-12日志。


2026-09-09 最新完整回归full13：2571项、3 failures/102 errors/36 skips、103.062秒，Failed。五项旧构象投影测试已迁到真实Tk/CLI有界证据与显式复核验收；无新增失败。剩余旧导入交互、wavefunction任务及legacy恢复仍待完成，C2未提交。详见规划进度与migration-full-13证据。


2026-09-09：最新完整回归更新为full15：2572项、3 failures/91 errors/36 skips、105.328秒，Failed；共享Worker Protocol v1迁至cbq_core且协议字节不变，已有vendoring/隔离加载及专项通过。旧导入/任务/legacy恢复继续迁移，C2尚未形成稳定提交，后续控制器/RDKit门槛不变。详见规划progress.md与migration-full-15证据。


2026-09-09：最新完整回归full16：2574项、3 failures/90 errors/36 skips、105.516秒，Failed；相对full15无新增失败，场景预设致命异常回滚测试独立迁移通过。近期Worker日志句柄、ESP故障边界、轨道缓存revision修复已纳入此轮。C2尚未稳定提交，旧导入/任务/legacy恢复继续收敛。详见规划progress.md及migration-full-16日志。


2026-09-09：四批检查点已提交至9eebdd7；完整回归full17为2573项、0 failures/88 errors/36 skips、110.906秒、Failed，未新增失败标识。错误分布旧import-preview55、wavefunction19、quick-import9、legacy路由5。原生Mesh编辑/Apply通过；legacy external-only导出不替代View恢复/回滚/保存重开，继续保留该门槛。C2尚未完成，详见规划文件和migration-full-17证据。

2026-09-09：最新完整回归为full20：2498项、0 failures/0 errors/36 skips、105.761秒，Passed。旧入口测试已迁移或在当前真实层保留安全契约；3个哈希锁定legacy fixture完成外部导出、当前Viewer恢复、注入失败回滚、evaluated mesh、保存重开和Project Connected检查。C2关闭并形成稳定提交；下一阶段为C3 CBQ 1.1收尾，C3、C4完成前不接L1。
