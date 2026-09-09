# CLI 与 GUI

## CLI

```powershell
chemblender-prepare formats --json
chemblender-prepare capabilities --json
chemblender-prepare doctor --json
chemblender-prepare inspect input.cube --json
chemblender-prepare convert input.cube --preset electron_density --unit electron_per_bohr3 --output result.cbq --json
chemblender-prepare validate result.cbq --json
chemblender-prepare upgrade old.cbq --output upgraded.cbq --json
chemblender-prepare derive result.cbq --operation grid.resolve_semantics --parameters '{"dataset_id":"UUID"}' --output derived.cbq --json
chemblender-prepare export result.cbq --entity UUID --format cube --preview --output result.cube --json
chemblender-prepare worker request.json result.json
```

精确参数以各命令 `--help` 为准。目标格式无法表达选中 CBQ 数据时，必须先 preview，再显式确认损失。

## GUI

运行 `chemblender-prepare-gui.exe`。它是 Windows GUI entry point，不会额外打开控制台。九个入口为 convert、inspect、derive、validate、upgrade、export、formats、capabilities、doctor。

选择输入文件和全新输出路径。derive 中填写 operation ID，例如 `molecule.optimize`；参数填写 JSON object，例如 `{"force_field":"MMFF94"}`。GUI 不经 shell 启动 CLI，显示进度和结果 JSON，通过文件请求取消；只有两秒内未确认取消时才终止自己持有的进程。
