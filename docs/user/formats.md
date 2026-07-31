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

The machine-readable
[reader capability matrix](../quantum-visualization/reader-capability-matrix.json)
is the source of built-in reader availability and dependency contracts.

For project storage, read [Project and sidecar](project-sidecar.md). For
assumptions and recovered values, read [Data quality](data-quality.md).
