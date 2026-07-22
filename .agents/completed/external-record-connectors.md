# External Record Connectors

## Result

- 定义 QCArchive、AiiDA、NOMAD 三种版本化 connector descriptor 与严格 request codec。
- URL、locator 与 environment reference fail closed；request/result/provenance 不保存 credential value 或本机绝对路径。
- 新增 `external_record.fetch@1`，offline fixture 经已有 QCSchema/CJSON adapter 进入 `QCProject`。
- provider mode 对 authentication、dependency 与 invalid record 返回独立稳定错误。
- artifact 使用内容寻址目录和原子替换；project 仍由 worker runner 原子 commit。

## Verification

- 定向 tests 覆盖三种 descriptor、strict codec、credential rejection、version mismatch、offline QCSchema replay、runner commit、authentication/dependency errors。
- 全量普通测试与 package contract 通过。

## Remaining Boundary

没有安装或调用 provider SDK；实际在线连接需明确目标服务和认证方式后再实现。
