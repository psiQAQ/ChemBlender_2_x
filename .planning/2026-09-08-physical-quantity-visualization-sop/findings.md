# Findings

## Starting state
- HEAD 3c80892, feat/quantum-visualization-workbench, clean. A-D completed; current task is a new expansion.
- Existing grid_volume creates VDB/Volume but no volume material. Existing density-only property surface contract is v2.
- Existing field sampling, zero-aware legends, scientific CSV, transactional rebuild and orbital image export must be reused.
- Browser groups logical views by render identity; independent duplicate views need instance identity and root ownership.
- Non-grid adapters exist but often lack public creation UI/materials. PDOS plotting, Fermi extraction and critic2 sampled-path parsing are missing.
- ECD is always unknown/AMBIGUOUS today; do not label unverified rotatory strengths as quantitative ECD. Raman source is activity.
- QCSchema gradient is a global PropertyDataset without structure_id, not directly a force vector. Explicit binding and minus sign required.

## Source and fixture decisions (research data)
- Local IOData water_sto3g_hf_g03.fchk, h2o.molden.input, ch3_hf_sto3g.fchk, nitrogen-mp2.fchk and water_sto3g_hf.wfx are real inputs. Nitrogen has SCF and MP2 RDMs; difference is MP2 minus SCF on identical affine/structure.
- cclib 07260dd0394cb1a2381d4d897746d727a12ad6ce has Gaussian/ORCA dvb IR/Raman/TD output fixtures. Existing lock .github/constraints/cclib-py313.txt; environment not installed.
- pymatgen 0428f232a569ffe6b16fa030d38ea35a56d70fd6: test-files/io/vasp/outputs/vasprun_Si_bands.xml.gz + inputs/KPOINTS_Si_bands; DOS uses fixtures/static_silicon/vasprun.xml.gz. Distinct calculations and E_F; band is 160 path points, DOS is 4^3 uniform mesh/10 irreducible points. MIT repository license. These are not evidence of converged grids.
- phonopy 2df40f4865d477f44d3b5d1ebcafc0b4af878e35 example/NaCl/{phonopy_disp.yaml,FORCE_SETS,BORN,POSCAR-unitcell,vasprun.xml-001,vasprun.xml-002}: actual VASP 4.6.35 displaced-cell data, BSD3.
- PyProcar fixed code 4a2ec9049af78fdd35b6214eef68fe40e5f356ed. HF dataset lllangWV/pyprocar_test_data at bf44809171f5228236c6a3716ba8933af08ddaeb, data/examples/fermi3d/non-spin-polarized.zip. 5,639,342 bytes, SHA256 1d079392bb1bc4dbd30606bde763bcf1f1aef6bafd3eb9a6aef3b94f25a029d5. In-memory prior audit: SrVO3, VASP6.4.3, Gamma21^3, 286 irreducible k, 20 bands, E_F=5.6990 eV, ISPIN1/ICHARG11/ISYM2, LDAUTYPE1, V U5/J0. Contains POTCAR and pickle: do not load pickle or redistribute entire package. Dataset card MIT but no package LICENSE; necessary text selection/license review pending.
- critic2 4b5dec9131c3a035af1b421d68a227c47fd641db supports ELF/LOL from WFX. Actual outputs still must be produced. FLUXPRINT/GRAPH 2/TEXT/END writes <root>_flux.txt with ordered path blocks, units and derivatives; source tests/015_grdplot/002_fluxprint_opts.cri and src/flux@proc.f90. CPREPORT JSON alone has no actual paths.
- MolecularNodes GPL3 (LICENSE.OLD not current), morbvis BSD3, PySCF Apache2 reference source initialized already; no new runtime imports from their source trees.

## Runtime
- Previous live query: Blender5.1.1 Windows, Python3.13.9, Cycles+FFmpeg, RTX4070TiSUPER OptiX, unsaved default 3-object scene. Must verify on implementation entry.
- Cache gbasis-py312 Python3.12.13, NumPy1.26.4, IOData1.0.1, GBasis0.1.0, SciPy1.16.3. Preserve existing pinned environment.
- Bundled Node has marked17.0.5; use it for offline HTML with no added doc runtime dependency.
## CBQ-only boundary audit

Existing 22-reader registry and worker load in independent Python without bpy/RDKit/Gemmi. Core model tags are stable class names, independent of Python package locations. Keep one shared model source; split core eager exports. Move original formats/readers/derivations/edits/exporters/Reader API/Worker outside the extension.

Hidden Viewer dependencies to remove: periodic symmetry rebuild uses gemmi.Op; old mesh/chemical operations use RDKit. CBQ 1.1 will store paired numeric symmetry rotation/translation arrays. Preserve old package integrity checks, including hashed schema 1.0 after changing current version. Ordinary old data remains readable; unsupported legacy symmetry expansion requires explicit external upgrade.

Shared dependency traps: report semantic-reference walker lives in import grouping; grid_sampling text output imports XYZ exporter; orbital_browser imports wavefunction evaluation; Structure View imports periodic bond-inference helper; project_service imports Blender project_link. Extract only needed pure helpers. Static element data stays single source.

Budget audit: qualification-08 contains 209 members, each matching current source or pinned wheels; no cache/extra source. ZIP 30,109,401 bytes; member unpacked 32,564,548; code 3,169,792 (+451,414), resources 2,506,004 and wheels 26,888,752 unchanged. Baselines updated to these measured values; all unexplained-growth allowances remain zero.

## 2026-09-08 本地处理模块调整

用户要求保留Blender分子编辑和高频交互，并通过单一本地exe异步重计算。旧计划“去掉所有编辑/配置入口及立即去wheel”已被替代。新增接口/operation、100ms/1s/2s性能和RDKit等价要求见完整方案，不视为已实现。

只读审计确认：当前未提交manifest删了wheels，stage_viewer也过滤wheels/.whl；延迟移除需要两者一致。chem_utils/mesh/_math/旧panel的整文件删除包含纯Mesh选择/测量等路径，必须按功能恢复，不因科学算法外置而删除。Worker协议当前仍在prepare/core/worker_protocol.py；后续移至共享边界再接统一控制器。现Python -m入口和隐藏/普通Tk测试不能代替真实exe/Blender前台性能证据。

当前CBQ面板全包验证/复制为同步路径，存在大包响应风险，需测量/有界处理；不能仅凭源码把它认定为已违反计算按钮的具体100ms门槛。候选无wheel安装/基础生命周期成功仅证明其覆盖范围，不能替代RDKit等价或纯Mesh编辑验收。

当前完整回归失败来源之一是setUp中的patch.dict(sys.modules)只在tearDown停止；导入已迁移模块失败时tearDown不执行，fake bpy污染后续CLI/benchmark导入检查。已用addCleanup保证异常setup仍清理。另一个实测迁移遗漏是整组ChemBlender/legacy被删除：分子提取不依赖旧注册，晶体CIF数据需要历史CIF_Atom/CIF_Structure RNA字段注册才可读取；直接obj.get无法取得这部分数据。外部legacy/cif_schema.py保存原字段和默认值，私有进程临时注册后复验三类fixture通过。MCP连接仍失败、blender-mcp --help的uv trampoline路径失败；Get-Process确认PID45116和Blender5.1精确路径；原生私有profile查询确认5.1.1/Python3.13.9，未操作已有进程。


