# ChemBlender 2.3.0 Wave 1 RDKit Tasks 2–8 Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` and
> `superpowers:test-driven-development`. Complete the first non-completed row,
> persist its evidence, and never skip ahead to Cube.

**Goal:** Complete the native RDKit-backed MOL/SDF/SMILES adapter, readers,
grouping, derivation, exporters and product UI without persisting an RDKit Mol
or loading RDKit during module import.

**Architecture:** Keep `QCProject` entities authoritative. RDKit is a
function-local parser/writer/derivation dependency. Every import uses the
Reader API and the completed host source-revision binding boundary; every
export reconstructs a temporary RDKit Mol from immutable project entities.

**Baseline:** `9477fdb8f79349d2c58a6e508e1493aadcd0c59a`

## Task Table

| Task | State | Implementation commit | Review status |
|---|---|---|---|
| 2 Shared adapter | completed | `4ae1e027`, `a9e12c01`, `d74f10ff`, `b0537e5b` | SPEC PASS; QUALITY PASS |
| 3 MOL reader | completed | `ef57adc2`, `5acfdf46` | SPEC PASS; QUALITY PASS |
| 4 SDF reader/recovery | completed | `8f69e7bd`, `4df0b809`, `f926da2b`, `0e9f776`, `dffaa85`, `bc32578`, `4d45697`, `344fa2c` | SPEC PASS; QUALITY PASS |
| 5 Conformer grouping | in_progress | — | — |
| 6 SMILES/3D | pending | — | — |
| 7 Exporters | pending | — | — |
| 8 UI/performance | pending | — | — |

## Global Constraints

- Execute Tasks 2–8 in order; each task has a RED, implementation commit,
  focused/full verification, independent specification and quality reviews,
  and a cursor checkpoint.
- Use Blender 5.1.2 bundled Python and pinned RDKit 2026.3.3.
- Keep RDKit imports function-local. `ChemBlender.core` and
  `ChemBlender.reader_api` imports must not load RDKit.
- Never persist an RDKit Mol in project, sidecar or canonical documents.
- Do not add dependencies, modify release metadata/workflows, start Cube,
  publish, or push.
- Preserve Reader API/canonical 0.1 and project/sidecar 0.2.

## Task 2 — Shared RDKit Molecule Adapter

**Files:** Create `ChemBlender/core/formats/rdkit_common.py` and
`tests/test_rdkit_common_adapter.py`; modify `core/formats/__init__.py`,
model validation or the architecture guide only when the implemented
responsibility requires it.

**Interfaces:** Internal frozen `RDKitMoleculeContext` and
`RDKitMoleculeAdaptation`; `adapt_rdkit_molecule(mol, raw_block, context)`.

**Scientific invariants:** Preserve exact raw bytes; always keep explicit-file
topology; sanitize a copy; emit a second sanitized topology only for a material
interpretation change; retain raw entities with `mol.sanitize_failed`; preserve
isotope, charge, map, names, atom chirality, bond order/aromaticity/stereo;
accept 2D as planar, accept 3D, never invent missing coordinates; deterministic
IDs/revisions/provenance; never persist RDKit objects.

**RED tests:** Charged, isotopic, atom-mapped, aromatic, tetrahedral/bond
stereo, unsanitized/sanitize-failed, 2D, 3D, missing-conformer, zero-bond and
optional-import isolation fixtures.

**Implementation steps:** Add frozen private context/result types; lazy-import
RDKit in the adapter; copy before sanitization; map identity/topology and
coordinates into current models; issue stable diagnostics; derive deterministic
identities from source binding and exact raw input.

**Focused tests:** `tests.test_rdkit_common_adapter`,
`tests.test_chemical_identity_records`, `tests.test_topology_record`,
Reader API bridge and optional-import contracts under Blender Python.

**Full regression:** Full discovery, `compileall`, `git diff --check`.

**Blender validation:** Pinned RDKit 2026.3.3 fixture matrix; no Blender UI
changes in this task.

**Review boundary:** Independent specification and code-quality review before
checkpoint; fix all Critical/Important/task-related Minor findings.

**Commit message:** `feat: add shared RDKit molecule adapter`

**Next task:** Task 3 — MOL V2000/V3000 reader.

## Task 3 — MOL V2000/V3000 Reader

**Files:** Create `ChemBlender/core/formats/mol.py`,
`tests/test_mol_reader.py`, `tests/fixtures/mol/README.md` and real V2000/V3000
fixtures; modify reader catalog, `core/mol_v2000.py`, capability matrix,
architecture guide and documentation contract as needed.

**Interfaces:** Primary reader ID `mol`, version `2`, with structure, topology,
atomic-identity and molecular-record capabilities; deprecated V2000-only
`mol-v2000` alias delegates to the primary implementation.

**Scientific invariants:** Content sniff V2000/V3000 exactly; reject ordinary
text and SDF delimiters; preserve source bytes/newlines; diagnose decode
replacement; reject multiple records; bind complete record/source identity;
preserve all adapter entities and exact created-ID accounting.

