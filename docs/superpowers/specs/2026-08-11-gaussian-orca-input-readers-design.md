# Gaussian and ORCA Cartesian Input Reader Design

## Goal

为 ChemBlender 增加两个内置、零第三方依赖的计算化学输入文件 reader，使用户能够通过现有 Quick Import 和 Project Browser 直接展示 Gaussian `.gjf`/`.com` 与 ORCA `.inp` 中的内嵌 Cartesian 分子结构。

本切片必须产生实际可操作的用户能力，不以孤立 parser、静态格式声明或构建成功代替 Blender 运行时导入。

## Product Boundary

新增两个独立 reader：

- `gaussian-input`：扩展名 `.gjf`、`.com`；
- `orca-input`：扩展名 `.inp`。

二者都只声明 `structure = supported`，使用现有 `ReaderDescriptor`、`ReaderRegistry`、`ImportBatch`、`Structure`、`ProvenanceRecord` 和 `ParserReport`。不新增依赖、执行器、计算任务模型或通用量子化学输入抽象。

成功导入得到一个非周期 `Structure`：

```text
Structure
├── atomic_numbers
├── coordinates: (atom, xyz), angstrom
├── molecular_charge
└── molecular_multiplicity
```

输入文件描述待执行任务，不证明计算已运行，因此不创建 `CalculationRecord`。route、method、basis、SCF 设置和程序运行控制不进入语义模型。

## Architecture

采用两个格式专属模块：

- `ChemBlender/core/formats/gaussian_input.py`
- `ChemBlender/core/formats/orca_input.py`

每个模块拥有自己的 sniff、parse 和 descriptor。它们复用现有模型，不互相调用，也不通过生成临时 XYZ 间接解析。这样可保持 reader ID、诊断和未来扩展边界清楚。

新增 reader 接入：

- `ChemBlender/core/reader_catalog.py`；
- `ChemBlender/core/__init__.py` public compatibility exports；
- 生成的 reader capability documents；
- Quick Import 和 drag-and-drop 使用的内置 registry；
- 用户格式文档与代表性工作流样例。

新增源模块的职责必须同步写入 `.agents/reference/code-architecture-guide.md`。

## Gaussian Syntax

读取顺序：

1. 跳过文件开头连续的 `%...` Link0 行；
2. 定位以 `#` 开头的 route section，并读取至空行；
3. 读取非空 title section，并读取至空行；
4. 读取恰好两个整数 `charge multiplicity`；
5. 读取至下一个空行或 EOF 的 Cartesian 原子行。

原子行严格为：

```text
Element x y z
```

`Element` 为标准元素符号，大小写规范化；D/T 映射为 H，并产生与 XYZ reader 一致的 warning。三个坐标必须为有限浮点数。

坐标块之后允许保留 basis/ECP 等后续输入内容，但 reader 不解释这些内容。文件任意位置出现 `--Link1--` 时拒绝整个文件，避免只展示多任务输入中的一个结构。

以下 Gaussian molecule specification 不在本切片范围：

- Z-matrix 或变量形式；
- freeze code；
- ONIOM layer；
- fragment、atom type 或其他原子修饰；
- 多任务 Link1 输入。

这些写法必须产生明确错误，不得猜测列含义或返回部分结构。

## ORCA Syntax

reader 定位唯一的内嵌坐标块：

```text
* xyz charge multiplicity
Element x y z
...
*
```

块首行的 charge 和 multiplicity 必须是整数，multiplicity 必须大于零。原子行使用与 Gaussian 相同的严格四列和有限数值规则。

`!...`、`%...` 和其他 ORCA 计算设置不参与结构解析。以下情况拒绝整个文件：

- `* xyzfile ...` 外部文件引用；
- 内部坐标；
- 未闭合坐标块；
- 多个坐标块；
- 带额外列或原子修饰的坐标行。

外部 XYZ 引用需要多文件来源身份和缺失文件策略，留给独立后续切片。

## Sniffing

sniffing 使用 registry 提供的有界 prefix，并同时参考扩展名与格式内容：

- Gaussian 的完整合法坐标给出 `EXACT`；带 `.gjf/.com` 后缀且包含 route 或 Link0 标记的截断/损坏输入仍给出 `PROBABLE`，以保留 reader-specific 失败诊断；无专用后缀时仍要求 route 与 charge/multiplicity 构成可信标记；
- ORCA 需要 `* xyz` 或可识别但不支持的 `* xyzfile` 标记；
- 扩展名本身不足以把普通 `.inp` 文本判为 ORCA；
- 完整且合法的内嵌结构返回 `EXACT`；
- prefix 截断或已明确识别程序格式但几何语法不受支持时返回 `PROBABLE`，使 parse 阶段能够给出具体错误；
- 非 UTF-8 文本、缺失格式标记或冲突语法返回 `NONE`。