迁移回归收口：修复 legacy/migration._cell 只检查最小角度导致 gamma=200 度被接受的问题；逐角覆盖 -1/0/180/200/NaN/Inf，拒绝时原项目不变。Project Browser 69项契约迁到实际 ProjectUIState、Mesh 编辑注册根和 biological 模块；保留 draw 延迟RNA写入、失效刷新及陈旧模块别名隔离。新增真实CBQ写入/预览/面板操作/事务导入，验证浏览器revision、自动选择和坐标；未恢复插件内 spglib 求值。浏览器69+迁移核心27共96项Passed。完整回归仍未通过，C2稳定提交、统一CLI及异步处理闭环仍待完成。


Reader外部边界回归：替换已移出的Blender全局handle测试，使用实际外部ReaderPluginDiscovery/registry，保留内置ID保护、重复ID故障隔离、manifest注销、注册表独立性及公开模型identity；真实preflight/commit事务测试继续保留来源/revision验证。冷Python阻断bpy、Viewer与科学依赖导入仍能建立22reader清单。README补外部注册代码并执行验证，旧2.3handle与示例明确标为历史机制，修复worker_client文档链接。Reader/文档/Browser组合202项Passed。第四轮全量2520项90.777秒，23failures/212errors/36skips，仍Failed；migration-full-04.log和-failures.json留证（先前带-t的发现命令因tests非普通package退出，已改-s执行）。全量发现cbq_import在无bpy时提前导入导致2项Browser测试错误，setUp/tearDown加入实际模块隔离；先无bpy导入再运行这2项的复现顺序验证Passed。其余主要旧import_preview/extxyz/quick_import/legacy routing/wavefunction UI契约，schema快照、生成文档和旧View迁移仍待处理。C2稳定提交尚未形成，不接入新控制器，不移除正式RDKit wheel。


CBQ 1.1与格式文档收口：Reader冻结快照差异已逐项核实，除已批准PeriodicSiteData数值旋转/平移两项可选ArrayData外，均为移动后的模块类型路径与Python3.12/3.13 Path路径差异。保留原快照及SHA不改，归一部署路径后验证旧字段，新增单独锁定两项字段类型/None默认的测试。reader_catalog导出execution_mode改为prepare；文档生成器不再读取已删除ui/export.py，改AST核对外部CLI实际13项--format选项。重生成能力JSON，CIF reader版本2同步；formats文档区分格式成熟度与迁移后尚未完成的UI验收、正式wheel保留与外部解析。28项模型/文档/目录定向测试Passed，generator --check Passed；架构导览同步两项职责。完整回归仍以full04的23failures/212errors为最近证据，未形成C2提交。


Viewer文件入口回归：FileHandler仅.cbq→chemblender.import_cbq，测试移除对已删除Reader handle的依赖并阻断外部parser/rdkit/gemmi导入；区域判断、重复注册、部分失败逆序清理、外来注册保留与缺API均保留，11项Passed。POSCAR显示的4项契约从旧导入面板setUp中分离，验证selective_dynamics三个轴标记及节点组/marker/主对象失败清理，4项Passed。原POSCAR导入侧8项仍需迁外部流程，未跳过或删除；其setUp增加addCleanup避免初始化失败泄漏fake bpy。架构导览同步FileHandler实际入口。完整回归仍未通过、C2稳定提交仍待完成。


VASP 4转换真实缺陷已修复：缺少species时旧CLI发布只有诊断无结构的CBQ并返回success，新增测试先复现失败，再于CLI/GUI共用_reader_batch拒绝无有效结构的POSCAR；缺元素提示--param species，保留解析层诊断用途。真实fixture经GUI参数转换Na,Cl，再用--project追加K,Br，验证两个结构并存、原UUID/revision和原包全部字节不变；错误组数不发布结果且原包不变。CLI22项21Passed/1可选IOData-GBasis Skip。docs/prepare补实际元素顺序与GUI操作。仍有旧POSCAR导入面板8项及其他迁移回归待处理，完整状态以full04 Failed为准。


POSCAR旧产品流8项已迁外部CLI/GUI真实入口，保留4项Prepared View测试。新增inspect的有界comment、scale/cell/体积单位、species/count、坐标模式、Selective Dynamics、速度块与缺元素提示；不截断转换provenance的60000字符原注释。GUI进度读取异常不再关闭存活子进程任务，先取消并等待退出清理。测试先复现缺预览及错误清理，再修复；12项产品流Passed，CLI22项21Passed/1可选backend Skip。原Blender raw-file modal机制不恢复，其相应科学约束、异步参数、取消和清理迁到外部入口；新Blender统一控制器的性能/故障门槛仍未完成。同步架构导览和prepare使用说明。第五轮完整回归已启动，尚未将其判定为通过。


第五轮完整回归2524项/88.531秒：21 failures、190 errors、36 skips，仍Failed，证据migration-full-05.log与-failures.json。POSCAR、FileHandler、生成文档和Reader冻结快照本轮无失败；主要剩余旧import_preview(74)、extxyz(40)、quick_import(26)、legacy routing(24)、wavefunction UI(22)及架构/发布/旧View契约。全量发现prepare环境隔离测试错误地要求整个共享测试进程无bpy；改为冷Python阻断bpy/ChemBlender导入并真实执行formats/inspect，CLI22项21Passed/1Skip重新通过。该修复尚未重跑全量。C2稳定提交仍未形成，统一CLI/Blender控制器/RDKit闭环未接入，正式wheel保留。


外部导出迁移：test_extxyz_workflow中29项原契约迁至ExternalExportSelectionTests，验证真实export_service的FrameSet/属性/拓扑/生物层级绑定、多记录隔离、Conformer metadata-only预览、PDB/MOL2/PQR实际往返及取消保持旧文件、未确认损失不写文件；4项格式选择改验证真实GUI argv与CLI parser。另加三种真实CBQ的CLI预览→未确认失败→确认写出测试，先复现三个格式report.written=False却status=success，再于CLI共用入口拒绝未确认损失，修复GUI相同完成状态。ExtXYZ missing_value_token同步传入CLI预览。外部导出30项+CLI22项共52项，51Passed/1可选backend Skip。该文件仍有11项旧RNA/modal契约待迁移到外部GUI生命周期，未删除/skip；不把同步export_service测试当作异步控制器验收。架构导览及prepare说明同步。最近完整回归仍是full05 Failed，未形成C2提交。


外部GUI生命周期：新增8项真实类故障测试，先复现日志第二次open失败泄漏stdout/Windows文件占用、启动UI失败后已有子进程、Fatal/报告widget异常跳过清理。CliProcess构造用ExitStack，界面初始化和after安排在Popen前；poll终态收集后finally清理，失败保留owner并安排重试，旧timer遇job=None安全返回。复查发现本轮中间实现会在poll返回None之后进程瞬间退出时误删尚未读取的result；添加红绿时序测试，以本次结果/异常的terminal状态决定清理，下一轮读取完成结果后再删除。活动进程Fatal请求取消并保留轮询、cancel Fatal保留owner；已退出Fatal及清理重试保持原异常identity。原ExtXYZ旧modal5项迁到新8项边界验证；该文件尚余6项旧选择/RNA/取消入口契约，未宣布全部迁完。GUI8+POSCAR12+CLI22+外部导出30=72项，71Passed/1可选backend Skip，含实际Tk调用CLI；全量未重跑，最近证据仍full05 Failed。架构导览同步GUI实际职责。


