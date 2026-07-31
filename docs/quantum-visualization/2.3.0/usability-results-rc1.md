# ChemBlender 2.3.0 RC1 可用性验收结果

## 结论

本轮 **hybrid scripted product/integration acceptance** 未发现 `Blocker` 或
`Major`。U01–U12 均完成；未修改 runtime 代码。三个 `Minor` 是已有
warning/Windows native-library 清理噪声，不改变科学映射、项目持久化或任务完成度。

所有 Blender 场景都安装同一个 packaged Extension。U01、U02、U04、U06、U08、
U10 和 U12 覆盖真实 operators；U09 用真实 operator 处理进程内构造的 replacement
revision；U03 的 preview/group/commit 是安装包 UI service 直调，export 才是
operator；U05、U11 还使用安装包内 core reader 或 `ExportJob` 做集成级语义复验；
U07 使用合成 canonical report 驱动真实 copy/page/export operators。它不是盲测
或独立人类参与者研究，因此
`Help required` 和 `Scientific misunderstanding` 只反映脚本执行期间可观察到的
产品提示与断言。

## 环境与证据

| 项目 | 值 |
| --- | --- |
| committed HEAD during final run | `fff5cebdac7c101f2e63497c72d3a4405028784e`；review-fix harness/docs 当时为 working-tree changes |
| runtime/package baseline | `c30dc1093e4a842f04dc1ce09d48760faacc02b5`；此后到本轮没有 runtime 修改 |
| OS | Windows 10 专业版 x64 |
| CPU / RAM | AMD Ryzen 7 4800H / 15.9 GiB |
| Blender / Python | 5.1.2 / 3.13.9 |
| RDKit / Gemmi | 2026.03.3 / 0.7.5 |
| package | `chemblender-2.3.0-alpha.1.zip`, 29,955,650 bytes |
| package SHA-256 | `0db367c18fd849897bb5ca0189c50c573bda40ea5db35c565a99f882115356ec` |
| isolated product profile | `D:\cbu-product-3d7aa3a8` |
| product command result | exit `0`; `PASS: ChemBlender extension lifecycle`; 253.574215 s raw wall time |
| legacy packaged acceptance | exact ZIP installed separately for all 3 fixtures; real preview/migrate operators; save/reopen |
| focused/full verification | 73 passed; 2014 passed / 26 skipped / 0 failed |
| Remote CI | Not Run — local Task 6 evidence only |

`tests/blender_smoke.py` 在一次真实 extension-native 安装中串行执行 U01–U11；
因此这些行的 `Elapsed time` 诚实记录共享的 253.574 s wall-clock 上界，不虚构
单击级时间。额外的 10k SDF 场景记录了 232.041566 s measured sequence、
126,467,983 bytes peak memory、21.0861/21.0909 ms browser-filter median/p95 和
5.73/5.79 ms 的 1,000-row RNA projection median/p95。

最终 raw stdout/stderr 与 timing 保留在 ignored review bundle
`.superpowers/sdd/2026-07-23-chemblender-2.3.0-wave-4-performance-ux/`：

- validate/build：`task6-final-validate.log`、`task6-final-build.log`；
- product：`task6-final-product-stdout.log`、
  `task6-final-product-stderr.log`、`task6-final-product-timing.json`；
- legacy：`task6-final-legacy-*-stdout.log`、
  `task6-final-legacy-*-stderr.log`、`task6-final-legacy-timings.json`。

## 任务结果

