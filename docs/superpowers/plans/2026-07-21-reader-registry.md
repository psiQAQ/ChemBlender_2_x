# Reader Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立不依赖 Blender 的显式 reader registry，并消除当前 `.mol2` 声明与实现不一致。

**Architecture:** 在 `ChemBlender/core/readers.py` 中实现 descriptor、capability、bounded sniff 和确定性选择；reader 只返回现有 `ImportBatch`。当前 Blender 读取路径暂不迁移到 registry，没有真实 reader 时不创建全局默认 registry。

**Tech Stack:** Python 标准库 `dataclasses`、`enum`、`pathlib`、`unittest`。

## Global Constraints

- 不新增依赖，不 import `bpy`、NumPy 或第三方 parser。
- sniff 最多读取文件前 65,536 bytes，不执行完整 parse。
- extension 只决定优先探测顺序，最终选择必须来自 sniff match。
- registry 不直接修改 `QCProject`；parse 结果必须是 `ImportBatch`。
- `.mol2` 在真实 reader 和 fixture 出现前不得对外声明支持。

---

### Task 1: Reader descriptor 与注册

**Files:**
- Create: `ChemBlender/core/readers.py`
- Modify: `ChemBlender/core/__init__.py`
- Create: `tests/test_quantum_readers.py`

**Interfaces:**
- Produces: `CapabilitySupport`、`SniffMatch`、`SniffResult`、`ReaderDescriptor`、`ReaderRegistry.register()`。

- [ ] **Step 1: 写失败测试**

测试使用以下 helper：

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.core import ImportBatch
from ChemBlender.core.readers import (
    CapabilitySupport,
    ReaderDescriptor,
    ReaderRegistry,
    SniffMatch,
    SniffResult,
)


def descriptor(reader_id, match=SniffMatch.POSSIBLE, priority=0, extensions=(".out",)):
    def sniff(path, prefix):
        return SniffResult(match, reader_id)

    def parse(path):
        return ImportBatch()

    return ReaderDescriptor(
        reader_id=reader_id,
        reader_version="1",
        extensions=extensions,
        capabilities={"structure": CapabilitySupport.SUPPORTED},
        priority=priority,
        sniff=sniff,
        parse=parse,
    )
```

加入：

```python
def test_descriptor_normalizes_extensions_and_capabilities(self):
    reader = descriptor("test-reader", extensions=("OUT", ".LOG"))
    self.assertEqual(reader.extensions, (".out", ".log"))
    self.assertEqual(reader.capabilities["structure"], CapabilitySupport.SUPPORTED)

