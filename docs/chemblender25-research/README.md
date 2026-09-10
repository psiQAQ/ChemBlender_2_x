# ChemBlender 2.5 用户教程调研与本地执行包

**调研基线：** `release/2.5.0 @ 478bbd498277a0ce9a32fc9b262f36ec8410d2d9`。截至 2026-09-10。

这是研究报告、案例设计和执行/验收材料。**本包没有本次新生成的 Blender GUI 截图、真实渲染或 `.blend` 工程；所有案例初始状态为 `not_run`。** 现有仓库资格结果与本次合成单元测试分开记录。

## 文件

| 文件 | 用途 |
|---|---|
| [research-report.html](research-report.html) | 可直接在浏览器阅读的完整报告；无自动加载的远程资源 |
| [research-report.md](research-report.md) | 同版 Markdown 报告，便于 agent 阅读和纳入项目 |
| [case-catalog.md](case-catalog.md) | 21 个教学案例＋1 个边界验收单；输入、场景、科学检查、截图要求与限制 |
| [case-catalog.json](case-catalog.json) | 机器可读案例和 21 operation/22 reader/13 export/10 CLI/9 GUI 映射；设计覆盖不等于实测通过 |
| [local-agent-task.md](local-agent-task.md) | 可交给本地 Codex/其他 agent 的执行任务书 |
| [T01.case-spec.json](T01.case-spec.json) | 首课验收规格，需结合真实 UI 固定执行细节 |
| [run-manifest.template.json](run-manifest.template.json) | 故意保持未执行状态的结果模板 |
| [evidence-format.md](evidence-format.md) | 证据字段、使用方式和工具不能证明的事项 |
| [validate_evidence.py](validate_evidence.py) | 只读标准库检查器，不运行 Blender，不发布任何内容 |
| [test_validate_evidence.py](test_validate_evidence.py) | 合成单元测试，不是 GUI 测试 |
| [validator-tests.txt](validator-tests.txt) | 本次检查器测试原始输出 |
| [validation-summary.json](validation-summary.json) | 本次交付包的机器检查结果和边界 |
| [sources.json](sources.json) | 30 条固定来源/官方参考与证据边界 |
| SHA256SUMS.txt | 本包文件完整性清单（不包含该清单自身） |

## 建议入口

先读完整报告的缺口与能力边界，再把 `local-agent-task.md`、`case-catalog.json` 和报告交给本地 agent。M0/T00/T01 的真环境、真 GUI 和冷重开闭环完成之前，不应批量将所有案例写成已验证教程。

检查器通过仅意味着文件/记录一致；真实科学计算、GUI 操作、视觉审阅和公开分发资格仍需分别验收。本次没有修改 GitHub 仓库、安装用户后端、创建 PR 或发布 Release/PyPI。
