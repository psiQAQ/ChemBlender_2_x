# 0030：RDKit 与 Gemmi 属于基础依赖，spglib 保持可选

## Status

Accepted for 2.3.0.

## Context

RDKit已随2.2.0打包。CIF要成为安装即用能力，需要可靠 parser；手写 CIF维护成本高。空间群重新识别不是读取文件已有数据的必要条件。

## Decision

RDKit继续作为第一优先级基础 wheel。Gemmi升级为2.3.0基础 wheel，负责 CIF语法、block/loop和raw envelope。spglib继续作为可选增强，派生空间群、标准化和Wyckoff结果，不覆盖文件声明。

新增 wheel遵循单个压缩10 MB、解压30 MB、合计20 MB目标；Gemmi例外必须有独立大小、加载、许可证、SHA和Blender lifecycle证据。

批准的 Gemmi artifact 为官方 PyPI
`gemmi-0.7.5-cp313-cp313-win_amd64.whl`，SHA-256
`ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d`。
压缩大小为 2,270,352 bytes，解压大小为 5,345,458 bytes，低于预算；
wheel 内含 `gemmi-0.7.5.dist-info/licenses/LICENSE.txt`（MPL-2.0）。

## Consequences

- CIF Quick Import不依赖外部 Python。
- Gemmi失败只影响 CIF reader，不影响扩展启用和其他格式。
- release artifact新增wheel inventory和license gate。

## Rejected Alternatives

- 继续使用手写 CIF作为正式基础实现。
- 同时打包 spglib并把重新识别作为导入条件。
- 将 ASE整体打入基础包。

## Verification Contract

隔离安装ZIP后可导入真实CIF并保留occupancy/Uij/envelope；移除spglib环境仍通过相同基础流程。
