# 2.3.0 依赖分层与包体预算

## 分层

| Tier | 边界 | 2.3.0 例子 |
| --- | --- | --- |
| 1 | 官方 ZIP 安装后直接可用；Blender 自带或已批准 wheel | NumPy、OpenVDB、Requests、RDKit、Gemmi、原生 readers |
| 2 | 小型低成本 wheel，可经 ADR 打包；总体预算受控 | 后续可能的小型纯 Python helper；spglib仍不进入基础包 |
| 3 | 独立 Python worker，版本或科学栈不适合 Blender 3.13 | cclib、IOData、GBasis、ASE、pymatgen、phonopy |
| 4 | 大型程序、VTK/GPU、服务或独立生态 | PyProcar、Multiwfn、critic2、QCArchive、AiiDA、NOMAD |

## 已批准基础依赖

### RDKit

- 继续使用仓库固定的 CPython 3.13 Windows x64 wheel。
- 不计入“新增轻量依赖”额度。
- 仍必须计入最终 ZIP、解压体积、许可证和加载性能基线。
- 基础分子格式和结构编辑可依赖 RDKit。

### Gemmi

- 2.3.0 将 Gemmi 从可选 external core 升级为基础 wheel。
- 采用独立 ADR；固定版本、官方 wheel URL、SHA-256、MPL-2.0 notices。
- 必须实测压缩/解压体积和 Blender enable/import/lifecycle。
- CIF reader晚加载 Gemmi；非 CIF 功能不应因 Gemmi失败而不可用。

### spglib

- 继续可选增强，不作为 CIF 导入条件。
- 文件声明的对称信息由基础 reader保留。
- spglib结果是派生实体，不覆盖文件声明。

## 新增 wheel 预算

```text
单个新增 wheel 压缩目标       <= 10 MB
单个新增 wheel 解压目标       <= 30 MB
全部新增 wheels 压缩目标      <= 20 MB
```

Gemmi 可以通过 ADR 例外，但不能绕过测量和说明。

## CI 门禁

每个 release artifact生成：

```text
artifact-size.json
wheel-inventory.json
licenses/
```

`artifact-size.json` 至少记录：

- 当前 ZIP bytes；
- 上一稳定 ZIP bytes；
- 增量和百分比；
- 每个 wheel 压缩/解压 bytes；
- Python 源码、`.blend` asset 和其他资源的分项大小。

未解释的显著增长失败；阈值由 ADR 和实际 2.2.0 baseline 固定，不能在 workflow 中散落魔数。
