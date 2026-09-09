# chemblender-prepare 0.1.0

[简体中文](../zh-CN/index.md)

The external tool owns raw-file parsing, scientific derivation, export and diagnostics. Blender invokes the same executable through Worker Protocol v1 and never runs `pip` or `uv`.

- [CLI and GUI](cli-and-gui.md)
- [Worker Protocol and Reader API](protocol-and-reader-api.md)
- [Optional route configuration](advanced-routes.md)
- [Generated public surface](../public-surface.json)

Public compatibility is CLI + Worker Protocol v1 + Reader API `1.0-rc1`. Importing `core.*`, GUI helpers, or worker implementation modules is unsupported.
