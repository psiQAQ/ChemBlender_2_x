# Multi-frame XYZ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将基础多帧 XYZ 归一化为首帧 `Structure` 与 datasets registry 中的 `FrameSet`，同时保持单帧行为不变。

**Architecture:** `FrameSet` 继承现有 `PropertyDataset`，通过 `structure_id` 引用首帧结构，坐标使用 `("frame", "atom", "xyz")`。`parse_xyz()` 顺序验证所有 frame，只在 frame 数大于一时创建 `FrameSet`；extXYZ 属性和 Blender frame handler 不进入本切片。

**Tech Stack:** Python 标准库 `array`、`dataclasses`、`pathlib`、`uuid`、`unittest`。

## Global Constraints

- 不新增依赖、registry 或 Blender UI。
- core 继续禁止 import `bpy`、RDKit 或 NumPy。
- 所有 frame 必须具有相同 atom count 和规范化元素顺序。
- 坐标单位固定为 `angstrom`，逐帧 comment 原样保留。
- 单帧 XYZ 不创建空或单帧 `FrameSet`。

---

### Task 1: FrameSet 语义模型与引用校验

**Files:**
- Modify: `ChemBlender/core/model.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `tests/test_quantum_core.py`

**Interfaces:**
- Consumes: `PropertyDataset`、`Structure`、`QCProject.datasets`。
- Produces: `FrameSet(...PropertyDataset fields..., structure_id: UUID, comments: tuple[str, ...])`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_quantum_core.py` 导入 `FrameSet`，加入：

```python
def test_frame_set_commits_with_matching_reference_structure(self):
    structure = Structure(
        id=uuid4(),
        revision="s1",
        atomic_numbers=(1, 1),
        coordinates=ArrayData(
            array_view(range(6), (2, 3)),
            ("atom", "xyz"),
            "angstrom",
        ),
    )
    frames = FrameSet(
        id=uuid4(),
        revision="f1",
        semantic_role="coordinates",
        domain="frame",
        data=ArrayData(
            array_view(range(12), (2, 2, 3)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure.id,
        comments=("first", "second"),
    )
    project = QCProject(id=uuid4(), schema_version="0.1")
    project.commit(ImportBatch(structures=(structure,), datasets=(frames,)))
    self.assertIs(project.datasets[frames.id], frames)

def test_frame_set_rejects_invalid_shape_comments_and_reference(self):
    structure_id = uuid4()
    common = {
        "id": uuid4(),
        "revision": "f1",
        "semantic_role": "coordinates",
        "domain": "frame",
        "status": DatasetStatus.COMPLETE,
        "source_calculation": None,
        "provenance_ids": (),
        "structure_id": structure_id,
    }
    with self.assertRaises(ValueError):
        FrameSet(
            data=ArrayData(
                array_view(range(6), (2, 3)),
                ("atom", "xyz"),
                "angstrom",
            ),
            comments=("first",),
            **common,
        )
    with self.assertRaises(ValueError):
        FrameSet(
            data=ArrayData(
                array_view(range(6), (2, 1, 3)),
                ("frame", "atom", "xyz"),
                "angstrom",
            ),
            comments=("only one",),
            **common,
        )
    frames = FrameSet(
        data=ArrayData(
            array_view(range(6), (2, 1, 3)),
            ("frame", "atom", "xyz"),
            "angstrom",
        ),
        comments=("first", "second"),
        **common,
    )
    project = QCProject(id=uuid4(), schema_version="0.1")
    with self.assertRaises(ValueError):
        project.commit(ImportBatch(datasets=(frames,)))
    self.assertEqual(project.datasets, {})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_core -v`

Expected: FAIL，因为 `FrameSet` 尚未导出。

- [ ] **Step 3: 实现最小模型**

在 `PropertyDataset` 后加入：

```python
@dataclass(frozen=True, slots=True)
class FrameSet(PropertyDataset):
    structure_id: UUID
    comments: tuple[str, ...]

    def __post_init__(self):
        super(FrameSet, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.semantic_role != "coordinates" or self.domain != "frame":
            raise ValueError("FrameSet must describe frame coordinates")
        if self.data.dims != ("frame", "atom", "xyz") or any(
            size <= 0 for size in self.data.shape
        ):
            raise ValueError("FrameSet data must have positive (frame, atom, xyz) dimensions")
        if self.data.shape[2] != 3:
            raise ValueError("FrameSet xyz dimension must have length 3")
        if self.data.unit in {"dimensionless", "unknown"}:
            raise ValueError("FrameSet coordinate unit must be known dimensional length")
        comments = tuple(self.comments)
        if len(comments) != self.data.shape[0] or any(
            not isinstance(comment, str) for comment in comments
        ):
            raise ValueError("FrameSet comments must contain one string per frame")
        object.__setattr__(self, "comments", comments)
```

