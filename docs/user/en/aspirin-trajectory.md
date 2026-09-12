# T06: aspirin trajectory and same-frame forces

## Current candidate: refined project and verified playback

The earlier walkthrough and images below retain their original candidate binding. For the current local review use `trajectory-refined.blend` with its complete same-name `.cbq` directory in `run-009/T06`. Extension SHA-256 is `a1e2da79253d505b60daa42aa465eb725cdd1eba00e6c81ce4082102a62d0f28`; prepare wheel SHA-256 is `b736bc61ecdbee77f61696576c98092afc7352a9af16b4367bfd3c2e3159af3a`. The fixed input and scientific units below are unchanged. New [Prepare GUI checks](../../../examples/tutorials/2.5.0/T06-run009-gui-check.json) and [all-frame View checks](../../../examples/tutorials/2.5.0/T06-run009-view-check.json) bind this candidate. Large artifacts are local review files; a distributable download is still pending.

![Refined source frame 15, Cycles 2400×1800 and 256 samples](../assets/2.5-tutorials/trajectory-refined-run009.png)

Atom display scale is `0.3`, vector display scale `0.35`, atom subdivision `5` and material roughness `0.3`. A point light of power `14000` and a disk fill light of power `1800`, size `8`, improve visibility. This project uses a single Set Shade Smooth atom branch with 21,000 smooth faces. It does not use the earlier Smooth by Angle modifier. The exact manual node wiring is given under **Refine and render**. Preserve the scientific arrays: these changes improve display surfaces, not data sampling resolution. Some arrows remain occluded in this projection.

1. Open the refined `.blend` beside its `.cbq`. If the restored Image Editor covers the scene, close that secondary window. Select the force View `ChemBlender Structure.001`, then use `Load Selected View` under `Scientific Representation`. Cold loading leaves scientific playback paused.
2. Select the coordinates FrameSet in Project Browser and click `Configure Trajectory Playback`. Scroll within the ChemBlender sidebar to the scientific controls. Retain Animation Start Frame `1` and Timeline Frames Per Source Frame `1`.
3. Click `Play` below `Apply Frame`, then `Pause`. These buttons were clicked through Computer Use on this candidate. The paused capture shows timeline frame `30`, corresponding to source frame `29`; coordinates and scaled forces matched that source frame within `1e-6`.

![Actual Pause result at timeline frame 30](../assets/2.5-tutorials/trajectory-pause-run009.jpg)

`Source Frame Index (0-based)` is the static Apply Frame input. It remained `0` during the recorded playback and is not a live frame counter. A minimal later test build adds read-only `Current Source Frame`, `Energy`, `Source Index` and `Step` rows below the controls. Installed-Extension replay verified the frozen values at frames 0, 15 and 31 without changing arrays: [current-frame panel check](../../../examples/tutorials/2.5.0/T06-current-frame-panel-check.json). The new rows still require a direct GUI capture; the replay is not labeled as a new GUI operation. The [GUI playback record](../../../examples/tutorials/2.5.0/T06-run009-playback-gui-check.json) separates MCP setup from actual clicks.

The refined pair passed original and moved-copy cold reopening with source frame 15 and smoothing intact: [refinement and recovery record](../../../examples/tutorials/2.5.0/T06-run009-refined-check.json). A separate copy also rebuilt and cold reopened while the recorded extXYZ was temporarily unavailable and the processor path did not exist: [offline recovery check](../../../examples/tutorials/2.5.0/T06-run010-offline-recovery-check.json). The newer 32-frame sequence uses explicit public FRAME and render replay, followed by native VSE assembly. H.264/MPEG4 playback at 2400×1800 and 24 fps reached the end in 1.333333 seconds under browser CDP offline emulation: [animation record](../../../examples/tutorials/2.5.0/T06-run009-animation-check.json). This is not a new Ctrl+F12 GUI validation or an operating-system network-isolation test. The original assembly retains absolute paths. The review-package assembly uses `//frames-refined/` and a relative MP4 output; moved-copy cold reopening, all 32 frame hashes and re-encoding passed: [portable video record](../../../examples/tutorials/2.5.0/T06-run009-portable-video-check.json). Keep the assembly beside the complete frame folder. Physical time remains unknown.

