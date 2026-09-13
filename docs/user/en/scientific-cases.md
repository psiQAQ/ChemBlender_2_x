# Scientific case gallery

This chapter covers T03, T05, T08–T16, T19, T20 and B01 with the current local candidate. Download the [review package](../../offline/artifacts/scientific-viewer-review.zip) (SHA-256 `4d921d21c475c0ae11acd25cc5f76d9552643d8a98f7a791968d5b7d1827483e`). It contains 22 directories; each keeps `project.blend` beside its complete `project.cbq/` and native PNG render. Imported sources are deliberately absent. Every pair passed separate-process cold reopen and `Rebuild Selected View` without the processor.

Exact common Viewer steps: extract without renaming members, open `project.blend`, confirm Project Browser says connected, select the entity or View, then use `Scientific Representation` → the named preset → `Research` → `Create View`. For recovery select the View and click `Rebuild Selected View`; never delete `project.cbq/arrays/*.npy`. These are native background Blender results, not direct mouse/keyboard captures or independent human acceptance.

| Case | Fixed input and exact route | Visible result and scientific boundary | Evidence |
| --- | --- | --- | --- |
| T03 | SMILES `CCO`; Prepare GUI `derive`, operation `molecule.conformers`, parameters `{"count":3,"force_field":"MMFF94"}`, then `validate`; Viewer `Structure publication` for each Structure. | Three retained conformers. MMFF94 ranks this run; it is not electronic energy. | [Receipt](../../../examples/tutorials/2.5.0/T03-current-candidate-check.json) |
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

Linked spectrum labels are smaller than a dedicated plot render. Direct GUI capture remains pending for every case in this chapter, and independent review remains unsigned.
