# `.cbq` 边车格式 v0.1

## 目标

`.cbq` 是 ChemBlender normalized project 的权威本地存储。`.blend` 只保存项目定位、
实体 UUID/revision 和显示状态，不保存大型科学数组的权威副本。

## 目录布局

```text
project.cbq/
├── manifest.json
├── arrays/
│   └── <content-sha256>.npy
└── cache/
    └── <namespace>/<cache-key>.<suffix>
```

v0.1 选择 NumPy `.npy`，因为 core 已依赖 NumPy，且该格式支持 dtype、shape、复数和
memory mapping，不增加 Blender Extension 依赖。Zarr 与 HDF5 等到代表性数据 benchmark
后只选择一种，不作为 v0.1 的兼容要求。

## Manifest contract

`manifest.json` 顶层字段为：

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `format` | `chemblender.cbq` | 格式识别符 |
| `manifest_version` | `0.1` | 存储协议版本 |
| `project_id` | UUID string | 防止 `.blend` 错连项目 |
| `project_schema_version` | non-empty string | `QCProject` schema 版本 |
| `project` | tagged object | normalized project graph |

数组引用必须包含相对路径、content SHA-256、文件 SHA-256、dtype 和 shape。路径只能位于
边车根目录内；reader 不接受绝对路径或 `..`。object dtype 和 pickle 不受支持。

## 写入与恢复

- 数组按 dtype、shape 和 C-contiguous bytes 计算 content hash，使用不可变文件名并去重。
- 新数组写到同目录临时文件，flush/fsync 后用 `os.replace` 发布。
- manifest 最后写入；同样使用同目录临时文件和原子替换。
- 写入失败时最后一个有效 manifest 仍可打开；未被 manifest 引用的数组可安全清理。
- 默认打开时校验每个 `.npy` 文件 SHA-256；显式快速模式可以推迟完整校验。

## Blender link

Scene 只记录 `project_id`、`project_schema_version` 和 sidecar locator。locator 优先相对
`.blend` 所在目录。恢复状态为 `connected`、`missing`、`incompatible`、`mismatch` 或
`invalid`。任何失败状态都不得删除现有 Object 或自动重写边车。

## Cache identity

hash 使用 canonical JSON 和 SHA-256，分四层：

```text
source      = bytes
parser      = source hash + reader ID/version + normalized options
derivation  = input UUID/revision + operation ID/version + normalized parameters
render      = entity UUID/revision + derivation hash + adapter ID/version
              + geometry-affecting settings
```

颜色、可见性等不会改变几何或采样的显示状态不进入 derivation identity。

## v0.1 非目标

- 并发 writer 和锁服务；
- source 文件复制策略；
- worker IPC；
- 远程定位或网络恢复；
- Zarr/HDF5/OpenVDB 的权威存储。
