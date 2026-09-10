# T07: density grids, slices and signed surfaces

Working draft. Public conversion, five primary Grid Views created through the GUI, signed display, numerical sampling, rendering and serial cold/cache recovery have evidence. Prepare GUI, the complete difference recomputation walkthrough, VASP input, remaining illustrations and independent human replay are pending.

![Rendered analytic density redistribution: blue positive, orange negative](../assets/2.5-tutorials/grid-difference-refined.png)

This image shows an analytic teaching density difference, not a molecular orbital or an HF/DFT calculation. The finer surface has smoother contours but still shows interpolation bands. Lighting changes apparent color; the image is not a quantitative color scale.

## Fixed input

Complete [installation](installation.md) and [the first lesson](first-aspirin.md). Use Blender 5.1.1, prepare 0.1.0 and candidate Extension SHA-256 `963b905f3e5ee3c5fc1fa53a1ccefd5c60616d89ac77977efe4afdbed066426a`.

Download [h2-lcao-1s-density-64.cube](../../../examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.cube), its [source/license note](../../../examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.md), and the [frozen case specification](../../../examples/tutorials/2.5.0/T07.case-spec.json). Older source-note import instructions do not replace the CBQ route below.

| Item | Reference |
| --- | --- |
| SHA-256 | `51fcb06343132c4b75f340aa5824434c9c622b51df7ea1ad3742920c78af66b4` |
| Model | Repository analytic H2 bonding 1s LCAO density; GPL-3.0 |
| Shape | 64 × 64 × 64; 262144 samples |
| Coordinates | bohr; origin (-6,-6,-6), diagonal step 0.1904761905 |
| Atoms | H at z = -0.7 and +0.7 bohr |
| Values | electron_per_cubic_bohr; min 7.75746861e-10, max 0.229296377 |
| Rectangular-sum integral | 1.9996717595939106 using serialized steps; approximately 2 electrons |

The Cube nuclear-charge column contains zero placeholders. Do not interpret these as physical nuclear charges.

## Prepare and import

Create a fresh lesson folder and use new output paths. These public commands were verified; replace the example folder. They are CLI evidence, not a recorded Prepare GUI session.

```powershell
chemblender-prepare inspect "D:\ChemBlenderLessons\T07\h2-lcao-1s-density-64.cube" --reader cube --json
chemblender-prepare convert "D:\ChemBlenderLessons\T07\h2-lcao-1s-density-64.cube" --reader cube --preset electron_density --unit electron_per_cubic_bohr -o "D:\ChemBlenderLessons\T07\h2-density.cbq" --json
chemblender-prepare validate "D:\ChemBlenderLessons\T07\h2-density.cbq" --json
```

Expect success with both an original ambiguous `scalar_field` / `unknown` grid and an appended complete `electron_density` grid. The explicit interpretation comes from the fixed input's provenance; Cube alone does not reliably supply quantity semantics. [Independent checks](../assets/2.5-tutorials/grid-science-check.json) matched every scalar, origin and step exactly.

1. In Blender's ChemBlender sidebar, set `CBQ Package`, then `Preview CBQ` and `Import CBQ`. These previously verified actions were replayed through MCP. If the browser has not drawn yet, open the ChemBlender tab; do not import twice.
2. Select the complete Electron Density in Project Browser. Under `Scientific Representation`, verify `Coordinates: bohr` and `Values: electron_per_cubic_bohr`.
3. With `Automatic` resolving to Grid volume, click `Create View`. The recorded display used Density Scale 10. This changes appearance, not the stored density.
4. Choose `Signed scalar isosurface`, keep `Dataset Index` 0, set `Isovalue` 0.05, and click `Create View`. Hide the earlier volume in viewport and render to inspect the surface independently.

![Actual primary density surface and its quantity labels](../assets/2.5-tutorials/grid-primary-surface.jpg)

All primary values are positive: the positive surface has 882 vertices / 880 faces; the negative surface is empty. This is expected, not a failure of signed rendering.

## Sample a slice, profile and colorbar

Select the complete primary density before each Create. Each operation below was performed through the actual GUI. Keep separate Views, and hide overlapping Views while inspecting one.