在 `QCProject.commit()` 中先建立包含现有和 incoming 结构的 `structures` 映射；处理 dataset 时对 `FrameSet` 验证 `structure_id`、atom 数和单位：

```python
structures = dict(self.structures)
structures.update((structure.id, structure) for structure in batch.structures)
structure_ids = set(structures)

if isinstance(dataset, FrameSet):
    try:
        reference = structures[dataset.structure_id]
    except KeyError as error:
        raise ValueError("FrameSet has a dangling structure reference") from error
    if dataset.data.shape[1] != len(reference.atomic_numbers):
        raise ValueError("FrameSet atom dimension must match its structure")
    if dataset.data.unit != reference.coordinates.unit:
        raise ValueError("FrameSet and structure coordinate units must match")
```

从 `ChemBlender.core` 导出 `FrameSet`。

- [ ] **Step 4: 验证并提交**

```powershell
uv run --no-project python -m unittest tests.test_quantum_core -v
git add ChemBlender/core/model.py ChemBlender/core/__init__.py tests/test_quantum_core.py
git commit -m "feat: add FrameSet semantic dataset"
```

Expected: core tests PASS。

### Task 2: 多帧 XYZ 归一化

**Files:**
- Modify: `ChemBlender/core/xyz.py`
- Create: `tests/fixtures/xyz/water-trajectory.xyz`
- Modify: `tests/test_xyz_reader.py`

**Interfaces:**
- Consumes: `FrameSet`、现有 XYZ 元素和坐标验证。
- Produces: 多帧 `parse_xyz(source: Path) -> ImportBatch`，以及 supported `trajectory` capability。

- [ ] **Step 1: 创建 fixture 与失败测试**

`tests/fixtures/xyz/water-trajectory.xyz`：

```text
3
frame 0
O 0.000000 0.000000 0.000000
H 0.758602 0.000000 0.504284
H -0.758602 0.000000 0.504284
3
frame 1
O 0.100000 0.000000 0.000000
H 0.858602 0.000000 0.504284
H -0.658602 0.000000 0.504284
```

在 `tests/test_xyz_reader.py` 导入 `CapabilitySupport` 和 `FrameSet`，定义 `TRAJECTORY_FIXTURE` 并加入：

```python
def test_parse_normalizes_multi_frame_xyz(self):
    batch = XYZ_READER.parse(TRAJECTORY_FIXTURE)
    self.assertEqual(len(batch.structures), 1)
    self.assertEqual(len(batch.datasets), 1)
    frames = batch.datasets[0]
    self.assertIsInstance(frames, FrameSet)
    self.assertEqual(frames.structure_id, batch.structures[0].id)
    self.assertEqual(frames.data.shape, (2, 3, 3))
    self.assertEqual(frames.comments, ("frame 0", "frame 1"))
    self.assertAlmostEqual(frames.data.values[1, 0, 0], 0.1)
    self.assertIn("trajectory", batch.report.parsed_capabilities)
    project = QCProject(id=uuid4(), schema_version="0.1")
    project.commit(batch)

def test_single_frame_does_not_create_frame_set(self):
    batch = XYZ_READER.parse(FIXTURE)
    self.assertEqual(batch.datasets, ())
    self.assertEqual(batch.report.parsed_capabilities, ("structure",))

def test_multi_frame_rejects_changed_atoms_and_truncation(self):
    cases = (
        b"1\nfirst\nH 0 0 0\n1\nsecond\nO 1 0 0\n",
        b"1\nfirst\nH 0 0 0\n2\nsecond\nH 1 0 0\n",
    )
    for content in cases:
        with self.subTest(content=content):
            with TemporaryDirectory() as directory:
                source = Path(directory) / "bad.xyz"
                source.write_bytes(content)
                with self.assertRaises(ValueError):
                    XYZ_READER.parse(source)

def test_xyz_descriptor_supports_trajectory(self):
    self.assertIs(
        XYZ_READER.capabilities["trajectory"],
        CapabilitySupport.SUPPORTED,
    )
```

