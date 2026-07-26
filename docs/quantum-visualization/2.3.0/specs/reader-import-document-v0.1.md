# Reader Import Document v0.1

## 范围

Reader Import Document 是 Reader API `0.1` 的进程间交换格式。它只表示
`PublicImportBatch` 和公开科学模型，不表示 `QCProject`，也不执行项目图校验。
调用方读取成功后，仍须通过 `internal_batch_from_public()` 完成主进程图校验。

## 公共接口

```python
public_batch_document(
    batch: PublicImportBatch,
    bundle_root: str | os.PathLike,
) -> bytes

public_batch_from_document(
    document: bytes,
    bundle_root: str | os.PathLike,
) -> PublicImportBatch

write_public_batch_bundle(
    root: str | os.PathLike,
    batch: PublicImportBatch,
) -> pathlib.Path

read_public_batch_bundle(
    root: str | os.PathLike,
) -> PublicImportBatch
```

`public_batch_document()` 写入或复用 `bundle_root/artifacts/` 中的数组，并返回
canonical UTF-8 JSON bytes；它不写 `import-batch.json`。
`write_public_batch_bundle()` 写入完整 bundle，并返回
`root/import-batch.json`。两个读取接口都立即、完整载入数组。

## Bundle 布局

```text
root/
├── import-batch.json
└── artifacts/
    └── {content_sha256}.npy
```

文档顶层字段必须恰好是：

```json
{
  "batch": {"$type": "PublicImportBatch"},
  "format": "chemblender.reader-import",
  "schema_version": "0.1"
}
```

实际 `batch` 对象还必须包含 `PublicImportBatch` 的全部 init fields。顶层缺失或
额外字段、错误 format、未知 schema 和未知公开 type/enum 属于
`CanonicalDocumentCompatibilityError`。

## Canonical JSON

- UTF-8，无 BOM、无结尾换行；
- object keys 按 Unicode code point 排序；
- separators 固定为 `(",", ":")`；
- `ensure_ascii=False`；
- `allow_nan=False`；
- 拒绝重复 JSON object keys、`NaN`、`Infinity` 和 `-Infinity`。

映射使用 `$dict` pair list 表示，按已编码 key 的 canonical JSON bytes 排序，
因此不依赖 Python dict 插入顺序。

## 值标签

每个 tagged object 只能有一个标签，字段集合必须完全匹配下表。

| 值 | 精确字段 |
| --- | --- |
| UUID | `{"$uuid"}` |
| enum | `{"$enum", "value"}` |
| bytes | `{"$bytes"}`，RFC 4648 Base64 |
| tuple | `{"$tuple"}`，值必须是 JSON array |
| list | `{"$list"}`，值必须是 JSON array |
| mapping | `{"$dict"}`，值必须是无重复 decoded key 的二项 pair list |
| model | `{"$type", ...all init fields}` |
| `ArrayData` | `{"$type", "values", "dims", "unit"}` |
| NPY array | `{"$array", "path", "content_sha256", "file_sha256", "shape", "dtype"}` |

`$array` 必须为 `"npy"`。`shape` 只能包含 exact non-negative `int`；`dtype`
使用 NumPy dtype string，禁止 object、structured 和 subarray dtype。缺失、
额外或 multiple tags 以及非法值属于 `CanonicalDocumentIntegrityError`。

### 注册 type tags

`PublicImportBatch`、`ArrayData`、`SourceRecord`、`SourceRevision`、
`CIFEnvelope`、`QCSchemaEnvelope`、`CJSONEnvelope`、`PeriodicSiteData`、
`MolecularTopology`、`Structure`、`SymmetryResult`、`CalculationMetadata`、
`CalculationRecord`、`PropertyDataset`、`AtomicProperty`、`FrameSet`、
`Grid3D`、`VibrationalModeSet`、`ExcitationContribution`、
`ExcitedStateReferences`、`ExcitedStateSet`、`Spectrum`、`BandPathBranch`、
`BandStructure`、`DensityOfStates`、`PhononModeSet`、`SurfaceProperty`、
`FermiSurfaceMesh`、`TopologyConnection`、`TopologyPath`、`TopologyGraph`、
`BasisShell`、`BasisConvention`、`BasisSet`、`OrbitalChannel`、`OrbitalSet`、
`DensityMatrix`、`ProvenanceRecord`、`ParserIssue`、`ParserReport`、
`DiagnosticValue`、`ImportDiagnostic`。

### 注册 enum tags

`CalculationStatus`、`DatasetStatus`、`IssueKind`、`BasisFunctionKind`、
`OrbitalKind`、`DensityMatrixLevel`、`DensityMatrixSpin`、`SpectrumKind`、
`SpectrumProfile`、`SpinChannel`、`EnergyReference`、`CriticalPointKind`、
`QualityStatus`、`DiagnosticSeverity`。

解码只按上述稳定 tag 查找 Reader API 公开 exact type；不读取 `__module__`，
不动态 import，也不接受子类。

## Artifact 身份与安全

数组先转换为 C-contiguous、non-subclass NumPy array。`content_sha256` 为以下
字节串的 SHA-256：

1. `{"dtype": dtype.str, "shape": shape}` 的 ASCII canonical JSON；
2. 数组的 C-order raw bytes。

`file_sha256` 是完整 `.npy` 文件 bytes 的 SHA-256。读取时必须同时满足：

- path 精确为 `artifacts/{content_sha256}.npy`；
- path 是相对 POSIX path，不含 absolute prefix 或 `..`；
- resolved path 保持在 bundle root 内，包含 symlink/junction 检查；
- file hash、shape、dtype 和 content hash 全部匹配；
- 使用 `numpy.load(..., allow_pickle=False)`；
- 禁止 object、structured、subarray dtype、pickle-backed payload 和 `.npz`。

writer 每次都以当前规范生成临时 NPY 并用 `os.replace()` 发布，不复用同
content hash 的历史文件 encoding。因此即使 bundle 中预置了使用其他合法
NPY header version 的同内容文件，输出 document bytes 与空目录写入仍完全
一致。

任何路径、文件、hash 或数组 metadata 不一致均为
`CanonicalDocumentIntegrityError`。格式不使用 pickle，不包含 module、
callable、shell、argv 或 Blender/project 对象。

JSON parse、tagged value encode 或 decode 超过 Python recursion limit 时也
统一转换为 `CanonicalDocumentIntegrityError`；实现不捕获 `BaseException`。

## 稳定异常

| 异常 | 含义 |
| --- | --- |
| `CanonicalDocumentError` | 所有 canonical document 错误的公共基类 |
| `CanonicalDocumentCompatibilityError` | 不支持的 format/schema/type/enum/tag |
| `CanonicalDocumentIntegrityError` | 非法 JSON、字段、值、路径、artifact 或 hash |
