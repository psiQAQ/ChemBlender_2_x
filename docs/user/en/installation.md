# Install, Update and Remove

## Requirements

- Windows x64, Blender 5.1.0 or newer, and `uv`.
- `chemblender-2.5.0.zip` and `chemblender_prepare-0.1.0-py3-none-any.whl` from the same release.

## Install Standard prepare

```powershell
uv tool install --python 3.12 "D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl[formats]"
$bin = uv tool dir --bin
Join-Path $bin 'chemblender-prepare.exe'
```

`uv tool` creates an isolated environment plus small launchers; it is not a single-file application. Standard installs NumPy, RDKit and Gemmi. Do not install these into Blender Python.

When 0.1.0 is published on PyPI, replace the wheel path with `"chemblender-prepare[formats]"`.

## Install the Extension

Open Blender **Preferences > Get Extensions**, choose **Install from Disk**, select `chemblender-2.5.0.zip`, enable ChemBlender, paste the absolute CLI launcher path into **Processor Executable**, then click **Test Processor**. The enabled module key is `bl_ext.user_default.chemblender`.

## Update or reinstall

```powershell
uv tool upgrade chemblender-prepare
uv tool install --python 3.12 "D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl[formats]" --force
```

Install a newer Extension ZIP from disk after saving and closing Blender. Re-run **Test Processor** after either component changes.

## Uninstall

Disable and uninstall the Extension in Blender, then run:

```powershell
uv tool uninstall chemblender-prepare
```

Uninstalling either component does not delete `.blend`/`.cbq` projects.
