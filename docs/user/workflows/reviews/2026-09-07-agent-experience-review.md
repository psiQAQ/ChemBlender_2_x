# ChemBlender 本轮体验验收

执行者：**Agent 模拟用户**。执行日期：**2026-09-07 至 2026-09-08，Asia/Shanghai**。

单位、过期任务测试及体验中发现的产品问题已修复；固定 wheel、最终 R25 包的本地自动验证、14 项双路径记录及同包复核已完成。**整体验收仍为 Blocked：真实用户 `user_default` 安装重试被自动审批拒绝。** OUTSIDE 的同步 MCP 渲染中途取消为 Not Run，远端 CI 本轮未执行。下列 Passed 仅指明示的已执行范围。

## 交付入口

- [14 个 Collection 的总展示 .blend](../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)、[2400×6000 总览渲染](../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)、[较小预览](../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-preview.png)、[14 集合同屏的真实窗口](../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)。
- [最终测试配对目录](../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/)、[28 路径索引及来源](../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)、[交付文件 hash](../../../../.blend-analysis/2026-09-07-review/outputs/final-delivery-manifest.json)。各项明细链接见下表。
- [最终 ZIP](../../../../.blend-analysis/2026-09-07-review/package-grid-label/chemblender-2.4.0.zip)、[五文件 artifact 审计](../../../../.blend-analysis/2026-09-07-review/package-grid-label/)、[自动验证结果与耗时](../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-qualification.json)。
- [已验证 UI 对应的公开 MCP 命令](../../../../tests/blender_review_commands.py)。本轮执行器 `scripts/reuse_blender.py` 每次执行重新读取该目录，核对公开 RNA/poll 和自建 profile 边界，并记录输入、结果、耗时及 UI 证据。

展示文件有 14 个顶层 Collection，每项含 UI/MCP 子集合。其几何为 R25 求值后的展示快照，模型各自缩放排版，普通 Workbench 材质不表达全部节点属性；每个子集合的 `source_blend` 指向权威配对。Volume 的真实体渲染、元素颜色及逐帧近景应看各项独立图片。ENV 没有科学数据，不要求空环境生成 sidecar。迁移的新副本、LIFE 的 Save As 和 Grid 冷恢复配对均另外保留。

## 最终同包复核

Blender **5.1.1**，bundled Python **3.13.9**，Windows；启用键 **`bl_ext.user_default.chemblender`**。独立分支 `fix/quantum-input-units-experience-review`，版本保持 **2.4.0**。最终打包源码 **`039bde7e1bf028b4b691d888d51460ae331ff678`**；后续提交只记录文档、验收命令和证据，不改变包内容。