**RED tests:** V2000/V3000 sniff and parse, `.mol` false positives, SDF
disambiguation, BOM/non-UTF8 diagnostic, multi-record rejection, alias
restriction/deprecation, sidecar reopen and default Structure View.

**Implementation steps:** Detect block version from bytes; call the Task 2
adapter; add catalog descriptor/capabilities; turn the legacy parser into a
thin compatibility wrapper; add real writer fixtures.

**Focused tests:** `tests.test_mol_reader`, adapter, reader catalog/bridge,
sidecar and Structure View contracts.

**Full regression:** Full discovery, compile and diff checks.

**Blender validation:** Quick Import V2000/V3000, save/reopen and default view.

**Review boundary:** Two independent reviews before checkpoint.

**Commit message:** `feat: add native MOL V2000 and V3000 reader`

**Next task:** Task 4 — recoverable multi-record SDF reader.

## Task 4 — Multi-record SDF Reader and Recovery

**Files:** Create `ChemBlender/core/formats/sdf.py`,
`tests/test_sdf_reader.py`, `tests/fixtures/sdf/README.md` and fixtures for
valid/malformed/mixed-property/duplicate/empty/mixed-version/CRLF/missing-final
delimiter/large indexed inputs; update catalog/docs as responsibilities change.

**Interfaces:** Reader ID `sdf`; byte-oriented bounded record iterator and
stable source-local record index/hash/key; raw and unambiguous typed property
columns.

**Scientific invariants:** Treat only a standalone `$$$$` line as delimiter;
retain exact MOL-block bytes and ordered duplicate/empty SD strings; establish
boundaries before RDKit; never silently skip `None`; Balanced Recovery retains
valid indices around a malformed record; do not merge records; Partial columns
use masks; stream with cancellation and staging cleanup.

**RED tests:** Required fixture matrix, MOL/SDF sniff separation, invalid middle
record, raw property fidelity, typed/mixed/missing columns, stable identities,
cancellation cleanup and 10k indexing.

**Implementation steps:** Build one bounded byte scanner and offsets; adapt
records independently; parse SD lexemes without overwriting raw data; build
columns only after unambiguous inference; introduce controlled blob/index
storage only if measured raw-block scaling requires it.

**Focused tests:** SDF reader, adapter, import preview, records, sidecar and
reader catalog.

**Full regression:** Full discovery and static checks.

**Blender validation:** Valid/malformed/mixed-property multi-record imports.

**Review boundary:** Two reviews plus measured 10k indexing evidence.

**Commit message:** `feat: add recoverable multi-record SDF reader`

**Next task:** Task 5 — conformer grouping.

## Task 5 — Intelligent SDF Conformer Grouping

**Files:** Create
`ChemBlender/core/import_pipeline/conformer_grouping.py` and
`tests/test_sdf_conformer_grouping.py`; modify existing grouping/transaction
and preview decision contracts only as required.

**Interfaces:** Immutable `suggest_conformer_groups(records)` results and an
explicit accept conversion to `ConformerSet`.

**Scientific invariants:** Never auto-group; prefer complete unique atom maps,
then canonical ranks/isomorphism with deterministic ties; finally require exact
elements, explicit topology, bond order, aromaticity, charges, isotopes and
stereo; atom count alone is insufficient; acceptance reorders coordinates and
property columns consistently and records evidence/provenance; stale
suggestions fail closed.

**RED tests:** Reordered equivalent records, atom-map precedence, differing
charge/bond/stereo/isotope rejection, ambiguous symmetry/review, acceptance,
stale snapshot, cancellation and atomic failure.

**Implementation steps:** Add private matching/evidence functions; produce
immutable suggestions; reuse current ImportCommitDecisions snapshot contract;
construct a ConformerSet only after acceptance.

**Focused tests:** Grouping, project transaction/model and preview decisions.

**Full regression:** Full discovery and static checks.

**Blender validation:** Core suggestion path only; UI completion is Task 8.

**Review boundary:** Two independent reviews before checkpoint.

**Commit message:** `feat: suggest and confirm SDF conformer groups`

**Next task:** Task 6 — SMILES source and deterministic 3D.

## Task 6 — SMILES Source and Deterministic 3D

**Files:** Create `ChemBlender/core/formats/smiles.py`,
`ChemBlender/core/derivations/__init__.py`,
`ChemBlender/core/derivations/smiles_3d.py`,
`tests/test_smiles_reader.py`, `tests/test_smiles_3d.py`; update catalog,
capability matrix and architecture docs as needed.

**Interfaces:** `parse_smiles_text()` and `derive_smiles_3d()` through the
unified source/preview model.

**Scientific invariants:** Preserve exact source text and text/smiles source
semantics without persisting random TEMP paths; emit canonical/isomeric SMILES,
charge, atomic identity and explicit topology; source parsing does not optimize
3D; optional deterministic planar coordinates are explicitly 2D; invalid text
produces no fake Structure; ETKDGv3 uses seed `0xC0FFEE`, one thread and
explicit AddHs/UFF/MMFF parameters in provenance; embedding/optimization
failures remain distinguishable.