导出交互剩余6项已迁完：外部ConformerSet显式SDF、MolecularRecord保留所选格式，GUI变更清除确认并请求预览、未变更文本事件不清除确认、Viewer注册根无raw export。真实受控Python子进程等待cancel marker，GUI cancel→poll收集cancelled结果→确认exit→清理task且重复cancel/poll不重复清理通过；只证明文件协议与生命周期，不代替科学后端两秒性能门槛。test_extxyz_workflow全36项Passed，旧fake bpy/ExportJob/RNA测试支架删除，GUI6个相关旧契约均有实际外部行为对应。prepare说明明确Conformer格式选择与预览触发。CIF的Browser占据率/disorder/ADP及绑定原envelope导出2项从旧导入setUp分离后Passed，旧setUp添加addCleanup防止失败泄漏bpy；多block预览仍待接外部入口。第六轮完整回归运行中，尚未判定通过。


第六轮全量2528项/92.266秒：20 failures、150 errors、36 skips，仍Failed；migration-full-06.log及-failures.json留证。导出workflow与外部GUI生命周期本轮无失败。该轮载入测试后才完成CIF两项迁移，CIF结果仍是旧3项错误；两项单独Passed不能改写本轮结果。C2稳定提交尚未形成，下一步继续CIF多block预览及旧import_preview/quick_import/legacy routing/wavefunction契约。

2026-09-09 CIF产品流迁移完成：外部inspect复用parse_cif，显示全部/有效block计数、位点、带单位晶胞及诊断；列表各限100，保留总数，前后hash检查拒绝输入变化。实际CLI convert保留两个结构、原CIF envelope及block key/index绑定；删除输入后重开CBQ，坐标/晶胞逐值一致。非结构块只诊断，不虚构位点。原默认block确认契约改为整包保留、导入后选择展示结构；删除旧fake bpy支架。CIF5项Passed，CLI22项21Passed/1可选backend Skip。新增边界测试最初漏计fixture已有2条诊断，改为与解析器完整诊断对照后通过。最近全量仍full06 Failed（20 failures/150 errors/36 skips），C2稳定提交、统一控制器和最终可视化验收仍待完成。

2026-09-09 纯编辑迁移补漏：从HEAD旧scientific_edit按函数恢复本地Mesh数据提取到ui/mesh_edit.structure_edit_arguments，不恢复旧科学模块导入或raw export。保留Structure/Topology revision、局部坐标、atom mapping、精确键级及周期shift；增加Edit Mode拒绝与angstrom/bohr显示单位校验，快照数组独立于后续Mesh改动。原结构派生测试改为实际本地提取→外部preview调用，10项原检查保留。新增复数坐标/晶胞红绿回归，修复_length_values先float转换而丢失虚部的漏洞。结构派生11+Mesh/Structure View共20项Passed；尚未做此补漏的Blender runtime。架构导览同步，Apply面板/共享冻结事务仍未接通。剩余grid UI导入失败是旧resolve_grid_selection科学语义操作已移外部，下一步应以CLI convert的preset/dataset/unit入口迁移契约；wavefunction job测试涉及真实异步安全门槛，不能简单删除。最近全量仍full06 Failed，稳定提交和全部后续门槛未完成。

2026-09-09 Grid UI契约已迁到真实external convert→CBQ读取：保留原始数组/revision、相同源UUID的语义派生身份、单位/小阈值显示、场景preset选择、旧表面重建回滚和modal清理等10项。Cube原reader每次parse生成新UUID，测试不再错误比较不同导入的UUID；同一prepared原始grid重新派生仍验证UUID/revision一致。发现GUI dataset留空与CLI默认0不一致，真实GUI argv红绿测试证明多dataset会误选0；取消CLI默认值，共用转换入口要求多dataset解释显式选择，单dataset仍可省略，不解释时保留完整原始网格。Grid10+CLI23共33项32Passed/1可选backend Skip。未改写full06全量Failed记录，未形成稳定提交，后续完整验收仍待执行。

2026-09-09 拓扑产品契约迁移：保留本地choices/accept/reject/foreign-ID三项；旧5项推断/UI机制改为4项外部契约（其中失败及晚取消合并subtests），真实CLI验证分子两条O-H键、周期shift与来源、同源确定性，受控推断失败/晚取消不发布且原文件不变，GUI清理异常保留job并重试。拓扑7+GUI8共15项Passed。不把晚取消发布保护等同于重计算两秒响应或新的Blender控制器验收，推断循环尚无协作取消。第七轮全量2556项91.016秒：19 failures、144 errors、36 skips，仍Failed；migration-full-07.log及-failures.json为最新证据。CIF/Grid/Structure derivation/Topology UI在本轮无失败，三项模块导入失败已消除。剩余import_preview74、quick_import26、legacy routing24、wavefunction22、docs8、legacy Blender3、release metadata3及performance/prerelease/repository各1。仍未形成C2稳定提交，下一步优先外部预览/导入功能与旧契约逐项对应，不能删除异步安全要求来制造通过。

2026-09-09 MOL2外部预览接通：从HEAD旧import_preview提取纯_mol2_summary至external formats/mol2.mol2_preview_summary，CLI inspect显示分子/原子数、明确命名interpreted_bond_count、拓扑数量、电荷类型/覆盖率、unsupported sections及有界诊断；前后hash和SourceRevision hash一致检查。旧四项MOL2预览/绘制契约迁至ExternalMol2PreviewTests四项：真实CLI small/unknown bond/mixed charge与实际GUI CliProcess子进程返回摘要。保留部分电荷只绑定对应结构，不把未知键虚构为拓扑。相同JSON字段由GUI报告呈现，未声称新增窗口截图验收。MOL2外部4+reader24+CLI23共51项50Passed/1可选backend Skip。旧ImportPreview其余70项仍待迁移；最近完整证据仍full07 Failed（19 failures/144 errors/36 skips）。架构导览和prepare说明同步，C2稳定提交及后续完整方案仍未完成。

2026-09-09 extXYZ外部预览：原ui/extxyz_preview整体迁至chemblender_prepare/extxyz_preview，benchmark更新同源import；CLI inspect复用preflight_reader_plugins/StagedImportSession，不通过完整parse加载数组，核验预览与源hash并finally discard。旧两帧属性/cell/PBC变化/假定单位测试改跑真实CLI；新增摘要失败实际staging清理测试。extXYZ2+benchmark1+CLI23共26项25Passed/1可选backend Skip。旧blender_smoke中依赖整个旧raw import UI的流程尚待整体迁移，不以本项宣称运行通过。ImportPreview旧剩余69项，最新全量仍full07 Failed；未形成稳定提交，后续统一控制器和完整方案未完成。架构导览及prepare说明同步。

