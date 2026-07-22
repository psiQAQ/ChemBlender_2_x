# QCSchema Exchange

Completed on 2026-07-22.

## Result

- 固定 QCElemental `v0.50.4` / `46034a0587e2e74426cb1ae2d4d7f66ad5cf6090` 作为 schema 审阅证据。
- 分离实现 AtomicResult v1/v2 与 Molecule 2/3 adapter，不依赖 QCElemental/Pydantic runtime。
- 将结构、charge/multiplicity、driver/model、program、properties、return result、success/error 与 provenance 映射到内部模型。
- 以 `QCSchemaEnvelope` 无损保留 `extras`、`native_files` 和尚未规范化的字段，并支持 `.cbq` round-trip。
- 修复 sidecar 对 NumPy 0-D 标量数组写入时被升维的问题。

## Verification

- `python -m compileall -q ChemBlender/core tests`: Passed。
- `python -m unittest discover -s tests -p 'test_*.py'`: Passed，250 tests，27 skipped。
- Blender 5.1.2 native extension validate/build: Passed，58 ZIP entries。
- ZIP audit: QCSchema adapter 已包含；QCElemental/Pydantic 未包含；仅固定 RDKit wheel。
- 隔离 `BLENDER_USER_RESOURCES` lifecycle smoke: Passed。
- QCElemental model runtime validation: Not Run；固定源码 checkout 未安装 package metadata/Pydantic，按本阶段“不新增依赖”约束不安装。
