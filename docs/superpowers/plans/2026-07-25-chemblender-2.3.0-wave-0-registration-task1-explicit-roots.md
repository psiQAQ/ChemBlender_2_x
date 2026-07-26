# ChemBlender 2.3.0 Explicit Blender Registration Roots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace recursive package discovery during ordinary Blender
enable/disable with one explicit, deterministic and atomically reversible
registration root while preserving the legacy user-visible inventory and the
Reader API registry/handle lifecycle.

**Architecture:** `ChemBlender.__init__` delegates to a Blender-host boundary
in `runtime.registration`. That module imports only explicit registration
roots through the live package namespace, reuses `auto_load` only for class
dependency ordering and safe class operations, owns rollback state, and
publishes the Reader API handle only after Blender registration succeeds.

**Tech Stack:** Python 3.13 standard library, Blender 5.1.2 Python API,
`unittest`, Blender Extensions CLI.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation` from reviewed baseline
  `7078356c85bd02fcb0db23b01490f87f16abfb94`.
- Do not install or upgrade dependencies.
- Do not create Task 2 UI modules or enter Release Groundwork or Wave 1–4.
- Do not hardcode `ChemBlender`, `bl_ext.user_default`, or any repository
  namespace in runtime registration.
- Ordinary enable/disable preserves the initialized Reader API registry,
  built-in reader objects, and Reader API model class identities.
- Preserve the original registration failure; append cleanup failures through
  `BaseException.add_note()`.
- Preserve `ChemBlender/auto_load.py` CRLF bytes and keep the standard
  commit-range `git diff --check` reproducible through a narrowly scoped
  `.gitattributes` rule.
- Keep the known 276-character Windows extraction-path failure as a known
  limit; a short-path pass does not resolve it.
- Update the architecture guide in the implementation commit.
- Do not push without a new explicit user authorization.

---

### Task 1: Introduce explicit registration roots

**Files:**
- Create: `ChemBlender/runtime/registration.py`
- Modify: `ChemBlender/runtime/__init__.py`
- Modify: `ChemBlender/runtime/reader_api_bridge.py`
- Modify: `ChemBlender/__init__.py`
- Modify: `ChemBlender/auto_load.py`
- Modify: `.gitattributes`
- Create: `tests/test_registration_contract.py`
- Create: `tests/fixtures/registration/legacy-registration-inventory.json`
- Modify: `tests/test_reader_api_bridge_contract.py`
- Modify: `tests/test_repository_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `auto_load.get_ordered_classes_to_register(modules)`,
  `auto_load._safe_register_class(cls)`,
  `auto_load._safe_unregister_class(cls)`,
  `register_reader_api_handle(package_root)`, and
  `remove_reader_api_handle(handle)`.
- Produces: `REGISTER_MODULE_NAMES: tuple[str, ...]`,
  `register_extension(package_root: str) -> None`, and
  `unregister_extension() -> None`.

- [x] **Step 1: Freeze the unmodified legacy Blender inventory**

Build the reviewed baseline with Blender 5.1.2, install it into an isolated
repository, collect stable JSON for discovered modules, ordered Blender
classes, module callbacks, handlers, and menu callbacks, then fully unregister.
Save the result as
`tests/fixtures/registration/legacy-registration-inventory.json` with full
baseline SHA and no temporary absolute paths or object addresses.

- [x] **Step 2: Write the failing registration contract**

Create `tests/test_registration_contract.py`. Assert the new module is
initially absent, the explicit roots exist and exclude pure core/Reader API,
future UI and legacy modules, imports are namespace-relative and `bpy`-free,
registration order is deterministic, unregistration is exact reverse order,
callbacks run once, every failure phase rolls back only attempt-owned state,
cleanup notes never replace the original exception, repeated cycles are
idempotent, incompatible handle owners survive, and optional stacks remain
unloaded. Update the existing root/bridge/repository tests to describe the new
single production path.

Run:

```powershell
& $pythonBin -m unittest tests.test_registration_contract -v
```

Expected: `FAIL` with `ModuleNotFoundError` for
`ChemBlender.runtime.registration`.

- [x] **Step 3: Implement atomic explicit registration**

Create `runtime.registration` with the inventory-proven
`REGISTER_MODULE_NAMES`. Import each root using
`importlib.import_module(relative_name, package_root)`, order and deduplicate
classes through the existing `auto_load` helpers, register classes before
module callbacks, publish the Reader API handle last, and store only owned
state. On any failure, reverse only completed steps and append cleanup error
types as exception notes.

- [x] **Step 4: Replace the ordinary recursive entry path**

Make root `register()` and `unregister()` lazy delegates to
`runtime.registration`. Remove the recursive discovery/cache-clearing
production entry from `auto_load`; retain only the class dependency/toposort
and safe register/unregister helpers used by the explicit root. Do not retain
a second production registration path for old tests.

- [x] **Step 5: Preserve Reader API lifecycle and extend runtime smoke**

Verify ordinary disable/enable preserves the private registry, built-in
descriptor and public model class identities; an external reader follows the
documented handle lifecycle; only the owned handle is removed. Extend
`tests/blender_smoke.py` to compare stable inventory, run two lifecycle cycles,
assert one trajectory handler/handle, no duplicate class warning, no residue,
and no optional stack or future UI imports.

- [x] **Step 6: Update architecture and run GREEN verification**

Document the new registration owner, minimal root delegation, narrowed
`auto_load`, persistent registry identity, and incremental future UI roots.
Run:

```powershell
& $pythonBin -m unittest `
  tests.test_registration_contract `
  tests.test_reader_api_bridge_contract `
  tests.test_repository_contract `
  tests.test_quantum_visualization_docs -v

& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

Then run Blender 5.1.2 native validate/build, ZIP audit, real default
`user_default` install, short-path isolated install, two register/unregister
cycles, legacy/new inventory comparison, Reader API handle/registry checks,
RDKit import, and optional-stack audit. Record the artificial long-path result
as a known limit.

- [x] **Step 7: Review and commit**

Obtain independent specification-compliance and code-quality reviews. Fix all
Critical, Important, and task-related Minor findings; rerun full verification.
Commit implementation as:

```bash
git commit -m "refactor: register Blender modules explicitly"
```

Update the active cursor with exact RED/GREEN and Blender evidence, commit the
checkpoint as:

```bash
git commit -m "chore: checkpoint explicit Blender registration roots"
```

Stop before Task 2 and do not push.
