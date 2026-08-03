# ChemBlender 2.4.0 Stable Local Readiness

State: `Passed`

## Scope

- Branch: `release/2.4.0`.
- Qualified metadata commit: `d92b3f067b0ff87a9d1dc379c2988b5d626532d7`.
- Version: `2.4.0`.
- Blender: Blender 5.1.2 with bundled Python 3.13.
- This record covers local qualification only. Remote integration, tagging and
  publication remain separate gates.

## Artifact identity

| Property | Observed value |
| --- | --- |
| Package | `chemblender-2.4.0.zip` |
| Checksum | `chemblender-2.4.0.sha256` |
| Artifact | `chemblender-2.4.0-windows-x64` |
| Package SHA-256 | `a8d99de7246c1d06d3cb84e8b915597a3821ead2451ef0bd6a546a5c94920bcf` |
| Checksum SHA-256 | `6a7bb40dbf4b1be1c4572fe5f7d4093809b786ce8569ff682a9a8149e0aed1ff` |
| Package size | 29,976,424 bytes |
| ZIP inventory | 189 members |
| Bad CRC member | none |

The package contained only the manifest-pinned Gemmi and RDKit wheels and
their required license records. Native preflight, Extension validate/build,
ZIP safety and inventory checks, dependency inventory and artifact-size budget
all passed.

A repeated local build initially included the previous ignored checksum as an
extra ZIP member. Removing that generated input before the clean build restored
the exact 189-member package and the SHA-256 recorded above; the final package
and both verifier inputs contain no nested checksum artifact.

## Verification

| Gate | Result |
| --- | --- |
| Focused Stable/release contracts | `Passed` |
| Full Python discovery | 2,206 passed / 26 skipped / 0 failed |
| `compileall -q ChemBlender worker tests` | `Passed` |
| Generated documentation drift | `Passed` — no drift |
| Stable manifest probe | `Passed` |
| Package-CI artifact verification | `Passed` |
| Release-assets verification | `Passed` |
| Isolated installed-product smoke | `Passed` |

- Stable manifest probe: `Passed`.
- Package-CI artifact verification: `Passed`.
- Release-assets verification: `Passed`.
- Isolated installed-product smoke: `Passed`.

The installed-product test used a fresh `BLENDER_USER_RESOURCES` repository
and the exact Stable ZIP. It exercised two extension lifecycle cycles and the
representative MOL2, PDB, PQR and multi-dataset Cube Project Browser paths.
Blender exited `0` and emitted both the Project Browser Cube export and full
extension lifecycle PASS markers.

Windows retained loaded Gemmi/RDKit binary files in the isolated temporary
profile during final cleanup. Those cleanup warnings occurred after all
product assertions passed and did not affect Blender's exit status or the
verified artifact.

## Remote and publication boundary

- Remote CI: `Not Run`.
- Annotated tag: `Not Run`.
- GitHub Release: `Not Run`.

No remote result, tag or public Release is inferred from this local record.
The Stable branch must still pass exact-head PR and merge CI, exact-tag package
CI, verification-only publication and independent public asset/body checks.
