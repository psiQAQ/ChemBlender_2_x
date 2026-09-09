# Automation and Reader Extension APIs

## Worker Protocol v1

Use `chemblender-prepare worker request.json result.json [--cancel-file PATH]`. A request identifies the CBQ project, project ID/schema/revision, operation ID/version, inputs, parameters and artifacts. The worker writes progress atomically, checks cancellation, and publishes one success/cancelled/error result. Blender rejects identity mismatch, stale revisions, invalid hashes and outputs outside its owned task directory.

The normative field contract is [local-worker-protocol-v1.md](../../quantum-visualization/specs/local-worker-protocol-v1.md). Treat request/result files as untrusted input and do not edit a live task.

## Reader API 1.0-rc1

Reader extensions use `chemblender_prepare.reader_api`, a manifest, deterministic discovery, a descriptor, and the worker bridge. Start with the [Reader API index](../../reader-api-v1/README.md), [manifest](../../reader-api-v1/manifest.md), [Python API](../../reader-api-v1/python-api.md), [worker bridge](../../reader-api-v1/worker-api.md), and [conformance](../../reader-api-v1/conformance.md).

The compatibility token stays `1.0-rc1`. A reader runs in its declared environment and cannot reach Blender internals. The machine-generated reader list is part of [public-surface.json](../public-surface.json).