def test_registry_rejects_duplicate_reader_id(self):
    registry = ReaderRegistry()
    registry.register(descriptor("same"))
    with self.assertRaises(ValueError):
        registry.register(descriptor("same"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_readers -v`

Expected: FAIL，因为 `ChemBlender.core.readers` 尚不存在。

- [ ] **Step 3: 实现 descriptor 与 register**

定义：

```python
class CapabilitySupport(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"

class SniffMatch(IntEnum):
    NONE = 0
    POSSIBLE = 1
    PROBABLE = 2
    EXACT = 3

@dataclass(frozen=True, slots=True)
class SniffResult:
    match: SniffMatch
    evidence: str

@dataclass(frozen=True, slots=True)
class ReaderDescriptor:
    reader_id: str
    reader_version: str
    extensions: tuple[str, ...]
    capabilities: Mapping[str, CapabilitySupport]
    priority: int
    sniff: Callable[[Path, bytes], SniffResult]
    parse: Callable[[Path], ImportBatch]
```

Descriptor 验证非空 ASCII reader ID/version、callable、非 bool integer priority、capability token 和 Enum value；extensions 统一为带前导点的小写唯一 tuple；capabilities 复制为 `MappingProxyType`。

`ReaderRegistry` 只持有 `dict[str, ReaderDescriptor]`。`register` 拒绝非 descriptor 和重复 ID。

- [ ] **Step 4: 运行测试并提交**

```powershell
uv run --no-project python -m unittest tests.test_quantum_readers -v
git add ChemBlender/core tests/test_quantum_readers.py
git commit -m "feat: add reader descriptors"
```

Expected: Task 1 tests PASS。

### Task 2: Bounded sniff 与确定性选择

**Files:**
- Modify: `ChemBlender/core/readers.py`
- Modify: `tests/test_quantum_readers.py`

**Interfaces:**
- Consumes: `ReaderDescriptor` 和 `ImportBatch`。
- Produces: `ReaderRegistry.select(source, reader_id=None)`、`ReaderRegistry.parse(source, reader_id=None)`、`ReaderNotFoundError`、`AmbiguousReaderError`。

- [ ] **Step 1: 写选择失败测试**

加入完整测试：

```python
def test_selects_highest_match_then_priority(self):
    registry = ReaderRegistry()
    registry.register(descriptor("probable", SniffMatch.PROBABLE, priority=100))
    registry.register(descriptor("exact-low", SniffMatch.EXACT, priority=1))
    registry.register(descriptor("exact-high", SniffMatch.EXACT, priority=2))
    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.out"
        source.write_bytes(b"content")
        self.assertEqual(registry.select(source).reader_id, "exact-high")

def test_equal_top_readers_are_ambiguous_independent_of_order(self):
    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.out"
        source.write_bytes(b"content")
        for order in (("alpha", "beta"), ("beta", "alpha")):
            registry = ReaderRegistry()
            for reader_id in order:
                registry.register(descriptor(reader_id, SniffMatch.EXACT, priority=1))
            with self.assertRaises(AmbiguousReaderError):
                registry.select(source)

def test_explicit_reader_bypasses_sniff_and_file_read(self):
    registry = ReaderRegistry()
    registry.register(descriptor("chosen"))
    selected = registry.select(Path("missing.out"), reader_id="chosen")
    self.assertEqual(selected.reader_id, "chosen")

def test_sniff_prefix_is_bounded(self):
    seen = []
    def sniff(path, prefix):
        seen.append(len(prefix))
        return SniffResult(SniffMatch.EXACT, "bounded")
    reader = descriptor("bounded")
    reader = ReaderDescriptor(
        reader.reader_id, reader.reader_version, reader.extensions,
        reader.capabilities, reader.priority, sniff, reader.parse,
    )
    registry = ReaderRegistry((reader,))
    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.out"
        source.write_bytes(b"x" * 70000)
        registry.select(source)
    self.assertEqual(seen, [65536])

def test_parse_requires_import_batch(self):
    reader = descriptor("bad")
    bad = ReaderDescriptor(
        reader.reader_id, reader.reader_version, reader.extensions,
        reader.capabilities, reader.priority, reader.sniff, lambda path: object(),
    )
    registry = ReaderRegistry((bad,))
    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.out"
        source.write_bytes(b"content")
        with self.assertRaises(TypeError):
            registry.parse(source)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_readers -v`

Expected: FAIL，因为 select/parse 和 selection errors 尚未实现。

- [ ] **Step 3: 实现最小选择算法**

```python
SNIFF_PREFIX_BYTES = 65536

def select(self, source, reader_id=None):
    source = Path(source)
    if reader_id is not None:
        try:
            return self._readers[reader_id]
        except KeyError as error:
            raise ReaderNotFoundError(reader_id) from error
    with source.open("rb") as stream:
        prefix = stream.read(SNIFF_PREFIX_BYTES)
    suffix = source.suffix.lower()
    readers = sorted(
        self._readers.values(),
        key=lambda reader: (suffix not in reader.extensions, reader.reader_id),
    )
    matches = [(reader.sniff(source, prefix), reader) for reader in readers]
    matches = [(result, reader) for result, reader in matches if result.match > SniffMatch.NONE]
    if not matches:
        raise ReaderNotFoundError(str(source))
    best_match = max(result.match for result, _ in matches)
    matches = [(result, reader) for result, reader in matches if result.match == best_match]
    best_priority = max(reader.priority for _, reader in matches)
    winners = [reader for _, reader in matches if reader.priority == best_priority]
    if len(winners) != 1:
        raise AmbiguousReaderError(tuple(sorted(reader.reader_id for reader in winners)))
    return winners[0]
```

每个 sniff 返回值必须是 `SniffResult`。`parse` 调用 selected descriptor，并拒绝非 `ImportBatch` 返回值。

- [ ] **Step 4: 运行测试并提交**

```powershell
uv run --no-project python -m unittest tests.test_quantum_readers tests.test_quantum_core -v
git add ChemBlender/core tests/test_quantum_readers.py
git commit -m "feat: select readers by bounded sniff"
```

Expected: reader 与 core tests PASS。

### Task 3: MOL2 声明修复与完整验证

**Files:**
- Modify: `ChemBlender/scaffold.py`
- Modify: `tests/test_quantum_readers.py`
- Modify: `.agents/active/quantum-visualization-foundation.md`

**Interfaces:**
- Consumes: reader contract。
- Produces: 与实际 `read_MOL` 能力一致的现有 UI 文件校验。

- [ ] **Step 1: 写 MOL2 回归失败测试**

```python
def test_legacy_file_validation_does_not_claim_mol2(self):
    source = (ROOT / "ChemBlender" / "scaffold.py").read_text(encoding="utf-8")
    valid_exts = source.split("valid_exts = {", 1)[1].split("}", 1)[0]
    self.assertNotIn('".mol2"', valid_exts)
```

在测试文件定义 `ROOT = Path(__file__).resolve().parents[1]`。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_readers.ReaderRegistryTests.test_legacy_file_validation_does_not_claim_mol2 -v`

Expected: FAIL，当前 `valid_exts` 包含 `.mol2`。

- [ ] **Step 3: 删除虚假声明**

从 `ChemBlender/scaffold.py::is_valid_filepath` 的 `valid_exts` 中只删除 `".mol2"`，不重构 Blender UI 或旧 reader。

- [ ] **Step 4: 更新 active 下一步**

记录 reader registry 最小切片已实现；Next Action 指向首个真实 lightweight reader adapter 与 capability fixture。第三方依赖仍不安装。

- [ ] **Step 5: 完整验证并提交**

```powershell
uv run --no-project python -m unittest discover -s tests -p "test_*.py" -v
uv run --no-project python -c "import sys, ChemBlender.core; assert 'bpy' not in sys.modules"
git diff --check
git add ChemBlender/scaffold.py ChemBlender/core tests/test_quantum_readers.py .agents/active/quantum-visualization-foundation.md
git commit -m "fix: align MOL2 capability declaration"
```

Expected: 全部 tests PASS，普通 core 导入不加载 `bpy`。
