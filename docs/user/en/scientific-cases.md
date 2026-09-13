# Scientific case gallery

This chapter covers T03, T05, T08–T16, T19, T20 and B01 with the current local candidate. Download the [review package](../../offline/artifacts/scientific-viewer-review.zip) (SHA-256 `4d921d21c475c0ae11acd25cc5f76d9552643d8a98f7a791968d5b7d1827483e`). It contains 22 directories; each keeps `project.blend` beside its complete `project.cbq/` and native PNG render. Imported sources are deliberately absent. Every pair passed separate-process cold reopen and `Rebuild Selected View` without the processor.

Exact common Viewer steps: extract without renaming members, open `project.blend`, confirm Project Browser says connected, select the entity or View, then use `Scientific Representation` → the named preset → `Research` → `Create View`. For recovery select the View and click `Rebuild Selected View`; never delete `project.cbq/arrays/*.npy`. These are native background Blender results, not direct mouse/keyboard captures or independent human acceptance.

| Case | Fixed input and exact route | Visible result and scientific boundary | Evidence |
| --- | --- | --- | --- |
| T03 | Prepare GUI `Convert`: `mixed-properties.sdf`, reader `sdf`; `Inspect`; `Review Conformer candidate`; check `Reviewed`; `Derive`; export the ConformerSet to SDF and reimport it. In Viewer select each Structure and use `Structure publication`. | Three source records stay independent; the explicit confirmation adds one ambiguous 3-frame ConformerSet with identity mappings. `ccd-3d-showcase.sdf` yields zero suggestions. T02, not T03, owns SMILES/MMFF94 generation. | [Receipt](../../../examples/tutorials/2.5.0/T03-current-candidate-check.json) |
| T05 | Fixed PDB/PQR/MOL2; Prepare GUI `convert`; Viewer `Trajectory frame` for PDB and `Atomic scalar` for PQR/MOL2 charge. | PDB model order, PQR charge/radius and MOL2 hierarchy remain distinct; atom-indexing does not make fields equivalent. | [Receipt](../../../examples/tutorials/2.5.0/T05-current-candidate-check.json) |
| T08 | Fixed FCHK/Molden through `python.wavefunction`; recorded `33³`, `0.25 bohr` HOMO/LUMO grids; `Signed scalar isosurface`, `+0.03/-0.03`. | Both phases are visible. Finite-box normalization is not a full-space proof. | [Receipt](../../../examples/tutorials/2.5.0/T08-current-candidate-check.json) |
| T09 | Fixed water/CH3/N2 FCHK; select CH3 spin density and `Signed scalar isosurface`. | Signed spin density remains signed; total, spin and post-SCF-minus-SCF densities are separate datasets. | [Receipt](../../../examples/tutorials/2.5.0/T09-current-candidate-check.json) |
| T10 | Fixed water density and ESP with the same Structure and affine grid; `Property on surface`. | ESP colors the density isosurface; ESP is not the isovalue. A nuclear-singularity probe is rejected. | [Receipt](../../../examples/tutorials/2.5.0/T10-current-candidate-check.json) |
| T11 | Fixed Gaussian/ORCA output through `python.scientific`; `Vibration mode`, selection index `1`, `Apply Phase`; separately `Spectrum plot`. | IR/Raman source fields remain distinct. Phase is animation phase, not physical time. | [Receipt](../../../examples/tutorials/2.5.0/T11-current-candidate-check.json) |
| T12 | Fixed Gaussian/ORCA TD output; `Spectrum plot` for UV–Vis/ECD; `Electronic spectrum linked` only for complete Gaussian states. | Gaussian ECD retains verified length gauge/unit. ORCA missing gauge/unit stays unknown and uses spectrum-only View. | [Receipt](../../../examples/tutorials/2.5.0/T12-current-candidate-check.json) |
| T13 | Fixed silicon band + KPOINTS and independent DOS calculation through `python.scientific`; `Band structure` or `Density of states`; reference `absolute`. | Declared k path is retained. Different Structures/Fermi levels are not silently aligned or merged. | [Receipt](../../../examples/tutorials/2.5.0/T13-current-candidate-check.json) |
| T14 | Fixed six-file NaCl phonopy input; `Phonon mode`, q-point index `1`, mode index `0`, then phase preview. | Complex periodic mode phase is shown; it is not elapsed time. | [Receipt](../../../examples/tutorials/2.5.0/T14-current-candidate-check.json) |
| T15 | Fixed critic2 JSON/NCI output; `Topology graph` and `NCI surface`. | Five critical points/four ordered paths and the paired 40³ field are shown; no missing path or bond energy is invented. | [Receipt](../../../examples/tutorials/2.5.0/T15-current-candidate-check.json) |
| T16 | MIT-declared SrVO3 six-text-file allowlist through `python.fermi`; `Fermi surface`. | Bands 16–18 on the declared 21³ Gamma mesh. POTCAR/WAVECAR/CHG/HDF5/pickle are excluded. | [Receipt](../../../examples/tutorials/2.5.0/T16-current-candidate-check.json) |
| T19 | Explicit external Python register/discover/conformance route; Viewer `Structure publication`. | External Reader API works without being added to the ordinary 22-reader GUI list. | [Receipt](../../../examples/tutorials/2.5.0/T19-current-candidate-check.json) |
| T20 | `qcschema.compute@1` through `python.qcschema`; select gradient and `Atomic vector`. | Real PySCF 2.13.1 RHF/cc-pVDZ energy `-76.0214183672713 Eh`; exchange validation alone is not compute success. | [Receipt](../../../examples/tutorials/2.5.0/T20-current-candidate-check.json) |
| B01 | With no provider credential/live transport, Prepare GUI `capabilities` then `doctor`; also test Cancel. | Provider unavailable, no network request and no output. This negative boundary has no scientific render/project by design. | [Receipt](../../../examples/tutorials/2.5.0/B01-current-candidate-check.json) |

