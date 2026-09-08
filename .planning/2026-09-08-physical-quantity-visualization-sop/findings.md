# Findings

## Starting state
- HEAD 3c80892, feat/quantum-visualization-workbench, clean. A-D completed; current task is a new expansion.
- Existing grid_volume creates VDB/Volume but no volume material. Existing density-only property surface contract is v2.
- Existing field sampling, zero-aware legends, scientific CSV, transactional rebuild and orbital image export must be reused.
- Browser groups logical views by render identity; independent duplicate views need instance identity and root ownership.
- Non-grid adapters exist but often lack public creation UI/materials. PDOS plotting, Fermi extraction and critic2 sampled-path parsing are missing.
- ECD is always unknown/AMBIGUOUS today; do not label unverified rotatory strengths as quantitative ECD. Raman source is activity.
- QCSchema gradient is a global PropertyDataset without structure_id, not directly a force vector. Explicit binding and minus sign required.

## Source and fixture decisions (research data)
- Local IOData water_sto3g_hf_g03.fchk, h2o.molden.input, ch3_hf_sto3g.fchk, nitrogen-mp2.fchk and water_sto3g_hf.wfx are real inputs. Nitrogen has SCF and MP2 RDMs; difference is MP2 minus SCF on identical affine/structure.
- cclib 07260dd0394cb1a2381d4d897746d727a12ad6ce has Gaussian/ORCA dvb IR/Raman/TD output fixtures. Existing lock .github/constraints/cclib-py313.txt; environment not installed.
- pymatgen 0428f232a569ffe6b16fa030d38ea35a56d70fd6: test-files/io/vasp/outputs/vasprun_Si_bands.xml.gz + inputs/KPOINTS_Si_bands; DOS uses fixtures/static_silicon/vasprun.xml.gz. Distinct calculations and E_F; band is 160 path points, DOS is 4^3 uniform mesh/10 irreducible points. MIT repository license. These are not evidence of converged grids.
- phonopy 2df40f4865d477f44d3b5d1ebcafc0b4af878e35 example/NaCl/{phonopy_disp.yaml,FORCE_SETS,BORN,POSCAR-unitcell,vasprun.xml-001,vasprun.xml-002}: actual VASP 4.6.35 displaced-cell data, BSD3.
- PyProcar fixed code 4a2ec9049af78fdd35b6214eef68fe40e5f356ed. HF dataset lllangWV/pyprocar_test_data at bf44809171f5228236c6a3716ba8933af08ddaeb, data/examples/fermi3d/non-spin-polarized.zip. 5,639,342 bytes, SHA256 1d079392bb1bc4dbd30606bde763bcf1f1aef6bafd3eb9a6aef3b94f25a029d5. In-memory prior audit: SrVO3, VASP6.4.3, Gamma21^3, 286 irreducible k, 20 bands, E_F=5.6990 eV, ISPIN1/ICHARG11/ISYM2, LDAUTYPE1, V U5/J0. Contains POTCAR and pickle: do not load pickle or redistribute entire package. Dataset card MIT but no package LICENSE; necessary text selection/license review pending.
- critic2 4b5dec9131c3a035af1b421d68a227c47fd641db supports ELF/LOL from WFX. Actual outputs still must be produced. FLUXPRINT/GRAPH 2/TEXT/END writes <root>_flux.txt with ordered path blocks, units and derivatives; source tests/015_grdplot/002_fluxprint_opts.cri and src/flux@proc.f90. CPREPORT JSON alone has no actual paths.
- MolecularNodes GPL3 (LICENSE.OLD not current), morbvis BSD3, PySCF Apache2 reference source initialized already; no new runtime imports from their source trees.

## Runtime
- Previous live query: Blender5.1.1 Windows, Python3.13.9, Cycles+FFmpeg, RTX4070TiSUPER OptiX, unsaved default 3-object scene. Must verify on implementation entry.
- Cache gbasis-py312 Python3.12.13, NumPy1.26.4, IOData1.0.1, GBasis0.1.0, SciPy1.16.3. Preserve existing pinned environment.
- Bundled Node has marked17.0.5; use it for offline HTML with no added doc runtime dependency.
