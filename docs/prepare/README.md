# ChemBlender Prepare

Convert quantum chemistry results into validated, self-contained CBQ packages for the ChemBlender Viewer. The external Python package owns file parsing, scientific derivation and scientific format export. Blender uses the same `cbq_core` model and renders prepared CBQ data.

From this repository, use `uv sync --frozen --extra formats`, then `uv run --frozen chemblender-prepare formats`. The `formats` extra supplies RDKit and Gemmi for molecular and crystal formats. NumPy is the only base runtime dependency. Additional scientific backends are installed in their documented isolated environments.

Run `uv run --frozen chemblender-prepare --help` for CLI commands, or `uv run --frozen chemblender-prepare-gui` for the Tkinter interface. Tk must be available in the chosen Python installation. Preparation runs outside Blender; the Extension does not install these dependencies.

This source tree is prepared for a future independent PyPI distribution. No PyPI publication has been performed.

Cube export requires an explicit `--dataset-index` for a grid containing multiple datasets. The GUI leaves this field blank until selected; preview and export both reject an unset selection. A scalar grid can be exported without the option. Conversion with `--preset` and `--unit` also requires an explicit `--dataset-index` for multiple datasets. Blank GUI selection does not select dataset zero. A single dataset uses index zero when omitted; conversion without interpretation retains the original multi-dataset grid.


`inspect POSCAR` reports the bounded comment, scale, scientific cell in angstrom, cell volume in cubic angstrom, species/count groups, coordinate convention, selective-dynamics and velocity-block presence. Missing VASP 4 species are flagged before conversion. Inspection does not publish a CBQ; the full original comment remains in conversion provenance. The GUI displays the same report through its `inspect` command.

### VASP 4 element assignment

VASP 4 POSCAR files contain count groups without element symbols. Supply their actual ordered symbols; the converter does not infer them from the comment or filename. For example, only when the two groups are sodium and chlorine:

```text
chemblender-prepare convert POSCAR --reader poscar --param species=Na,Cl -o structure.cbq
```

In the GUI, select `convert` and reader `poscar`, then enter `species=Na,Cl` in Advanced reader parameters. Missing or invalid assignments fail without publishing a CBQ. To retain an existing package while preparing another interpretation, use `--project existing.cbq` and a different output directory. The original package is preserved.

Export preview succeeds without creating a file. If the preview requires loss confirmation, an export without `--confirm-loss` returns an error and creates no output; the GUI reports the same failure. Review the omitted fields before confirming. This also applies to PDB, MOL2 and PQR exports.

For a `ConformerSet`, explicitly select SDF (`--format sdf`). Other formats are rejected with a diagnostic; the tool does not silently change the requested file format. A selected `MolecularRecord` retains your explicit MOL/SDF/SMILES format. Changing GUI inputs clears loss confirmation and switches back to preview mode; click Run to obtain the updated preview before confirming export.

### Crystal export options

The GUI exposes these controls when the corresponding export format is selected. Blank fields preserve the existing exporter defaults. Preview reports omitted fields before `--confirm-loss` permits export. Format changes do not forward hidden settings.

| CLI option | Default when unspecified | Meaning |
| --- | --- | --- |
| `--cif-mode` | Preserve when a source envelope exists, otherwise normalized | `preserve` or `normalized`; normalized output may omit unknown source content |
| `--poscar-comment` | Existing exporter default | Single-line output comment |
| `--poscar-coordinate-mode` | Existing exporter default | `direct` or `cartesian` |
| `--poscar-scale-policy` | Existing exporter default | `unit`, `preserve_source`, or `target_volume` |
| `--poscar-target-volume` | Unset | Positive volume in Å³; must match the scientific cell, not resize it |
| `--poscar-source-scale` | Unset | Explicit nonzero source scale for `preserve_source` |
| `--poscar-include-selective-dynamics` / `--no-poscar-include-selective-dynamics` | Preserve constraints | Include or explicitly omit selective-dynamics flags |
| `--poscar-velocity-mode` | Existing exporter default | `direct` or `cartesian` velocity coordinates |

Setting any POSCAR option constructs the existing validated `PoscarExportSettings`; fields not supplied use that model's defaults. These controls change serialization, never the authoritative CBQ cell or coordinates.

CIF `inspect` reports the total and valid block counts, site counts, cells with units, and parser diagnostics. Preview lists are limited to 100 blocks and 100 diagnostics; totals indicate omitted entries. `convert` preserves every valid structure and its source-local block binding in one CBQ, including the original CIF envelope. It does not silently select the first block. Choose the prepared structure to display in Blender. Blocks without importable atom sites remain in the source envelope and are diagnosed, not turned into invented structures. Gemmi is needed only in the external environment.

MOL2 `inspect` reports molecule/atom counts, `interpreted_bond_count`, molecule and charge types, partial-charge coverage, unsupported sections and bounded diagnostics. Unsupported bond types can leave usable atoms with no interpreted topology; a successful inspection does not mean every source field is supported. The GUI Inspect action runs this same CLI in its child process.

