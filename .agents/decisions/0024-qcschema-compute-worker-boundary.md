# 0024：QCSchema compute worker 边界

## Status

Accepted for Phase 4 optional execution.

## Context

QCSchema exchange 和 local worker 已稳定，但 Blender 主进程不能加载 SCF 或程序 harness。
固定的 QCEngine v0.50.0 提供 `compute`、program discovery 和 `FailedOperation`，但不包含
PySCF harness。

## Decision

- 注册 `qcschema.compute@1`，只接受严格 AtomicInput、显式 backend/program 和受控资源参数。
- QCEngine 使用字典输入/输出和结构化失败，不允许 AtomicInput 内覆盖本机配置。
- PySCF 使用独立的最小 API adapter；首版仅支持 v2 energy + HF/RHF/UHF。
- 两个后端都输出 AtomicResult，再复用 QCSchema adapter；后端不直接创建内部实体。
- 任务依赖延迟导入并只存在于外部 worker 环境。

## Consequences

- 缺依赖、输入错误、计算失败和无效结果有稳定错误码，且不会提交部分结果。
- cooperative cancel 只能在 native call 前后生效；立即取消使用一次一进程的 terminate 边界。
- QCEngine procedure 若不返回 AtomicResult 会以 `invalid_result` 拒绝，首版不支持优化 procedure。
- Blender Python 当前未安装 QCEngine/PySCF，因此真实 SCF smoke 为 Not Run；fake backend 合同覆盖可重复 CI。

## Verification Contract

1. fake QCEngine 校验准确调用参数、成功/FailedOperation 与 missing dependency。
2. fake PySCF H2 HF/STO-3G 校验 Bohr、charge/spin、RHF 选择和 v2 AtomicResult。
3. runner 成功才提交；失败和取消保持 project 无新增 calculation。
4. default registry import 不加载 `qcengine` 或 `pyscf`。
5. Extension build ZIP 不包含 worker、QCEngine、QCElemental 或 PySCF。
