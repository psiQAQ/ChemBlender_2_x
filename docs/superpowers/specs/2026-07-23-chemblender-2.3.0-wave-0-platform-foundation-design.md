# ChemBlender 2.3.0 Wave 0 Platform Foundation Design

## Status

Approved direction for `2.3.0-alpha.1`.

## 1. Goal

Create the project, source, import, plugin and UI foundation using existing XYZ and Cube readers as proof inputs. Wave 0 does not add the Wave 1–3 formats.

## 2. Deliverable slice

```text
existing XYZ/Cube fixture
→ Quick Import
→ reader discovery and staged parse
→ Import Preview
→ session QCProject
→ default structure/volume view
→ Save Project
→ close and reopen
→ Project Browser shows sources/data/diagnostics/views
```

## 3. Core modularization

Split `core/model.py` by responsibility while preserving public imports and sidecar type names. The split is staged:

1. Introduce `core/model/` package and an explicit schema registry.
2. Move leaf types first: arrays, enums, diagnostics.
3. Move structure/topology/property/grid.
4. Move spectroscopy/wavefunction/periodic/topology graph.
5. Move project transaction types.
6. Keep `core/model.py` as a compatibility shim for one alpha if required; remove only after import and sidecar migration tests prove no consumer remains.

No model move may change constructor fields or canonical type tags unless a schema migration is included.

## 4. Source and project state

Add source/revision registries to QCProject. SourceRevision points to created entities and diagnostics. QCProject validation checks:

- source/revision relationships;
- created entity references;
- diagnostic references;
- parse identity format;
- source hash and byte size;
- locator is not used as identity.

ProjectSession exists outside the frozen project model and owns temporary paths, dirty state, active entity and link status.

## 5. Import staging

Staging parse outputs remain isolated under a session-specific directory. `ImportPreview` contains no live Blender objects. Existing readers are adapted through a compatibility wrapper that constructs a public batch and source metadata.

Conflict resolution is deterministic and explicit. A confirmed transaction publishes project data and sidecar generation before view creation.

## 6. Reader API 0.x

Wave 0 publishes internal documentation and one in-tree minimal built-in adapter through the new API. It does not promise third-party stability. The canonical document supports all existing public model types used by XYZ/Cube and references large arrays by content-addressed artifacts.

Reader availability is separate from selection:

```python
ReaderAvailability(
    available=True,
    execution_mode="built_in",
    reason_code="available",
    detail=""
)
```

Optional readers can be detected but Preview must show unavailable before parse.

## 7. Blender registration

Replace recursive core scanning with explicit registration roots. The migration may retain existing `auto_load` topological sort for registered classes, but module enumeration is explicit. A smoke test asserts that enabling the extension does not import optional scientific stacks and does not import every pure core submodule.

## 8. UI minimum

### Quick Import panel

- Select Files.
- Project status.
- validation mode.
- recent import summary.
- Save Project.
- Open Workspace.

### Import Preview dialog

- source rows;
- reader and availability;
- capability/quality summary;
- duplicate action;
- commit/cancel.

### Project Browser

A flattened UIList supports By Source/By Data and selection. Wave 0 only needs Sources, Structures, Grids, Diagnostics and Views, but row contracts must support later groups.

## 9. Workspace asset

Provide a workspace on demand. The implementation may append a reviewed WorkSpace datablock from a bundled `.blend` asset. It must not assume the user has an unmodified default workspace. If the asset cannot load, the N-panel remains usable and reports a non-blocking diagnostic.

## 10. Version and release groundwork

- Make package/artifact names dynamic from manifest.
- Add a Blender 5.1.2 prerelease manifest probe.
- Record the accepted version syntax before changing the main manifest.
- Add GitHub pre-release support only after the probe.

## 11. Exit criteria

- `import ChemBlender.core` remains `bpy`-free.
- Existing sidecar v0.1 reads or migrates.
- Source/session/project tests pass.
- XYZ/Cube flow works through UI and save/reopen.
- explicit registration lifecycle passes twice.
- enable timing baseline recorded.
- alpha.1 package can be built under a verified version scheme.
