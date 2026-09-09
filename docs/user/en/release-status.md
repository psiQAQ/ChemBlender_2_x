# Release Status and Known Limits

This documentation targets the local 2.5.0 release candidate. The latest previously published Extension is 2.4.0; `chemblender-prepare 0.1.0` is not on PyPI until publishing is authorized. Local artifacts are not proof of remote publication.

Compatibility is locked to Extension 2.5.0, Worker 0.1.0, Worker Protocol 1, and Reader API `1.0-rc1`.

The clean Python 3.12 Standard qualification resolved the following installed distributions. NumPy and transitive Pillow may resolve to newer compatible versions on a later install; use `uv pip list --python <tool-python>` and the installed distributions' license files as the authoritative local inventory.

| Distribution | Qualified version | License metadata | Role |
| --- | --- | --- | --- |
| chemblender-prepare | 0.1.0 | GPL-3.0-or-later | processor |
| NumPy | 2.5.3 | BSD-3-Clause and bundled compatible notices | arrays |
| RDKit | 2026.3.3 | BSD-3-Clause | molecular formats and operations |
| Gemmi | 0.7.5 | MPL-2.0 | CIF formats |
| Pillow | 12.3.0 | MIT-CMU | RDKit transitive dependency |

Known limits:

- Standard does not install wavefunction, scientific, Fermi, critic2, QCEngine or online-provider backends.
- Provider fetch and QCSchema compute report unavailable without an actual provider/compute backend.
- Blender does not expose every Worker operation as a panel button.
- Moving only one half of a `.blend`/`.cbq` pair requires Relink.
- Internal `chemblender_prepare.core.*` and GUI helpers are not a stable Python SDK.

See the [2.4 archive](../../archive/2.4.0/README.md) for old UI evidence; do not use it as the 2.5 daily tutorial.
