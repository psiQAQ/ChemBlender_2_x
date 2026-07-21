# XYZ Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现首个无第三方依赖的 XYZ reader，将单帧 XYZ 归一化为 `Structure`、`ProvenanceRecord` 和 `ParserReport`。

**Architecture:** 新建 `ChemBlender/core/xyz.py`，复用纯数据模块 `ChemBlender/Chem_data.py::ELEMENTS_DEFAULT` 获取原子序数，使用标准库 `array`/`memoryview` 承载坐标。导出一个 `XYZ_READER` descriptor，由调用方显式注册；多帧和 extXYZ 属性只报告 unsupported，不在首切片建模。

**Tech Stack:** Python 标准库 `array`、`hashlib`、`math`、`pathlib`、`uuid`、`unittest`。

## Global Constraints

- 不新增依赖，不 import `bpy`、RDKit 或 NumPy。
- 单位固定为 XYZ 约定的 `angstrom`；不从注释猜测其他单位。
- 必须验证 atom count、元素符号、有限坐标和行数。
- 不静默丢弃额外原子列或后续 frame；通过 `ParserReport` 明确标记 unsupported。
- reader 返回 `ImportBatch`，不直接提交 `QCProject`。

---

### Task 1: XYZ 内容探测

**Files:**
- Create: `ChemBlender/core/xyz.py`
- Create: `tests/fixtures/xyz/water.xyz`
- Create: `tests/test_xyz_reader.py`

**Interfaces:**
- Produces: `sniff_xyz(source: Path, prefix: bytes) -> SniffResult`。

- [ ] **Step 1: 创建 golden fixture 与失败测试**

`tests/fixtures/xyz/water.xyz`：

```text
3
water
O 0.000000 0.000000 0.000000
H 0.758602 0.000000 0.504284
H -0.758602 0.000000 0.504284
```

`tests/test_xyz_reader.py`：

```python
import unittest
from pathlib import Path

from ChemBlender.core import SniffMatch
from ChemBlender.core.xyz import sniff_xyz


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "xyz" / "water.xyz"


class XYZReaderTests(unittest.TestCase):
    def test_sniff_recognizes_complete_xyz_content(self):
        result = sniff_xyz(FIXTURE, FIXTURE.read_bytes())
        self.assertEqual(result.match, SniffMatch.EXACT)

    def test_sniff_rejects_non_xyz_content(self):
        result = sniff_xyz(Path("bad.xyz"), b"not-an-atom-count\n")
        self.assertEqual(result.match, SniffMatch.NONE)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_xyz_reader -v`

Expected: FAIL，因为 `ChemBlender.core.xyz` 尚不存在。

- [ ] **Step 3: 实现 bounded-compatible sniff**

`sniff_xyz` 解码 UTF-8 BOM，要求首行为正整数、存在注释行，随后最多检查 atom count 行；每个已检查 atom line 至少四列、元素存在于 `ELEMENTS_DEFAULT`、三个坐标可转为有限 float。

- 全部 atom lines 位于 prefix 且有效：`EXACT`。
- prefix 截断但已有 atom line 有效：`PROBABLE`。
- 只有有效 atom count/注释，尚无 atom line：`POSSIBLE`。
- 结构字段无效：`NONE`。

- [ ] **Step 4: 运行测试并提交**

```powershell
uv run --no-project python -m unittest tests.test_xyz_reader tests.test_quantum_readers -v
git add ChemBlender/core tests/fixtures/xyz/water.xyz tests/test_xyz_reader.py
git commit -m "feat: add XYZ reader detection"
```

Expected: sniff 和既有 registry tests PASS。

### Task 2: 单帧 XYZ 归一化

**Files:**
- Modify: `ChemBlender/core/xyz.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `tests/test_xyz_reader.py`

**Interfaces:**
- Consumes: `ArrayData`、`Structure`、`ProvenanceRecord`、`ParserReport`、`ImportBatch`。
- Produces: `parse_xyz(source: Path) -> ImportBatch` 和 `XYZ_READER: ReaderDescriptor`。

- [ ] **Step 1: 写 parse 失败测试**

加入：

```python
def test_registry_selects_xyz_by_content_with_wrong_extension(self):
    registry = ReaderRegistry((XYZ_READER,))
    with TemporaryDirectory() as directory:
        source = Path(directory) / "water.data"
        source.write_bytes(FIXTURE.read_bytes())
        self.assertIs(registry.select(source), XYZ_READER)

