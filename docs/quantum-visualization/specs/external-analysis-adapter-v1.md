# External analysis adapter v1

## 边界

外部分析只在 `worker/` 进程内执行。Blender Extension 和 request JSON 都不能传入任意 executable、
argv 或 shell 片段；显式注册的 adapter 根据已验证 recipe 生成 `ExternalInvocation`。

## Descriptor

`ExternalAdapterDescriptor` 声明：

- program ID 与 adapter version；
- 支持的 recipe ID；
- executable 候选名称与 version probe argv；
- invocation mode：`argv` 或 `stdin_script`；
- license、homepage 和 citation。

v1 内置 descriptor：

- critic2：`critic2 -q -t -l input.cri output.cro`；
- Multiwfn：`Multiwfn wavefunction`，命令脚本由 adapter 写入 stdin，UI 不接触菜单序号。

Descriptor 不代表程序已安装，也不代表某类输出 parser 已实现。

## Runner

`run_external_program` 使用 `subprocess.Popen` 参数列表和 `shell=False`，工作目录固定为调用者提供的
job root。stdin 与 expected artifacts 必须是 root 内的相对路径；已有 expected output 被拒绝，避免把
旧文件误认为本次结果。

stdout/stderr 直接写入 job root 的日志文件。运行记录保存：program/version、argv、状态、return code、
elapsed time、stdout/stderr SHA-256、expected artifacts 和 error code。

只有 return code 为零且所有 expected artifacts 都是本次产生的普通文件时状态为 `success`。program
缺失、非零退出、timeout、cancel 或 missing output 都不构造 `ImportBatch`，因此不能发布 dataset。

## 非目标

- 不使用 `shell=True`，不执行 request 提供的命令。
- 不在 v1 解析 critic2/Multiwfn 科学输出。
- 不安装、构建或自动下载外部程序。
