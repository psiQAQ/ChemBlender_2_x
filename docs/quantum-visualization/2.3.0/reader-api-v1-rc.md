# Reader API v1 RC

ChemBlender 2.3.0 冻结 Reader API `1.0-rc1`。它是 reader 插件与宿主之间的
纯 Python 科学数据边界；不暴露 `QCProject`、Blender RNA、第三方 parser
对象或可调用对象。

## 版本与兼容范围

- 当前版本：`1.0-rc1`。
- 插件 manifest 使用半开区间 `>=MAJOR.MINOR,<MAJOR.MINOR`。
- v1 插件应声明 `>=1.0,<2.0`；RC token 按 `(1, 0)` 参与范围判断。
- `>=0.x,<1.0` 实验插件不兼容 v1，manifest 解析返回明确兼容性错误。该错误
  只使插件不可注册，不应阻止 ChemBlender 扩展本身注册。
- `plugin_version` 和各 `reader_version` 仍是独立的数字点分版本。

## 冻结的公开边界

权威导出列表位于 `ChemBlender.reader_api.__all__`。公开 dataclass 字段、
必填/可选状态、enum 值和两个 manifest dataclass 由
`tests/fixtures/reader-api/public-schema-v1-rc1.json` 的逐类型 SHA-256
快照锁定；fixture 自身另有 `.sha256` 文件。

字段删除、重命名、类型语义改变或 enum 值改变属于 breaking change。新增字段
只能是带默认值的可选字段，并须同时更新：

1. schema 快照与 hash；
2. 本文或对应格式规范；
3. canonical round-trip 与兼容测试。

breaking change 在 2.3.0 冻结后必须先提交 release-blocking ADR。

## Reader plugin manifest v1

顶层字段固定为：

| 字段 | 说明 |
| --- | --- |
| `schema_version` | 固定为 `"1"` |
| `plugin_id` | 稳定的小写 token |
| `plugin_version` | 数字点分版本 |
| `chemblender_api` | Reader API 兼容范围 |
| `execution_mode` | `built_in`、`extension` 或 `worker` |
| `license` | 非空、去重、排序的许可证字符串 |
| `readers` | 非空 reader 表列表 |

每个 reader 表固定包含 `reader_id`、`reader_version`、`extensions` 和
`capabilities`。未知字段、缺失字段、重复 reader ID 和不兼容范围均 fail
closed。

## 与交换文档版本的关系

Reader API 版本不是 canonical Reader Import Document 的 schema 版本。后者
继续使用 `chemblender.reader-import` / `0.1`，其字节编码、array artifact
hash 和安全路径契约不因本次 API 冻结而改变。

公开模块导入不得加载 `bpy`、Gemmi、spglib、RDKit 或其他 optional stack。