def test_parse_normalizes_structure_and_provenance(self):
    batch = XYZ_READER.parse(FIXTURE)
    self.assertEqual(len(batch.structures), 1)
    structure = batch.structures[0]
    self.assertEqual(structure.atomic_numbers, (8, 1, 1))
    self.assertEqual(structure.coordinates.shape, (3, 3))
    self.assertEqual(structure.coordinates.dims, ("atom", "xyz"))
    self.assertEqual(structure.coordinates.unit, "angstrom")
    self.assertEqual(len(batch.provenance), 1)
    self.assertEqual(len(batch.provenance[0].source_hash), 64)
    self.assertEqual(set(batch.report.created_entity_ids), {structure.id, batch.provenance[0].id})

def test_parsed_batch_commits_to_project(self):
    batch = ReaderRegistry((XYZ_READER,)).parse(FIXTURE)
    project = QCProject(id=uuid4(), schema_version="0.1")
    project.commit(batch)
    self.assertEqual(len(project.structures), 1)
    self.assertEqual(len(project.provenance), 1)

def test_parse_rejects_invalid_symbol_and_nonfinite_coordinate(self):
    cases = (
        b"1\nbad\nNoSuch 0 0 0\n",
        b"1\nbad\nH nan 0 0\n",
    )
    for content in cases:
        with self.subTest(content=content):
            with TemporaryDirectory() as directory:
                source = Path(directory) / "bad.xyz"
                source.write_bytes(content)
                with self.assertRaises(ValueError):
                    XYZ_READER.parse(source)

def test_extra_columns_and_frames_are_reported(self):
    content = b"1\nfirst\nH 0 0 0 charge=0\n1\nsecond\nH 1 0 0\n"
    with TemporaryDirectory() as directory:
        source = Path(directory) / "extra.xyz"
        source.write_bytes(content)
        batch = XYZ_READER.parse(source)
    paths = {issue.path for issue in batch.report.issues}
    self.assertEqual(paths, {"atom_properties", "trajectory"})
```

补充 imports：`TemporaryDirectory`、`uuid4`、`QCProject`、`ReaderRegistry`。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_xyz_reader -v`

Expected: parse tests FAIL，因为 `parse_xyz` 尚未实现。

- [ ] **Step 3: 实现最小 parse**

`parse_xyz` 必须：

1. 一次读取 source bytes 并计算 SHA-256；
2. UTF-8 BOM 解码并验证 atom count 与 `2 + atom_count` 最小行数；
3. 将元素符号规范化为首字母大写；`D`/`T` 映射为 H 并添加 warning issue；
4. 使用 `array.array("d", flat_coordinates)` → shaped `memoryview` 构造 `ArrayData`；
5. 创建 UUID、`revision=source_hash` 的 `Structure` 与 `ProvenanceRecord`；
6. 原子行超过四列时添加 `unsupported` issue，path 为 `atom_properties`；
7. 第一帧后仍有非空行时添加 `unsupported` issue，path 为 `trajectory`；
8. 返回 report created IDs 与 batch 实体完全一致的 `ImportBatch`。

完成 `parse_xyz` 后定义 descriptor：

```python
XYZ_READER = ReaderDescriptor(
    reader_id="xyz",
    reader_version="1",
    extensions=(".xyz",),
    capabilities={
        "structure": CapabilitySupport.SUPPORTED,
        "trajectory": CapabilitySupport.UNSUPPORTED,
    },
    priority=100,
    sniff=sniff_xyz,
    parse=parse_xyz,
)
```

- [ ] **Step 4: 运行测试并提交**

```powershell
uv run --no-project python -m unittest tests.test_xyz_reader tests.test_quantum_core tests.test_quantum_readers -v
git add ChemBlender/core/xyz.py tests/test_xyz_reader.py
git commit -m "feat: normalize XYZ structures"
```

Expected: XYZ、core、registry tests PASS。

### Task 3: 状态与完整验证

**Files:**
- Modify: `.agents/active/quantum-visualization-foundation.md`

**Interfaces:**
- Consumes: `XYZ_READER`。
- Produces: 下一切片入口。

- [ ] **Step 1: 更新 active**

记录单帧 XYZ adapter 与 golden fixture 已完成；Next Action 指向多帧 XYZ `FrameSet` 最小建模，不提前实现 extXYZ 属性 schema。

- [ ] **Step 2: 完整验证**

```powershell
uv run --no-project python -m unittest discover -s tests -p "test_*.py" -v
uv run --no-project python -c "import sys, ChemBlender.core; assert 'bpy' not in sys.modules"
git diff --check
```

使用已固定 SHA-256 的 ignored RDKit wheel运行 native Extension validate；再在 `--factory-startup --background` Blender 5.1.2 进程中验证 `register → unregister`，并确认 `ChemBlender.core.xyz` 被 auto-load 导入。

- [ ] **Step 3: 提交**

```powershell
git add .agents/active/quantum-visualization-foundation.md
git commit -m "docs: advance XYZ reader development"
```