2026-09-09 发布契约迁移：审查正式manifest差异仅文件权限描述与取消网络权限，RDKit/Gemmi wheels列表保持不变；更新两处manifest哈希锁和无network契约。两个build测试使用真实 sibling cbq_core fixture及真实stage_viewer，验证共享核心字节一致、--output-dir、精确产物名称、缺产物失败及源manifest不变。release_metadata/prerelease_probe/repository_contract/viewer_staging共63项，62 Passed/1平台相关Skip，diff --check Passed。未运行新的完整回归或Blender runtime，最近完整证据仍full07 Failed（19 failures/144 errors/36 skips）；文档链接/源码目录契约、旧导入UI/worker安全契约仍待迁移，C2尚未形成稳定提交。

2026-09-09 文档契约迁移：按真实cli._reader_batch/_convert/_publish调用链重写docs/development/import-pipeline.md，区分CLI worker转换与外部Python预览确认事务，去掉已移除Blender Quick Import/Reader bootstrap作为当前入口的说明；source-revisions更新共享模型、外部编辑和CBQ冲突规则，明确Apply闭环仍待接通。历史2.3 public-core-api保留旧接口并标注历史，源码链接固定到经git cat-file验证的迁移前54ecf4c；修复历史2.4验收测试误改为prepare命名空间的问题，不改历史结果。formats明确开发分支不同于released2.4.0，外部导出和生命周期未完成边界保留。文档38项现在37 Passed/1 Failed（code_architecture_guide源码清单尚待迁移），migration-docs-02.log及-failures.json留证；生成文档与三项格式/历史契约共15 Passed，diff --check Passed。本轮未运行全量或Blender runtime，全量最新仍full07 Failed，C2稳定提交和完整后续验收未完成。

2026-09-09 架构清单迁移完成：226个Python源码路径与ChemBlender/cbq_core/chemblender_prepare三根精确一致；移除20个无直接目标的旧入口行，补齐14个新文件，更新ProjectUIState及6处拆分后入口职责和数据流，明确Mesh Apply/统一controller/RDKit闭环未完成。文档38项Passed；第八轮全量2557项，8 failures、137 errors、36 skips，仍Failed；migration-full-08.log与-failures.json为最新证据。剩余legacy migration Blender3、legacy routing24、performance1、quick import26、wavefunction22、import preview69；文档/发布契约在全量无失败。diff --check Passed。未形成C2稳定提交，不把源码清单覆盖等同于功能等价。下一步仍按旧功能对应真实外部或本地入口迁移并保留安全验收；performance失败为旧运行时探针三版本均须字符串，但当前Blender探针可返回None，需分清缺依赖与产品失败。用户更新目标要求及时同步文档/目标，完整目标保持active。

2026-09-09 性能探针修复：旧单测把普通外部Python必须找到Blender当作前提；实测当前_blender_executable为None，版本全null是未知环境，不是已验证Blender损坏。同时红绿测试复现探针串联import导致任一科学包缺失就丢全部版本，改为独立捕获ImportError/OSError并保留Blender/其它可用版本；不引入新包。版本报告测试使用明确输入检查传递，另验证无可执行文件不启动进程。performance_budget共10 Passed，包括未完整版本仍拒绝正式qualification的原测试。架构导览/规划同步，diff --check Passed。本轮未运行真实Blender或完整回归，最新全量仍full08 Failed（2557项8 failures/137 errors/36 skips），C2未稳定提交，UI/异步/恢复迁移和全部后续目标仍未完成。

2026-09-09 轨道选择迁移：两项纯选择测试从旧WavefunctionJob夹具拆为PreparedOrbitalSelectionTests，保留源UUID、spin、orbital选择以及列表重排稳定性；去掉现Viewer不存在的nuclear_charge/density_level控件断言，但这些计算参数随source切换清空/复验的要求继续属于外部控制器待验收，未宣称完成。新增红绿回归发现显式源UUID缺失/非法会静默选第一套轨道，修复_selected_orbitals为明确不可用，面板显示诊断并提供重新选择；仅未指定来源时初始默认。选择3+orbital_browser6共9 Passed；旧9项任务安全测试仍待迁移，tearDown改finally保证即使旧clear入口缺失也清理session，不隐去原失败。架构/规划同步，diff --check Passed；未跑本修改Blender runtime或新全量，最新仍full08 Failed，C2和完整方案未完成。

2026-09-09 外部PubChem迁移补漏：从HEAD旧legacy/reader_bridge保留纯请求/取数/来源复验实现至chemblender_prepare/pubchem_import.py，引用统一外部ImportRequest和共享model/session；旧9项来源/hash/metadata篡改、同步与延迟materialization复验、CBQ保存重开测试全部改用外部模块并通过。默认requests替换为stdlib urllib，30秒超时、64MiB有界响应；新增默认fetch响应关闭/超限测试通过，不新增依赖，不恢复Viewer网络权限。此为外部Python入口，CLI/GUI、真实PubChem和协作取消尚未完成。PubChem10+文档38共48 Passed，架构清单227文件，diff --check Passed。其它legacy operator路由、QuickImport/ImportPreview和wavefunction任务安全仍待迁移；最新全量仍full08 Failed，本轮无新Blender runtime/全量，未形成C2稳定提交。

2026-09-09 PubChem取消与暂存清理：新增is_cancelled检查，覆盖取数前、两次HTTP之间、下载后、SDF写入后和返回前；取消抛出既有CancelledError，不返回可提交请求。统一写入/请求构造异常清理，仅删除本次成功创建的文件，保留同名旧文件；清理失败以exception note附加，不掩盖原始异常。红绿复现metadata半文件泄漏并修复；13项PubChem测试Passed，含部分SDF写入、metadata失败、同名冲突及清理失败。阻塞HTTP两秒取消、真实网络和CLI/GUI接通仍未完成。未运行新全量/Blender；最新全量仍full08 Failed，C2稳定提交及完整目标未完成。

2026-09-09 外部导入选择迁移与full09：两项旧QuickImport多文件/未知扩展名测试迁至ExternalImportSelectionTests，实际运行GUI参数生成→CLI worker→CBQ，不再只mock旧Blender入口；删除原始输入后校验CBQ仍可读取。红绿复现GUI忽略validation-mode而固定balanced，新增readonly三模式选择、默认balanced、无效值启动前拒绝，实际worker逐文件接收maximum；Tk控件及真实子进程通过。目标组26项25 Passed/1 skipped（缺IOData/GBasis），旧预览确认/会话不变安全要求仍在未完成迁移范围。第九轮全量2565项89.714秒，7 failures/124 errors/36 skips，Failed；migration-full-09.log及-failures.json留证。分组：import_preview69、quick_import24、wavefunction19、legacy_routing15、legacy_migration_blender3、benchmark_harness1。最后一项为旧字符串检索将子进程bpy代码误认主进程import，改为实际屏蔽bpy加载后运行harness，benchmark/performance/docs59 Passed；未因此重算full09或声明全量通过。架构与准备工具说明同步，完整目标active、C2尚未稳定提交，统一控制器/RDKit闭环及最终科学可视化验收继续待完成。

2026-09-09 默认物理量展示迁移：旧两项default view测试从已删除import-preview夹具拆到PreparedDefaultViewTests，使用真实外部preflight产物，保留斜Cube、signed角色、结构fallback、坐标单位限制、冻结plan等断言。发现科学面板AUTO固定grid_volume且旧planner漏difference_density；新增共享UI default_grid_preset，按cbq_core语义表default_surface_mode而非单看signed（generic_scalar虽signed但默认仍volume）及COMPLETE状态选择，两处UI复用。所有语义preset、显式选项、ambiguous回退回归及grid_semantics共17 Passed。不读取科学数组、不自动建几何、不改存储。RDG保留NCI选择。真实Blender渲染未运行；最新完整回归仍full09 Failed（2565项7 failures/124 errors/36 skips），未算术改写统计，C2稳定提交与完整目标仍未完成。