| ID | Completion | Elapsed time | Errors | Help required | Scientific misunderstanding |
| --- | --- | --- | --- | --- | --- |
| U01 Extension install | Passed | 253.574 s shared product run | None | None | None |
| U02 XYZ import | Passed | 253.574 s shared product run | None | None | None; real Quick Import/confirm operators and Structure/revision bindings passed |
| U03 SDF conformers | Passed | 253.574 s shared product run; 10k measured sequence 232.041566 s | None | Built-in review confirmation | None; staging used Quick Import, preview/group/commit used installed UI services, export used the operator, and `ConformerSet` identity remained distinct |
| U04 Cube semantic resolution | Passed | 253.574 s shared product run | None | Built-in semantic controls | None; real import/resolve/surface operators kept the Ambiguous source Grid immutable and derived a Complete `scalar_field` |
| U05 CIF import/save/reopen/export | Passed | 253.574 s shared product run | None | None | None; direct installed-package parse/`ExportJob`, Blender View/save/reopen, and fractional/cell/occupancy assertions passed; fixture has no ADP round-trip claim |
| U06 PDB import/save/reopen | Passed | 253.574 s shared product run | None | None | None; real Quick Import/confirm operators preserved hierarchy/altloc/occupancy and reopen state |
| U07 diagnostics paging/export | Passed | 253.574 s shared product run | None | None | None; a synthetic canonical report passed real operator paging/export, bounded preview and complete export assertions |
| U08 save/reopen | Passed | 253.574 s shared product run | None | None | None; constructed installed-package Project/View passed real Blender save/reopen, `.cbq` links and clean/link-only manifest stability |
| U09 revision actions | Passed | 253.574 s shared product run | None | Built-in Keep/Update/Comparison choices | None; real operators acted only on the selected logical View, using an in-process replacement revision/Grid |
| U10 scientific edit | Passed | 253.574 s shared product run | None | Built-in confirmation | None; direct preview plus real apply operator kept the original Structure immutable and derived `USER_EDITED` topology |
| U11 export/reimport | Passed | 253.574 s shared product run | None | Built-in loss preview where required | None; SDF used the export operator, while XYZ/extXYZ/CIF also used installed-package core/`ExportJob` semantic re-import |
| U12 legacy 2.1 molecule | Passed | 8.119 s | None | Explicit preview/confirm operators | None |
| U12 legacy 2.2 crystal | Passed | 8.107 s | None | Explicit preview/confirm operators | None |
| U12 legacy 2.2 edited scaffold | Passed | 8.083 s | None | Explicit preview/confirm operators | None |

每个 legacy 进程都使用独立 fresh profile，输出
`PASS: packaged legacy migration and reopen` 且 exit `0`。运行前 SHA-256 分别
匹配
`36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`、
`f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a` 和
`a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740`；
安装包 SHA-256 均匹配
`0db367c18fd849897bb5ca0189c50c573bda40ea5db35c565a99f882115356ec`。
profiles 为 `D:\cbu-legacy-21-cef600a7`、
`D:\cbu-legacy-22-crystal-65299021` 和
`D:\cbu-legacy-22-edited-323bf25f`；这三项不使用 checkout
`ChemBlender` import。

## 问题分级

| ID | 等级 | 观察 | 处理 |
| --- | --- | --- | --- |
| M-01 | Minor | `mesh.py` 报告既有 `invalid escape sequence '\W'` SyntaxWarning | 不影响执行或科学结果；RC scope freeze 下不在 Task 6 修改 |
| M-02 | Minor | 合成 10k SDF 触发 RDKit “tagged as 2D”/非零 Z warning | 生成数据仍按断言映射；不属于数据损坏 |
| M-03 | Minor | Windows 退出时已加载的 Gemmi/RDKit DLL 无法从 fresh profile 删除 | 进程 exit `0`；第二次 fresh install 仍通过；保留为已知 cleanup 限制 |

- `Blocker`: 0
- `Major`: 0
- `Minor`: 3

smoke 中出现的 “Apply Scientific Edits”、不兼容 node group、非法 recovery action
等 `Error:` 行是刻意执行的 fail-closed 负向场景；测试验证了拒绝文本和未修改状态，
不计为用户任务失败。

## 剩余限制

- 本轮没有独立人类参与者，不能据此量化菜单发现时间或首次阅读理解成本。
- U01–U11 共享一次 product run；只报告真实共享 wall-clock，不推导未采集的单步时间。
- CIF、extXYZ 和部分 export 复验是安装包内 direct core/`ExportJob` 集成断言，
  不是 UI 点击；U07 的 report 是合成输入。完整执行层级见验收脚本。
- Remote CI: Not Run；该证据不得描述为远端 CI。
