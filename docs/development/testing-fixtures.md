# 测试 fixture 维护规则

Fixture 是可复现科学行为的输入证据，不是随手复制的样例。新增或替换 fixture 时，
先确定 provenance、license 和 exact bytes，再写测试。

## Provenance 最小记录

非显然的、外部取得的、生成的或二进制 fixture 应在同目录 `README.md` 记录：

| 字段 | 要求 |
| --- | --- |
| 目的 | 该文件证明的 reader、错误恢复或 round-trip 边界 |
| 来源 | 上游 URL、公开数据库 ID、release/tag/commit，或生成脚本/测试函数 |
| 许可 | SPDX 或原始分发许可；无法确认时不得提交 |
| 变换 | 截取、换行、字段编辑、压缩、Blender 保存版本等 |
| 完整性 | 文件 bytes 和 SHA-256；hash-locked 二进制必须逐文件记录 |
| 预期 | Complete/Partial/Ambiguous/Invalid、诊断或失败模式 |

仓库自产的最小文本 fixture 可以标记为 synthetic，并说明生成规则。不得把 fixture
来源误写成 runtime dependency；例如 ASE/libAtoms/OVITO 样例只证明兼容语义时，
基础 reader 仍可保持 dependency-free。

## Bytes、换行和二进制

- 以 bytes 构造 parser 边界期望，不依赖平台默认 encoding。
- 常规文本使用 UTF-8 无 BOM；需要证明 CRLF 行为的文件保持 exact CRLF。
- 在 `.gitattributes` 明确 `text`/`eol`，避免 checkout 自动改写 fixture。
- NPY 使用 `allow_pickle=False`；canonical artifact 的文件 hash 与 content hash
  分别验证。
- `.blend`、NPY 等二进制使用 `-text`/hash contract。发生路径或二进制冲突时停止，
  不使用 `ours`/`theirs` 自动选择。

三个已发布 legacy `.blend` 的版本、生成环境、对象清单和 hash 见
[`tests/fixtures/legacy-blend/README.md`](../../tests/fixtures/legacy-blend/README.md)。
这些文件是 hash-locked；迁移测试只能消费，不能为了通过测试重存或重写。
Reader API public schema 的 JSON 与 digest 位于
[`tests/fixtures/reader-api/`](../../tests/fixtures/reader-api/)。

## 添加或修改流程

1. 先加入最小 fixture 和失败测试；确认失败来自缺少的 parser/恢复行为。
2. 记录 provenance、license、变换和 SHA-256。公开数据库 fixture 还应记录稳定 ID。
3. 实现最小行为，覆盖 valid、边界和 malformed 路径；不要只断言“没有抛异常”。
4. 若 reader capability 或 fixture family 变化，更新
   `ChemBlender/core/reader_catalog.py` 并运行生成器；不得手改生成表掩盖 stale catalog。
5. 运行 focused module、repository line-ending/hash contract、Reader API conformance
   和完整 discovery。

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest `
  tests.test_repository_contract `
  tests.test_generated_docs_fresh `
  tests.test_reader_conformance_v1 -v
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
```

大型性能输入优先由 `ChemBlender/benchmarks/datasets.py` 以固定 seed 流式生成并记录
SHA-256，不提交可再生的大文件。Fixture 需要第三方 runtime 时，测试必须明确
optional dependency gate；不能把 skip 记为已验证。
