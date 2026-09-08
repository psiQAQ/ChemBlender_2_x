# Windows 扩展更新后的冷依赖检查

更新 ZIP 后，在一个新的 Blender 进程中核对依赖。当前进程已经载入的 DLL 可能掩盖磁盘文件缺失；`FINISHED`、面板仍能显示或同进程 `reload` 不能代替这一步。

1. 对本地验证使用独立 `BLENDER_USER_RESOURCES`，通过原生 Extensions 安装同一 ZIP，明确选择 `User Default`，启用后保存 Preferences。
2. 关闭使用该测试 profile 的进程，保存 PID 和可执行路径用于核对。保留 `.blend/.cbq` 测试配对。
3. 使用相同 profile 启动新的 Blender，执行只读核对脚本；不要加 `--factory-startup`，因为本步需要验证已保存的启用状态。

```powershell
$env:BLENDER_USER_RESOURCES = 'D:\qualification\test-profile'
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' `
  --background --python-exit-code 1 `
  --python tests/blender_cold_dependencies.py -- `
  --package 'D:\qualification\chemblender-2.4.0.zip' `
  --output 'D:\qualification\cold-dependencies.json'
if ($LASTEXITCODE -ne 0) { throw 'Cold dependency verification failed' }
```

脚本检查 `bl_ext.user_default.chemblender`、实际 NumPy/RDKit/Gemmi 导入与来源，以及包内 wheel 的 Python、Pyd、DLL 文件是否与隔离安装逐一相同。输出绑定 ZIP SHA-256。它补充完整 `tests/blender_smoke.py`，不代替注册、资源、Reader API 和产品流程测试。

失败时保存 JSON、窗口提示和安装日志，并停止依赖相关操作。仅对自己创建的测试 profile，可在相关进程全部退出后归档损坏的 `.local`，再以 `--factory-startup` 通过原生 Extensions 重装同一固定 ZIP、启用并保存 Preferences；随后再次执行上面的新进程检查。实际用户的共享扩展依赖目录需要单独评估，不能照搬测试目录恢复步骤。

## 实际用户共享目录恢复

真实 profile 可能由多个已启用扩展共同管理依赖。先核对各扩展 manifest 的 wheel 所有权、实际模块来源及运行进程；完整备份 config、extensions、scripts 并校验。关闭占用该 profile 的进程前保存用户工作，只操作已核对路径和 PID 的进程。

保留正常用户 Preferences，通过原生 Extensions 安装到 user_default。不要针对现有真实 profile 使用 --factory-startup 或清空共享 .local：失去其他扩展的启用记录可能使 wheel 管理器删除它们需要的文件。若仍启用旧 ChemBlender，仅禁用旧键并保留文件，再安装和启用 bl_ext.user_default.chemblender、检查并保存 Preferences。

ChemBlender 自身不打包 NumPy；若另一个已启用扩展正式声明了 NumPy wheel，应保留该声明及现有文件，不能强制改回 bundled NumPy。安装后执行冷依赖检查、完整 smoke，再冷启动，并将其他扩展和共享依赖与备份逐文件比对。完整 smoke 使用正常 Preferences 和 --keep-enabled，不能把隔离 profile 的重置命令照搬过来。

已执行案例与精确构建身份见[2026-09-08 实际用户安装恢复](../user/workflows/reviews/2026-09-08-user-install-recovery.md)。
