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

2026-09-09：C2稳定提交为`a12858e`。C3在该提交上重新运行数值对称、历史完整性/升级、事务导入和ProjectLink五模块101项全部Passed/2.570秒，full20亦已覆盖，未发现产品缺口；C3关闭。下一阶段C4外部包基线，完成前不接L1。

2026-09-09：C3状态提交为`cf8225f`。C4已确认冻结lock、7个CLI命令和prepare/Tk/真实格式专项（111 Passed/1 optional skip）；wheel/sdist尚未构建。当前环境缺hatchling/build，安全策略要求用户明确授权uv在隔离构建环境取得pyproject已声明的hatchling；未修改依赖或启动L1。

2026-09-09：C4预构建证据提交为`ab45b8b`。连续第三个目标回合复核仍无hatchling/build及当前发行物，因缺少隔离构建依赖获取的用户明确授权，目标状态blocked。恢复入口固定为C4 `uv build`、wheel/sdist内容与隔离安装验收；C2/C3已完成，不得回退或越过C4接L1。

2026-09-09：用户已授权并成功运行`uv build`。0.1.0 wheel/sdist通过归档安全、RECORD/元数据/入口点、受控源码完整性审计；本地wheel `--no-deps`隔离安装后，模块来源、launcher及22 readers/13 operations实际输出均通过。未改变环境、lock或依赖文件，C4关闭；下一阶段为L1统一Worker入口。

2026-09-09：L1统一入口已完成。新增版本化`capabilities --json`、共享Worker v1文件入口、无副作用`doctor`和固定外部环境路由；缺少专用路由明确fail closed，不回退主Python。相关121项Passed/1 optional skip，最终wheel/sdist离线构建、CRC/内容、隔离安装launcher和三套真实环境探测通过；22 readers/13 operations均可用，跨GBasis worker返回预期协议错误。critic2为WSL ELF，Windows doctor如实warning，留待L5处理。未改变依赖/lock；下一阶段严格进入L2 Blender异步控制器。

2026-09-09：L2 Blender异步控制器已完成。全局仅保存一个`processor_executable`；Test Processor和公共Worker控制器无shell异步运行，严格校验任务归属、identity、状态和退出码，取消两秒后仅终止owned PID tree。phase/frame采用100 ms尾随本地预览。专项98项、Blender 5.1.1源码/安装版私有profile、validate/build、ZIP审计及2509项全量均Passed（36 skips）；正式包仍保留锁定RDKit/Gemmi wheels。下一阶段严格进入L3，将现有wavefunction、Fermi和scientific reader操作接到该统一控制器。

2026-09-09：L3现有重计算迁移已完成。scientific reader、Fermi及五项wavefunction operation统一经单一processor executable、公共modal控制器和Worker v1执行；输入冻结、输出identity/hash、原始来源归一化、事务追加、新UUID自动选择及任务清理后数组存活均通过。真实缓存VASP、FCHK数值，Blender 5.1.1源码/正式ZIP私有profile的reader→MO→View→保存重开→删除源文件闭环均Passed。正式staging validate/build生成29,715,245 bytes、111 members、SHA256 `14171c26b6f8a2ba24a68b4f4edc8313330410ce011f7f0af60b4e96adfa89d0`，保留锁定RDKit/Gemmi wheels；全量2515项0 failures/0 errors/36 skips、134.046秒。下一阶段严格进入L4 RDKit操作闭环，wheel仍不得移除。

2026-09-09：L4 RDKit操作闭环已完成。`molecule.smiles_to_3d/kekulize/optimize/energy/export@1`复用同一CLI、Worker v1和Blender异步控制器，覆盖ETKDG/AddHs、MMFF/UFF、芳香/Kekulé、势能标量及MOL/SDF/SMILES；纯Mesh编辑/Apply保留原子身份并追加新结果。真实CLI、Blender 5.1.1源码/最终正式ZIP全新profile、保存重开和移走输入均Passed；最终ZIP 29,718,231 bytes、111 members、SHA256 `24c4f48fffe69edf5367657f8158ef6fe806986d1be69c2ae8564ea2b58bb3e5`，全量2519项0 failures/0 errors/36 skips、137.914秒。未改依赖/lock，RDKit/Gemmi wheels继续保留；下一阶段严格进入L5 QTAIM/phonon/NCI真实科学操作。

2026-09-09：L5专业分析已完成。`topology.qtaim/grid.nci_fields/periodic.phonon@1`通过统一CLI、Worker v1和Blender异步控制器实际运行critic2 1.3.15与phonopy 4.4.0，冻结并核验WFX/YAML/FORCE_SETS/BORN，发布TopologyGraph、成对Grid3D及复数PhononModeSet；连续操作只归一化本次来源，不再改写历史provenance。正式ZIP全新profile完成自动View、保存重开和源移走，输出`BLENDER_PROFESSIONAL_OPERATIONS_PASSED`。validate/build和111-member ZIP审计Passed，包29,719,942 bytes、SHA256 `8b7b65b7b2a2d643614753e1d4b5c2cea8469ec94763f65879c928dffd4944f5`；最终full 2521项0 failures/0 errors/36 skips、139.705秒。artifact资源预算仍按旧基线Failed，留到最终L8精确产物审计；未改依赖/lock或移除wheel。下一阶段严格进入L6 RDKit等价、性能、取消、结果可信和生命周期门槛。

2026-09-09：L6删除前门槛已完成。历史`78c2d8d` RDKit调用面与当前外部operation完成芳香/Kekulé、手性、带电、多片段、AddHs、ETKDG、MMFF/UFF、势能及MOL/SDF/SMILES等价；Blender纯编辑冻结、过期输入、结果路径/hash/link信任边界、真实NCI 128³取消和三分子保存/Save As/目录移动/冷重开/VDB重建/Cycles均Passed。阿司匹林冷进程额外开销0.01761秒；真实Blender modal 0.0000078秒、running 0.01089秒、取消0.33582秒。全量2524项0 failures/0 errors/37 skips、145.698秒。正式包仍保留RDKit/Gemmi wheels；下一阶段严格进入L7正式瘦身和无依赖隔离验收。
