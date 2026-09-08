# 本地交付验证记录

2026-09-08，源码提交 `67ace7363a9dcc0bab29bdc2601ea6a6357d621f`。已完成可用环境中的真实分子、原子属性和轨迹流程；完整物理量计划仍有待运行项目。结构化证据与原始日志哈希见 [verification.json](verification.json)。

| 检查 | 结果 | 依据与范围 |
| --- | --- | --- |
| unittest | Passed | 2504 tests，36 optional skips；119.703 s。最后的原子颜色/项目归属修复另有实际 Blender/Cycles 回归；只修剪 EOF 空行不改变运行逻辑 |
| Extension validate/build、ZIP 审计 | Passed | 209 个成员；源码哈希与最终快照一致；参考子模块、worker、示例与规划文件不进入 ZIP |
| 私有 user_default 安装、启停和冷启动 | Passed | Blender 5.1.1 / Python 3.13.9；106 classes、22 readers；RDKit/Gemmi 实际运行 |
| 最终包完整 Blender smoke | Passed | exit 0，104.031 s；198 个 Python 模块与当前源码一致；真实导入、Save As/reopen、大文件、取消和卸载检查通过 |
| 分子场景生命周期 | Passed | 3 工作台、40 总 View、61 个科学 NPY；Save As、整体移动、删除 VDB 后公开重建与重开，科学哈希不变 |
| PQR / rMD17 生命周期 | Passed | 2 工作台、6 View、14 个科学 NPY；Save As、整体移动、独立进程重开与 32 帧坐标/力检查通过 |
| 图片、动画与 GUI | Passed | 28 正式 Cycles 静图、128 PNG 帧、4 MP4；11 张原生窗口截图；公开创建、加载、更新、重建、渲染、保存和重开 |
| 离线 SOP | Passed | 标题目录互链、39 图片；1440 / 390 px 真浏览器检查通过，无横向溢出或控制台错误 |
| 全部可选真实后端 | Not Run | 新环境尚未批准安装；不能用合成数据、已有渲染适配器或固定输入文件代替完整科学验收 |
| 共享真实用户安装、远端 CI / 发布 | Not Run | 本轮使用私有配置，未改变共享用户环境；远端操作未获授权 |

最终开发包位于本地缓存 `.agents/cache/scientific-extension-qualification-20260908-08/source/ChemBlender/chemblender-2.4.0.zip`（从仓库根目录起算，不随 Git 分发），30109401 bytes。SHA-256：`fa66bc9f407b3e87d894fd8fc9d0069a470c3e0cc690ae33f009190ca6867995`。包名沿用当前 manifest 版本，不代表已发布新版本。

完整 smoke 在 Windows 进程内卸载已加载的 RDKit 库时出现私有测试目录的 DLL 占用清理警告，最终检查和退出码均通过；未为消除警告删除共享文件。旧失败日志保留，最新通过结果没有覆盖它们。

## 实际完成的科学范围

真实 FCHK 的 MO、总电子密度、自旋密度、MP2−SCF 差分密度和 ESP 已经贯通计算、面板、等值面/体积/切片/剖面、模板出图和保存重开。PQR 电荷、rMD17 构型和逐帧力已贯通原子颜色、箭头、播放与动画导出。科学方法、输入哈希、单位和显示参数见[示例索引](../../../examples/scientific-visualization/README.md)。

ELF/LOL/NCI/QTAIM、振动与光谱、Band/DOS/PDOS、声子和 Fermi 的数据适配、原生显示和面板入口已有实现与针对测试；本轮固定真实输入的全部计算、渲染和 SOP 验收仍待 [hash-locked 环境提案](../../../examples/scientific-visualization/dependencies/PROPOSAL.md)。依赖审批依据是仓库 [AGENTS.md](../../../AGENTS.md) 的 Python Environment 要求：`Do not install or change Python dependencies without explicit approval.` 已批准的缓存环境创建不改写为所有新包安装已批准。

## 可重放证据

- [分子工作台生命周期](../../../examples/scientific-visualization/output/molecular/scenes/lifecycle-verification.json)
- [原子与轨迹工作台生命周期](../../../examples/scientific-visualization/output/atom-trajectory/scenes/lifecycle-verification.json)
- [GUI 截图和公开操作记录](screenshots/REPLAY.md)与[离线页面浏览器检查](browser-qa.json)
- [资格验证入口](../../../tests/qualify_scientific_extension.py)与[完整 Blender smoke](../../../tests/blender_smoke.py)

重放时使用独立用户目录；输入和科学数组以原始字节哈希为准，显示缓存可以删除后重建。没有提供网格积分域收敛证明，也没有把原始 ECD 单位、轨迹帧次序或显示箭头缩放解释成额外物理结论。