2026-09-09 原生Mesh编辑修复：MCP连接失败且blender-mcp仍报uv trampoline错误，确认已有Blender进程45116不操作其场景，另用私有profile原生后台5.1.1/Python3.13.9实测。新增tests/blender_mesh_edit.py红绿复现Set Bonds创建缺失custom-data层后BMEdge引用失效；Set Atoms同路径同步修复为创建层后重新遍历选中元素，保持borrowed BMesh所有权。原生测试通过键级/精确键级、清芳香标记、元素选择、原子替换、90度测量和operator注册注销；guard拒绝rdkit/gemmi/chemblender_prepare导入。加入test_mesh_edit常规subprocess测试，2 Passed。曾误指定不存在test_scientific_edit_ui导致命令失败，已定位实际freeze测试为test_structure_derivation，不把该错误算产品故障。证据.blend-analysis/mesh-edit-native-01/red.log和native.log。未做整个Extension新安装或完整回归，Apply入库/外部优化、截图SOP及其余完整目标未完成；最新全量仍full09 Failed。

2026-09-09 旧调用清单验收迁移：LegacyCallerInventoryTests两项从要求已删除crys_utils/panel的旧按钮存在，改为当前注册清单与Viewer源码AST检查，确认旧直接晶体写入class/operator无入口，同时CBQ导入和纯Mesh编辑仍注册。原始read_MOL/read_Cryst/read_cif/read_poscar及block helper调用清单保持精确空集；移除旧scientific_edit._write_xyz唯一例外，因为该入口已迁出Viewer。2 Passed，不通过恢复旧直写逻辑解决测试。此为入口边界验证，不证明scientific Apply、外部优化或旧View恢复完成；这些运行门槛继续保留。没有改产品代码、安装依赖、执行新全量或Blender，最新全量仍full09 Failed，C2及完整目标active。


2026-09-09 外部inline SMILES闭环：CLI convert新增--smiles-text，复用既有外部preflight、ImportSource.smiles_text和暂存校验，保留inline:smiles/text hash、angstrom和MolecularRecord；明确smiles.planar_2d_generated，未声称3D/优化。GUI增加files/smiles选择与文本字段，文本模式不传隐藏文件参数；实际Tk→CLI子进程→CBQ通过。三项旧Blender SMILES入口验收迁为真实外部身份/校验/GUI流程，保留其输入安全要求。29项28 Passed/1 skipped（IOData/GBasis缺失）；文档60 Passed，diff --check Passed。README及架构职责同步。未执行新全量或Blender，最新全量仍full09 Failed，C2稳定提交、统一controller和RDKit等价门槛未完成。


2026-09-09 外部发布故障注入：新增真实CLI转换测试，先生成原CBQ，再分别在reader成功后取消、save_project成功后取消、已保存数组篡改后验证失败。核验注入确实发生，取消/错误状态正确、新目标与发布暂存均不存在、任务目录已清理、原CBQ所有文件逐字节不变且validate通过。首次测试包装器误读参数索引导致测试失败，修正后通过，不记为产品缺陷。test_prepare_cli共27项26 Passed/1 skipped（IOData/GBasis）。本轮仅补外部发布证据，没有以此删除旧Blender场景取消/事务要求；场景侧及预览交互迁移继续未完成。最新全量仍full09 Failed，未新跑全量或Blender，完整目标及C2稳定提交仍active。


2026-09-09 CBQ提交后UI误报修复：在真实共享import_package事务上注入浏览器刷新RuntimeError，复现数据已入库但operator返回CANCELLED。CHEMBLENDER_OT_import_cbq增加明确提交边界，成功入库立即清除旧preview和重复来源确认，后续UI错误报告已导入/需刷新并返回FINISHED，提交前错误仍CANCELLED。测试使用假bpy承载真实operator与真实CBQ读写/事务，确认旧/新结构均保留；不是原生Blender运行证据。CBQ UI+package import共13 Passed；同步准备工具错误恢复说明。不删除旧场景事务/取消门槛，完整全量仍full09 Failed，C2提交及后续目标未完成。


2026-09-09 外部预览事务验收迁移：将旧ImportPreviewUIContractTests的changed_conformer_suggestion和missing_batch两项改为ExternalPreviewTransactionTests，直接真实preflight SDF/XYZ→外部commit_import_preview，不依赖已删除面板或补兼容层。保留原诊断要求，并强化断言：过期构象证据不调用publication，项目对象/科学实体/目录不变；缺批次不产生CBQ。既有实现已满足，无产品补丁。相关project_transaction/SDF构象/新外部事务共43 Passed；尚未覆盖新GUI分组审阅控件，原其它UI要求继续待迁移。未新跑全量/Blender，最新full09仍Failed，C2稳定提交及完整目标未完成。


2026-09-09 第十轮完整回归：2569项/93.344秒，6 failures、116 errors、36 skips，Failed；migration-full-10.log、-failures.json、-summary.json留证。分组：旧import_preview64、quick_import22、wavefunction_ui19、legacy_operator13、legacy_blender3、新prepare_cli1。真实Tk子进程暴露Windows progress.json替换PermissionError，造成SMILES转换失败；CLI两个进度写入点统一_write_progress，按既有Worker策略仅对非权威进度PermissionError留待下次更新，前后检查取消，权威result/CBQ写入不吞异常。故障注入验证XYZ/SMILES遇锁仍成功、同时取消则不发布；test_prepare_cli28项27 Passed/1 skipped。未重算完整回归为Passed。blender-mcp trampoline失败/MCP9876不可达，私有后台实测5.1.1/Python3.13.9及extension repos；原用户进程45116未动。C2稳定提交及完整目标仍未完成。


2026-09-09 外部ESP端到端契约补验：新增test_prepare_cli真实CLI→Worker→新CBQ检查，四输入顺序Structure/Basis/OrbitalSet/effective charge，缺charge或density_level在求值前失败不发布；给定0.5有效电荷而原子序数1，求值边界保留0.5，分块调用多次；RDM、ESP及两条provenance同时入库，原CBQ逐文件不变。ESP数值函数为测试替身，不记真实后端数值通过。首次替身误将NumPy电荷当AtomicProperty，修正后该用例Passed。旧WavefunctionJob场景冻结/取消/发布等测试仍保留待统一控制器接入，不拿外部测试代替场景行为。README补充ESP CLI输入和原包保留说明。未新跑全量或Blender，最新full10仍Failed（2569项6 failures/116 errors/36 skips），C2及完整目标未完成。


