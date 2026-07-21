# Changelog

All notable changes to the maintained ChemBlender release line are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow semantic versioning.

## [Unreleased]

### Added

- Added a manually dispatched Release workflow that publishes only the exact successful tag CI artifact.
- Added deterministic ZIP, checksum, manifest, wheel, and Release asset digest verification.
- Added versioned changelog extraction so GitHub Release notes come from this file.

### Fixed

- Release verification can inspect artifacts from tags created before the Release workflow existed.
- Manifest comparison now ignores platform line-ending differences while preserving TOML field validation.

## [2.2.0] - 2026-07-21

### Added

- Added the `ChemBlender/` Blender Extension layout and `blender_manifest.toml`.
- Bundled the pinned RDKit 2026.3.3 CPython 3.13 Windows x64 wheel for offline installation.
- Added repository contracts, isolated Blender installation tests, package auditing, and Windows package CI.

### Changed

- Migrated the maintained legacy add-on to Blender's extension-native installation and module namespace.
- Reused Blender-provided NumPy and Requests; Pillow remains unbundled because ChemBlender does not use it.
- Hardened register, unregister, repeated reload, and packaged `.blend` library handling.

### Compatibility

- Blender 5.1.0 or later.
- Windows x64.

### Installation

- Download `chemblender-2.2.0.zip` and `chemblender-2.2.0.sha256` from the GitHub Release.
- Verify the checksum, then install the ZIP directly through Blender's **Install from Disk** extension action without extracting it.

### Verification

- The published ZIP is the exact artifact from the successful [`v2.2.0` package workflow](https://github.com/psiQAQ/ChemBlender_2_x/actions/runs/29789621435).
- ZIP SHA-256: `65f157c9d6af89ecc81e426ff866f4c9be5e99c713abe51e9e5d5b67bd5005a5`.
- The package passed manifest validation, clean-profile installation, RDKit 3D embedding, two extension lifecycle cycles, and both `.blend` library checks.

### Known Limitations

- Disabling the extension after RDKit has loaded may report file-removal warnings on Windows because native DLLs remain locked until Blender exits.

## [2.1.1] - 2026-07-21

### Changed

- Published the final legacy add-on release.
- Compressed `Chem_Nodes.blend` from 17,887,213 to 1,189,463 bytes.
- Compressed `Chem_Nodes_En.blend` from 17,764,762 to 1,209,480 bytes.
- Updated the legacy add-on version to 2.1.1 without adding extension packaging or runtime dependency changes.

### Verification

- Both optimized `.blend` libraries opened successfully in Blender 5.1.2 and preserved their expected objects and node groups.

## [2.1.0] - 2026-07-07

### Changed

- Imported the latest ChemBlender 2.1.0 source as commit `78c2d8d8d6361302bf8f19a568c3d7cfccde4c19`, based on upstream commit `9077096b776cd18ca85adb4b50253a0d3c18fd76`.

[Unreleased]: https://github.com/psiQAQ/ChemBlender_2_x/compare/v2.2.0...HEAD
[2.2.0]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.2.0
[2.1.1]: https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.1.1
[2.1.0]: https://github.com/psiQAQ/ChemBlender_2_x/commit/78c2d8d8d6361302bf8f19a568c3d7cfccde4c19
