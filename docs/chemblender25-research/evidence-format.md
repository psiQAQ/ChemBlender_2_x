# 证据格式和检查器边界

此格式是本次研究提供的**拟定独立格式**，不是 ChemBlender 已有运行协议，也不是新增稳定 API。应优先映射到仓库已有可复用记录，避免并存两套事实源。

## 最少记录

| 文档/字段 | 要求 |
|---|---|
| case spec | 固定 case ID、必要步骤、GUI 要求、科学检查、产物类型和冷重开门槛；录制前确定并计算哈希 |
| manifest status | `not_run/running/blocked/failed/passed`；未通过必须有原因 |
| baseline | 调研/执行范围的完整 commit 与本次实际 Extension/prepare 制品 SHA-256；不要由文件名推断版本 |
| environment | 实际 Blender 版本、操作系统、隔离 profile、唯一运行 ID；完整记录作为 environment artifact 留存 |
| artifacts | `id/kind/path/sha256`；路径相对于 manifest 所在目录，禁止绝对路径、`..` 和链接；图像另绑定 Extension SHA |
| steps | `id/status/interaction/event_id/before_artifact_id/after_artifact_id` |
| GUI events | JSON 数组；含事件 ID、step ID、实际动作、UTC 时间、process-session ID、interaction 和前后截图 ID |
| checks | `id/status/expected/observed/artifact_ids`；实际值来自科学数据/运行观察，不是照抄 expected |
| lifecycle | 新旧进程会话 ID、科学身份/数组哈希和实际状态；独立进程不能只看当前 PID 数值推断 |
| review | 审阅状态、实际审阅者/agent 标识、是否独立；记录不替代真正阅读图片与数据 |

`kind` 在首课中使用：`environment/gui_raw/render/events/assertions/scene_blend/cbq_manifest/lifecycle/review`。原始 GUI 和 render 使用 PNG；检查器仅验证 PNG 头部、引用和哈希，不解析界面内容。标注图和视频可以作为额外 artifact，不能取代原始截图。

真实 GUI 的 `interaction` 为 `os_gui` 或 `human_gui`。`blender_operator`、`cli`、`worker` 均为合法的实际自动化类别，但不能满足标记 `requires_gui=true` 的步骤。这并不要求所有科学计算通过鼠标触发；教程中本来属于 CLI 的步骤应在 case spec 中如实定义。

`.blend` 与 `.cbq/manifest.json` 必须同目录、同 stem。权威 CBQ schema/实体校验仍应实际调用当前 `chemblender-prepare validate`；本检查器只确认配对文件与 JSON 结构，**不会重新实现 CBQ validator**。

## 运行

使用本地标准 Python，不需要 pip 安装。代码支持 Python 3.10+；Windows 下为了检查 junction，使用 Python 3.12+。本次运行环境的精确版本和测试结果见 `validation-summary.json`。

```bash
# 20 个合成单元测试，不连接 Blender。
python -m unittest test_validate_evidence -v

# 模板未执行，必须返回 incomplete，退出码 2。
python validate_evidence.py run-manifest.template.json --spec T01.case-spec.json
```

真实运行后，指定该 run 的 manifest 和已冻结 spec。发布候选一致性检查增加 `--publish`，并通过 `--expected-extension-sha256` 和 `--expected-prepare-sha256` 传入从独立发布制品核验取得的完整哈希。此选项**不会上传、打 tag 或发布任何内容**。

退出码：`0=integrity_ok`，`1=invalid`，`2=incomplete`。`integrity_ok` 只说明所检查的记录和文件一致，不等同于教程 Passed 或产品可发布。

## 不会证明的事情

本检查器不会证明截图来自真实 GUI 输入，不验证记录作者身份，不独立重算科学结果，不执行 Blender，不证明相关许可允许分发，不校验实际安装目录一定对应所报 ZIP，也不替代第二 profile 盲走。事件顺序、截图文字可读性、真实渲染内容、科学图注和安装态须另行检查。

单元测试全部在临时目录中构造合成记录，图片是 1×1 人造 PNG，`.blend` 是明确标识的假字节。它们用于测试检查器拒绝错误记录，不属于教程样例。合成运行的 `synthetic=true` 在 `--publish` 下被拒绝；这些测试资产不打包为真实成果。
