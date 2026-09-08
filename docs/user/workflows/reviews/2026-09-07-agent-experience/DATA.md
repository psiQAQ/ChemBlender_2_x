# DATA — 科学编辑、topology、晶体与生物数据

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：原始与 +1 Å Derived 数据不变；晶体约束隐藏/恢复；缺少 spglib 时停止且不产生结果。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-DATA-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-DATA-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/DATA/UI/DATA-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-DATA-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-DATA-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/DATA/MCP/DATA-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI **Passed**；MCP **Passed**。全部 required case 的最终统一复核仍待完成。

## 已执行 UI

前置为独立空文件 DATA UI、DATA/UI 集合；输入不可变 `inputs/mol2/substructure.mol2`。约 21:13–21:24，具体动作/耗时见本轮 `logs/ui-actions.jsonl`。

1. N → ChemBlender → Select Files，预览显示 Complete、3 atoms、2 bonds、GASTEIGER charge，确认。
2. Browser → By Data；滚动列表选择 Structure，显示 explicit-file 两条键及 Compute Proposal。
3. 计算 distance proposal，Reject；公开 decisions_json 为 rejected，未改变一个已有对象。再次计算提示 Matching topology proposal already exists；Accept 清空 rejected 并记录 accepted，来源 topology 保留。
4. 使用 Show 与 Show Atoms Only 检查显示切换。按钮按接受状态重新排序，必须重新观察标签，不能沿用原位置。
5. 选择 Structure，Tab → A → G → X → 1 → Enter → Tab。Apply Scientific Edits 显示 3→3 atoms、Moved 3、最大位移 1 Å、无 element/bond/cell 变化、4 个 source-linked results 不继承。
6. Cancel 后无 derived 对象；再次打开并 OK 后创建 Derived 对象。Ctrl+S 选择保存位置，再 Ctrl+S，生成 `DATA-R5-UI.blend` 与 `.cbq`。

入口藏在 Browser 选中 Structure 后的下半部分，需滚动；预览文案清楚。小样例计算即时反馈，有明确的拒绝、接受、取消与成功状态。取消科学编辑不会撤销用户先前的 Blender 顶点编辑，科学 Project 的提交由确认控制。

## 证据与待完成

- 截图 `DATA-01` 至 `DATA-13` 保存在[本轮截图目录](../../../../../.blend-analysis/2026-09-07-review/screenshots/)。科学预览：[DATA-10-edit-preview.png](../../../../../.blend-analysis/2026-09-07-review/screenshots/DATA-10-edit-preview.png)；确认：[DATA-12-derived.png](../../../../../.blend-analysis/2026-09-07-review/screenshots/DATA-12-derived.png)。
- [配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R5-UI.blend)、[sidecar](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R5-UI.cbq/manifest.json)。动作绑定 `f2cbd41` / ZIP `966dc8a7def7343fa29b1823ea72e2ea43a04015655bf32da0bd2f6c2a824daf`。
- 尚需：源/派生科学数组与 provenance 完整核对、晶体约束、生物层级、独立 MCP 全路径和最终包复核。当前无 DATA 产品缺陷已确认；reload 缺陷另记 ENV/LIFE。

## 晶体面板失败与修复

CONTCAR 预览显示 27 Å³ cell、Na/Cl、Cartesian、Selective Dynamics 和 ion/lattice velocities。选择周期 Structure 后，面板在约束区报 `TypeError: bad operand type for unary ~: LazyNpyArray`，后续控件不显示。P2 可用性问题，未改变科学数据；两个 marker 和约束数据仍在。失败现场 `outputs/failures/DATA-lazy-constraints.blend/.cbq` 绑定 4b9882c / b655ad3f。

回归用真实保存/打开 sidecar，复现同一错误；改用 NumPy array protocol 后 66 Browser tests 通过。新 ZIP `bdc869ac8aed4ffddeb5d3d65af95aed71d65f9bb2c9a79a8f0f85027317f5bc`，只有 properties.py +35 unpacked / +19 packed；完整 2,297 tests / 26 skips 和隔离 smoke 105.67 s 通过。`DATA-R7-02` 显示 2 constrained atoms、Toggle Selective Constraints；实际点击后 hidden=true / visible_flag=false（DATA-R7-UI-constraints-hidden.json），再次点击恢复两个 marker。spglib 缺失时 Derive Symmetry 禁用并显示原因。MCP 同包已安装，独立 DATA 操作待执行。


## R8：失败、修复和独立重测

生物默认 View 的 atoms/points 分支仅输出顶点，没有可见几何。P2，影响可用性和视觉结果，不改变科学坐标、来源键或层级。旧包实际 Blender smoke 以 `biological default View has no renderable geometry` 失败；`dc1ff3d` 添加受控的低面数显示球体，使用 `cbq_visible` 和 `vdw_radius × 0.25`，不推断键。源代码变化为 node.py +1767 bytes、views/structure.py +181 bytes；最终 ZIP 增长 399 bytes，未解释增长为零。

