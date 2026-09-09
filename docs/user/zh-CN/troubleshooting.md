# 错误与恢复

| 现象 | 检查 | 恢复 |
| --- | --- | --- |
| Test Processor 无法启动 | 绝对路径及文件是否存在 | 运行 `uv tool dir --bin`，填入 CLI `.exe` 后重试 |
| Standard 不完整 | `chemblender-prepare doctor --json` | 在 Python 3.12 中强制重装带 `[formats]` 的 wheel |
| 可选 operation unavailable | `capabilities` 的原因和环境 | 只配置文档指定的 route/backend，不修改 Blender Python |
| 移动后项目链接缺失 | `.blend` 与 `.cbq/` 位置 | 将两者放回一起或 Relink，再 Verify |
| revision/hash 过期 | 任务开始后输入是否变化 | 检查当前项目并新建显式 operation |
| 取消仍在等待 | 等待当前计算块结束 | 持有者两秒后只能终止自己的任务；复用输出前先校验 |
| 缓存丢失 | CBQ 实体是否仍通过校验 | 本地 Rebuild View/cache |

不要复用半成品、手改 `manifest.json`、向 route 注入仓库路径，也不要向 Blender 自带 Python 安装包。
