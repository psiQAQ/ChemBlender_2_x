# DATA — 科学编辑、topology、晶体与生物数据

执行者：**Agent 模拟用户**。当前 UI **Not Run（部分步骤已完成，整项未完成）**；MCP **Not Run**。

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