最终包 SHA-256：`0006d0b4131b4f4a0e36639116e58bdb7aa2d4d9f777018fee3c9cd07d3983fc`。2,297 tests / 26 documented skips / 0 failures or errors；完整隔离 smoke 105.5 s、编译、生成文档、原生 validate/build、ZIP 审计和 verifier 均通过。

前置状态：两个独立空文件，各建 DATA 集合，下设 UI 或 MCP；输入均为本轮 `inputs/DATA/` 的三个不可变副本：model-trajectory.pdb、substructure.mol2、velocities.CONTCAR。UI 操作约 21:53–22:15；MCP 导入预览 0.742 s、确认 2.037 s，各局部操作低于 1 s（不含审批等待）；精确请求和原生动作耗时见日志。

UI：Select Files 多选三项 → 滚动长 Preview → 保留独立来源并确认；Browser 选择 MOL2 Structure → Compute Proposal → Reject → Accept；Outliner 选择对象 → Edit Mode 全选 → X 移动 1 → Apply Scientific Edits → Cancel，确认无 Derived → 再次预览并确认；选择周期 Structure → 2 constrained atoms → 隐藏/恢复；BiologicalHierarchy → Create Size-Aware Default View → chain A、residue ALA → Configure 2 MODEL Frames → 时间轴第 2 帧。

MCP：从相同空前置状态独立 quick_import → 读取 preview_json → confirm_import；只使用公开 Browser RNA 定位实体，调用 compute/reject/accept/switch_topology；公开 mesh/transform Operator 移动原子，错误的 XYZ 导出路径使提交停止且无 Derived，修正后 apply_scientific_edits 成功；toggle_selective_constraints 隐藏/恢复，derive_crystal_symmetry 明确报告 spglib 缺失；create_biological_view、select_biological_atoms、play_biological_models 和公开 frame_set 完成相同选择与首尾帧检验。MCP 的科学提交是 EXEC 操作，没有独立的科学编辑取消 Operator；可取消预览通过 UI 验证，不能把 MCP 错误路径称为取消按钮测试。

实际结果：两条路径均保留源坐标 x=[0,1.3,2.5]，新派生实体为 x=[1,2.3,3.5]，unit=angstrom，数组文件 hash 正确；拓扑拒绝/接受状态准确，atoms-only 清除 View 绑定；两个约束标记可恢复。生物选择为 [true,true]，默认 alternate-location 可见掩码 [true,false]，对应 20 个可渲染面。第 1/2 MODEL 坐标由 (11,12,13) 移到 (14,15,16)。

体验评价：Browser 入口可找到，但完整选中项控件较长，需要滚动；多文件 Preview 也需滚动到底部才能确认。信息清楚，短任务有完成/失败反馈，错误后能够继续。View、模型选择和科学数组一致。证据相机最初按三维最大边长取景导致纵向裁切，已修正为考虑图像宽高比；这是证据脚本问题。

UI 点击初测使用 0601b546 构建；保留原有混合换行后形成上述最终包。两者功能代码一致，最终包已重新通过真实 UI Install from Disk 安装；UI/MCP 安装中的全部 Python 文件与最终 ZIP 逐字节一致，最终状态和渲染证据单独保存，不将旧包完整流程冒作新包完整重跑。

- [UI 最终配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R8-UI/DATA-UI.blend)、[MCP 最终配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R8-MCP/DATA-MCP.blend)。每项文件含 DATA 集合及对应路径子集合。
- [UI 最终渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/DATA-R8-UI-render-final.png)、[MCP 最终渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/DATA-R8-MCP-render-final.png)、[真实窗口生物显示](../../../../../.blend-analysis/2026-09-07-review/screenshots/DATA-R8-23-biological-visible.png)、[科学编辑预览](../../../../../.blend-analysis/2026-09-07-review/screenshots/DATA-R8-16-edit-preview.png)。
- [双路径科学数据核对](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R8-science-check.json)、[MCP topology](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R8-MCP-topology.json)、[MCP 生物状态](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R8-MCP-biology.json)、[最终包 UI 身份](../../../../../.blend-analysis/2026-09-07-review/outputs/DATA-R8-UI-final-package.json)。

证据纠正：旧 DATA-R5-UI 及 failures/DATA-lazy-constraints 配对文件后来曾被测试脚本继续使用，sidecar 已前进，不能作为不可变、hash 匹配的旧失败冷重开证据。原始失败截图、错误日志及旧 ZIP 回归仍有效。本节 R8 使用全新状态和独立目录，后续不再在其中导入新来源。
