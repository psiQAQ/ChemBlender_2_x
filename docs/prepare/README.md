# ChemBlender Prepare 0.1.0

External Python 3.12 processing for the ChemBlender 2.5 Viewer. Public interfaces are the CLI, GUI, Worker Protocol v1, and Reader API `1.0-rc1`; internal Python modules are not a stable SDK.

- [English](en/index.md)
- [简体中文](zh-CN/index.md)
- [Generated public surface](public-surface.json)

Standard install:

```powershell
uv tool install --python 3.12 "chemblender-prepare[formats]"
uv tool dir --bin
```

Use a release wheel path instead of the package name until 0.1.0 is published on PyPI.