## T03 direct-GUI walkthrough

1. In Prepare `Convert`, choose `examples/user-workflows/inputs/sdf/mixed-properties.sdf`, set reader `sdf`, set an output `.cbq`, and click `Run`.
2. Switch to `Inspect`, select that CBQ, and click `Run`. Open `Review Conformer candidate`; verify three records, mapping `[0, 1, 2]` for each record, and the symmetric-isomorphism warning.
3. Check `Reviewed`, choose a new output CBQ, and click `Derive`. The result must contain a `ConformerSet` with shape `[3, 3, 3]`, unit `angstrom`, status `ambiguous`, while all three source Structures remain present.
4. In `Export`, select the ConformerSet, choose `sdf`, first run Preview and then Write. Convert the written SDF back to CBQ and run `validate` on both CBQs.
5. Convert `ccd-3d-showcase.sdf`, inspect it, and click `Review Conformer candidate`. The visible result must say `conformer_suggestion_count: 0` and refuse review.
6. Keep `project.blend` beside `project.cbq/`, open it in Blender, confirm three Project Browser entries, select the first Structure, and press F12. For recovery, remove access to the imported source, cold-open the pair, select each View, and click `Rebuild Selected View` without a processor.

![T03 mapping and ambiguity warning](../assets/2.5-tutorials/scientific/t03-prepare-mapping-current.png)

![T03 different-molecule rejection](../assets/2.5-tutorials/scientific/t03-negative-rejected-current.png)

![T03 current Project Browser](../assets/2.5-tutorials/scientific/t03-project-browser-current.png)

![T03 current F12 result](../assets/2.5-tutorials/scientific/t03-f12-current.png)

The final F12 used the camera matrix already recorded in the native render receipt. Restoring that matrix and render visibility was an authorized MCP support action and is not labeled as a direct GUI click; opening the final installed candidate, inspecting Project Browser, pressing F12, inspecting the result, and quitting without saving were direct OS-GUI actions. The technical checker passes; independent human review remains unsigned.

## Native render gallery

![T03 conformers](../assets/2.5-tutorials/scientific/t03-conformers.png)

![T05 PDB models](../assets/2.5-tutorials/scientific/t05-pdb-models.png)

![T08 FCHK HOMO phases](../assets/2.5-tutorials/scientific/t08-fchk-homo.png)

![T09 signed spin density](../assets/2.5-tutorials/scientific/t09-spin-density.png)

![T10 density surface colored by ESP](../assets/2.5-tutorials/scientific/t10-density-esp.png)

![T11 vibration mode](../assets/2.5-tutorials/scientific/t11-vibration.png)

![T11 Gaussian IR linked View](../assets/2.5-tutorials/scientific/t11-gaussian-ir.png)

![T12 UV–Vis](../assets/2.5-tutorials/scientific/t12-gaussian-uvvis.png)

![T12 ECD](../assets/2.5-tutorials/scientific/t12-gaussian-ecd.png)

![T13 absolute-energy bands](../assets/2.5-tutorials/scientific/t13-bands.png)

![T14 NaCl phonon mode](../assets/2.5-tutorials/scientific/t14-phonon.png)

![T15 QTAIM](../assets/2.5-tutorials/scientific/t15-qtaim.png)

![T15 NCI](../assets/2.5-tutorials/scientific/t15-nci.png)

![T16 SrVO3 Fermi surface](../assets/2.5-tutorials/scientific/t16-fermi.png)

![T19 external Reader API result](../assets/2.5-tutorials/scientific/t19-reader-api.png)

![T20 QCSchema gradient](../assets/2.5-tutorials/scientific/t20-qcschema-gradient.png)

Linked spectrum labels are smaller than a dedicated plot render. T03 now has current direct Prepare/Blender GUI captures; the other cases still require their case-specific direct GUI pass. Independent review remains unsigned for every case.