更新现有额外列测试：合法第二 frame 不再产生 `trajectory` issue，只保留 `atom_properties`。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_xyz_reader -v`

Expected: FAIL，因为 parser 仍将后续 frame 报告为 unsupported。

- [ ] **Step 3: 顺序解析全部 frame**

提取私有 `_parse_frame(lines, offset)`：

```python
def _parse_frame(lines, offset):
    if len(lines) < offset + 2:
        raise ValueError("XYZ frame is missing its atom count or comment")
    try:
        atom_count = int(lines[offset].strip())
    except ValueError as error:
        raise ValueError("XYZ atom count must be an integer") from error
    if atom_count <= 0:
        raise ValueError("XYZ atom count must be positive")
    end = offset + 2 + atom_count
    if len(lines) < end:
        raise ValueError("XYZ source does not contain the declared atom frame")

    atomic_numbers = []
    coordinates = []
    has_extra_columns = False
    isotope_symbols = set()
    for index, line in enumerate(lines[offset + 2 : end], start=1):
        fields = line.split()
        if len(fields) < 4:
            raise ValueError(f"XYZ atom line {index} must contain four fields")
        symbol = _normalize_symbol(fields[0])
        if symbol not in _XYZ_SYMBOLS:
            raise ValueError(f"unknown XYZ element symbol: {fields[0]}")
        if symbol in {"D", "T"}:
            isotope_symbols.add(symbol)
            symbol = "H"
        try:
            xyz = tuple(float(value) for value in fields[1:4])
        except ValueError as error:
            raise ValueError(f"XYZ atom line {index} has invalid coordinates") from error
        if not all(math.isfinite(value) for value in xyz):
            raise ValueError(f"XYZ atom line {index} has non-finite coordinates")
        atomic_numbers.append(_ATOMIC_NUMBERS[symbol])
        coordinates.extend(xyz)
        has_extra_columns = has_extra_columns or len(fields) > 4
    return (
        end,
        tuple(atomic_numbers),
        tuple(coordinates),
        lines[offset + 1],
        has_extra_columns,
        isotope_symbols,
    )
```

`parse_xyz()` 循环到文件末尾，仅忽略末尾空行；如果没有解析出 frame，显式失败：

```python
frames = []
offset = 0
while offset < len(lines):
    if not any(line.strip() for line in lines[offset:]):
        break
    offset, numbers, coordinates, comment, extra, isotopes = _parse_frame(
        lines, offset
    )
    if frames and numbers != frames[0][0]:
        raise ValueError("XYZ frames must use the same atom order")
    frames.append((numbers, coordinates, comment))
    has_extra_columns = has_extra_columns or extra
    isotope_symbols.update(isotopes)
if not frames:
    raise ValueError("XYZ source is missing an atom frame")
```

首帧继续构造 `Structure`。frame 数大于一时用全部扁平坐标构造：

```python
flat_frame_coordinates = [
    value for _, coordinates, _ in frames for value in coordinates
]
frame_values = memoryview(array.array("d", flat_frame_coordinates))
frame_values = frame_values.cast("B").cast(
    "d", shape=(len(frames), len(frames[0][0]), 3)
)
frame_set = FrameSet(
    id=frame_set_id,
    revision=source_hash,
    semantic_role="coordinates",
    domain="frame",
    data=ArrayData(
        frame_values,
        ("frame", "atom", "xyz"),
        "angstrom",
    ),
    status=DatasetStatus.COMPLETE,
    source_calculation=None,
    provenance_ids=(provenance_id,),
    structure_id=structure_id,
    comments=tuple(frame[2] for frame in frames),
)
```

report 的 created IDs 包含 `FrameSet`；多帧 parsed capabilities 为 `("structure", "trajectory")`。将 descriptor 的 trajectory capability 改为 `SUPPORTED`。

- [ ] **Step 4: 验证并提交**

```powershell
uv run --no-project python -m unittest tests.test_xyz_reader tests.test_quantum_core tests.test_quantum_readers -v
git add ChemBlender/core/xyz.py tests/fixtures/xyz/water-trajectory.xyz tests/test_xyz_reader.py
git commit -m "feat: parse multi-frame XYZ trajectories"
```

Expected: XYZ、core 和 registry tests PASS。

### Task 3: 状态与完整验证

**Files:**
- Modify: `.agents/active/quantum-visualization-foundation.md`

**Interfaces:**
- Consumes: 已验证的 `FrameSet` 和多帧 `XYZ_READER`。
- Produces: 下一条跨格式结构归一化计划入口。

- [ ] **Step 1: 更新 active**

将多帧 XYZ/`FrameSet` 移入 Completed；Next Action 指向第二种无第三方依赖结构格式 reader 的选择与实现计划，以满足 Phase 0 “两种结构格式归一化一致”验收。extXYZ 与 Blender trajectory adapter 继续延期。

- [ ] **Step 2: 完整验证**

```powershell
uv run --no-project python -m unittest discover -s tests -p "test_*.py" -v
uv run --no-project python -c "import sys, ChemBlender.core; assert 'bpy' not in sys.modules"
git -c core.whitespace=cr-at-eol diff --check
```

使用固定 SHA-256 的 ignored RDKit wheel 运行 native Extension validate/build；在干净 `BLENDER_USER_RESOURCES` 中安装构建 ZIP，验证 register/unregister、RDKit 和 `bl_ext.user_default.chemblender.core.xyz` 实际导入。

- [ ] **Step 3: 提交**

```powershell
git add .agents/active/quantum-visualization-foundation.md
git commit -m "docs: advance multi-frame XYZ development"
```
