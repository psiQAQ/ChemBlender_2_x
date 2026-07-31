# Data quality and diagnostics

ChemBlender preserves trustworthy data and makes recovery visible. A quality
badge describes what the reader/import contract could establish for an entity;
it does not certify the underlying experiment or calculation.

| Badge | Meaning | User action |
| --- | --- | --- |
| Complete | Required semantics for this entity are present | Continue, while still checking provenance |
| Partial | Trusted data was retained but optional or per-record content is missing | Inspect diagnostics before analysis/export |
| Ambiguous | More than one scientific interpretation remains | Resolve the stated assumption or keep the result out of final reporting |
| Incomplete | Required content is not complete enough for the intended workflow | Supply a better source or use only the explicitly retained subset |
| Invalid | Identity, integrity or required semantics failed validation | Do not commit/use the affected entity |

Balanced validation is the default. Strict rejects more recoveries; Maximum
retains more trustworthy partial data. None of the modes silently repairs an
unrecoverable structure identity.

## Read a diagnostic

The diagnostic view can show:

- source, source revision, record and entity identity;
- field path and stable diagnostic code;
- original and normalized values;
- recovery action;
- **scientific consequence**;
- **suggested action**.

The on-screen preview is bounded and may be truncated. Copy or export the
canonical JSON/Markdown report when you need complete evidence.

## Decide what is valid

- A Complete entity is valid only for the source revision and assumptions
  recorded in its provenance.
- Partial and Ambiguous entities remain inspectable, but export or final-report
  use can require explicit confirmation.
- A normalized unit or recovered optional property is recorded; it is not
  silently rewritten as source fact.
- A Blender View is never the authority for quality. Deleting or transforming
  the View does not change the project entity's badge.
- Derived Structures, Grids and topologies have their own revisions. Results
  attached to the source revision do not automatically become valid for a
  derived revision.

For topology-specific decisions, continue with
[Scientific editing and topology](scientific-editing.md).
