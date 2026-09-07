# REP-BIOLOGICAL — PDB MODEL 与 PQR 参数

执行者：**Agent 模拟用户**。UI **Passed**；独立 MCP **Passed**。UI 首测使用真实窗口 R22/R23；根据用户 2026-09-08 的后续授权，R24 在独立 UI profile 内使用已验证 UI 对应的公开 MCP 命令重放，并实际检查窗口。该重放不冒充新一次原生鼠标键盘首测。

最终版本 Blender **5.1.1** / Python **3.13.9**，source `5066cab35b28e21c484eeb64db026273cdea4243`，R24 ZIP SHA-256 `66e0a701ddbac2bf4cf4c4104da9b32a4e14cb632cefaf46a471d2a966861e9b`。两条路径均核对安装目录内全部 Python 文件与同一 ZIP 一致；整轮最终统一复核仍待完成。

前置为两个独立 profile 的空场景；UI 路径结束后才开始独立 MCP 路径。不可变输入的逐字节副本、大小和 SHA-256 见[输入清单](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-inputs.json)。

| 输入 | 规模与科学含义 |
| --- | --- |
| `1d3z-ubiquitin-nmr.pdb` | 1,015,821 bytes；10 MODEL × 1231 atoms，chain A，76 residues；NMR 构象集合，不赋予动力学时间含义 |
| `apbs-protein-rna-nb.pqr` | 70,047 bytes；998 atoms，41 residues，998 charge/radius；22 个合法零半径；源 chain IDs 为空，按残基序号回退恢复两个 segment |

| 项目 | 原生 UI 首测 | 最终 R24 公开命令重放与独立 MCP |
| --- | --- | --- |
| 导入 | N 侧栏 ChemBlender → Select Files → Preview → OK，依次导入 PDB/PQR | 两份空场景分别 quick_import，读取 preview_json 后 confirm_import；每次等待公开摘要 committed |
| 层级 | Browser By Data 搜索 hierarchy，选择匹配层级及 Outliner View | 公开 Browser RNA 与 View 的 hierarchy ID 匹配；两个 hierarchy、两个有可见几何的 View |
| PDB 选择 | Chain A → Select Chain；First/Last Residue 均为 1 → Select Residue Range | select_biological_atoms 分别选中 1231 和 19 原子；掩码与源文本逐索引相同 |
| MODEL | Configure 10 MODEL Frames；原生数字框输入 1/10；空格播放和暂停 | play_biological_models、scene.frame_set、screen.animation_play/cancel；首末顶点正确变化，播放 true→false，残基掩码保持 |
| PQR | 属性菜单 PQR Radius → At Most → 0 → Select Property Threshold | selector=property、property_role=radius、comparison=less_equal、threshold=0；精确选中 22 原子 |
| 文案与诊断 | 原生发现摘要截断、选择无反馈、空 chain IDs 被统称为 chains | 新窗口显示 chain/segment entries=2、blank source chain IDs=2、residues=41、atoms=998；选择后有数量提示 |
| 保存与视觉 | 保存操作已在此前 LIFE/OUTSIDE 原生验收 | 两条路径 public save_as_mainfile；配对清单/hash 验证；各有首末 MODEL 和 PQR 单体渲染，集合与相机一并保存 |

入口可以在侧栏找到；选择功能需要先匹配数据行和 View。F3 搜索 Quick Import/Select Files 没有命中，输入保护停止后返回侧栏成功。导入有阶段进度与 Cancel 按钮；本项没有重复执行导入取消。PDB/PQR Preview 只显示 reader、质量、能力与默认 View，详细数目及警告在提交后检查，已校正相邻样例文档。PQR 的 Partial 对应一条元素推断汇总 warning，不是遗漏了 998 个属性值。

原生成功记录的操作输入累计 **58.58 秒**，不含观察间隔。最终保留的命令记录累计 UI profile **13.06 秒**、独立 MCP **12.93 秒**，包括状态检查与渲染，不能当作一次连续操作的端到端耗时。重放执行器按公开状态等待异步提交；最初过早检查 committed 的测试脚本断言已修正，完整路径从空场景重跑。

科学验证独立解析源文本，核对全部 10×1231 坐标、998 个 PQR 坐标、coordinates/occupancy/b_factor/partial_charge/radius 五个数据集。单位分别保持 angstrom、dimensionless、angstrom_squared、elementary_charge、angstrom。两条路径的五组数组 hash 相同；源 chain IDs 与 segment indices 分别保留 `A/0`、空值/0、空值/1。选择只写 View 属性，不改写权威来源。详见[科学数据与配对 hash](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-R24-science-check.json)。

| 问题与严重程度 | 失败证据 | 修复与重测 |
| --- | --- | --- |
| UX，轻微：默认宽度截断 MODEL/chain/residue；选择后无数量反馈；无科学数组影响 | [R22 冻结配对、截图、失败测试](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/REP-BIOLOGICAL-feedback/failure.json) | `8eb2f10`；先失败后通过；R23 原生显示 1231/19 选择数量，R24 双路径保持 |
| 科学文案，中等：两个空 chain ID segment 被称作两条源链；源数据正确保留 | [R23 冻结配对、截图、失败测试](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/REP-BIOLOGICAL-chain-label/failure.json) | `5066cab`；显示 chain/segment entries 及 blank source ID 数；R24 实际窗口、双路径和源数据验证通过 |
| 证据相机，轻微：首次单体取景误用正交相机宽高比例，图片被裁切；非产品错误 | [裁切图片与修正记录](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/REP-BIOLOGICAL-detail-framing/incident.json) | 修正本轮展示脚本，重渲染六张；最终单体完整，无产品修复 commit |

R24 对 R23 仅 `ui/biological.py` 增加 195 bytes 未压缩 / 58 bytes 压缩；包体 29,989,752 bytes、未压缩 32,112,866 bytes，未解释增长 allowance=0。20 项专项、2313 项完整测试（26 个已注明原因的 skip）、编译、生成文档检查、原生 validate/build、ZIP 审计、artifact verifier 与完整隔离 smoke **105.35 秒**通过。两个 profile 的新进程依赖检查通过；本项没有冷重开生物配对，不将冷依赖检查写作配对冷重开。

| 最终图像 | UI profile | 独立 MCP |
| --- | --- | --- |
| PDB MODEL 1 | [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-UI-pdb-model1-detail.png) | [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-MCP-pdb-model1-detail.png) |
| PDB MODEL 10 | [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-UI-pdb-model10-detail.png) | [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-MCP-pdb-model10-detail.png) |
| PQR | [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-UI-pqr-detail.png) | [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-MCP-pqr-detail.png) |

默认 View 为灰色原子点几何，不是 ribbon/cartoon，也未凭空添加拓扑。单体渲染由证据相机整理；两条路径对应的 PNG 解压像素流完全相同，见[图像比较](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-R24-render-comparison.json)。

- [最终分段文案窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R24-03-chain-segment-final.png) / [原生残基反馈](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R23-08-residue-feedback.png) / [原生零半径选择](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-BIOLOGICAL-R23-21-zero-radius.png)
- [UI 配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-R24-UI/REP-BIOLOGICAL-UI.blend)，集合 `REP-BIOLOGICAL/UI`；[独立 MCP 配对](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-R24-MCP/REP-BIOLOGICAL-MCP.blend)，集合 `REP-BIOLOGICAL/MCP`。
- [可复用公开命令与 UI 证据目录](../../../../../tests/blender_review_commands.py)；[UI 最终状态](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-R24-UI-saved.json) / [MCP 最终状态](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-BIOLOGICAL-R24-MCP-saved.json)。
