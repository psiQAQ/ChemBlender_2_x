# ChemBlender 2.3.0 Wave 0 Registration and UI Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace recursive pure-module loading with explicit registration and deliver the first Quick Import, Import Preview, Project Browser and workspace flow using existing XYZ/Cube readers.

**Architecture:** Blender registration modules are explicit. UI operators call pure import/session services. A session manager maps Blender windows/scenes to ProjectSession objects without making Scene properties authoritative.

**Tech Stack:** Blender 5.1 Python API, `bpy.types.Panel`, `Operator`, `UIList`, `PropertyGroup`, `FileHandler`, existing view adapters and core services.

## Global Constraints

- Blender RNA/datablock changes occur on the main thread.
- UI code does not parse formats or mutate QCProject registries directly.
- Quick Import and Project Browser use one Import Pipeline.
- N-panel remains functional if the dedicated workspace asset fails.
- Register/unregister twice without duplicate classes, handlers, menus or sessions.
- Ordinary enable/disable preserves the initialized reader registry, its built-in
  readers and registered model classes. A full extension update/reload creates a
  new handle, so external readers must register again through that handle.
- Update architecture guide in every module-responsibility commit.

---

### Task 1: Introduce explicit registration roots

**Files:**
- Create: `ChemBlender/runtime/registration.py`
- Modify: `ChemBlender/runtime/__init__.py`
- Modify: `ChemBlender/runtime/reader_api_bridge.py`
- Modify: `ChemBlender/__init__.py`
- Modify: `ChemBlender/auto_load.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `tests/test_registration_contract.py`
- Modify: `tests/test_reader_api_bridge_contract.py`
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `REGISTER_MODULE_NAMES`, `register_extension()` and `unregister_extension()`.

- [x] **Step 1: Record the live Blender registration inventory**

In Blender 5.1.2, record the currently registered modules, classes, handlers and
menus before changing registration. This live inventory is the baseline for
detecting omissions and duplicates; do not infer it from recursive source
discovery alone.

- [x] **Step 2: Write static registration and handle-lifecycle tests**

Parse `registration.py` and assert the explicit module tuple contains only
registration roots that exist in Task 1 and excludes prefixes
`ChemBlender.core`, `ChemBlender.reader_api` and `ChemBlender.legacy`. Assert
the Reader API handle is published only after all explicit modules register,
removed before reverse-order module unregistration, and rolled back without
masking the original registration exception.

- [x] **Step 3: Implement explicit module imports**

```python
REGISTER_MODULE_NAMES = (
    ".panel",
    ".periodictable",
    ".extension",
    ".chem_utils",
    ".crys_utils",
    ".output",
    ".scaffold",
    ".trajectory_view",
)
```

Import each name with `importlib.import_module(relative_name, package_root)` so installed keys such as `bl_ext.user_default.chemblender` work without hardcoding the repository namespace. Continue using class dependency topological sort on only these modules.

- [x] **Step 4: Change extension entrypoint and preserve registry ownership**

`ChemBlender.__init__.register()` calls `register_extension()`, which registers
the explicit modules before publishing the Reader API handle. Unregister removes
the owned handle before unregistering modules in reverse order. A failed
registration rolls back only modules and handle state owned by that attempt and
re-raises the original exception, adding cleanup notes without replacing it.
Ordinary enable/disable must not clear or recreate the initialized reader
registry, its built-ins or registered model classes. Preserve import-cache
cleanup only where a full extension update/reload requires it; external readers
then re-register through the newly published handle.

- [x] **Step 5: Expand Blender smoke**

Assert optional stacks absent and a representative pure module not needed by
registration remains unloaded until used. Assert one trajectory handler.

- [x] **Step 6: Verify and commit**

Run static and documentation-contract tests, validate/build and two lifecycle
cycles. Compare the final Blender inventory with the Step 1 baseline, allowing
only the explicit Task 1 changes. Commit runtime registration, handle bridge,
architecture guide and tests together.

### Task 2: Add Blender ProjectSession manager

**Files:**
- Create: `ChemBlender/ui/__init__.py`
- Create: `ChemBlender/ui/session.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `tests/test_ui_session_contract.py`
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `get_scene_session(scene)`, `new_scene_session(scene)`, `close_scene_session(scene)`, load/save handlers.

