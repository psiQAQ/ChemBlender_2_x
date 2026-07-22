# Phase 4 External Record Connectors

## Goal

建立 QCArchive、AiiDA 与 NOMAD 的可选只读 connector contract，使外部记录先转换为现有 QCSchema/CJSON/normalized import boundary，而不把服务 SDK 引入 Blender Extension。

## Success Criteria

- connector descriptor 声明 provider、locator schema、capabilities、authentication reference 与返回 envelope。
- connector request/result/error 使用版本化 JSON contract，禁止把 token 或本机绝对路径写入 project/provenance。
- worker operation 可从离线 fixture 重放 external record，并通过现有 adapter 进入 `QCProject`。
- dependency/network/auth 缺失返回稳定错误；不伪装为 parser failure。
- tests 覆盖 QCArchive/AiiDA/NOMAD 三种 descriptor、redaction、version mismatch 与离线 replay。

## Constraints

- 本阶段不安装服务 SDK、不访问用户账号、不执行网络写入。
- Blender Extension 只发 request 和消费 normalized result；provider SDK 留在可选 worker 环境。
- 不复制 QCSchema/CJSON normalization。

## Next Action

盘点 worker operation registry、QCSchema adapter 与 artifact envelope，先定义 provider-neutral request/result schema 和离线 fixture operation。

## References

- [QCSchema adapter](../decisions/0022-versioned-qcschema-exchange.md)
- [Local worker boundary](../decisions/0016-local-worker-v1-and-npy-retention.md)
- [数据与 Blender 边界](../../docs/quantum-visualization/architecture/data-boundary.md)
