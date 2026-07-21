# Quantum Semantic Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ChemBlender Extension 内建立可由普通 CPython 导入和验证的最小量子化学语义核心。

**Architecture:** 新代码位于 `ChemBlender/core/`，随 Extension 一起打包；`ChemBlender.__init__` 改为仅在 register/unregister 时导入 Blender `auto_load`。核心使用标准库 dataclass、UUID、Enum 和 duck-typed array metadata，不导入 `bpy`、NumPy 或第三方 parser。

**Tech Stack:** Python 3.11+/Blender Python 3.13、标准库 `dataclasses`/`enum`/`uuid`/`unittest`。

## Global Constraints

- 不新增或安装依赖；core 不能 import `bpy`、RDKit 或 NumPy。
- 保留 Blender 5.1+ Extension 布局，代码必须位于 `ChemBlender/` 包内。
- 只实现 ADR 0003/0004 的最小模型和事务；reader registry、边车存储和 Blender adapter 留给后续切片。
- 所有新增 Markdown/Python 使用 UTF-8 无 BOM和 LF。
- 每个任务先运行失败测试，再写最小实现，再提交。

---

### Task 1: 普通 CPython 导入边界与 ArrayData

**Files:**
- Modify: `ChemBlender/__init__.py`
- Create: `ChemBlender/core/__init__.py`
- Create: `ChemBlender/core/model.py`
- Create: `tests/test_quantum_core.py`

**Interfaces:**
- Produces: `ArrayData(values: object, dims: tuple[str, ...], unit: str)`，以及可安全执行的 `import ChemBlender.core`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_quantum_core.py` 建立标准库 array helper，并加入：

```python
import array
import subprocess
import sys
import unittest

from ChemBlender.core import ArrayData


def array_view(values, shape):
    raw = memoryview(array.array("d", values))
    return raw.cast("B").cast("d", shape=shape)


class QuantumCoreTests(unittest.TestCase):
    def test_core_import_does_not_load_bpy(self):
        code = "import sys; import ChemBlender.core; assert 'bpy' not in sys.modules"
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_array_data_reads_shape_dtype_and_unit(self):
        data = ArrayData(array_view(range(6), (2, 3)), ("atom", "xyz"), "angstrom")
        self.assertEqual(data.shape, (2, 3))
        self.assertEqual(data.dtype, "d")

    def test_array_data_rejects_invalid_dimensions_and_units(self):
        values = array_view(range(6), (2, 3))
        for dims, unit in ((('atom',), 'angstrom'), (('atom', 'atom'), 'angstrom'), (('atom', 'xyz'), '')):
            with self.subTest(dims=dims, unit=unit):
                with self.assertRaises(ValueError):
                    ArrayData(values, dims, unit)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_core -v`

Expected: FAIL，因为 `ChemBlender.core` 尚不存在或父包导入 `auto_load` 时找不到 `bpy`。

- [ ] **Step 3: 实现惰性 Blender 入口**

将 `ChemBlender/__init__.py` 改为：

```python
def register():
    from . import auto_load

    auto_load.init()
    auto_load.register()


def unregister():
    from . import auto_load

    auto_load.unregister()
```

- [ ] **Step 4: 实现最小 ArrayData**

在 `ChemBlender/core/model.py` 中使用 frozen/slots dataclass。`__post_init__` 必须：

```python
shape = tuple(getattr(self.values, "shape"))
if len(shape) != len(self.dims):
    raise ValueError("dims must match array rank")
if len(set(self.dims)) != len(self.dims) or any(not dim for dim in self.dims):
    raise ValueError("dims must be unique non-empty names")
if not re.fullmatch(r"[a-z][a-z0-9_]*", self.unit):
    raise ValueError("unit must be a lower_snake_case token")
dtype = str(getattr(self.values, "dtype", getattr(self.values, "format", "unknown")))
```

通过 `object.__setattr__` 写入 `shape` 和 `dtype`。缺少 shape、负 shape 或 bool dimension 时抛出 `TypeError`/`ValueError`。在 `ChemBlender/core/__init__.py` 导出 `ArrayData`。

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run --no-project python -m unittest tests.test_quantum_core -v`

Expected: 3 tests PASS，子进程导入后 `bpy` 不在 `sys.modules`。

- [ ] **Step 6: 提交**

```bash
git add ChemBlender/__init__.py ChemBlender/core tests/test_quantum_core.py
git commit -m "feat: add pure Python quantum array core"
```

### Task 2: 语义实体与 Grid3D

