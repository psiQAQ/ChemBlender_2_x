# Release Status and Known Limits

This documentation targets the local 2.5.0 release candidate. The latest previously published Extension is 2.4.0; `chemblender-prepare 0.1.0` is not on PyPI until publishing is authorized. Local artifacts are not proof of remote publication.

Compatibility is locked to Extension 2.5.0, Worker 0.1.0, Worker Protocol 1, and Reader API `1.0-rc1`.

Known limits:

- Standard does not install wavefunction, scientific, Fermi, critic2, QCEngine or online-provider backends.
- Provider fetch and QCSchema compute report unavailable without an actual provider/compute backend.
- Blender does not expose every Worker operation as a panel button.
- Moving only one half of a `.blend`/`.cbq` pair requires Relink.
- Internal `chemblender_prepare.core.*` and GUI helpers are not a stable Python SDK.

See the [2.4 archive](../../archive/2.4.0/README.md) for old UI evidence; do not use it as the 2.5 daily tutorial.
