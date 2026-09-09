# ChemBlender

[简体中文](README.zh-CN.md)

ChemBlender 2.5 is a Blender 5.1+ Viewer for validated CBQ scientific projects. Scientific parsing and recomputation run in the separate `chemblender-prepare` tool; Blender keeps editing, views, animation, caching, Cycles rendering, and project reopening independent of scientific Python packages.

The workflow is result-first and program-neutral on Windows x64 with Blender 5.1. Standard readers cover XYZ/extXYZ, MOL V2000/V3000, SDF, SMILES, CIF, POSCAR/CONTCAR, MOL2, PDB/PQR, Cube, CJSON and QCSchema. Save the `.blend` beside its `.cbq` sidecar and keep them together; optional backends remain explicit external routes.

## Components

| Component | Version | Responsibility |
| --- | --- | --- |
| ChemBlender Extension | 2.5.0 | CBQ import/export, pure-Mesh editing and Apply, views, animation, project lifecycle and rendering |
| chemblender-prepare | 0.1.0 | CLI/GUI conversion, validation, derivation, export, diagnostics and Worker Protocol v1 |

The Extension ZIP contains no RDKit, Gemmi, or other scientific wheel. The Standard prepare install contains NumPy, RDKit and Gemmi in its own Python 3.12 `uv tool` environment. Optional wavefunction, scientific, Fermi, critic2, QCEngine and provider capabilities report themselves as unavailable until configured.

## Install

1. Install `chemblender-2.5.0.zip` through Blender **Preferences > Get Extensions > Install from Disk**.
2. Install Standard prepare from a release wheel:

```powershell
uv tool install --python 3.12 "D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl[formats]"
uv tool dir --bin
```

3. Copy the absolute path to `chemblender-prepare.exe` into ChemBlender preferences and run **Test Processor**.

The future PyPI command will be `uv tool install --python 3.12 "chemblender-prepare[formats]"`; 0.1.0 is not on PyPI until the release is published.

## Start here

- [English user guide](docs/user/en/index.md)
- [English prepare CLI/GUI/API guide](docs/prepare/en/index.md)
- [中文用户指南](docs/user/zh-CN/index.md)
- [中文 prepare CLI/GUI/API 指南](docs/prepare/zh-CN/index.md)
- [Machine-generated public surface](docs/prepare/public-surface.json)
- [Code architecture guide](.agents/reference/code-architecture-guide.md)
- [Archived ChemBlender 2.4.0 experience review](docs/user/2.4.0-experience-review.md)
- [Archived 2.4.0 workflow index](docs/user/workflows/README.md)
- [Archived 2.4.0 example corpus](examples/user-workflows/README.md)
- [Release history](CHANGELOG.md)

CBQ is the only scientific exchange boundary. Keep each saved `project.blend` beside its `project.cbq/` directory. Moving or removing the processor does not remove already stored scientific entities or their rebuildable Blender views.

Project website: https://www.chemblender.com
