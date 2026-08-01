# Reader API v1 Compatibility

当前发布 token 为 `1.0-rc1`，插件声明 `chemblender_api = ">=1.0,<2.0"`。
兼容判断使用 major/minor family；RC token 参与 `(1, 0)` 范围。2.3.0 正式版
保留 `1.0-rc1` token；stable token 提升留待后续明确的 Reader API 兼容门，
不因 final Release 状态自动改写。

## 兼容规则

- **same major**：v1 host 保留已发布的必填字段、字段含义、enum 值、异常分类和
  canonical 行为。
- **optional fields**：兼容增加必须带安全默认值；旧 document 缺失时仍可读，
  新 writer 不得改写无关旧语义。
- 新公开符号可以兼容增加，但插件只能依赖其声明支持的最小 host 版本。
- 删除、重命名、改变 required 状态或改变现有值语义属于 breaking change。
- deprecation 至少保留 **two formal minor releases**，文档同时给出替代接口和移除
  时间；2.3.x 内不得静默删除。
- 超出兼容范围的插件保持 **disabled**，宿主产生 compatibility
  **diagnostic**；不得阻止主 Extension 注册或 sidecar reopen。

## 冻结证据

`ChemBlender.reader_api.__all__`、公开 dataclass init fields 和 enum values 由
`tests/fixtures/reader-api/public-schema-v1-rc1.json` 及其 SHA-256 锁定。每个兼容
增加必须同步更新 snapshot、canonical round-trip、本文档和 conformance tests。
