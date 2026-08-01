# Formats, maturity and dependencies

ChemBlender reports format support as **F0–F5** maturity rather than a single
yes/no flag:

| Level | Evidence boundary |
| --- | --- |
| F0 | Detect the source and explain reader/dependency failures |
| F1 | Preserve structure identity, coordinates and cell where applicable |
| F2 | Preserve chemistry/site semantics such as bonds, charge, occupancy or hierarchy |
| F3 | Preserve results such as frames, properties or Grid3D values |
| F4 | Complete the Quick Import, Project Browser, View, save/reopen and diagnostic workflow |
| F5 | Export and semantic round-trip within a stated loss policy |

Maturity can differ between import and export. A readable format is not
automatically a lossless round-trip format.

## Base 2.3.0 format scope

| Format | Current product boundary |
| --- | --- |
| XYZ/extXYZ | Native import; XYZ/extXYZ export; multi-frame, typed properties, cell/PBC and validity masks where present |
| MOL V2000/V3000 | RDKit-backed import and MOL export with representability/loss checks |
| SDF | RDKit-backed multi-record import, conformer review and SDF export |
| SMILES | RDKit-backed text/file import, deterministic 3D derivation and SMILES export |
| CIF | Gemmi-backed import of crystal/site/symmetry metadata and controlled CIF export |
| POSCAR/CONTCAR | Native import/export with Direct/Cartesian, scale, selective dynamics and supported velocity data |
| MOL2 | Native multi-molecule import with atom/bond/substructure/charge annotations; export readiness is lower maturity than import |
| PDB/PQR | Native import of biological hierarchy/alternate locations or charge/radius data; no general Project Browser writer |
| Cube | Native Structure + Grid3D import and Blender Volume/Surface workflow; no lossless Cube re-export claim |
| CJSON | Lightweight structure/topology/property envelope import and controlled core export; no general Project Browser writer |
| QCSchema | Dependency-free built-in import for Molecule and AtomicResult JSON; maps Structure and supported numeric properties while preserving the complete source JSON as a raw envelope; no general Project Browser writer |

The Project Browser export workflow currently writes XYZ, extXYZ, MOL, SDF,
SMILES, CIF and POSCAR. It shows a loss preview and requires confirmation when
the selected format cannot represent source semantics. Never infer export
support merely because an import reader exists.

## Bundled and optional dependencies

Windows x64 release packages bundle exact RDKit and Gemmi wheels. RDKit serves
MOL/SDF/SMILES chemistry; Gemmi serves CIF parsing/export. Their objects stay
behind adapters and are not stored in the project or sidecar.

An **optional backend** such as cclib, IOData, ASE or pymatgen is available only
when its separately managed runtime passes availability checks. These adapters
cover additional computational-output or periodic-data sources but do not
define base-package success. A missing optional backend produces an explicit
reader availability diagnostic instead of a silent fallback.

OpenVDB files generated for Blender Volumes/Surfaces are derived caches, not a
scientific interchange format. Grid3D remains the authoritative field and can
rebuild those caches.

The generated
[format capability document](format-capabilities.json) and
[dependency document](dependencies.json) record built-in reader contracts and
pinned release-wheel facts without claiming the current machine is available.
The earlier
[reader-capability-matrix.json](../quantum-visualization/reader-capability-matrix.json)
path is generated from the same bytes for compatibility.

For project storage, read [Project and sidecar](project-sidecar.md). For
assumptions and recovered values, read [Data quality](data-quality.md).

<!-- BEGIN GENERATED FORMAT CAPABILITIES -->
## Generated format capability reference

Reader API `1.0-rc1`. Runtime availability is evaluated when a reader is selected; this table records the probe contract, not the current machine state.

