# Phase 1 Blender Adapter Closure

Completed on 2026-07-22.

## Delivered

- Added a normalized `Structure` point-Mesh adapter with stable atom IDs and angstrom display conversion.
- Added atom scalar attributes, missing-value mask, display range, color mapping and dataset provenance metadata.
- Unified force/gradient-compatible atomic vectors and vibration arrows under one `vector_arrow_v1` Geometry Nodes contract.
- Added an in-memory `FrameSet` manager that updates one Mesh on `frame_change_post`, clamps frame indices and removes handlers on unregister.
- Added atom selection and stick-spectrum state/mode linked selection with strict source UUID checks.
- Advanced cclib to schema 4 so charge and spin datasets carry `AtomicProperty.structure_id`.

## Verification

- Blender Python: 134 tests passed, 7 skipped.
- cclib 1.8.1 environment: 134 tests passed, 4 skipped.
- Blender 5.1.2 native validate/build completed.
- Fresh isolated Blender user resources: package install, real Geometry Nodes evaluation, trajectory handler lifecycle and uninstall passed.

## Deferred Boundaries

- No final product panel, 2D plot widget, colorbar object or automatic bond reconstruction.
- Long-trajectory lazy loading, interpolation and `.blend` reopen/session restoration remain Phase 3 work.
- cclib multi-frame gradients remain explicitly unsupported rather than silently selecting one frame.
