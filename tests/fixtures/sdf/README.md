# SDF fixtures

`records.sdf` contains two independently indexed V2000 water records with SD
fields.  The test module constructs malformed-middle, duplicate/empty,
mixed-property, mixed-version, CRLF, missing-final-delimiter and 10k-index
streams byte-for-byte so each expected delimiter, offset and recovery invariant
is visible beside its assertion.  The generated 10k stream is deliberately not
tracked as a repository fixture.
