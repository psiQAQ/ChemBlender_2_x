# CLI and GUI

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

Use each command's `--help` for exact parameters. Export preview and explicit loss confirmation are required where the format cannot represent the selected CBQ data.

## GUI

Launch `chemblender-prepare-gui.exe`. It is a Windows GUI entry point and does not open an extra console. The nine entries are convert, inspect, derive, validate, upgrade, export, formats, capabilities, and doctor.

Choose files and a new output path. For derive, enter an operation ID such as `molecule.optimize` and a JSON object such as `{"force_field":"MMFF94"}`. The GUI starts the CLI without a shell, displays progress/result JSON, requests cancellation through a file, and only terminates its owned process if cancellation is not acknowledged within two seconds.