The older `trajectory-view.blend` draft contains overlapping flat and smooth display branches; use the refined pair. Rebuild may remove custom appearance nodes, which must be reapplied. On a copy, clearing derived geometry and REBUILD restored the saved recipe at source frame 0. Use `Load Selected View`, set Source Frame Index to `15`, then `Apply Frame` before saving to restore that static preview. Coordinates and forces, View identity, unchanged arrays and subsequent cold reopening passed: [rebuild record](../../../examples/tutorials/2.5.0/T06-run009-rebuild-check.json). Custom smoothing was removed and needs reapplication. Direct GUI capture of the new scalar rows and independent human acceptance remain open.

The local `T06-review.zip` contains 92 files (121,561,147 bytes): input and license note, refined paired project, static render, 32 frames, relative video assembly, MP4, bilingual handover and evidence. SHA-256: `8eea79a46ea7967bda201619dbb066e6a2908315bdc9c884c1c4844284c8003a`. Fresh extraction passed scientific-project cold reopening and video frame-path/hash checks: [package record](../../../examples/tutorials/2.5.0/T06-run009-package-check.json). This is a local review package, not final acceptance or a bundled download in this offline page.

This is a working draft. Input conversion, all-frame scientific comparisons, actual Create View / Apply Frame / Play / Pause operations and a static render have evidence. The 32-frame PNG sequence, H.264 encoding, original/moved cold reopening and derived-geometry rebuilding also passed. Continuous screen recording, remaining GUI coverage and independent human replay are pending.

![Aspirin source frame 15 with scaled force arrows](../assets/2.5-tutorials/trajectory-frame15.png)

Gray is carbon, red is oxygen, white is hydrogen and yellow arrows show atomic forces. The input has no prepared bonds, so this view displays atoms and arrows. Some arrows overlap atoms in this projection. Light and shading change the displayed colors; this image is not a quantitative color scale.

## Fixed input and prerequisites

Complete [installation](installation.md) and [the first lesson](first-aspirin.md). Use Blender 5.1.1 and prepare 0.1.0. The accepted run-009 evidence uses Extension SHA-256 `a1e2da79253d505b60daa42aa465eb725cdd1eba00e6c81ce4082102a62d0f28`; the scalar-panel test candidate is separately bound by its receipt and is not yet the consolidated Phase 4 candidate. Download [aspirin-rmd17-32.extxyz](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz), its [source and license note](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.md), and the [frozen specification](../../../examples/tutorials/2.5.0/T06.case-spec.json). The source note contains older Quick Import instructions; use the CBQ route below for 2.5.

| Item | Reference |
| --- | --- |
| Input SHA-256 | `95ad7342776441a9ce2d524a65351dad8b8e29ab40857b4ed858d17ab71a409a` |
| Source | CC0 rMD17 v3 aspirin; NPZ rows 0, 100, …, 3100 |
| Shape | 32 frames × 21 atoms × 3 components |
| Coordinates | angstrom |
| Forces | electron_volt_per_angstrom |
| Energy | electron_volt |
| step | dimensionless array-row identifier |
| source_index | Original index; unit unknown and semantic status ambiguous |
| Physical time interval | Not supplied; label by source frame, never ps |

## Prepare the CBQ

Put the input in a new lesson folder. In Prepare, use the installed Standard runtime Python and follow these recorded steps:

1. Choose `inspect`, paste the extXYZ path into the input field and set Reader ID to `extxyz`. Click `执行` (Execute). Changing operation rearranges the form; locate the button again before clicking. Expect `success`, frame_count `32`, atomic_force and frame properties energy/source_index/step.

![Actual Prepare inspect result](../assets/2.5-tutorials/trajectory-prepare-inspect.jpg)

2. Choose `convert`, retain the input and Reader ID, set Input Type to `files` and Validation Mode to `balanced`. Enter a new output CBQ path and click `执行`. Expect `success`; the no-prepared-bonds diagnostic is consistent with the atom/arrow View below. The recorded GUI output used `gui-converted.cbq` to preserve the existing project.

![Actual Prepare convert result](../assets/2.5-tutorials/trajectory-prepare-convert.jpg)

The [GUI-output scientific check](../assets/2.5-tutorials/trajectory-gui-science-check.json) compared all 32 frames independently against the input. These equivalent public commands also passed; replace the example paths.