extXYZ `inspect` uses the reader preview staging path and reports frame counts, atom/frame properties, cell availability, PBC changes and assumed units. Its summary does not materialize scientific array values. Staging is discarded after inspection, including failures.

### PubChem Python preparation

`chemblender_prepare.pubchem_import` preserves the existing explicit PubChem staging API outside Blender: `stage_pubchem_import(query, session)`, `verified_pubchem_parameters(path, session)` and `attach_verified_pubchem_provenance(...)`. It verifies owned session paths, URL/CID metadata and input hashes before attaching provenance. `file_import_request` and `smiles_import_request` create requests for the external Python import pipeline.

The default HTTP reader uses Python's standard library, a 30-second request timeout and a 64 MiB response limit. No `requests` dependency is needed. Tests use controlled responses; live PubChem, GUI/CLI integration and cancellation within two seconds during blocking HTTP remain pending. A staged SDF is an intermediate input: parse, verify and publish CBQ through the external pipeline before importing it into Blender. No Viewer network permission or automatic fetch is added.

The optional callable `is_cancelled` is checked before lookup, between HTTP requests, after download and before returning the staged request. Cancellation raises `concurrent.futures.CancelledError`. Failed or cancelled writes remove only files created by that call; cleanup errors are attached to the original exception. These checkpoints do not interrupt an in-flight blocking HTTP read.

GUI convert exposes the same validation modes as the CLI: strict, balanced (default), and maximum. The selected mode is forwarded to every reader worker in a multi-file conversion; invalid modes are rejected before launching a process. Add multiple source paths on separate lines. Reader selection uses content sniffing when the suffix is unknown. Conversion publishes one verified CBQ only after every selected source succeeds; this is distinct from the external Python preflight/confirmation API.

In the development Viewer, Scientific View > Representation > Automatic uses the prepared grid's semantic role and completeness status. Complete MO, spin density, difference density and ESP select signed isosurfaces; electron density, generic scalar fields and unconfirmed fields default to volume display. RDG retains its NCI surface option and requires a compatible coloring field. An explicitly selected representation is preserved. This selection uses metadata only; creating or rebuilding the geometry still requires the panel action. Runtime rendering acceptance for this revised automatic selection remains pending.

Local editing regression: run `.venv/Scripts/python.exe -m unittest tests.test_mesh_edit -q`. When Blender 5.1 is available (or set BLENDER_EXECUTABLE), this launches a private factory-startup profile and exercises the actual Select Element, Set Atoms, Set Bonds and Measure operators, including initially missing BMesh attribute layers. The check blocks imports of RDKit, Gemmi and the external processor. It tests local Mesh drafts, not scientific Apply publication or the external optimization loop.

### Inline SMILES preparation

```text
chemblender-prepare convert --smiles-text "CO" --validation-mode strict -o methanol.cbq
```

In the GUI, choose `convert`, set input type to `smiles`, enter the text, choose a validation mode and output directory, then click Run. The GUI launches the external CLI and displays its progress and diagnostics. File paths and hidden reader-specific parameters are ignored in this mode; the CLI rejects mixing file inputs with `--smiles-text`.

This conversion uses the existing RDKit SMILES reader and generates planar two-dimensional coordinates, reported as `smiles.planar_2d_generated`. It is not a 3D conformer calculation or an optimized quantum-chemical geometry. CBQ records `inline:smiles`, the text hash, angstrom coordinates and molecular identity. Invalid input and cancellation do not publish a CBQ. RDKit must be available in the external environment; this path does not install packages or execute inside Blender.

If Blender reports “CBQ imported, but its interface needs refresh”, the scientific import has already committed. Existing and newly imported entities remain in the project, and the consumed preview is cleared. Refresh the Project Browser before choosing a representation; do not interpret this warning as a cancelled import or repeat the conversion.

On Windows, a reader may briefly hold progress.json open. Permission errors updating this advisory progress file are retried on the next progress update; cancellation is still checked before and after the attempt. CBQ and final result publication errors remain fatal and are not treated as progress-file conflicts.

For `derive --operation wavefunction.esp_from_orbitals_grid`, provide four `--input` UUIDs in order: Structure, BasisSet, OrbitalSet, and the structure-bound effective nuclear-charge AtomicProperty. Parameters must include `density_level` (`scf` or `post_scf`), grid `origin`, `step_vectors`, and `shape`; `chunk_size` bounds evaluation blocks. The operation derives the total density matrix and ESP grid together and publishes both in a new CBQ. Missing charges or density level are rejected; atomic numbers do not replace effective ECP charges. The source CBQ remains unchanged. Actual numerical evaluation requires the external scientific backend.

Real wavefunction regression can be run in the existing GBasis environment with `python -m unittest tests.test_wavefunction_grid tests.test_wavefunction_observables tests.test_prepare_cli.PrepareCLITests.test_real_fchk_mo_derive_uses_existing_numerics -v`. It covers real FCHK numerical evaluation and CLI MO/ESP publication and reopening. IOData and GBasis are required; inspect skip counts. Integration passes do not replace Blender panel, rendering or lifecycle acceptance. Integral reference values are finite-grid regression baselines, not a claim that domain and grid convergence is complete.
