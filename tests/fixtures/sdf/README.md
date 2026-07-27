# SDF fixtures

`records.sdf` contains two independently indexed V2000 water records with SD
fields. `malformed-middle.sdf`, `duplicate-empty.sdf`, `mixed-properties.sdf`,
`mixed-version.sdf`, and `missing-final.sdf` cover record-local recovery,
standard SDWriter property headers, categorical/missing property values, mixed
MOL versions, and an absent final delimiter. `crlf.sdf` is a tracked fixture
with CRLF line endings. The generated 10k stream is deliberately not tracked
as a repository fixture.