```powershell
chemblender-prepare inspect "D:\ChemBlenderLessons\T06\aspirin-rmd17-32.extxyz" --reader extxyz --json
chemblender-prepare convert "D:\ChemBlenderLessons\T06\aspirin-rmd17-32.extxyz" --reader extxyz -o "D:\ChemBlenderLessons\T06\aspirin-trajectory.cbq" --json
chemblender-prepare validate "D:\ChemBlenderLessons\T06\aspirin-trajectory.cbq" --json
```

Expect success and a FrameSet with `coordinates`, an `atomic_force` AtomFrameProperty, and frame properties `energy`, `step`, `source_index`. All stored coordinates, forces and numeric frame properties matched independently parsed input text exactly. Atom species/order stayed constant across all 32 frames. Preserve the ambiguous source_index status; a successful conversion does not supply missing units.

## Create and inspect the trajectory

1. In a new scene, set `CBQ Package`, confirm the path, then use `Preview CBQ` and `Import CBQ`. The recorded import added nine entities. This import reused verified public Operators through MCP; the following trajectory controls were tested through the actual GUI.
2. Select the FrameSet in Project Browser. Under `Scientific Representation`, retain `Automatic` and `Research`; the description reads `Trajectory frame`. Click `Create View`.
3. Select the `atomic_force` dataset. `Automatic` now resolves to `Trajectory with forces`. Click `Create View` again. This creates a separate View bound to the same FrameSet and its force property.
4. Hide the earlier plain trajectory View in viewport and render, retaining it in the project. Hide the default Cube in both places. Select the force View and frame it with numpad `.`. Overlapping Views at different frames can otherwise look like extra atoms.
5. In the force View controls, set `Source Frame Index (0-based)` to `15`, then click `Apply Frame`. The preview updates coordinates and force arrows together. Check frames `0` and `31` in the same way; the captures below show both endpoints after authorized public FRAME replay.

![Actual Apply Frame operation at source frame 15](../assets/2.5-tutorials/trajectory-apply-frame.jpg)

![Source frame 0 after FRAME replay](../assets/2.5-tutorials/trajectory-frame0.jpg)

![Source frame 31 after FRAME replay](../assets/2.5-tutorials/trajectory-frame31.jpg)

[Endpoint checks](../assets/2.5-tutorials/trajectory-first-last-check.json) confirm coordinates and scaled forces within display tolerance. These screenshots document the visible result; they do not represent new manual Apply Frame clicks.

The subsequent public `FRAME` replay checked all 32 frames. Display vertices and vectors matched the corresponding source arrays within `1e-6` at display precision, while authoritative arrays remained unchanged. When Vector Display Scale differs from 1, compare displayed vectors against source force multiplied by that scale. The [recorded all-frame check](../assets/2.5-tutorials/trajectory-force-check.json) used scale 1 before cosmetic refinement.

| Source frame | Energy, eV | step | source_index |
| --- | --- | --- | --- |
| 0 | -17617.8287419 | 0 | 161596 |
| 15 | -17617.4879446 | 1500 | 26491 |
| 31 | -17617.7618802 | 3100 | 151469 |

These are dataset references, not energies recomputed by Blender. In the scalar-panel test build they appear as read-only rows for the currently displayed View frame. `source_index` remains explicitly `unit unknown; ambiguous`.

## Play and pause

Scroll within the sidebar until `Play` and `Pause` appear below `Apply Frame`. Keep Animation Start Frame `1` and Timeline Frames Per Source Frame `1`. Click `Play`: the recorded timeline range became 1–32, with source frame equal to timeline frame minus one. Click `Pause` to stop both timeline and scientific playback. Twelve timestamped screenshots were sampled during actual playback; they are not a continuous recording.

`Apply Frame` previews a static source frame. The scene timeline can show another number while paused; use the source-frame control and saved View metadata when identifying that preview. A display rate of 24 fps does not establish the missing physical sampling interval or statistical independence of these selected configurations.

## Refine and render