2026-09-09 真实波函数迁移数值验收：复用现有gbasis-py312，不安装或改依赖。Python3.12.13/NumPy1.26.4/qc-iodata1.0.1/qc-gbasis0.1.0/SciPy1.16.3。test_wavefunction_grid与observables共20项全部Passed、0 skips、9.14秒，包含水FCHK MO/密度积分既有离散网格基准、pure基组约定、CH3自旋密度和真实ESP；日志real-wavefunction-migration-01.log。注意MO积分1.00457与电子数10.0097为既有有限网格回归值，不标为精确归一/域收敛验收。扩大原CLI真实FCHK用例至MO+ESP：输入四实体/显式scf，真实GBasis求值→Worker→CBQ重开，ESP(3,2,1)bohr约0.0297531414634，保留结构绑定且RDM同包，1项Passed/0 skips/0.836秒。此轮未用数值替身，原GUI模拟用例与真实科学证据分开。首次版本探测gbasis.__version__不存在，改importlib.metadata，未误报环境不可用。Blender新面板/渲染/缓存重开未运行，最新全量仍full10 Failed；C2稳定提交及完整目标未完成。


2026-09-09 本地Apply共享依赖纠偏：核查现有structure_edit仅标准库/NumPy及cbq_core模型，返回新UUID/revision Structure、USER_EDITED Topology和parent provenance，不做RDKit或重计算。为落实用户明确的Blender显式Mesh→CBQ Apply，将唯一实现从chemblender_prepare/core/edits/structure.py移动至cbq_core/structure_edit.py，更新唯一测试调用和架构导览，不复制/新建facade。初次文档检查发现source-revisions旧相对链接，已修复；共享核心冷导入/科学编辑/文档共52 Passed。算法及EDIT_VERSION保持不变。下一步必须接mesh_edit面板Apply并复用事务发布/旧View保留，不把本轮模块移动当成Apply已完成；统一控制器尚不接入。未跑新全量/Blender，最新full10 Failed，C2稳定提交及完整目标未完成。

2026-09-09：package_import 原有候选项目持久化后切换逻辑提取为 commit_session_batch，整包导入和本地 Apply 共用；不另存临时整包或复制模型。Apply 后创建 View 失败属于已提交数据的显示恢复问题，返回 FINISHED 并给 warning；提交前失败返回 CANCELLED。

2026-09-09：Apply必须通过标准structure_publication preset创建新View，直接create_structure_view缺少scene preset重建绑定。隔离安装发现新迁入structure_edit仍绝对import cbq_core，源码环境掩盖了vendoring失败；改包内相对import，并在stage_viewer审计中拒绝共享core绝对自引用。完整core源码仍原样复制/hash校验。

2026-09-09：旧QuickImport的Scene属性所有权要求仍适用当前CBQ，不能因旧属性取消而丢弃；三项测试已改用真实cbq_import.register/unregister。旧fatal-cleanup契约移至PrepareWindow后复现MemoryError被普通ValueError掩盖（MemoryError属于Exception）；修复start/poll优先级，失败清理保留job且安排轮询重试，不丢任务所有权。

2026-09-09：CliProcess已有ExitStack可在Popen启动失败时关闭两个日志并删除临时目录，无需产品代码补丁。旧Blender线程启动、立即持有staging与GeneratorExit传播要求分别由外部启动失败四异常用例及既有GUI fatal-result用例覆盖。旧面板保留CHEM_PT_Build的断言不符合新边界，替换为实际draw调用生成CBQ Preview/Import/Export及本地Edit/Apply按钮，并检查注册清单排除旧入口。

2026-09-09：原legacy runtime验收包含备份集合重挂、自动旧材质/节点恢复等旧UI职责；外部export仅记录display settings，不应把导出成功视为显示恢复完成。保留旧失败测试，新增external-only路径证明读取和导出不改原场景；真实对象快照比仅源文件hash更强。


2026-09-09：外部GUI CliProcess增加首次取消单调时钟，两秒仍运行时仅terminate持有的Popen一次，重复取消不延后；保留所有权直到实际退出，有最终结果则读取，无结果强制退出明确诊断不伪造cancelled/success。GUI生命周期13 Passed/2.065秒，包含真实不响应Python子进程与另一独立进程持续存活检查；之前GUI+CLI41项40 Passed/1 skipped。外部后端可能再启动子进程，此处不声明进程树取消门槛通过，也不声明强制退出时输出发布状态已确定。架构导览同步，未新跑全量/Blender，最新full11仍Failed，C2未提交。


2026-09-09：旧QuickImport四项文件选择/属性/路径测试迁到ExternalImportSelectionTests，现5 Passed：GUI选择替换/取消保留、多路径与默认balanced参数、目录/缺失文件在有效首文件之后仍不发布；已有maximum实际worker传递继续覆盖。新路径协议直接接收完整路径，原basename拼接限制不再适用，未恢复旧入口。第十二轮完整回归2571项、3 failures/107 errors/36 skips、100.079秒，Failed；日志migration-full-12。失败仍集中旧preview/quick UI、wavefunction任务与legacy路由/恢复，C2未提交，后续统一控制器和完整交付未完成。


2026-09-09：外部inspect接通MOL/SDF真实preflight暂存与既有conformer grouping，输出有界记录/版本/属性列/诊断/候选及atom mapping证据、对称歧义复核标志；默认keep_independent，不写CBQ。真实GUI所用CliProcess子进程records.sdf通过；注入分组取消和分析中源变化均拒绝结果并清理暂存。CLI+GUI生命周期+外部预览事务46项45 Passed/1 skipped（可选环境），9.090秒。旧显式接受构象分组测试尚保留，未把候选检查当合并入口完成；无新全量/Blender，最新full12仍Failed，C2未提交。导览与local-processor操作说明同步。


2026-09-09：显式构象接受CLI草稿加入--conformer-group UUID=SNAPSHOT及单独--review-conformer，复用accept_conformer_group和事务fragment，拒绝未复核/过期/未知候选及被截断映射。但新增端到端test_explicit_conformer_acceptance_reopens_and_rejects_stale_or_unreviewed仍Failed：成功分支无法匹配新解析的候选，未发布CBQ。已确认worker任务路径及preflight每次uuid4 source_revision_id使候选跨任务不稳定；统一到preflight、固定ImportSource.id两次尝试均不足。草稿未完成，不能宣称显式合并可用。下一步应让复核绑定持久化的准备CBQ/任务快照，而不是放松快照校验或继续猜测身份字段。当前CLI草稿和失败回归保留待修；GUI尚未接接受入口。最新全量仍full12 Failed，C2未提交。


2026-09-09：显式构象分组改为convert生成CBQ→inspect该包→derive molecule.group_conformers@1。移除上一轮不稳定的raw convert flags、临时preflight绕路和固定ImportSource.id尝试；新增薄Worker适配复用原算法、v1校验/发布，仅追加ConformerSet/属性列/provenance。core project_conformer_batch提供持久化实体输入，CLI raw/CBQ共用有界证据显示。真实SDF转换后移走原文件、重复inspect候选一致、接受后CBQ完整重开/原记录结构保留、原包所有字节不变通过；未复核/未知候选/过期snapshot/字符串复核均拒绝。CLI+GUI生命周期+外部预览事务47项46 Passed/1 skipped，9.988秒；专用GUI复核控件与取消/故障更完整门槛待补，现可使用通用derive参数。导览/SOP说明更新；没有用该专项关闭旧构象UI测试或全部迁移门槛。最新全量full12仍Failed，C2未提交。


