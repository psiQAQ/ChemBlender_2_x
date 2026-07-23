# 2.3.0 测试、发布与旧项目迁移边界

## 1. 测试层

```text
Layer 1  pure contract tests
Layer 2  native real-format tests
Layer 3  optional dependency integration
Layer 4  Blender adapter and UI smoke
Layer 5  package/install/lifecycle
Layer 6  migration/performance/release verification
```

### Layer 1

使用标准库 `unittest`，无 Blender、无可选依赖。覆盖模型、canonical document、source identity、transaction、diagnostics和exporter纯函数。

### Layer 2

使用可再分发真实文件：XYZ/extXYZ、MOL/SDF、Cube、CIF、POSCAR、MOL2、PDB/PQR、CJSON。每个 fixture有来源、许可证、预期数值和能力说明。

### Layer 3

独立 job安装 cclib/IOData/GBasis等 pinned环境，目标 integration tests禁止 skip。此层不阻断基础 reader开发提交，但阻断包含相应 adapter变更的合并和预发布。

### Layer 4

Blender 5.1.2 smoke覆盖：Quick Import、Project Browser最小操作、StructureView、Volume、save/reopen、handlers、register/unregister。

### Layer 5

官方 ZIP隔离安装、真实 `user_default` 冷进程、wheel import、重复 enable/disable、asset检查、ZIP审计。

### Layer 6

旧 `.blend` migration fixtures、sidecar schema migration、性能 baseline、artifact size/license和 exact-tag release。

## 2. Fixture 规则

每个 fixture目录包含 `README.md`，记录：

- 来源或生成脚本；
- 许可证/再分发依据；
- 文件 hash；
- 软件和版本；
- 预期实体、单位和关键数值；
- 有意包含的异常；
- 不用于测试的字段。

合成 fixture用于边界测试，不能替代至少一个真实 writer输出。

## 3. 旧场景迁移

打开旧 `.blend` 时只检测，不自动修改：

```text
Legacy ChemBlender Objects Detected
→ Migrate to Project
→ scan and preview
→ temporary QCProject
→ create new views
→ verify
→ user confirms save
```

旧对象移动到 `ChemBlender Legacy Backup` collection并隐藏，默认不删除。迁移事务失败时移除本轮项目和新 view。无法证明的字段标为 `legacy_unverified`。

## 4. 发布列车

```text
alpha.1 Wave 0
alpha.2 Wave 1
beta.1  Wave 2 + schema/API freeze
beta.2  Wave 3 + conformance
rc.1    Wave 4, fixes only
2.3.0   final
```

任何 prerelease tag前先验证 Blender原生 manifest version规则。Release workflow对 prerelease设置 `--prerelease`，不设 latest；final才设置 latest。

## 5. CI topology

```text
native-core-windows
optional-qc-core-windows
blender-package-windows
release-contract-ubuntu
```

- version/artifact name从 manifest解析；
- package workflow不散落版本字符串；
- tag必须与 manifest/version mapping一致；
- exact-tag artifact保留期足够覆盖发布；
- release不重建；
- artifact size、wheel inventory、licenses作为制品；
- CI摘要列出 run/skip/fail counts。
