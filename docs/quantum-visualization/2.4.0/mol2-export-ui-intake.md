# ChemBlender 2.4.0 MOL2 Export UI Intake

## 结论

选择 **Task 2 — MOL2 Export UI Workflow**。Task 1 的 native core writer 已由
PR #9 以普通 merge commit `63f6043bdfe1a15fa411662f2bd418de6ebee85e`
进入 `main`，精确 head `1e40cdf52d794f6e00dea815966bdfd58a744286`
对应的 `extension-package` 与 `optional-qc-core` runs 均 Passed。

当前用户可在 capability 文档中看到 MOL2 export 为 `F5 / core /
preview_confirmation`，但 `ChemBlender.ui.export._FORMAT_ITEMS` 和 Blender 文件
过滤器仍没有 `mol2`。因此 core 能力无法从现有 Project Browser 导出入口使用，
这是 Task 1 合并后最小且可验证的产品闭环缺口。

## 方案比较

| 方案 | 结果 | 代价/风险 | 决策 |
| --- | --- | --- | --- |
| 扩展现有通用 export operator | 复用 selection、preview、后台 job、取消和原子发布 | 只需投影选中 MOL2 实体 | **选择** |
| 新建 MOL2 专用 operator/module | 可独立定制 | 重复生命周期、registration 和错误处理 | 拒绝 |
| 只保留 core Python API | 无新代码 | Blender 用户仍无法使用 | 拒绝 |

## 边界

本任务只扩展 `ChemBlender/ui/export.py` 及其现有显式 registration root。选中
Structure 或 MolecularRecord 后，UI 将相关 Structure、TopologyRecord、
MolecularRecord、ChemicalAnnotation 和 AtomicProperty 投影为 core writer 所需的
最小实体集合。loss preview、确认、取消和 destination 发布继续由现有通用流程与
Task 1 writer 承担。

不新增 UI 模块、operator、RNA 大对象、第三方依赖或科学模型；不实现 PDB、PQR、
Cube export；不修改 Reader API、sidecar schema、manifest version、CHANGELOG、tag
或 Release。
