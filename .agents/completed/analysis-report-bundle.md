# Analysis Report Bundle

Completed on 2026-07-22.

## Result

- 新增 versioned `chemblender_analysis_report/1`。
- 汇总 calculation、dataset、provenance parent closure、recipe plan、citation 与 artifact hash。
- 新增确定性 Markdown renderer 和不覆盖既有目录的原子 bundle writer。
- failed/incomplete/ambiguous 数据保持显式状态，不生成有效结论表述。

## Evidence

- targeted manifest、ordering、failure、artifact、stale binding 与 Blender-free import tests passed。
- repository `268` tests passed、`27` skipped；Extension validate/build passed。
- ZIP 共 `60` entries，包含 report core，不包含 worker、submodules、模板引擎或量化执行依赖；isolated Blender lifecycle smoke passed。

## Boundary

未生成 PDF/DOCX，未嵌入大型数组或图像，未执行外部程序、联网或读取 connector 凭据。