| Representation | Settings | Expected check |
| --- | --- | --- |
| Scientific plane slice | Origin (-1,-1,0), U (2,0,0), V (0,2,0), 65 × 65; symmetric range off; color 0 to 0.25 | 4225 valid samples; maximum error 7.404e-9 against independent trilinear interpolation |
| Scientific line profile | Start (-1,0,0), end (1,0,0), 129 samples | Distance label 0–2 bohr; values 0.0630902003 to 0.176022212; maximum error 7.951e-9 |
| Scientific colorbar | Symmetric range off; color 0 to 0.25; width 2, height 0.2 in display angstrom | Endpoints 0 and 0.25; electron_per_cubic_bohr label |

Click `Create View` after setting each representation. Slice/profile coordinates above are bohr. More display samples interpolate the same 64³ field; they do not add scientific information. See the [slice check](../assets/2.5-tutorials/grid-slice-check.json) and [profile/colorbar check](../assets/2.5-tutorials/grid-profile-check.json). Clear composed illustrations of these three Views remain pending.

## Signed difference result and refinement

The recorded extension example subtracts the sum of two isolated analytic 1s atomic densities from the bonding density, on the same structure and affine grid. The [reproducible input generator](../../../examples/tutorials/2.5.0/generate_t07_density_pair.py) and frozen specification define both datasets. Public `grid.resolve_semantics` and `grid.difference` processing passed, but a complete user recomputation sequence and its GUI route are still pending.

For the recorded difference dataset, choose `Signed scalar isosurface`, set Isovalue 0.005 and click `Create View`. Blue marks positive redistribution, orange negative. The [difference check](../assets/2.5-tutorials/grid-difference-check.json) verifies all 262144 subtractions, with range -0.0345176831 to 0.0204030833. A disposable right grid shifted by 0.1 bohr was rejected for incompatible affine geometry without changing inputs or writing an output.

![Actual signed difference surface at isovalue 0.005](../assets/2.5-tutorials/grid-signed-surface.jpg)

The actual `Separate Positive / Negative Volume` control was also tested. It uses a signed VDB and two shader branches, not two independent scientific grids. Full VDB values agree with the scientific difference within 1.122e-9 at float32 precision. A final volume render remains pending.

For the preview image, the recorded settings were Cycles CPU, 2400 × 1800, 256 samples and denoising; Principled material Roughness 0.32; orthographic camera (4,-8,3) aimed at the origin, scale 3.2; area light (2,-4,5), 450 W, size 4; world color (0.12,0.12,0.12), strength 0.7. Hide unrelated Views in both viewport and render.

In Geometry Nodes, select each signed surface's `Volume to Mesh` node. Change `Resolution Mode` from `Grid` to `Size`, then `Voxel Size` to 0.025. Keep Threshold 0.005. This new control was tested through Computer Use on the positive surface; the same operation was replayed for the negative surface. Counts increased from 490/612 to 8464/9972 vertices. Blender's native length labels follow scene settings; here 0.025 numeric display units map to 0.025 angstrom. The source grid spacing remains approximately 0.1007956592 angstrom. This is display resampling, not a finer scientific calculation.

## Save, hand over and recover

Save `h2-grid.blend` with the adjacent `h2-grid.cbq` directory. Move the entire pair. The recorded pair contains seven View roots. Original and moved copies reopened in separate processes with local VDB paths, scientific hashes and refined surface settings intact. Do not start a second Blender while the current tutorial process is still running.

In a fresh disposable copy only, removal of eight `cache/render` VDB files followed by `Rebuild Selected View` for all seven Views passed through public Operator replay. Independent cold reopening after rebuilding also passed. Never remove authoritative `.npy` arrays. [Recovery receipt](../../../examples/tutorials/2.5.0/T07-recovery-check.json).

Rebuild restores the generated `Grid` resolution: reapply Size 0.025 and any custom material refinement afterward. The original refined project is unchanged. These checks do not yet prove GUI recovery or rebuilding while both original sources and the processor are unavailable; do not label that route fully offline-ready. The distributable case package and independent human acceptance remain pending.