**RED tests:** `.smi`/`.smiles`, direct text source, invalid input, exact bytes,
canonical/isomeric identity, reproducible embedding, parameter/provenance,
embedding failure and partial optimization failure.

**Implementation steps:** Lazy-import RDKit; materialize UI text only inside
owned staging; reuse the adapter for source entities; add deterministic
derivation with explicit parameters and immutable result.

**Focused tests:** SMILES reader/3D, adapter, source staging, project graph and
optional-import contracts.

**Full regression:** Full discovery and static checks.

**Blender validation:** Text/file import and deterministic derivation under
pinned RDKit.

**Review boundary:** Two independent reviews before checkpoint.

**Commit message:** `feat: add SMILES source and deterministic 3D derivation`

**Next task:** Task 7 — molecular exporters.

## Task 7 — MOL/SDF/SMILES Exporters

**Files:** Create `ChemBlender/core/exporters/rdkit_molecular.py`,
`tests/test_rdkit_molecular_export.py`, `tests/test_molecular_roundtrip.py`;
modify or deprecate only relevant `ChemBlender/output.py` helpers.

**Interfaces:** `export_mol()`, `export_sdf()` and `export_smiles()` consume
authoritative project entities and return export/loss documents.

**Scientific invariants:** Reconstruct only a temporary RDKit Mol; preserve
identity, charge, isotope, maps, aromaticity, explicit bonds and stereo; V3000
bond IDs begin at one; fail or request V3000 when V2000 is insufficient; keep
SDF order/titles/raw property order with explicit duplicate policy; never label
derived conformers as original; report SMILES coordinate/property loss; use
short sibling temp, fsync/replace, cancellation cleanup and no overwrite on
failure.

**RED tests:** V3000 ID regression, V2000 representability, molecular entity
construction, deterministic MOL/SDF/SMILES bytes, loss/confirmation, atomic
write/cancel and semantic round trips.

**Implementation steps:** One project-to-RDKit builder; format-specific
serialization around it; reuse existing atomic path helper; reduce legacy
V3000 helper to a compatibility wrapper.

**Focused tests:** Exporter and roundtrip modules plus adapter/MOL/SDF/SMILES,
atomic-path and legacy output regressions.

**Full regression:** Full discovery and static checks.

**Blender validation:** Export and re-import representative sources.

**Review boundary:** Two independent reviews before checkpoint.

**Commit message:** `feat: add RDKit molecular exporters`

**Next task:** Task 8 — UI and performance closure.

## Task 8 — UI, Legacy and Performance Closure

**Files:** Modify `ChemBlender/ui/quick_import.py`,
`ChemBlender/ui/import_preview.py`, `ChemBlender/ui/project_browser/`,
`ChemBlender/ui/export.py`, `ChemBlender/read.py`,
`ChemBlender/runtime/registration.py`, `tests/blender_smoke.py`; create a
focused UI module only where responsibility cannot fit an existing module.

**Interfaces:** Unified file/text import, record/property browsing, explicit
conformer acceptance and loss-aware molecular export.

**Scientific invariants:** Preview exposes record/version/recovery/sanitize/
property/group summaries; browser groups raw/typed records and ConformerSets;
Keep Independent is default and review evidence is visible; default view uses
only the first valid record or accepted first group; no 10k object fan-out;
SMILES text and migrated file actions use Reader API; MOL2 is explicitly
unsupported; every new UI module is an explicit registration root.

**RED tests:** Preview/browser rows, grouping decisions, unified FileHandler and
SMILES operator, exporter loss confirmation, legacy `None`/MOL2 errors,
registration/reload, save/reopen and 10k filtering/cancellation.

**Implementation steps:** Add the minimum RNA state for summaries/choices;
delegate scientific work to core services; route legacy actions; register
modules explicitly; keep large arrays/records outside RNA; instrument the 10k
path.

**Focused tests:** UI contracts, registration, reader/exporter workflow,
project browser and Blender smoke.

**Full regression:** Full discovery, compile, diff and clean-worktree checks.

**Blender validation:** V2000, V3000, malformed-middle SDF, properties,
conformer acceptance, SMILES/3D, save/reopen, export/reimport and two lifecycle
cycles.

**Review boundary:** Per-task reviews plus final Tasks 2–8 spec and quality
reviews.

**Commit message:** `feat: complete RDKit molecular import and export workflow`

**Next task:** Stop before Cube Task 1.

## Final Verification and Stop Boundary

- Run full tests, `compileall`, diff/worktree checks.
- Native preflight, validate/build, ZIP audit, `user_default` and short-path
  isolated installs, two lifecycle cycles and full RDKit product smoke.
- Record 10k SDF indexing/preview/browser median, p95 and peak memory.
- Confirm RDKit tests did not skip, no RDKit Mol is persisted, no dependency or
  Cube runtime was added, and `Remote CI: Not Run`.
- Complete final independent spec/quality reviews.
- Commit `chore: checkpoint RDKit molecular workflow`.
- Stop with Cube Task 1 unstarted and do not push.
