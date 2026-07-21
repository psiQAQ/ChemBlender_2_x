# Phase 0 数据边界议程

本文列出 Phase 0 必须形成的五项 ADR。它记录决策问题和证据要求，不提前代替 ADR 作结论。

## 量子化学语义模型

- 问题：哪些最小对象足以承接结构、计算记录、属性、网格与来源信息？
- 最小内容：对象身份、所有权、数组字段、缺失值、解析置信度和派生关系。
- 已有约束：权威模型不使用 Blender `PropertyGroup`；大型数组不写入 Mesh attributes。
- 验证证据：至少两种结构格式归一化一致；一个不完整输出能显式报告缺失字段。
- 推迟选择：轨道、振动、激发态和拓扑图的全部专用字段；dataclass 与 Pydantic 的选择。

## Grid3D 数据约定

- 问题：怎样表达分子与周期体系中的标量网格，而不丢失坐标语义？
- 最小内容：origin、三个完整 step vectors、shape、dataset axis、values、单位、坐标约定和 semantic role。
- 已有约束：必须支持非正交网格和多 dataset；网格数值、物理语义与显示样式分离。
- 验证证据：正交与斜网格 fixture 的索引到笛卡尔坐标转换正确；Cube 多 dataset 不被静默截断。
- 推迟选择：OpenVDB、Zarr、HDF5、压缩和 chunk 形状。

## 单位约定

- 问题：单位在解析、归一化、派生计算和 Blender 显示之间如何传递？
- 最小内容：规范单位名、dimensionless 标记、输入单位、转换记录和无法确定单位时的错误状态。
- 已有约束：所有数值必须带单位或明确标为 dimensionless；不能从文件后缀推断物理语义。
- 验证证据：坐标、能量、频率与网格轴各有一个转换案例；round-trip 不重复换算。
- 推迟选择：自建单位表或采用 QCElemental 等库；用户界面的显示单位偏好。

## reader capability contract

- 问题：reader 如何声明、探测并报告对结构和计算属性的支持程度？
- 最小内容：reader ID/version、extensions、sniff、capabilities、优先级、输出类型和 `ParserReport`。
- 已有约束：能力状态至少区分 supported、partial、unsupported、ambiguous；第三方容器不直接进入 Blender。
- 验证证据：MOL2 声明与实现不一致成为回归测试；`.log/.out` 内容探测不会只依赖扩展名。
- 推迟选择：插件发现机制、外部 worker 协议和运行时安装方式。

## Blender 与边车数据的职责边界

- 问题：哪些内容写入 `.blend`，哪些内容由项目边车持久化？
- 最小内容：project/dataset UUID、显示设置、缓存引用、派生对象身份、source hash 和失效规则。
- 已有约束：`.blend` 保存视图状态与可重建缓存；边车保存权威数组、来源和 provenance。
- 验证证据：重开 `.blend` 后可恢复 dataset 引用；源文件变化后旧表面不会继续标为有效。
- 推迟选择：`.cbq` 目录布局、Zarr/HDF5、OpenVDB 和本地 IPC。

## ADR 顺序

1. 量子化学语义模型。
2. `Grid3D` 数据约定与单位约定。
3. reader capability contract。
4. Blender 与边车数据的职责边界。

后续 ADR 可以引用前一项的对象和术语，避免五份文档各自定义一套 ID、单位或缓存含义。
