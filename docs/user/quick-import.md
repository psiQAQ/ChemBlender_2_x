# Quick Import

Quick Import is the common entry point for ChemBlender's built-in readers. It
stages input first; it does not write scientific entities into the project
until you confirm Import Preview. Use it for a single file, multiple files or
drag and drop.

## Start an import

- **Single file:** open the ChemBlender sidebar, choose **Quick Import**, then
  **Select Files**, and select one file.
- **Multiple files:** select several files in the same file picker. ChemBlender
  does not scan a directory automatically.
- **Drag and drop:** drop supported files into the 3D View or Project Browser.
  File Handler input enters the same Quick Import path.
- **SMILES text:** choose **Import SMILES** and enter the text directly.

Validation defaults to **Balanced**. **Strict** rejects recoveries that
Balanced may retain with diagnostics; **Maximum** keeps more trustworthy
partial data. The selected mode never turns invalid identity data into a valid
Structure.

## Review Import Preview

Import Preview shows each source's selected reader and availability,
capabilities, quality badge and relevant scientific summary. Depending on the
format, the summary can include frames and properties, cell/PBC, records and
topology, Grid3D semantics, CIF blocks or POSCAR species.

Resolve every visible decision before confirming:

1. For a duplicate or revision conflict, choose the exact target revision when
   an update/replace action requires one.
2. For source or conformer grouping, keep **Keep Independent** unless the
   displayed evidence supports **Accept Group**. Ambiguous mappings require
   explicit review confirmation.
3. Check assumed units, partial properties, occupancies and other diagnostics.
4. Check **Default View**. The automatic planner proposes **Structure**,
   **Grid Volume** or **Signed Isosurface** only from the staged revision and
   supported Grid3D semantics.

Confirm Import Preview only after it matches your intent. The commit is atomic:
a failed validation does not leave a partly committed project.

## Cancel safely

Choose **Cancel** in Quick Import or Import Preview to stop the active job and
discard its owned staging data. Cancellation is cooperative, so a large reader
may take a moment to reach its next cancellation checkpoint. Wait until the
job disappears before starting another import. Cancelling before confirmation
does not add its staged entities or default View to the project.

After a successful import, continue in the
[Project Browser](project-browser.md). Review
[data quality](data-quality.md) before export or scientific interpretation.
