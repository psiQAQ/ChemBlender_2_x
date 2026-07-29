# Hand-authored MOL2 fixtures

These fixtures are original test data dedicated to the public domain under
CC0-1.0. They exercise syntax only; coordinates and charges are hand-checked
test values, not scientific reference data.

| File | Contract |
| --- | --- |
| `small.mol2` | Two atoms, one bond, arbitrary atom/bond IDs and user charges. |
| `aromatic.mol2` | Six carbon atoms and six aromatic bonds. |
| `substructure.mol2` | Two substructures, atom assignments and root atoms. |
| `multi.mol2` | Two independent `MOLECULE` records. |
| `malformed.mol2` | Valid atom block with a bond that references atom ID 999. |
