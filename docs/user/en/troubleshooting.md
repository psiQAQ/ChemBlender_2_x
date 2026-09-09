# Errors and Recovery

| Symptom | Check | Recovery |
| --- | --- | --- |
| Test Processor cannot start | Absolute path and file existence | Run `uv tool dir --bin`, paste the CLI `.exe`, retry |
| Standard incomplete | `chemblender-prepare doctor --json` | Force-reinstall the `[formats]` wheel in Python 3.12 |
| Optional operation unavailable | `capabilities` reason and environment | Configure only the documented route/backend; do not modify Blender Python |
| Project link missing after move | `.blend` and `.cbq/` locations | Put the pair together or use Relink, then Verify |
| Stale revision/hash | Input changed after task start | Inspect the current project and start a new explicit operation |
| Cancellation pending | Wait for the current calculation block | The owner may terminate only its task after two seconds; verify output before reuse |
| Cache missing | CBQ entity still verifies | Rebuild the View/cache locally |

Never reuse a partial output, edit `manifest.json` by hand, inject repository paths into a route, or install packages into Blender's bundled Python.
