# SimpleCoords Reader Extension

This separately installable Blender Extension demonstrates the public
ChemBlender Reader API v1. It registers
`org.chemblender.example.simplecoords` through the published
`chemblender.reader_api.v1` handle and never imports ChemBlender private
modules.

## Format

```text
CBSIMPLE 1
units angstrom
atoms 3
O 0.0 0.0 0.0
H 0.7 0.0 0.5
H -0.7 0.0 0.5
```

Version 1 accepts UTF-8 files, `angstrom` coordinates and the `H`, `C`, `N`
and `O` element symbols. The declared atom count must match the coordinate
rows.

## Build and install

From this directory, run:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --command extension build
```

Install and enable ChemBlender first, then install the generated
`chemblender_reader_example-1.0.0.zip`. Disabling or uninstalling this example
only removes reparsing support for `.cbsimple`; structures already committed
to a ChemBlender sidecar remain available.

Run its source tests from the repository root:

```powershell
python -m unittest discover -s examples/reader-extension/tests -p "test_*.py" -v
```
