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

## Remote integration and publication

- Remote CI: `Passed`.
- PR #22: `https://github.com/psiQAQ/ChemBlender_2_x/pull/22`.
- Exact checkpoint: `a39894d38d170b29a218d9b16f38230fb8bc6987`.
- PR-head `extension-package`: run `30777435670`, `Passed`.
- PR-head `optional-qc-core`: run `30777435669`, `Passed`.
- Ordinary merge commit: `302b6efec366f1f1657663659b89e8ce526877a5`.
- Merge-head `extension-package`: run `30777713611`, `Passed`.
- Merge-head `optional-qc-core`: run `30777713610`, `Passed`.
- Checkpoint ancestry in `origin/main`: `Passed`.
- Annotated tag: `Passed`.
- Tag object: `65212c7bdee8a3e14ed86b8d7b4e2d8e989bd0cf`.
- Tag peeled commit: `302b6efec366f1f1657663659b89e8ce526877a5`.
- Exact-tag `extension-package`: run `30777953426`, `Passed`.
- Exact package artifact: ID `8842759083`, name
  `chemblender-2.4.0-windows-x64`, not expired at publication.
- Verification-only `extension-release`: run `30778221407`, `Passed`; publish
  job skipped.
- Publication `extension-release`: run `30778260789`, `Passed`.
- GitHub Release: `Passed`.
- Release ID: `363951894`.
- Release URL:
  `https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.4.0`.
- Release state: latest, non-draft and non-prerelease.

## Independent public verification

| Public asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `chemblender-2.4.0.zip` | 29,976,423 | `939d00f292ca41748870094c15a24ac6adf95f28eab293d3c55d6315d8244571` |
| `chemblender-2.4.0.sha256` | 88 | `f50e93ff8a828732a6518faac7789a2ccea00ca50e7aca5283134348228666a7` |

- Release-assets verification: `Passed`.
- ZIP inventory: 189 members; bad CRC member: none; nested checksum: none.
- Release body match: `Byte-identical` to the tagged `CHANGELOG.md` entry
  (1,431 UTF-8 bytes).

## Remaining-plan audit

The repository has no tracked `.agents/active/` or `.agents/queued/` task.
The quantum-visualization roadmap marks Phase 0–4 and all 29 ordered entries
complete. Unchecked boxes remaining in older implementation plans are
historical execution notation whose outcomes are recorded in completed
cursors, merged PRs and published Releases; they do not define approved
unfinished product work.