1. On the selected force View, use `Load Selected View`, set Vector Display Scale to `0.35` and enable `Light Quantitative Colors`, then `Update Style / Parameters`. This smaller arrow scale is a display choice, not a force-unit conversion.
2. Open Geometry Nodes for the force View's `ChemBlender Ball and Stick` modifier. In its existing `CH_Ball and Stick` group, set `Subdivision` to `5`; keep source coordinates and forces intact.
3. In the same node editor, press `Shift+A`, search for `Set Shade Smooth`, and insert it after `ChemBlender Scientific Atom Material`. Wire `Group.001: Ball and Stick` → `ChemBlender Scientific Atom Geometry` → `ChemBlender Scientific Atom Material` → `Set Shade Smooth: Mesh` → `Join Geometry`. Keep the separate `ChemBlender Vector Instances` link into `Join Geometry`. Remove the old direct atom-material-to-Join link, otherwise the flat and smooth atom branches overlap and double the faces from 21,000 to 42,000.

![Retained earlier Smooth by Angle experiment; the refined project uses the node route above](../assets/2.5-tutorials/trajectory-smooth.jpg)

4. In Camera properties choose `Orthographic`, set Location `(0, -16, 11)`, Rotation X `0.968509` radians, Y/Z `0`, and Orthographic Scale `11`. Put the Point Light at `(0, -16, 11)`, Power `14000`, Radius `3`. Add an Area light named `Tutorial Fill` at `(5, 4, 8)`, Shape `Disk`, Power `1800`, Size `8`; aim it at the origin. In World properties set Background linear RGB to `(0.18, 0.18, 0.18)` and Strength `1`.
5. In Render Properties choose Cycles, Device `CPU`, Render Samples `256`, and enable denoising. In Output Properties set `2400×1800`, `100%`, File Format `PNG`. Apply source frame 15, press `F12`, then use `Image → Save As…`; save the paired `.blend` beside its complete `.cbq` directory.
6. For animation, configure playback first, press `Pause` without disabling the scientific playback flag, set Start/End to `1`/`32`, choose a new `//frames-refined/frame_` PNG output and use `Render → Render Animation` (`Ctrl+F12`). In a separate Video Editing scene use `Add → Image/Sequence`, select the 32 PNG files in filename order, set 24 fps and the same 2400×1800 size, then choose `FFmpeg Video`, container `MPEG-4`, codec `H.264`, output `//trajectory-refined.mp4`, and render the animation. This manual path matches the verified relative-path VSE project; the original assembly action was API replay, not a recorded GUI sequence.

Rebuild or Update can replace display objects. Reapply Subdivision 5 and the single Set Shade Smooth node branch after such replacement; inspect the node links before rendering. More display polygons or smoother normals do not add new scientific samples.

## Handover and recovery boundaries

The working pair is `trajectory-refined.blend` plus the complete `trajectory-refined.cbq` directory. Retain the static PNG and full PNG sequence separately. Original and relocated-copy cold reopening passed, retaining source frame 15, both Views, force scaling and the single smooth node branch. Scientific playback is disabled after loading; explicitly start it again before playing. On a separate copy, the recorded source file was temporarily renamed and the processor preference pointed to a nonexistent executable. Clearing the force View mesh and using REBUILD restored source frame 0 from local CBQ arrays; `Load Selected View` plus Apply Frame 15 restored the review preview, and an independent process cold reopened it with the source and processor still unavailable. The seven CBQ files remained byte-identical. Reapply the cosmetic node branch after rebuild; never delete authoritative `.npy` arrays as display-cache repair.

One animation attempt was cancelled while diagnosing a pre-render audit mismatch. A two-frame test showed that `render_pre` runs before source-frame updating; `render_post` matched the right frame, and animation frame 2 matched an explicit same-frame static render pixel-for-pixel. That was an evidence-timing issue, not a demonstrated product wrong-frame defect. Final acceptance must inspect completed frames and post-render checks.

See the [32-frame audit](../assets/2.5-tutorials/trajectory-animation-check.json), [video integrity record](../assets/2.5-tutorials/trajectory-video-check.json), [original/moved cold record](../assets/2.5-tutorials/trajectory-cold-recovery.json) and [display rebuild record](../assets/2.5-tutorials/trajectory-cache-recovery.json). Large frame sequences, MP4 and paired projects remain in the local case artifact directory, outside the Extension ZIP.

Human replay, continuous GUI recording and a direct capture of the new scalar frame rows remain pending. The local review package exists but is not a final distributable. [Media provenance](../assets/2.5-tutorials/provenance.json) records original captures separately from rendered images.