**Files:**
- Modify: `ChemBlender/core/model.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `tests/test_quantum_core.py`

**Interfaces:**
- Consumes: `ArrayData`。
- Produces: `Structure`、`CalculationRecord`、`PropertyDataset`、`Grid3D`、`ProvenanceRecord`、`ParserIssue`、`ParserReport` 和状态 Enum。

- [ ] **Step 1: 写实体与网格失败测试**

在测试文件中从 `uuid` 导入 `uuid4`，并加入：

```python
def test_structure_and_non_orthogonal_grid(self):
    structure = Structure(
        id=uuid4(), revision="r1", atomic_numbers=(6, 1),
        coordinates=ArrayData(array_view(range(6), (2, 3)), ("atom", "xyz"), "angstrom"),
    )
    grid = Grid3D(
        id=uuid4(), revision="g1", semantic_role="electron_density", domain="grid",
        data=ArrayData(array_view(range(24), (2, 3, 4)), ("x", "y", "z"), "electron_per_cubic_bohr"),
        status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        origin=(0.0, 0.0, 0.0),
        step_vectors=((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.0, 1.0)),
        coordinate_unit="bohr",
    )
    self.assertEqual(structure.coordinates.shape, (2, 3))
    self.assertEqual(grid.grid_shape, (2, 3, 4))

def test_grid_rejects_singular_vectors_and_wrong_spatial_dims(self):
    cases = (
        (
            ArrayData(array_view(range(8), (2, 2, 2)), ("x", "y", "z"), "dimensionless"),
            ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ),
        (
            ArrayData(array_view(range(8), (2, 2, 2)), ("z", "y", "x"), "dimensionless"),
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ),
    )
    for data, steps in cases:
        with self.subTest(dims=data.dims, steps=steps):
            with self.assertRaises(ValueError):
                Grid3D(
                    id=uuid4(), revision="g1", semantic_role="test_grid", domain="grid",
                    data=data, status=DatasetStatus.COMPLETE, source_calculation=None,
                    provenance_ids=(), origin=(0.0, 0.0, 0.0), step_vectors=steps,
                    coordinate_unit="bohr",
                )

def test_unknown_unit_requires_ambiguous_status(self):
    common = dict(
        id=uuid4(), revision="d1", semantic_role="mulliken_charge", domain="atom",
        data=ArrayData(array_view(range(2), (2,)), ("atom",), "unknown"),
        source_calculation=None, provenance_ids=(),
    )
    with self.assertRaises(ValueError):
        PropertyDataset(status=DatasetStatus.COMPLETE, **common)
    dataset = PropertyDataset(status=DatasetStatus.AMBIGUOUS, **common)
    self.assertEqual(dataset.status, DatasetStatus.AMBIGUOUS)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_core -v`

Expected: FAIL，实体类型尚未定义。

- [ ] **Step 3: 实现状态和实体**

在 `model.py` 中定义字符串 Enum：

```python
class CalculationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"

class DatasetStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"

class IssueKind(str, Enum):
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    WARNING = "warning"
```

实现 frozen/slots dataclass，字段固定为：

```python
Structure(id, revision, atomic_numbers, coordinates, cell=None)
CalculationRecord(id, revision, status, input_structure_ids, result_structure_ids, dataset_ids, provenance_ids)
PropertyDataset(id, revision, semantic_role, domain, data, status, source_calculation, provenance_ids)
Grid3D(...PropertyDataset fields..., origin, step_vectors, coordinate_unit)
ProvenanceRecord(id, revision, producer, producer_version, source, source_hash, parent_ids, operation, parameters)
ParserIssue(kind, path, message)
ParserReport(reader_id, reader_version, created_entity_ids, parsed_capabilities, issues)
```

最小验证包括 UUID 类型、非空 revision/token、原子序数范围、coordinates dims/shape、cell shape、unknown unit 状态、Grid3D 空间末三维、三个有限 step vectors 和非零 determinant。`Grid3D.grid_shape` 从 `data.shape[-3:]` 派生，不重复存储。

- [ ] **Step 4: 导出公共类型并运行测试**

在 `core/__init__.py` 显式导出上述类型和 `__all__`。

Run: `uv run --no-project python -m unittest tests.test_quantum_core -v`

Expected: 所有实体和网格测试 PASS。

- [ ] **Step 5: 提交**

```bash
git add ChemBlender/core tests/test_quantum_core.py
git commit -m "feat: add quantum semantic entities"
```

### Task 3: QCProject 原子提交

**Files:**
- Modify: `ChemBlender/core/model.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `tests/test_quantum_core.py`

**Interfaces:**
- Consumes: Task 2 的全部实体。
- Produces: `ImportBatch` 和 `QCProject.commit(batch: ImportBatch) -> None`。

- [ ] **Step 1: 写原子事务失败测试**

加入两个测试：

