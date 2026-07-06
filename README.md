# ChemBlender

ChemBlender is a Blender 5.1 extension for molecular and crystal structure modeling with Geometry Nodes.

## Installation

Install the packaged extension zip from Blender 5.1 on Windows.
The extension bundles the RDKit wheel under `wheels/` and Blender installs it into the extension's private Python environment.

## Repository Notes

- `blender_manifest.toml` declares the extension metadata and bundled wheels.
- `wheels/` contains the Windows `cp313` RDKit wheel used by Blender 5.1.
- Runtime code no longer performs `pip install`; RDKit is expected to be provided by the extension package.

## Source

https://www.chemblender.com