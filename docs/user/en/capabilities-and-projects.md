# Capabilities and Projects

The Standard processor supports core CBQ operations, 22 registered readers subject to their declared dependencies, and 13 public export formats. Read the exact generated lists in [public-surface.json](../../prepare/public-surface.json) and [format-capabilities.json](../format-capabilities.json).

`capabilities` is the live truth for the current machine. `doctor` fails when Standard NumPy/RDKit/Gemmi is incomplete and emits concrete warnings for unconfigured optional routes, critic2, QCEngine/provider operations, or readers.

A saved project is a pair:

- `project.blend`: scenes, Blender Views, presentation and a project link.
- `project.cbq/`: authoritative scientific entities, provenance, revisions, arrays and rebuildable caches.

Keep the pair together. Import and external operations append provenance-backed entities. Mesh Apply creates a derived Structure; it does not rewrite imported coordinates. View changes never become scientific data automatically.