```python
def test_project_commits_valid_batch(self):
    structure_id, calculation_id, dataset_id, provenance_id = (uuid4() for _ in range(4))
    structure = Structure(
        id=structure_id, revision="s1", atomic_numbers=(1,),
        coordinates=ArrayData(array_view(range(3), (1, 3)), ("atom", "xyz"), "angstrom"),
    )
    provenance = ProvenanceRecord(
        id=provenance_id, revision="p1", producer="test", producer_version="1",
        source="fixture.xyz", source_hash="a" * 64, parent_ids=(),
        operation="parse", parameters=(),
    )
    dataset = PropertyDataset(
        id=dataset_id, revision="d1", semantic_role="mulliken_charge", domain="atom",
        data=ArrayData(array_view(range(1), (1,)), ("atom",), "elementary_charge"),
        status=DatasetStatus.COMPLETE, source_calculation=calculation_id,
        provenance_ids=(provenance_id,),
    )
    calculation = CalculationRecord(
        id=calculation_id, revision="c1", status=CalculationStatus.SUCCESS,
        input_structure_ids=(structure_id,), result_structure_ids=(structure_id,),
        dataset_ids=(dataset_id,), provenance_ids=(provenance_id,),
    )
    report = ParserReport(
        reader_id="test", reader_version="1",
        created_entity_ids=(structure_id, calculation_id, dataset_id, provenance_id),
        parsed_capabilities=("structure", "atomic_property"), issues=(),
    )
    project = QCProject(id=uuid4(), schema_version="0.1")
    project.commit(ImportBatch(
        structures=(structure,), calculations=(calculation,), datasets=(dataset,),
        provenance=(provenance,), report=report,
    ))
    self.assertIs(project.structures[structure_id], structure)
    self.assertIs(project.calculations[calculation_id], calculation)
    self.assertIs(project.datasets[dataset_id], dataset)
    self.assertIs(project.provenance[provenance_id], provenance)

def test_project_rejects_dangling_reference_atomically(self):
    project = QCProject(id=uuid4(), schema_version="0.1")
    calculation = CalculationRecord(
        id=uuid4(), revision="c1", status=CalculationStatus.SUCCESS,
        input_structure_ids=(uuid4(),), result_structure_ids=(),
        dataset_ids=(), provenance_ids=(),
    )
    with self.assertRaises(ValueError):
        project.commit(ImportBatch(calculations=(calculation,)))
    self.assertEqual(project.calculations, {})

def test_project_rejects_duplicate_uuid_atomically(self):
    duplicate_id = uuid4()
    structure = Structure(
        id=duplicate_id, revision="s1", atomic_numbers=(1,),
        coordinates=ArrayData(array_view(range(3), (1, 3)), ("atom", "xyz"), "angstrom"),
    )
    dataset = PropertyDataset(
        id=duplicate_id, revision="d1", semantic_role="charge", domain="atom",
        data=ArrayData(array_view(range(1), (1,)), ("atom",), "elementary_charge"),
        status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
    )
    project = QCProject(id=uuid4(), schema_version="0.1")
    with self.assertRaises(ValueError):
        project.commit(ImportBatch(structures=(structure,), datasets=(dataset,)))
    self.assertEqual(project.structures, {})
    self.assertEqual(project.datasets, {})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_core -v`

Expected: FAIL，`ImportBatch` 和 `QCProject` 尚未定义。

- [ ] **Step 3: 实现 ImportBatch 与 QCProject**

字段固定为：

```python
@dataclass(frozen=True, slots=True)
class ImportBatch:
    structures: tuple[Structure, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    datasets: tuple[PropertyDataset | Grid3D, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    report: ParserReport | None = None

@dataclass(slots=True)
class QCProject:
    id: UUID
    schema_version: str
    structures: dict[UUID, Structure] = field(default_factory=dict)
    calculations: dict[UUID, CalculationRecord] = field(default_factory=dict)
    datasets: dict[UUID, PropertyDataset | Grid3D] = field(default_factory=dict)
    provenance: dict[UUID, ProvenanceRecord] = field(default_factory=dict)
```

`commit` 先构造现有与 batch 的全局 UUID 集合，拒绝现有冲突、batch 内跨类型重复和 dangling references；验证 report 的 created IDs 也必须位于提交后的实体集合。所有检查通过后才分别 `dict.update`，检查阶段不得修改 registry。

- [ ] **Step 4: 运行核心与仓库测试**

Run: `uv run --no-project python -m unittest tests.test_quantum_core tests.test_repository_contract tests.test_quantum_visualization_docs -v`

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add ChemBlender/core tests/test_quantum_core.py
git commit -m "feat: add atomic quantum project imports"
```

### Task 4: 文档状态与包验证

**Files:**
- Modify: `.agents/active/quantum-visualization-foundation.md`

**Interfaces:**
- Consumes: 可运行的 `ChemBlender.core`。
- Produces: 下一切片的明确入口与完整验证证据。

- [ ] **Step 1: 更新 active 下一步**

记录首个语义核心切片已实现，并将 Next Action 指向 reader registry 最小实现：descriptor、sniff selection、ImportBatch adapter contract 和 `.mol2` 声明回归。不要把运行日志或临时路径写入 durable roadmap。

- [ ] **Step 2: 运行全部标准库测试**

Run: `uv run --no-project python -m unittest discover -s tests -p "test_*.py" -v`

Expected: 全部 PASS。

- [ ] **Step 3: 验证 Extension 包内容与普通导入**

Run:

```powershell
uv run --no-project python ChemBlender/scripts/validate_extension.py
uv run --no-project python -c "import sys, ChemBlender.core; assert 'bpy' not in sys.modules"
git diff --check
```

Expected: validator exit 0；core 导入不加载 `bpy`；diff check 无错误。

- [ ] **Step 4: 提交**

```bash
git add .agents/active/quantum-visualization-foundation.md .agents/README.md
git commit -m "docs: advance quantum core implementation"
```

仅在文件确有实质状态变化时创建该 commit；否则跳过空提交。
