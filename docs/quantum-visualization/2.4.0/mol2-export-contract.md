# Native MOL2 export contract

ChemBlender 2.4.0 Task 1 adds a dependency-free normalized MOL2 core writer. It does
not promise byte-identical or lossless Tripos round-trip and does not add Blender UI.

## Readiness and confirmation

- `Unsupported` readiness raises `ValueError`; the message contains ordinally sorted,
  duplicate-free missing-field tokens.
- `Partial` readiness adds one `missing:<token>` preview entry per token.
- Raw-only information omitted by normalization adds stable loss entries.
- `NO_CHARGES` does not require a `partial_charge` property.
- A destination is not created until `confirm_loss=True` when the preview requires
  confirmation.

The raw-loss codes are exactly:

- `source_atom_ids_renumbered`;
- `source_bond_ids_renumbered`;
- `molecule_status_bits_omitted`;
- `molecule_comments_omitted`;
- `atom_status_bits_omitted`;
- `substructure_fields_omitted`;
- `unknown_sections_omitted`.

The unique bound raw record is parsed with the native `iter_mol2_records()` and
`parse_mol2_record()` functions. A substructure row containing only the emitted
canonical `GROUP` type is not a loss; additional raw substructure fields are.

## Deterministic normalized output

- Records sort by `(source_record_index, record_key, structure UUID)`, independent of
  container insertion order.
- Atom and bond IDs are allocated as `1..N` in emitted order.
- Numeric text uses finite, locale-independent `.17g` formatting; negative zero is
  normalized to `0`.
- Semantic round-trip compares scientific entities, not UUIDs, whitespace or
  provenance.
- Unsupported periodic shifts, non-angstrom coordinates, malformed token fields and
  non-finite values fail closed.
