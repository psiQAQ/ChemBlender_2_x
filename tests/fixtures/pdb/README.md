# PDB syntax fixtures

- `atom-hetatm.pdb`: exact ATOM/HETATM columns, altloc, insertion code,
  authoritative element/charge, and missing or invalid element-column recovery.
- `altloc.pdb`: two alternate locations for the same atom site.
- `multimodel.pdb`: MODEL/ENDMDL grouping and a TER segment boundary.
- `conect.pdb`: CONECT records before atoms, reciprocal multiplicity, and
  connectivity with unknown order.
- `cryst1.pdb`: CRYST1 cell parameters, declared space group, and Z value.
- `malformed.pdb`: short atom row, unresolved element, and mismatched model
  markers with recoverable atoms.
