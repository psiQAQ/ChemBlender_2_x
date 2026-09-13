# SrVO3 uniform-k-mesh VASP text bundle

Source dataset: `lllangWV/pyprocar_test_data`

- Pinned commit: `bf44809171f5228236c6a3716ba8933af08ddaeb`
- Source archive: `data/examples/fermi3d/non-spin-polarized.zip`
- Archive SHA-256: `1d079392bb1bc4dbd30606bde763bcf1f1aef6bafd3eb9a6aef3b94f25a029d5`
- Dataset card SHA-256: `687ae78d0ebbb60e127bc33e136f5dcb8493b3c27c9789e9448273f91f83be77`
- Declared license: MIT (`dataset-card.md` preserves the pinned source metadata)
- Repository inclusion approved by the user on 2026-09-13 for the ChemBlender 2.5 offline tutorial.

Only `IBZKPT`, `INCAR`, `KPOINTS`, `OUTCAR`, `POSCAR`, and `PROCAR` are copied verbatim from the pinned archive. `POTCAR`, `WAVECAR`, `CHGCAR`, `vaspout.h5`, `ebs.pkl`, `structure.pkl`, and every other archive member are excluded. ChemBlender reads only the six listed text files and never performs POTCAR lookup or pickle loading.

This provenance record preserves the upstream MIT declaration and source identity; it does not claim that ChemBlender produced the VASP calculation or owns third-party copyrights.