sniff 只负责 reader 选择；完整性、唯一性和所有科学边界由 parse 阶段重新验证。

## Import Result and Provenance

成功解析时：

- 对原始字节计算 SHA-256；
- 坐标归一化为 `ArrayData(..., ("atom", "xyz"), "angstrom")`；
- charge/multiplicity 写入 `Structure` 现有字段；
- provenance 记录绝对来源、source hash、格式和坐标模式；
- Gaussian title 可进入 provenance parameters；
- report 只声明 `structure` capability；
- D/T 映射进入 `ParserIssue`，其余受支持输入不制造噪声诊断。

Quick Import pipeline 继续负责权威 `SourceRecord`、`SourceRevision`、preflight、preview 和 atomic commit；reader 不创建第二套来源系统。

## Error Boundary

下列条件抛出 `ValueError`，由现有导入管线转为用户可见诊断：

- UTF-8 解码失败；
- 缺少必要 section 或 section 顺序错误；
- charge/multiplicity 无效；
- multiplicity 非正；
- 空坐标块；
- 未知元素；
- 坐标非数值或非有限；
- 原子行不是严格四列；
- 本设计列出的复杂或多结构语法。

不返回部分 `ImportBatch`，不静默跳过无效原子，不从文件中任选一个结构。

## User Examples and Documentation

在 `examples/user-workflows/inputs/` 增加最小、可复用的 Gaussian 与 ORCA 输入，以及相邻 Markdown 来源/语义说明。样例保持轻量，适合 Quick Import 手工验证。

更新：

- `docs/user/formats.md` 的生成格式表及必要边界说明；
- `docs/quantum-visualization/reader-capability-matrix.json`；
- `docs/user/format-capabilities.json`；
- `docs/user/dependencies.json`；
- `.agents/reference/code-architecture-guide.md`。

生成文件只通过 `ChemBlender/scripts/generate_format_docs.py` 更新并用 `--check` 验证。

## Verification

TDD 顺序：先添加失败测试，再实现最小生产代码。

单元与契约验证包括：

- Gaussian `.gjf`/`.com` 与 ORCA `.inp` golden fixtures；
- 两个 reader 归一化后的原子序数、坐标、单位、charge 和 multiplicity；
- D/T warning；
- 内容 sniffing、错误扩展名识别和普通 `.inp` 拒绝；
- 所有明确排除语法和截断输入；
- registry reader 数量、唯一 ID、能力矩阵 freshness；
- Quick Import preflight、preview、commit 与 `QCProject` 引用完整性；
- 普通 CPython 导入不加载 `bpy`。

仓库验证包括相关单元测试、生成文档 `--check`、静态包检查、`git diff --check` 和最终 worktree 状态。

Blender 5.1 运行时验证必须通过公开的 `bpy.ops.chemblender.quick_import` 分别导入两个工作流样例，并确认：

- selected reader ID 正确；
- Project Browser 出现结构；
- 分子对象在场景中可见；
- charge/multiplicity 保存在项目数据；
- register/unregister 或重复 reload 不因新 reader 回归。

静态 parser 测试、manifest 解析、ZIP 存在或构建成功都不能替代此运行时证据。

## Rejected Alternatives

- 单一 `quantum-input` reader：会混合程序语法、reader identity 和错误诊断。
- 转换为临时 XYZ：会丢失 charge/multiplicity、原生错误位置和来源语义。
- 本阶段支持 `xyzfile`：需要新的多文件来源和缺失引用策略。
- 自动解析 route/method/basis：输入关键词组合复杂，且不属于结构展示能力的验收条件。
- 宽松接受额外原子列：freeze code 与整数坐标存在歧义，可能展示错误几何。

## References

- Gaussian remote file conventions: <https://gaussian.com/wp-content/uploads/dl/remote.pdf>
- Gaussian input and visualization guide: <https://gaussian.com/wp-content/uploads/dl/gv6.pdf>
- ORCA coordinate input: <https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/coordinates.html>
- 计算化学知识库 Gaussian 章节: <https://wcn4y6qviiko.feishu.cn/wiki/CIhLwXDEIiPvafkcyTxcDFTrnVV>
- 计算化学知识库 ORCA 输入输出章节: <https://wcn4y6qviiko.feishu.cn/wiki/L65Nw3V2qi5FGskZoyecDxKSn1c>
