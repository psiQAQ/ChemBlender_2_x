# ChemBlender

ChemBlender turns scientific structure and calculation files into inspectable
Blender projects and views. It is **result-first** and **program-neutral**:
scientific entities, provenance, revisions and quality states belong to the
project, while Blender objects are views and rebuildable caches.

## Requirements

- Windows x64.
- Blender 5.1 or newer.
- Install the release ZIP as a Blender Extension; do not copy it into the
  legacy add-on directory.

Viewer release packages contain no scientific wheels and use Blender's bundled
NumPy. Raw-format parsing and scientific recomputation run through the separately
installed `chemblender-prepare` executable; moving that processor does not affect
already imported CBQ data, local Mesh editing, views, caches or rendering. Its
optional backends remain isolated from Blender and report availability explicitly.

## Start with a project

1. Use [Quick Import](docs/user/quick-import.md) for a single file, multiple
   files, SMILES text or drag and drop.
2. Review reader choice, quality, conflicts, grouping and the proposed default
   View in Import Preview.
3. Inspect committed sources, data and views in the
   [Project Browser](docs/user/project-browser.md).
4. Save the Blender file to publish its scientific project.

The ChemBlender 2.4.0 base format scope is XYZ/extXYZ, MOL V2000/V3000, SDF, SMILES, CIF,
POSCAR/CONTCAR, MOL2, PDB/PQR, Cube, CJSON and QCSchema. Import, export, loss
and dependency maturity differ by format; see the
[format guide](docs/user/formats.md) before relying on round-trip behavior.

## Keep the project pair together

Saving a project uses two paths: `example.blend` for Blender views and
`example.cbq/` for authoritative scientific data. The `.blend` stores a
relative link when possible. Back up and move both paths together—**keep them together**—
or the project can reopen with a missing or mismatched link.
Recovery and cache safety are covered in the
[project sidecar guide](docs/user/project-sidecar.md).

Related user guides:

- [User workflow center: import, process, visualize, export and project lifecycle](docs/user/workflows/README.md)
- [Provenance-backed workflow samples and per-file format notes](examples/user-workflows/README.md)
- [Scientific visualization SOP, Cycles images and replayable workbenches](docs/quantum-visualization/scientific-visualization/README.md)
- [ChemBlender 2.4.0 human experience review](docs/user/2.4.0-experience-review.md)
- [Data quality and diagnostics](docs/user/data-quality.md)
- [Scientific editing and topology](docs/user/scientific-editing.md)

## Development

- [Documentation index](docs/README.md)
- [Extension migration and local build](docs/migration/2.2.0-extension.md)
- [Branch and release workflow](docs/development/branch-and-release.md)
- [Quantum chemistry visualization roadmap](docs/quantum-visualization/roadmap.md)
- [中文代码架构导览](.agents/reference/code-architecture-guide.md)

Scientific dependencies belong to the external prepare environment and are not
installed into Blender or tracked as wheel files in this repository.

Project website: https://www.chemblender.com