- [x] **Step 1: Write pure registry tests**

Test a weak-key/session mapping helper outside Blender where possible. It must not serialize ProjectSession into Scene.

- [x] **Step 2: Implement handlers**

Create the UI package root and add its session module to explicit registration
in this commit. On first use, create a session. On `load_post`, resolve a
sidecar link if present; otherwise create an empty session. On `save_pre`, if
dirty and the blend has a path, attempt to publish the sibling `.cbq` and update
the Scene link only after verification. Blender's `save_pre` handler cannot
cancel the `.blend` save. On sidecar failure, preserve dirty state and the last
verified Scene link, and expose a visible error/recovery state without claiming
that the `.blend` save was cancelled.

- [x] **Step 3: Add exit cleanup**

Unregister removes handlers, closes lazy arrays and owned temporary roots according to dirty/recovery policy. Unsaved dirty sessions leave a recovery marker rather than being destroyed without notice.

- [x] **Step 4: Verify and commit**

Blender smoke creates, saves, reloads and unregisters a session, and asserts
exactly one session load handler. Update registration, the architecture guide
and documentation contract in the same commit.

### Task 3: Add Quick Import properties and file chooser

**Files:**
- Create: `ChemBlender/ui/quick_import.py`
- Create: `ChemBlender/ui/properties.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `ChemBlender/panel.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `tests/test_quick_import_contract.py`
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `CHEMBLENDER_OT_quick_import`, validation mode property and N-panel section.

- [ ] **Step 1: Add operator contract tests**

Inspect Blender class definitions and assert operator ID, multi-file collection property, FILE_PATH directory and accepted validation modes.

- [ ] **Step 2: Implement invoke/execute**

Add the new UI modules to explicit registration in this commit. Use Blender
file selector with
`files: CollectionProperty(type=bpy.types.OperatorFileListElement)` and
`directory`. Build `ImportRequest`, obtain the current registry through the
internal `get_reader_plugin_registry()` accessor, call
`preflight_reader_plugins()`, and store the resulting `ImportPreview` in
session UI state. Quick Import must never access the private `_REGISTRY`, the
old core reader registry, or a `QCProject` private registry. Do not commit
during file chooser completion.

- [ ] **Step 3: Add N-panel**

Show project state, dirty badge, Select Files, validation mode, recent summary, Save Project and Open Workspace. Existing Build Molecules panel remains.

- [ ] **Step 4: Verify with XYZ and Cube**

Blender smoke invokes the operator execute path with fixture paths, confirms preview exists and project is unchanged.

- [ ] **Step 5: Commit**

Commit UI, explicit registration, architecture guide and tests together.

### Task 4: Add Import Preview dialog and commit operation

**Files:**
- Create: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `tests/test_import_preview_ui_contract.py`
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `CHEMBLENDER_OT_confirm_import`, `CHEMBLENDER_OT_cancel_import` and preview row PropertyGroups.

- [ ] **Step 1: Implement projection from pure preview**

Rows copy only display strings, IDs, status enums and selected actions into Blender properties. Large arrays and batches remain in session staging.

- [ ] **Step 2: Implement draw**

Show source, reader, availability, capability summary, quality badge, conflict action and default view checkbox. Blocking diagnostics disable Confirm.

- [ ] **Step 3: Implement confirm**

Add the preview module to explicit registration in this commit. Call
`commit_import_preview`, then apply default view plans. Track created objects;
if view application fails, remove them and report data committed/view failed.
Increment the UI/session browser revision after a successful import commit.

- [ ] **Step 4: Implement cancel**

