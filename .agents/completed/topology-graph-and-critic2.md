# TopologyGraph and critic2 JSON Adapter

## Result

- 新增 `CriticalPointKind`、`TopologyConnection`、`TopologyPath` 与 `TopologyGraph`。
- critic2 `cpreport JSON` adapter 提取 cell CP、nonequivalent properties、connectivity、单位和 provenance。
- critical points 使用稳定 UUID；source/options 变化会产生新 revision。
- Blender adapter 将 CP 写入单 Mesh named attributes，仅将真实 sampled paths 写为 Curve。
- 明确记录最小 fixture 来自 critic2 `4b5dec9` 的 JSON writer schema，数值不作为科学基准。

## Evidence

- targeted topology/parser/sidecar tests：4 passed。
- full suite：240 tests passed，27 optional-dependency skips。
- Blender 5.1.2 native validate/build passed。
- 隔离 Extension install、CP attributes、coordinate conversion、sampled Curve、reload/RDKit/disable lifecycle passed。

## Decision

`.agents/decisions/0021-topology-graph-and-critic2-json.md`

## Known Limitations

- critic2 JSON 不含 gradient-path samples，因此 parser 只生成 connectivity。
- basin properties、basin surfaces 和 human-readable `.cro` parser 未实现。