2026-09-09：加强持久化CBQ构象分组端到端用例，实际校验两帧angstrom坐标（绝对误差1e-12）、原子映射、Energy/Flag属性列与记录顺序；加入缺失记录输入和accept计算期间cancel marker，均不发布新包，随后成功重开且原包字节不变。初次测试误用不存在的original_name，按模型实际semantic_role修正，1测试/1.149秒Passed。测试数据属性无单位声明，未赋予Energy物理能量单位。无产品实现变化，不扩展结论到非恒等映射/单位混合、真实GUI复核或完整生命周期；未重跑全量，full12仍Failed，C2未提交。


2026-09-09：外部GUI新增CBQ构象候选复核窗口，校验可编辑报告的必要字段，选择/查看映射、歧义明确复核后填入derive；切换候选清除复核，清空旧输出，不自动运行。真实Tk→CLI→新CBQ测试Passed，覆盖无默认选择、畸形报告、未复核拒绝、切换复核失效、显式运行与旧包字节不变。CLI/GUI生命周期/外部预览事务48项47 Passed/1 skipped，11.011秒；更新操作说明和架构导览。未重跑完整回归/Blender，最新full12仍Failed，C2未形成稳定提交。根据实际失败优先收敛迁移回归，完整交付目标与RDKit删除门槛不降低。


2026-09-09：旧ImportPreview五项构象投影契约迁到tests/test_prepare_cli.py：缓存/缺缓存不在UI计算→test_tk_conformer_review_requires_selection_and_runs_explicitly与test_conformer_projection_bounds_and_tk_rejects_hidden_mapping；有界记录/隐藏复核/原子映射→后者101候选、101记录、1000原子映射及真实Tk拒绝路径。新显示上限100取代旧20条/160字符，完整计数及truncated保留，隐藏第101条歧义仍使requires_review为真。两项专项Passed/1.180秒；修复测试Tk销毁前待处理ThemeChanged事件告警。删除仅对应五项旧入口测试，其他旧分组/提交/生命周期验收仍保留。full13已启动，结果待完成。


2026-09-09：第十三轮完整回归2571项、3 failures/102 errors/36 skips、103.062秒，Failed；migration-full-13日志/summary/failures已保存。与full12失败标识比较无新增失败，减少五项为有替代验收的旧构象投影测试迁移。剩余分组：import_preview59、wavefunction19、legacy_operator13、quick_import11、legacy_migration3。C2仍未提交，完整方案目标不变，优先继续旧导入交互与任务/legacy迁移。git diff --check Passed（既有换行提示）。


2026-09-09：补齐CBQ import真实发布故障回归：写入、暂存验证、最终验证分别失败后，活动project身份/dirty/path不变、原包全部字节及lazy数组可读性保持；失败候选由inspect_publication_orphans识别，不是活动包；随后重试成功，结构追加并完整重开。旧project close失败仅返回cleanup warning，新发布数据保持。CBQ包导入/Viewer UI/底层publication共34 Passed/1.369秒。核查发现当前提交沿当前sidecar原子替换，与旧UI临时generation旋转不同，底层刻意保留失败候选用于恢复；因此没有删除旧旋转/外部saved sidecar保护/cleanup测试，仍须确认迁移后的生命周期覆盖。未修改产品实现、未重跑全量，最新full13仍3 failures/102 errors/36 skips，C2未提交。


2026-09-09：真实all-failed SDF复现CLI错误返回success并发布无科学实体CBQ。恢复旧import_preview的ERROR/INVALID诊断阻断与严格isolated SDF例外到CLI reader转换门禁；inspect仍可报告损坏内容。新test_sdf_record_recovery_is_visible_and_all_failed_input_is_rejected验证malformed-middle有效索引0/2与诊断重开、全失败不发布、错误关联有效记录/插件完整性错误注入拒绝；对应旧UI测试已迁移移除。CLI/GUI48项47 Passed/1 skipped，11.422秒；增强注入后单项Passed/0.573秒。说明文档同步，未重跑全量，最新full13仍Failed，C2未提交。


2026-09-09：旧操作路由验收迁移：新增外部GUI command_arguments→CLI真实CIF/POSCAR/CONTCAR/SDF/MOL2五格式转换与CBQ重开，验证strict参数、源路径及源字节保持；与LegacyCallerInventoryTests两项注册/AST检查共3 Passed/1.260秒。原文件转发两测试及已移除晶体直接写入/旧面板两测试，由该真实转换和已有六类旧writer不可达检查替代，未恢复旧入口。legacy路由模块实跑21测试、0 failures/8 errors，仍Failed（errors含SMILES预设subtests），证据legacy-routing-migration-01.log；剩余SMILES预设、PubChem主入口和旧导出/编辑桥接等待迁移。纯Mesh编辑本轮源码检查保留，未新跑Blender。不以专项推算全量，full13仍最新Failed，C2未提交。


2026-09-09：外部GUI恢复历史SMILES预设选择，复用cbq_core.element_data.preset_smiles，选择仅填文本、可编辑、不启动进程；空选择保留手写文本。实际Tk选择Glc/G/PE三类代表→同CLI参数→CBQ结构/拓扑/来源重开通过，窗口请求高度≤850。旧legacy_smiles_presets测试已迁移，catalog原始字符串未改；历史库立体化学/端基和部分命名未科学校准，界面按key呈现并提示核对，不声称3D/优化或整库化学等价。CLI/GUI生命周期50项49 Passed/1 skipped、12.565秒；导览与操作说明更新。全量未重跑，full13仍最新Failed，C2未提交。


2026-09-09：PubChem 接入外部 convert --pubchem 与 GUI 输入类型，复用 owned download/preflight/verified provenance，来源 revision locator 改为 URL。网络失败、取消、源内容篡改专项拒绝发布并清理 SDF；CLI/GUI 共51项50 Passed/1 skipped，12.929秒。真实 CID962 下载成功，verify_arrays 重开确认 O/H/H、两键、angstrom、二维诊断及来源hash，证据 pubchem-live-01.json。未移除旧modal/host安全测试，未将GUI参数测试视作真实在线点击验收。全量未重跑，full13仍Failed，C2未形成稳定提交。


2026-09-09：复现并修复共享commit_session_batch提前覆盖已保存sidecar的问题：导入/纯Mesh Apply统一发布到会话temporary_root/project.cbq，显式保存前保持旧保存包。新增真实CBQ重开→失败注入→成功导入测试，先Failed再修复，验证旧包全部字节、dirty/session、移走输入后的自有数组重开；导入/Viewer/publication共35 Passed/1.389秒。沿用底层原子发布和失败候选恢复，不宣称旧generation轮换/Blender完整生命周期门槛已关闭。full14正在运行。


2026-09-09：full14完成2572项、4 failures/93 errors/36 skips、108.469秒，Failed，日志/summary/failures已保存。新增失败为PubChem mock未命中：旧LegacyReaderBridgeTests清除sys.modules却留下package属性旧模块，外部模块已无bpy状态，移除不必要的pop以保持模块身份。LegacyReaderBridge全组+PubChem转换14 Passed/0.417秒，未重跑全量；不把修复后专项结果改写为full14通过。C2仍未提交，接下来继续导入生命周期/旧任务迁移。