Discard staged session and clear UI state; assert project and scene objects unchanged.

- [ ] **Step 5: Verify and commit**

Blender smoke tests confirm/cancel and commits XYZ/Cube. Commit UI, explicit
registration, architecture guide and tests together.

### Task 5: Add Project Browser flat-tree model and UIList

**Files:**
- Create: `ChemBlender/ui/project_browser/model.py`
- Create: `ChemBlender/ui/project_browser/panel.py`
- Create: `ChemBlender/ui/project_browser/__init__.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `tests/test_project_browser_model.py`
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `BrowserMode`, `BrowserRow`, `build_browser_rows()`, `CHEMBLENDER_UL_project_rows`, Project Browser panel.

- [ ] **Step 1: Write pure row projection tests**

Build a project with source, structure, grid and diagnostic, plus a UI/session
`ViewRecord`. `ViewRecord` is presentation state only: it is never a
`QCProject`, `.cbq` or model-registry entity. Assert By Source and By Data
order, depth, parent IDs, quality and search filtering. Assert no array values
are accessed by using a sentinel lazy array that raises on `__array__`.

- [ ] **Step 2: Implement cached rows**

Cache key includes a monotonic UI/session browser revision, mode, search and
filters. Increment and invalidate the revision on project replacement, import
commit, view creation/deletion, relink and reopen. Row display never traverses
large arrays.

- [ ] **Step 3: Implement UIList**

Rows show indentation, icon, quality marker, name and view count. Selection writes active entity ID to session state and updates the properties panel.

- [ ] **Step 4: Verify and commit**

Add the Project Browser registration root in this commit. Pure model tests and
Blender row selection smoke pass. Commit UI, explicit registration,
architecture guide and tests together.

### Task 6: Add drag-and-drop FileHandlers

**Files:**
- Create: `ChemBlender/ui/file_handlers.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `tests/test_file_handler_contract.py`
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: FileHandlers for 3D View and Project Browser that invoke Quick Import.

- [ ] **Step 1: Add Blender-version guarded contract tests**

Assert each handler has `bl_import_operator="chemblender.quick_import"`, a deterministic extension list derived from available built-in descriptors and a `poll_drop` restricted to supported area types.

- [ ] **Step 2: Implement handlers**

Do not parse in `poll_drop`. Unsupported or ambiguous extension can still reach content sniff through the import operator when Blender supplies a path; do not claim directories.

- [ ] **Step 3: Verify registration lifecycle**

Build/install and assert handlers register once and unregister cleanly.

- [ ] **Step 4: Commit**

Commit handlers, explicit registration, architecture guide and tests together.

### Task 7: Add the optional ChemBlender Workspace

**Files:**
- Create: `ChemBlender/ui/workspace.py`
- Create: `ChemBlender/assets/Chem_Workspace.blend`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `ChemBlender/blender_manifest.toml` build exclusions only if required
- Modify: `tests/blender_smoke.py`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `CHEMBLENDER_OT_open_workspace` and bundled WorkSpace datablock named `ChemBlender`.

- [ ] **Step 1: Create the workspace asset in Blender 5.1.2**

The asset contains only the `ChemBlender` WorkSpace and required screens. Configure a central 3D View, a left browser-capable 3D View sidebar, right properties area and bottom text/graph area. Remove unrelated scenes/objects before saving.

- [ ] **Step 2: Implement safe append**

Load the WorkSpace by exact name using `bpy.data.libraries.load(link=False)`. Reuse an existing compatible workspace. On failure, return CANCELLED with a diagnostic and leave the current workspace unchanged.

- [ ] **Step 3: Test package and fallback**

Smoke asserts the asset is in ZIP, opening switches workspace, repeated open does not duplicate, and a simulated missing asset does not break N-panel Quick Import.

- [ ] **Step 4: Commit**

Add the workspace module to explicit registration in this commit. Commit the
binary asset, operator, registration change, package test and architecture
guide together.
