# QCEngine and PySCF Optional Execution

Completed on 2026-07-22.

## Result

- 固定 QCEngine `v0.50.0` / `d1842c4dd2c1e61eb9075a0d32ffefc7c4d5b318`。
- 新增 `qcschema.compute@1` 和严格的 QCSchema/资源参数边界。
- QCEngine 成功结果进入既有 QCSchema adapter；FailedOperation 不提交内部实体。
- 新增 PySCF v2 energy + HF/RHF/UHF 最小 adapter，共用 AtomicResult 回收路径。
- 修正 worker entity/output enumeration，使 QCSchema/CJSON envelopes 可被原子发布验证。

## Evidence

- targeted fake backend、runner commit/failure/cancel tests passed。
- Blender Python live probe：`qcengine` 与 `pyscf` 均未安装，因此真实 H2 SCF smoke Not Run。
- repository `262` tests passed、`27` skipped；Extension validate/build passed。
- ZIP 共 `59` entries，未包含 `worker/`、`submodules/`、QCEngine、QCElemental 或 PySCF；isolated Blender lifecycle smoke passed。

## Boundary

未安装依赖、未把计算后端带入 Extension，也未实现 procedure、远程调度或数据库 connector。
