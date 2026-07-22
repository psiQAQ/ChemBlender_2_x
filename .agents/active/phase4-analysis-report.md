# Phase 4 Analysis Report Bundle

## Goal

从现有 project、recipe、calculation、dataset、provenance 与 citation contract 生成确定性的本地分析报告包，使计算和可视化结果可审计、可引用、可重新生成。

## Success Criteria

- 定义纯 Python、versioned report manifest，不依赖 `bpy`。
- 选择 calculation/dataset 时收集输入、单位、状态、provenance、recipe 与引用。
- Markdown/JSON 输出顺序稳定，缺失或失败数据显式标记，不把它们写成有效结论。
- 报告只引用现有 artifact；不自动联网、上传或执行外部程序。
- Extension ZIP 保持不包含报告 worker 或第三方模板引擎。

## Constraints

- 首版不生成 PDF/DOCX，不引入模板依赖。
- 不读取 connector、凭据或远程数据库。
- 不把 Blender 截图作为必需输入；场景/图像 artifact 仅按引用登记。

## Next Action

盘点 recipe citation、project provenance 与 artifact identity，先以失败测试固定 report manifest v1 和 Markdown renderer。

## References

- [工作流与 connector 计划](../../docs/quantum-visualization/plans/workflows-and-connectors.md)
- [Recipe contract v1](../../docs/quantum-visualization/specs/recipe-contract-v1.md)
- [QCSchema compute worker v1](../../docs/quantum-visualization/specs/qcschema-compute-worker-v1.md)
