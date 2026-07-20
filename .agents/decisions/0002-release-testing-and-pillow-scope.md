# 0002: Release Testing and Pillow Scope

## Status

Accepted for ChemBlender 2.2.0 release readiness.

## Decision

- Keep the release contract suite on Python's standard-library `unittest` runner. Add pytest only when its fixtures, parameterization, plugins, or reporting remove demonstrated maintenance cost.
- Do not bundle Pillow while ChemBlender does not import PIL or exercise Pillow-dependent RDKit APIs.
- Revisit the manifest wheel set before adding `rdkit.Chem.Draw`, direct PIL imports, or another Pillow-dependent feature.
- Treat Blender's NumPy and Requests as host capabilities only after verifying them with an isolated `BLENDER_USER_RESOURCES` root.
- Declare `network` permission for user-requested molecular and scaffold downloads. Network access must never install Python packages.
- Require repository contracts, native validate/build, ZIP audit, isolated install, real install, and GitHub Actions before declaring a release candidate ready.

## Consequences

The 2.2.0 package stays small and avoids an unused Pillow wheel. Clean-profile tests prevent an existing Blender extension environment from hiding missing runtime dependencies. Any future Pillow-dependent feature must update this decision, manifest metadata, CI download pins, and runtime tests together.