2026-09-09：补强CBQ Viewer生命周期回归：saved scene→reviewed import→旧包字节不变→删除输入→显式保存→close_session清理临时包→新session仅从保存包重开，结构与数组保留。原import_preview的external_saved_sidecar/close_session两项由该链及package_import保存保护测试替代，已移除对应旧入口测试。另复现preview_json为list/null/scalar导致AttributeError，缺counts/hash等被错误接受；_preview_document现在校验报告对象、SHA256、非负整数计数和文本列表，损坏报告要求重新预览。九类损坏输入先6 failures/3 errors再修复。CBQ导入/Viewer/session/UI session共69 Passed/1.492秒。未重跑全量和Blender安装版；full14仍最新Failed，C2未提交。


2026-09-09：核查旧revision/target提示契约，尚无完整新入口替代，未删除这些测试。确认open_project默认verify_arrays=True，无需重复改实现。复现普通XYZ convert静默忽略--entity并返回success，增加入口检查仅critic2接受该绑定参数；新增测试先Failed再通过。CLI/GUI52项51 Passed/1 skipped、13.107秒。文档说明--project仅追加而非自动结构绑定。全量未重跑，最新full14仍Failed，C2稳定提交及后续统一入口目标保留。


2026-09-09：Worker Protocol v1从chemblender_prepare/core迁至cbq_core/worker_protocol.py，文件字节未改SHA256=46ea1eca7ad68c1a40b5add0a7f89af08f94e0048624e4f2f03d988e7044d699，17个调用文件同步（含CLI/GUI/worker/client及测试patch路径）。协议/波函数worker/CLI/GUI74项73 Passed/1 skipped、15.344秒。新增真实共享core staging测试检查协议复制字节与hash，并以Python -I -S加载vendored协议，未导入prepare/bpy/RDKit/Gemmi/NumPy；staging两项Passed/0.543秒。测试初稿cancelled缺WorkerError被既有校验拒绝，改为合法success样例；协议行为未修改。架构导览同步。此项为C2共享模块迁移，不代表capabilities/doctor/统一workerCLI或Blender控制器已接通；完整回归待重跑，C2尚未稳定提交。


2026-09-09：full15完整回归2572项、3 failures/91 errors/36 skips、105.328秒，Failed；共享Worker协议迁移后无新增失败标识。剩余旧任务/导入/legacy恢复未关闭。补强外部ESP derive专项：真实runner/CBQ链，mock数值后端，返回成功后取消、伪造request_id、后端OSError均不发布目标且输入包全部字节不变，单项Passed/0.510秒。此增强在full15加载测试之后运行，不算入其覆盖。旧WavefunctionJob的活动revision/快照裁剪/任务所有权测试保留，未以外部故障专项替代。C2尚未稳定提交。


2026-09-09：复现外部start_worker在stderr打开失败及Popen KeyboardInterrupt时泄漏日志句柄，Windows临时目录清理出现WinError32。改为with顺序管理stdout/stderr，Popen成功后父进程句柄即关闭，子进程持有自己的句柄；请求目录保留诊断，不视作成功结果。新增失败注入及真实stdlib子进程写日志验证；协议+scientific import21项20 Passed/1 skipped、1.493秒，新增实际子进程后协议15 Passed/1.051秒。测试自身用ExitStack确保失败时也先关捕获句柄再清理目录。架构导览更新；全量未重跑，full15仍最新Failed，C2未稳定提交。


2026-09-09：轨道缓存来源缺失structure/basis/orbital revision时被默认视为当前值，新增回归先复现三个失败，再移除默认回退；缺失或过期revision均不列为可用缓存。轨道浏览/出图/CBQ导入23项Passed，0.379秒；初次命令误写test_package_import，已纠正为test_cbq_package_import。diff --check通过。未重跑全量或Blender，full15仍最新Failed，C2未稳定提交。近期优先收敛迁移和回归，再接统一处理器，完整科学可视化与SOP目标不缩减。


2026-09-09：将scene preset致命异常对象回滚测试移出已删除的import_preview UI setup，直接加载当前Viewer实现，保留清理已创建对象及原异常identity断言，单项Passed。完整回归full16为2574项、3 failures/90 errors/36 skips、105.516秒，Failed；相对full15无新增失败标识。包含Worker日志句柄、ESP后置取消/identity、严格轨道缓存revision回归。C2仍未稳定提交。旧source revision候选与CBQ同UUID冲突属于不同语义，尚未以现有CBQ测试宣称全部等价，后续继续核验。


2026-09-09：修复CBQ重复来源确认边界。已确认导入的同内容来源再次导入原包时原来仍要求确认；preview现对已有source revision UUID使用既有内容冲突检查，完全相同的实体直接复用，新来源仍需明确确认。新增三个CBQ的默认拒绝/确认追加/两包复用/第三包仍拒绝及manifest不变回归，先复现再修复。另复现重新Preview继承先前allow_duplicate_sources=True，现每次重建预览重置确认；增强现有UI入口测试。CBQ package/Viewer17 Passed/0.621秒，diff检查通过。未重跑完整回归，full16仍最新Failed；不将此专项等同旧revision候选UI全部迁移，C2未提交。


2026-09-09：迁移Quick Import两项构象预计算契约：旧_PreflightJob后台预计算由CLI inspect生成候选、Tk纯复核及显式异步derive替代。增强test_sdf_inspection_cancel_and_changed_source_discard_staging，实际触碰cancel marker前后检查传入候选函数的is_cancelled回调，验证cancelled结果与暂存目录清理；既有真实Tk选择/复核/子进程derive/CBQ重开测试复跑通过。删除旧preflight_job_precomputes_conformer_suggestions_off_main_thread与preflight_job_cancels_conformer_precompute两项，其他旧任务契约保留。CLI39项38 Passed/1 skipped，11.039秒；GUI生命周期13 Passed/2.067秒。未重跑全量，full16仍最新Failed，C2未提交。


2026-09-09：用户确认额度恢复后，本地Git写入已成功。前三批检查点为27f67c9（共享核心/外部准备）、85ab235（Viewer及依赖政策）、8244d12（测试）；文档/示例为第四批。首批77项76 Passed/1 skipped、15.778秒；暂存检查发现迁入文件原有空白，四文件清理后AST相同、cached diff check通过。最初自动生成补丁输出超长未执行，改用保留换行的字节级格式清理。全部为开发快照，full16仍Failed，C2未关闭；legacy external-only导出验收不能替代View恢复/回滚/保存重开验收，继续补齐。用户本地.vscode设置不提交，无push。


2026-09-09：四批提交27f67c9/85ab235/8244d12/9eebdd7已成功，工作树仅剩用户.vscode/，暂存为空，54ecf4c..HEAD累计diff check通过。继续目标后完成full17（9eebdd7）：2573项、0 failures/88 errors/36 skips、110.906秒、Failed，无新增失败ID。错误分布import-preview55/wavefunction19/quick-import9/legacy路由5。原生纯Mesh编辑/Apply通过；legacy仅external-only导出通过，不代表旧View恢复和回滚已完成，相关门槛保持未完成。blender-mcp --help仍trampoline错误、MCP9876不可达；CIM读取被拒后Get-Process确认用户Blender PID45116路径，未修改该进程。私有后台实时确认Blender5.1.1/Python3.13.9与extension repositories。完整回归日志、summary、失败列表见.blend-analysis/2026-09-08-cbq-architecture-consolidation/migration-full-17*。下阶段继续收敛C2，随后才进入统一入口和控制器；目标保持active。
