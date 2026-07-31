# ChemBlender 2.3.0 RC1 可用性验收结果

## 结论

本轮 scripted operator acceptance 未发现 `Blocker` 或 `Major`。U01–U12
均完成；未修改 runtime 代码。三个 `Minor` 是已有 warning/Windows native-library
清理噪声，不改变科学映射、项目持久化或任务完成度。

这是可重复的 Blender operator-level 验收，不是盲测或独立人类参与者研究；
因此 `Help required` 和 `Scientific misunderstanding` 只反映脚本执行期间可观察到的
产品提示与科学断言。

## 环境与证据

| 项目 | 值 |
| --- | --- |
| checkout HEAD | `c30dc1093e4a842f04dc1ce09d48760faacc02b5` |
| OS | Windows 10 专业版 x64 |
| CPU / RAM | AMD Ryzen 7 4800H / 15.9 GiB |
| Blender / Python | 5.1.2 / 3.13.9 |
| RDKit / Gemmi | 2026.03.3 / 0.7.5 |
| package | `chemblender-2.3.0-alpha.1.zip`, 29,955,650 bytes |
| package SHA-256 | `0db367c18fd849897bb5ca0189c50c573bda40ea5db35c565a99f882115356ec` |
| isolated product profile | `D:\cbw4-usability-rc1c` |
| product command result | exit `0`; `PASS: ChemBlender extension lifecycle`; 252.760 s |
| legacy aggregate result | exit `0`; 1 test with 3 fixture subtests `OK`; 10.334 s |
| Remote CI | Not Run — local Task 6 evidence only |

`tests/blender_smoke.py` 在一次真实 extension-native 安装中串行执行 U01–U11；
因此这些行的 `Elapsed time` 诚实记录共享的 252.760 s wall-clock 上界，不虚构
单击级时间。额外的 10k SDF 场景记录了 232.460 s measured sequence、
126,465,997 bytes peak memory、20.96/21.63 ms browser-filter median/p95 和
5.64/5.67 ms 的 1,000-row RNA projection median/p95。

## 任务结果

| ID | Completion | Elapsed time | Errors | Help required | Scientific misunderstanding |
| --- | --- | --- | --- | --- | --- |
| U01 Extension install | Passed | 252.760 s shared product run | None | None | None |
| U02 XYZ import | Passed | 252.760 s shared product run | None | None | None; Structure/revision assertions passed |
| U03 SDF conformers | Passed | 252.760 s shared product run; 10k measured sequence 232.460 s | None | Built-in review confirmation | None; canonical identity and `ConformerSet` remained distinct |
| U04 Cube diagnostics/semantic resolution | Passed | 252.760 s shared product run | None | Built-in semantic controls | None; Ambiguous source Grid remained immutable and derived `scalar_field` was Complete |
| U05 CIF import/save/reopen/export | Passed | 252.760 s shared product run | None | None | None; fractional/cell/occupancy/ADP assertions passed |
| U06 PDB import/save/reopen | Passed | 252.760 s shared product run | None | None | None; hierarchy/altloc/occupancy assertions passed |
| U07 diagnostics paging/export | Passed | 252.760 s shared product run | None | None | None; bounded preview and complete canonical export both passed |
| U08 save/reopen | Passed | 252.760 s shared product run | None | None | None; `.blend`/`.cbq` links and clean-save manifest were stable |
| U09 revision actions | Passed | 252.760 s shared product run | None | Built-in Keep/Update/Comparison choices | None; only the selected logical View changed |
| U10 scientific edit | Passed | 252.760 s shared product run | None | Built-in confirmation | None; original Structure stayed immutable and derived topology was `USER_EDITED` |
| U11 export/reimport | Passed | 252.760 s shared product run | None | Built-in loss preview where required | None; semantic re-import assertions passed |
| U12 legacy 2.1 molecule | Passed | 3.289 s | None | Explicit preview/confirm contract | None |
| U12 legacy 2.2 crystal | Passed | 3.428 s | None | Explicit preview/confirm contract | None |
| U12 legacy 2.2 edited scaffold | Passed | 3.275 s | None | Explicit preview/confirm contract | None |

每个 legacy 进程都使用独立 fresh profile，输出
`PASS: legacy migration transaction and reopen` 且 exit `0`。运行前 SHA-256
分别匹配 `36b05c3…`、`f2995e82…` 和 `a6af8e23…`。

## 问题分级

| ID | 等级 | 观察 | 处理 |
| --- | --- | --- | --- |
| M-01 | Minor | `mesh.py` 报告既有 `invalid escape sequence '\W'` SyntaxWarning | 不影响执行或科学结果；RC scope freeze 下不在 Task 6 修改 |
| M-02 | Minor | 合成 10k SDF 触发 RDKit “tagged as 2D”/非零 Z warning | 生成数据仍按断言映射；不属于数据损坏 |
| M-03 | Minor | Windows 退出时已加载的 Gemmi/RDKit DLL 无法从 fresh profile 删除 | 进程 exit `0`；第二次 fresh install 仍通过；保留为已知 cleanup 限制 |
| E-01 | 环境 | Blender 内置 Grease Pencil brush asset 报告无法转换为相对路径 | 非 ChemBlender 文件，不计产品 issue |

- `Blocker`: 0
- `Major`: 0
- `Minor`: 3

smoke 中出现的 “Apply Scientific Edits”、不兼容 node group、非法 recovery action
等 `Error:` 行是刻意执行的 fail-closed 负向场景；测试验证了拒绝文本和未修改状态，
不计为用户任务失败。

## 剩余限制

- 本轮没有独立人类参与者，不能据此量化菜单发现时间或首次阅读理解成本。
- U01–U11 共享一次 product run；只报告真实共享 wall-clock，不推导未采集的单步时间。
- Remote CI 未运行；该证据不得描述为远端 CI。
