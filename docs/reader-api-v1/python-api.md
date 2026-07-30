# Reader API v1 Python API

源码树内的测试与内置 reader 可以从 `ChemBlender.reader_api` 导入。独立安装的
Extension 必须使用 [API handle bootstrap](README.md#installed-extension-bootstrap)，
不得猜测安装模块名。

## 生命周期

1. **discovery**：built-in reader 随宿主注册；Extension 通过 handle callback
   显式注册，不扫描任意 `sys.path`。
2. **availability**：`PublicReaderDescriptor.availability` 提供 `available`、
   `reason_code` 与安全 detail；不可用 reader 返回诊断，不进入 parser。
3. **sniff**：宿主创建最多 64 KiB prefix 的 `SniffRequest`。reader 返回精确
   `SniffResult`；选择按 match、priority 和稳定 reader ID 处理。
4. **parse**：宿主创建 `ParseRequest`，包含已校验 source hash、validation mode、
   canonical parameters、staging root、`ProgressEvent` callback 与
   `is_cancelled` callback。reader 只返回 exact `PublicImportBatch`。
5. **progress/cancel**：progress 必须单调且满足
   `0 <= completed <= total`。长循环应周期调用 `is_cancelled`；取消时不发布
   staged artifact。
6. **diagnostics**：结果通过 `ParserReport`、`ParserIssue` 与
   `ImportDiagnostic` 表达质量和恢复行为。
7. **canonical**：跨进程结果使用 canonical Reader Import Document 与
   content-addressed NPY；主进程重新校验后才进入项目事务。
8. **sidecar**：成功提交后的科学实体属于 `.cbq`。插件之后缺失不影响
   sidecar reopen 或已有 view，只使 reparse unavailable。

## 精确公开符号

以下列表与 `ChemBlender.reader_api.__all__` 精确一致。未列出的 module、name 或
attribute 都不是 Reader API v1 契约。

```python
PUBLIC_SYMBOLS = (
    'READER_API_VERSION',
    'ExecutionMode',
    'CapabilitySupport',
    'ReaderAvailability',
    'ReaderManifestEntry',
    'ReaderPluginManifest',
    'PublicReaderDescriptor',
    'ArrayData',
    'AtomicIdentityData',
    'CategoricalData',
    'SourceRecord',
    'SourceRevision',
    'CIFEnvelope',
    'QCSchemaEnvelope',
    'CJSONEnvelope',
    'BiologicalAtomSiteData',
    'BiologicalChain',
    'BiologicalHierarchy',
    'BiologicalModel',
    'BiologicalResidue',
    'ChemicalAnnotation',
    'ExternalReference',
    'PeriodicSiteData',
    'MolecularTopology',
    'MolecularRecord',
    'RawRecordProperty',
    'RecordPropertyColumn',
    'ConformerSet',
    'TopologyRecord',
    'TopologySource',
    'Structure',
    'SymmetryResult',
    'CalculationMetadata',
    'CalculationRecord',
    'PropertyDataset',
    'AtomicProperty',
    'FrameSet',
    'FrameProperty',
    'AtomFrameProperty',
    'CellFrameProperty',
    'Grid3D',
    'VibrationalModeSet',
    'ExcitedStateSet',
    'Spectrum',
    'BandStructure',
    'DensityOfStates',
    'PhononModeSet',
    'FermiSurfaceMesh',
    'TopologyGraph',
    'ExcitationContribution',
    'ExcitedStateReferences',
    'BandPathBranch',
    'SurfaceProperty',
    'TopologyConnection',
    'TopologyPath',
    'BasisShell',
    'BasisConvention',
    'BasisSet',
    'OrbitalChannel',
    'OrbitalSet',
    'DensityMatrix',
    'ProvenanceRecord',
    'ParserIssue',
    'ParserReport',
    'DiagnosticValue',
    'ImportDiagnostic',
    'CalculationStatus',
    'DatasetStatus',
    'IssueKind',
    'BasisFunctionKind',
    'OrbitalKind',
    'DensityMatrixLevel',
    'DensityMatrixSpin',
    'SpectrumKind',
    'SpectrumProfile',
    'SpinChannel',
    'EnergyReference',
    'CriticalPointKind',
    'QualityStatus',
    'DiagnosticSeverity',
    'PublicImportBatch',
    'PublicBatchError',
    'PublicBatchValidationError',
    'public_batch_from_internal',
    'internal_batch_from_public',
    'CanonicalDocumentError',
    'CanonicalDocumentCompatibilityError',
    'CanonicalDocumentIntegrityError',
    'public_batch_document',
    'public_batch_from_document',
    'write_public_batch_bundle',
    'read_public_batch_bundle',
    'ReaderConformanceCase',
    'ReaderConformanceCheck',
    'ReaderConformanceResult',
    'run_reader_conformance',
    'SniffMatch',
    'SniffResult',
    'SniffRequest',
    'ParseRequest',
    'ProgressEvent',
    'ReaderPlugin',
    'ReaderPluginRegistry',
    'builtin_reader_plugin_registry',
    'WorkerReaderError',
    'WorkerReaderExecutionError',
    'WorkerReaderIntegrityError',
    'parse_with_worker',
)
```

## Plugin protocol

`ReaderPlugin` 提供 frozen `manifest`、`descriptor`、integer `priority`，
并实现：

```python
def sniff(request: SniffRequest) -> SniffResult: ...
def parse(request: ParseRequest) -> PublicImportBatch: ...
```

业务 reader 不接收 Blender context、`QCProject`、shell command 或动态 import
路径，也不直接写项目或 sidecar。