最终 ZIP SHA-256：`661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

原生 UI 首测使用 Windows 鼠标、键盘、菜单、弹窗和屏幕截图，独立 MCP 路径使用公开 Operator/RNA。用户后续允许重复 UI 操作改用 MCP，因此最终复核在两套独立 profile 中重放已验证命令，不冒充新的原生首测。每份复核先从干净文件副本打开，核对已安装源码，再检查公开状态、下表操作及科学数组。首次体验、失败证据和修复 commit 的版本仍在 14 份明细中保留，不将旧包结果改标为 R25。

| 项目明细 | UI 路径最终复核 | MCP 路径最终复核 | R25 实际复核范围 |
| --- | --- | --- | --- |
| [ENV](2026-09-07-agent-experience/ENV.md) | 隔离 Passed；实际安装 Blocked | 隔离 Passed；实际安装 Blocked | 两个隔离 user_default 的 R25 安装、新进程依赖检查；28 次加载中的启用键、Reader API、Scene RNA；完整隔离 register/unregister/reload smoke。实际用户安装 Blocked。 |
| [IMP](2026-09-07-agent-experience/IMP.md) | Passed | Passed | 已保存导入数据和单位的数组完整性；CCO 预览取消；未知 Gaussian 单位诊断、拒绝确认、取消后几何不变。 |
| [DATA](2026-09-07-agent-experience/DATA.md) | Passed | Passed | 原始与 +1 Å Derived 数据不变；晶体约束隐藏/恢复；缺少 spglib 时停止且不产生结果。 |
| [VIEW](2026-09-07-agent-experience/VIEW.md) | Passed | Passed | 重开后重新绑定轨迹及 force；首尾帧坐标/力与权威数组一致，播放/暂停恢复；保存的 Grid/Surface 绑定和展示几何。 |
| [EXP](2026-09-07-agent-experience/EXP.md) | Passed | Passed | 选择周期结构；未确认 XYZ 的 cell/PBC 损失时无输出，确认后文件仅含所选坐标；原回读语义及配对数组保持。 |
| [LIFE](2026-09-07-agent-experience/LIFE.md) | Passed | Passed | 重开既有 revision 比较项目、Save As 新配对，UUID/manifest 一致；Connected 状态拒绝不适用的 Verify。 |
| [MIG](2026-09-07-agent-experience/MIG.md) | Passed | Passed | 新复制的旧场景分别预览、拒绝未确认执行、确认迁移、四原子/三键、备份和配对保存；原 MIG 文件另行完整性核对。 |
| [AGENT](2026-09-07-agent-experience/AGENT.md) | Passed | Passed | 公开 RNA/poll、未知单位阻断反馈、失败确认停止及取消恢复；两测试连接持续可用。 |
| [OUTSIDE](2026-09-07-agent-experience/OUTSIDE.md) | Passed | Passed | 普通材质/World/Area/Camera 及 Collection 随文件恢复；最终包下两张 Eevee 渲染已实际查看且像素相同，科学数组不变。 |
| [REP-MOLECULAR](2026-09-07-agent-experience/REP-MOLECULAR.md) | Passed | Passed | 八个默认 View 在 R25 下恢复并求值；59 个唯一权威数组与原配对一致；两路径各八模型展示快照入总览。 |
| [REP-TRAJECTORY](2026-09-07-agent-experience/REP-TRAJECTORY.md) | Passed | Passed | 32×21 数据重开与重配置、帧 1/32 坐标及 force、播放/暂停；energy/step/source_index 数组完整性。 |
| [REP-BIOLOGICAL](2026-09-07-agent-experience/REP-BIOLOGICAL.md) | Passed | Passed | 19 原子的 residue mask、MODEL 1/10 坐标、22 个零 radius 选择；完整 PDB/PQR 五数组和层级保存状态。 |
| [REP-CRYSTAL](2026-09-07-agent-experience/REP-CRYSTAL.md) | Passed | Passed | 三个周期输入的 View/数据绑定、18 个唯一数组、单元格/占据/无序元数据完整性；缺 spglib 的公开失败停止。 |
| [REP-GRID](2026-09-07-agent-experience/REP-GRID.md) | Passed | Passed | 本项完整干净体验已使用 R25：64³ 全体素、显式语义/单位 provenance、Cycles Volume/正负表面、四 VDB 真正新进程重建；再复核配对及展示。 |

28 份副本全部通过安装 Python 字节比对、Reader API/Scene RNA/poll 和保存状态检查；26 份科学配对的 UUID/manifest 与全部权威数组文件通过核对，原始文件未改变。MIG 另从两份旧场景副本重新迁移，OUTSIDE 在 R25 下重新 Eevee 渲染；REP-GRID 的完整干净导入、语义确认、Cycles 渲染与真正新进程冷恢复本来就发生在最终 R25。最终阶段没有再次逐个点击所有历史菜单；完整原生体验和完整自动 smoke 与上述针对性复核共同提供证据。

## 单位与任务治理修复

`bed5cab` 先复现 Gaussian `Units=Bohr/AU`、ORCA `! Bohrs` 的坐标误读，再修 reader。Gaussian 仅 route section 解析 `Units=...`/括号形式；ORCA 处理简单关键字及 `%coords Units`。一致重复允许，冲突/未知或不可靠坐标配置拒绝，标题和注释不改变坐标单位。输出统一 Å，显式 Bohr 因子 **0.529177210903**，显式 Å 与默认输入保留既有数值语义。

两个 reader 版本为 **2**，现有 provenance parameters 记录源/输出单位及因子；公开函数签名、Reader API 和 sidecar schema 保持。已保存项目不自动缩放，reader 版本变化进入既有 revision 冲突流程；单元和实际 smoke 验证旧结果保留、新 revision 坐标正确。Windows 发布前关闭 lazy array 映射，避免重新导入发布被旧映射锁住。

过期测试改为任务状态一致性：代表样例任务必须 completed、不能仍 active；索引有效且活跃任务不超过一个。治理检查保留。格式说明、生成文档、样例说明和 Unreleased 变更记录同步更新。

最后新增干净检出的文档证据回归：未随 Git 分发的本轮证据目录不存在时允许离线检出，目录存在却缺少被引用文件仍失败，普通文档死链仍失败。回归先复现旧检查失败，再作定点修复；没有删除任务或链接治理检查。该修改只涉及仓库测试，不改变 R25 ZIP。

体验中另修复 Browser draw 写 RNA、公开 Preview/取消/JSON 参数、reload 会话、惰性晶体约束、生物默认 View、力箭头逐帧/几何/起点、重开绑定、导出损失预览与确认、配对 Save As/Relink/revision、迁移预览/显示、MOL2 标签、生物层级反馈和 Grid 小阈值显示。每项明细均保留对应失败—回归—修复—重测链。

## 依赖、构建与自动验证

仅按 `ChemBlender/dependencies.toml` 补齐以下既定 wheel，逐一验证文件名、cp313 ABI、SHA-256、许可证与大小；没有升级或加入可选后端。wheel 未纳入 Git，测试依赖放在本轮 `test-site`，NumPy 使用 Blender bundled 版本 **2.3.4**，未写 Blender 全局 site-packages。

| wheel | 字节 | 许可证 | SHA-256 |
| --- | ---: | --- | --- |
| rdkit-2026.3.3-cp313-cp313-win_amd64.whl | 24,618,400 | BSD-3-Clause | f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48 |
| gemmi-0.7.5-cp313-cp313-win_amd64.whl | 2,270,352 | MPL-2.0 | ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d |

| 检查 | 结果 | 本轮最终证据 |
| --- | --- | --- |
| 专项失败用例与修复后回归 | Passed | 各项明细；最后 Grid 8 项专项 |
| 完整 unittest | Passed：2315 tests，26 skips，0 failures/errors | `logs/FINAL-R25-unittest-close.log`；测试 112.908 秒，进程 114.110 秒 |
| 源码/测试 compile、生成文档检查 | Passed | `FINAL-R25-compile.log`、`FINAL-R25-generated-docs.log` |
| 原生 extension validate/build | Passed | `qualification-grid-label-static.log`；最终追加 validate 2.749 秒 |
| ZIP 内容审计、大小预算、artifact verifier | Passed | `package-grid-label/`；最终 verifier 1.028 秒 |
| 全新临时 BLENDER_USER_RESOURCES 安装及完整 blender_smoke.py | Passed | `FINAL-R25-isolated-smoke-retry.log`，104.846 秒 |
| 两个实际可见测试 profile 的 user_default 安装/新进程依赖 | Passed | UI 3.312/1.961 秒，MCP 3.104/1.952 秒；`R25-catalog-install-cold.json` |
| 原用户真实 user_default 安装 | **Blocked** | 首次失败，重试被自动审批拒绝；`actual-user-smoke.log` |
| 本轮 GitHub Actions | **Not Run** | 未进行远端写入，不引用历史 CI 或 Blender 5.1.2 |

26 个 skip 均在[逐项原因清单](../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-skips.json)：缺少已明确不安装的 ASE、cclib、IOData、phonopy、pymatgen、spglib、GBasis；Gemmi 的“未安装”分支因本轮已安装而跳过；Windows 目录 symlink 缺少权限。不能把这些 optional backend 的计算能力标为已实测通过。

追加 smoke 首次将归档 ZIP 路径传给脚本，脚本按 `ZIP.parent.parent` 查仓库夹具而失败；改用仓库内 SHA 完全相同的 ZIP 后完整通过。失败日志保留并归为测试调用路径问题。Windows 在同进程卸载已加载 RDKit DLL 时仍输出清理锁定警告；生命周期断言通过，两套自建 profile 的独立冷依赖检查进一步验证真实新进程导入。已有 `mesh.py:513` 的 SyntaxWarning 未作为本轮修复扩展范围。

## 包体逐项归因

最终 **29,989,841 packed bytes / 32,113,134 unpacked bytes**，其中代码 2,718,378、资源 2,506,004、wheel 26,888,752 bytes。所有 unexplained-growth allowance 保持 **0**。

相对最初本轮单位修复包增加 **6,431 packed / 24,618 unpacked bytes**，仅 17 个实际修改的代码成员；[逐文件字节、原因和 SHA 归因](../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-package-attribution.json)已与 ZIP 成员求和核对，资源及 wheel 完全相同。各中间包的修复归因和 build identity 保留在本轮目录。

最初本轮包相对历史预算增加 6,245/21,713 bytes，其中包括此前已提交却未计入预算的两个 reader、公开导出/注册，以及 panel 的 CRLF 1,619 bytes。[历史包重建](../../../../.blend-analysis/2026-09-07-review/baseline-reconstruction.json)与[初始成员归因](../../../../.blend-analysis/2026-09-07-review/package-native-delta.json)已区分这些原因；不能将全部历史差值声称为本轮新增代码。最终相对原历史预算总差值为 12,676 packed / 46,331 unpacked bytes。

## 文件保留与剩余边界

报告单独保存，不改写历史人工验收及其 Not Run 状态。[真实用户窗口只读结果](../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-user-preservation.json)与先前状态相同：`1.blend`、Cube/Light/Camera、dirty=false；原进程没有用于测试操作。根目录未跟踪的 `1.blend` 属于用户，不提交。本轮日志、截图、渲染、测试配对及失败副本保留在 ignored `.blend-analysis/2026-09-07-review/`，交付 hash 清单不包含整个 Python/profile 缓存。

早期 DATA 的失败配对曾被测试脚本继续使用，不能冒充不可变 checkpoint；明细明确注明，原失败截图和日志仍有效。后续失败均另存完整配对并保留。总览首次相机裁切及本轮脚本的路径/RNA 读取错误也保留记录，修正后复核，不将测试工具问题算成产品缺陷。

自动审批拒绝的具体动作是再次安装/清理真实用户扩展目录，原因是首次已触发 NumPy 清理和权限错误，可能影响现有 MCP。当前可供审批的对象为上方同一 R25 ZIP；真实目录备份、关闭占用后的安装及冷启动验证尚未执行。未推送、未创建 tag、未发布 Release、未提高版本。