| Reader | Import | Export | Runtime | Fixtures |
| --- | --- | --- | --- | --- |
| `ase-structure` (`.vasp`, `.poscar`, `.contcar`, `.extxyz`, `.xyz`, `POSCAR`, `CONTCAR`) | atomic_property=partial, crystal=supported, structure=supported | F0 / none / not_available | runtime module `ase` | ASE extXYZ, ASE POSCAR |
| `cclib_output` (`.log`, `.out`) | atomic_property=supported, energy=supported, excited_state=supported, structure=supported, trajectory=supported, vibration=supported | F0 / none / not_available | runtime module `cclib` | Gaussian output, ORCA output |
| `cif` (`.cif`) | cif_envelope=supported, crystal=supported, structure=supported | F5 / project_browser / preview_confirmation | runtime module `gemmi` | CIF crystal, CIF disorder, CIF multi-block |
| `cjson` (`.cjson`) | atomic_identity=supported, atomic_property=supported, excited_state=partial, grid=partial, orbital=partial, spectrum=partial, structure=supported, topology=supported, trajectory=partial, vibration=partial | F5 / core / controlled_envelope | built-in | CJSON result envelope |
| `cube` (`.cube`, `.cub`) | atomic_property=supported, grid=supported, structure=supported | F0 / none / not_available | built-in | Gaussian Cube, multi-dataset Cube |
| `extxyz` (`.xyz`, `.extxyz`) | properties=supported, structure=supported, trajectory=supported | F5 / project_browser / preview_confirmation | built-in | ASE extXYZ, libAtoms extXYZ, OVITO extXYZ |
| `iodata_wavefunction` (`.fchk`, `.fch`, `.molden`, `.input`) | atomic_property=supported, basis_set=supported, density_matrix=supported, orbital=supported, structure=supported | F0 / none / not_available | runtime module `iodata` | FCHK, Molden |
| `mol` (`.mol`) | atomic_identity=supported, molecular_record=supported, structure=supported, topology=supported | F5 / project_browser / preview_confirmation | runtime module `rdkit` | MOL V2000, MOL V3000 |
| `mol-v2000` (`.mol`) | atomic_identity=supported, molecular_record=supported, structure=supported, topology=supported | F5 / project_browser / preview_confirmation | runtime module `rdkit` | MOL V2000 |
| `mol2` (`.mol2`) | atomic_property=supported, multi_record=supported, structure=supported, substructure=supported, topology=supported | F5 / core / preview_confirmation | built-in | Tripos MOL2, MOL2 multi-record, MOL2 substructure |
| `pdb` (`.pdb`) | atomic_identity=supported, atomic_property=supported, crystal=partial, hierarchy=supported, multi_model=supported, structure=supported, topology=partial, trajectory=supported | F0 / none / not_available | built-in | PDB altloc, PDB CONECT, PDB multi-model |
| `poscar` (`.vasp`, `.poscar`, `.contcar`, `CONTCAR`, `POSCAR`) | atomic_property=supported, crystal=supported, structure=supported | F5 / project_browser / preview_confirmation | built-in | VASP 4, VASP 5, POSCAR velocity |
| `pqr` (`.pqr`) | atomic_identity=supported, atomic_property=supported, hierarchy=supported, structure=supported | F0 / none / not_available | built-in | PQR chain, PQR no-chain |
| `pymatgen-vasp-grid` (`.chgcar`, `.parchg`, `.elfcar`, `.locpot`, `CHGCAR`, `PARCHG`, `ELFCAR`, `LOCPOT`) | crystal=supported, grid=supported, structure=supported | F0 / none / not_available | runtime module `pymatgen` | CHGCAR, ELFCAR, LOCPOT, PARCHG |
| `pymatgen-vasprun-electronic` (`.xml`) | band_structure=supported, dos=supported, projection=partial, structure=supported | F0 / none / not_available | runtime module `pymatgen` | vasprun.xml band/DOS |
| `qcschema` (`.json`) | calculation_record=partial, energy=partial, gradient=partial, structure=supported | F5 / core / source_envelope | built-in | QCSchema AtomicResult, QCSchema Molecule |
| `sdf` (`.sdf`) | atomic_identity=supported, molecular_record=supported, record_property=partial, structure=supported, topology=supported | F5 / project_browser / preview_confirmation | runtime module `rdkit` | SDF malformed-record recovery, SDF multi-record |
| `smiles` (`.smi`, `.smiles`) | atomic_identity=supported, molecular_record=supported, structure=supported, topology=supported | F5 / project_browser / preview_confirmation | runtime module `rdkit` | SMILES file, SMILES text |
| `xyz` (`.xyz`) | structure=supported, trajectory=supported | F4 / project_browser / single_structure_coordinates_only | built-in | XYZ single-frame, XYZ trajectory |
<!-- END GENERATED FORMAT CAPABILITIES -->
