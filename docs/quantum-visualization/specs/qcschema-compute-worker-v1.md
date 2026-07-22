# QCSchema compute worker v1

`qcschema.compute@1` 是外部 worker 的固定 operation，不属于 Blender Extension。
请求参数必须恰好包含：

| 参数 | 允许值 | 说明 |
| --- | --- | --- |
| `backend` | `qcengine`、`pyscf` | 选择延迟导入的可选后端 |
| `input_data` | QCSchema AtomicInput v1/v2 | 禁止内嵌 `_qcengine_local_config` |
| `program` | lower token | QCEngine harness 名；PySCF 固定为 `pyscf` |
| `return_version` | `1`、`2` | PySCF 首版仅返回 v2 |
| `task_config` | `ncores`、`memory`、`retries`、`scratch_messy` | 不接受路径、MPI command 或任意环境配置 |

QCEngine 调用固定使用 `raise_error=False`、`return_dict=True`。成功的 AtomicResult
先原子写入 `.cbq/cache/qcschema-compute/<hash>/result.json`，再由 versioned QCSchema
adapter 生成 `ImportBatch`；project 重开验证后 worker 才发布 success。

PySCF adapter 首版只接受 QCSchema v2 `energy` driver、HF/RHF/UHF、字符串 basis 和
空 keywords。它直接调用 PySCF Python API，不执行 shell、输入脚本或任意 Python。

错误码为 `invalid_input`、`dependency_missing`、`calculation_failed` 或
`invalid_result`。失败不提交 dataset。取消文件在执行前和结果发布前复查；长时间 native
调用如需立即停止，由 client 终止该任务的专属 worker 进程。

QCEngine、QCElemental、PySCF 及其依赖由独立 worker 环境管理，不进入 Extension ZIP，
也不会在 Extension import/register 时探测或安装。
