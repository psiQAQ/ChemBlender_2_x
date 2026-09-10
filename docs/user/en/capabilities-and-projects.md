# Capabilities and Projects

The Standard processor supports core CBQ operations, 22 registered readers subject to their declared dependencies, and 13 public export formats. Read the exact generated lists in [public-surface.json](../../prepare/public-surface.json) and [format-capabilities.json](../format-capabilities.json).

`capabilities` is the live truth for the current machine. `doctor` fails when Standard NumPy/RDKit/Gemmi is incomplete and emits concrete warnings for unconfigured optional routes, critic2, QCEngine/provider operations, or readers.

A saved project is a pair:

- `project.blend`: scenes, Blender Views, presentation and a project link.
- `project.cbq/`: authoritative scientific entities, provenance, revisions, arrays and rebuildable caches.

Keep the pair together. Import and external operations append provenance-backed entities. Mesh Apply creates a derived Structure; it does not rewrite imported coordinates. View changes never become scientific data automatically.

## Save, move and recover a project (T18)

Use **File > Save As**, enter a new `.blend` filename, then click **Save As**. ChemBlender writes the matching `.cbq` folder. Move both together; quit Blender and reopen the moved `.blend` to check the handoff. **Cancel** in the file dialog leaves the current project in place.

If only the `.blend` was moved, existing objects may still be visible while scientific data is unavailable. In the 3D Viewport press **N**, choose **ChemBlender**, and find **Project Browser**. **Project link: Missing** and **No project data** indicate that the scientific link needs recovery; visible geometry alone does not prove the project is complete.

![Project Browser reports the missing scientific project](../assets/2.5-tutorials/project-link-missing.jpg)

Click **Relink**. In the file dialog, navigate inside the matching `.cbq` folder, keep the filename **manifest.json**, and click **Recover Project Link**. Selecting an unrelated project produces `sidecar project UUID or manifest hash does not match scene link`; the existing View remains. Dismiss the error report, click **Relink** again, and select the correct manifest. Do not use **Detach** to bypass a mismatch.

![An unrelated CBQ is rejected without replacing the existing View](../assets/2.5-tutorials/project-link-mismatch.jpg)

After recovery, save the `.blend` to create its local paired `.cbq`. Quit and reopen it in a new Blender process. Check that the expected entities and Views return. Keep your original pair until this check passes.

The T18 aspirin run verified 21 atoms, unchanged entity UUID/revision, nine identical scientific arrays, GUI Save As/Cancel, rejection followed by successful Relink, and independent-process reopening of both saved pairs. Screenshots use candidate ZIP `a1e2da79…`; this is Agent evidence, with independent human acceptance still pending. Full receipts: [GUI Save As](../../../examples/tutorials/2.5.0/T18-run007-gui-save-check.json), [GUI recovery](../../../examples/tutorials/2.5.0/T18-run007-gui-relink-check.json), [cold reopen](../../../examples/tutorials/2.5.0/T18-run007-gui-pairs-cold-check.json).
