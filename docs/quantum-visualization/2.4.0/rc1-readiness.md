# ChemBlender 2.4.0-rc.1 Local Readiness

## Result

State: `Passed`.

The Windows Blender Extension candidate is locally qualified for ordinary
branch integration. This is a pre-tag snapshot: it is not exact-HEAD remote CI,
an annotated tag, or a published GitHub Release.

## Candidate Identity

| Evidence | Value |
| --- | --- |
| Baseline | `ab00bbec7551c31e41b5acacf7f8bde8bb69e52f` |
| Candidate metadata commit | `6f605d2a1c3ec18379fc60b599b78fcc0b06ed9a` |
| Qualification HEAD | `b172e37d25cb483736f90460b4ed4f9cf4777bb2` |
| Version | `2.4.0-rc.1` |
| Package | `chemblender-2.4.0-rc.1.zip` |
| Checksum | `chemblender-2.4.0-rc.1.sha256` |
| Artifact | `chemblender-2.4.0-rc.1-windows-x64` |
| Package SHA-256 | `b3df84593f79e14dc594b075c57f09f53fbed0ea75199fa1739ea8c30deb64b7` |
| Checksum SHA-256 | `d119f3cfb5b72e83ffadf20ce0b011a498e39cb07e9811fa1ef323467ea89b27` |
| Package size | 29,976,427 bytes |
| ZIP inventory | 189 members; CRC/path/type checks Passed |

The package contains the unchanged pinned RDKit `2026.3.3` and Gemmi `0.7.5`
Windows CPython 3.13 wheels. Reader API remains `1.0-rc1`; sidecar/project
schema remains `1.0`; canonical document remains `0.1`.

## Local Verification

- Release metadata and `2.4.0-rc.1` CHANGELOG extraction: `Passed`.
- Prerelease validation probe: `Passed` with Blender 5.1.2; temporary source
  tree removed and the production manifest was not rewritten.
- Standard-library suite: 2,202 passed / 26 skipped / 0 failed.
- `compileall`, generated format-document freshness and `git diff --check`:
  `Passed`.
- Native Blender 5.1.2 extension validate/build: `Passed`.
- Dependency hashes and license inventory: `Passed`.
- Package-CI artifact verification: `Passed`.
- Release-assets verification: `Passed`.
- Artifact budget: `Passed`; the canonical Windows-checkout manifest resource
  baseline is 5 bytes larger, package bytes are 5 below the previous baseline,
  and every unexplained-growth allowance remains zero.
- Isolated installed-product smoke: `Passed` under a fresh default Windows
  `TEMP`-rooted `BLENDER_USER_RESOURCES`, including two lifecycle cycles and
  representative MOL2, PDB, PQR and Cube Project Browser workflows.

Blender exited with code 0 and emitted `PASS: ChemBlender extension lifecycle`.
Its attempted in-process cleanup reported expected Windows locks for loaded
RDKit/Gemmi native libraries; the fresh profile install and process exit are
the functional gate.

## Remote And Publication Boundary

- Remote CI: `Not Run`.
- Annotated tag: `Not Run`.
- Exact-tag package CI: `Not Run`.
- `extension-release` verification/publication: `Not Run`.
- GitHub Release: `Not Run`.

The next authorized stage is ordinary push, ready PR, exact PR-head CI,
ordinary merge and exact merge-SHA CI. Creating `v2.4.0-rc.1` remains a
separate explicit authorization boundary.
