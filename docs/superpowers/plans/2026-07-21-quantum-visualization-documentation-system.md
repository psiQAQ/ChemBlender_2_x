# ChemBlender 量子化学可视化文档体系实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立量子化学可视化总路线图、七个主题计划、参考仓库占位和唯一 active task，为后续 ADR 与代码实施提供稳定入口。

**Architecture:** `docs/quantum-visualization/` 保存稳定路线与主题计划，`.agents/active/` 只保存当前任务，`submodules/README.md` 记录按需引入规则。一个标准库 `unittest` 文件验证文档结构、必需章节、本地链接、编码和 submodule 空占位状态。

**Tech Stack:** Markdown、Python 3.11 标准库 `unittest`、Git。

## Global Constraints

- 本轮不创建 `chemblender_core`，不修改 ChemBlender 运行时代码。
- 不添加或安装 Python/Blender 依赖，不创建 `.gitmodules`，不拉取外部仓库。
- 不修改 Git remote，不 push，不发布版本。
- 新增 Markdown 使用 UTF-8 无 BOM；保留仓库现有换行策略。
- 路线图按物理语义和架构责任组织，不按文件后缀组织。
- 只有一个 `.agents/active/` 文档；尚未启动的主题留在路线图和计划中。
- 候选库不因写入 `references.md` 或 `submodules/README.md` 自动成为依赖。

---

### Task 1: 文档契约测试与路线图入口

**Files:**
- Create: `tests/test_quantum_visualization_docs.py`
- Create: `docs/quantum-visualization/README.md`
- Create: `docs/quantum-visualization/roadmap.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-07-21-quantum-visualization-development-system-design.md`
- Produces: `QuantumVisualizationDocsTests.read_doc(relative_path)`；后续任务向同一测试类追加契约。

- [ ] **Step 1: 写入首个失败测试**

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "quantum-visualization"


class QuantumVisualizationDocsTests(unittest.TestCase):
    def read_doc(self, relative_path: str) -> str:
        path = ROOT / relative_path
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
        return raw.decode("utf-8")

    def test_roadmap_entrypoints_exist(self):
        index = self.read_doc("docs/quantum-visualization/README.md")
        roadmap = self.read_doc("docs/quantum-visualization/roadmap.md")
        self.assertIn("roadmap.md", index)
        for phase in range(5):
            self.assertIn(f"Phase {phase}", roadmap)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `ERROR`，指出 `docs/quantum-visualization/README.md` 不存在。

- [ ] **Step 3: 创建路线图入口**

`README.md` 必须包含：项目定位、阅读顺序、当前 Phase 0、路线图链接、设计规格链接、文档与 `.agents/active/` 的职责区别。

`roadmap.md` 必须包含：

- Phase 0 数据边界：五项 ADR、最小纯 Python 契约、MOL2 能力回归案例；
- Phase 1 分子量子化学闭环：cclib、IOData、Cube、轨迹、振动、光谱和表面；
- Phase 2 周期量子化学：Gemmi/spglib、pymatgen、band/DOS、费米面、phonopy；
- Phase 3 大型数据与交互：边车、hash、OpenVDB、worker、长轨迹；
- Phase 4 工作流与自动化：recipe、Multiwfn/critic2、数据库 connector；
- 每个 Phase 的进入条件、交付结果和退出条件；
- 推进规则：同一时间只激活一个主题，验收后才选择下一项。

- [ ] **Step 4: 运行测试并确认通过**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `OK`，1 test passed。

- [ ] **Step 5: 提交**

```bash
git add tests/test_quantum_visualization_docs.py docs/quantum-visualization/README.md docs/quantum-visualization/roadmap.md
git commit -m "docs: add quantum visualization roadmap"
```

### Task 2: 数据边界、语义核心与 reader 计划

**Files:**
- Create: `docs/quantum-visualization/architecture/data-boundary.md`
- Create: `docs/quantum-visualization/plans/semantic-core.md`
- Create: `docs/quantum-visualization/plans/readers-and-formats.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: Phase 0 边界与统一优先级定义。
- Produces: 五项 ADR 的决策问题；语义核心和 reader 两个主题的 P0/P1/P2 backlog。

- [ ] **Step 1: 向测试类追加必需章节契约**

```python
    def test_foundation_plans_have_required_sections(self):
        required = (
            "## 范围",
            "## 非目标",
            "## 优先级",
            "## 依赖关系",
            "## 交付物",
            "## 验收标准",
            "## 参考仓库触发条件",
        )
        for relative_path in (
            "docs/quantum-visualization/plans/semantic-core.md",
            "docs/quantum-visualization/plans/readers-and-formats.md",
        ):
            text = self.read_doc(relative_path)
            for heading in required:
                self.assertIn(heading, text, relative_path)

    def test_data_boundary_lists_five_decisions(self):
        text = self.read_doc(
            "docs/quantum-visualization/architecture/data-boundary.md"
        )
        for decision in (
            "量子化学语义模型",
            "Grid3D 数据约定",
            "单位约定",
            "reader capability contract",
            "Blender 与边车数据的职责边界",
        ):
            self.assertIn(decision, text)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: 两个新增测试因文档不存在而 `ERROR`。

- [ ] **Step 3: 写入数据边界议程**

`data-boundary.md` 对五项决策分别记录：问题、必须确定的最小内容、已有约束、验证证据、明确推迟的选择。不得把 dataclass/Pydantic、Zarr/HDF5、GBasis/ORBKIT 等候选方案写成既定结论。

- [ ] **Step 4: 写入两个基础主题计划**

`semantic-core.md`：

- P0：`Structure`、`CalculationRecord`、`PropertyDataset`、`Grid3D`、`ParserReport`、`Provenance`，数组 `dtype/shape/dims/unit/source` 契约，普通 CPython 测试；
- P1：轨道、振动、激发态、周期数据的专用容器；
- P2：`TopologyGraph`、数据库记录与 provenance graph；
- 验收：core 无 `bpy`，缺失字段不静默丢弃，跨格式结构归一化一致。

`readers-and-formats.md`：

- P0：reader/capability registry、内容 sniffing、ParserReport、MOL2 声明回归、cclib/IOData/Gemmi/spglib adapter 边界；
- P1：ASE、QCSchema v1/v2、CJSON、周期体数据；
- P2：phonopy、critic2、Multiwfn 和数据库 connector；
- 验收：能力矩阵来自真实 fixture，unsupported/partial/ambiguous 状态可区分。

- [ ] **Step 5: 运行测试并确认通过**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `OK`，3 tests passed。

- [ ] **Step 6: 提交**

```bash
git add tests/test_quantum_visualization_docs.py docs/quantum-visualization/architecture/data-boundary.md docs/quantum-visualization/plans/semantic-core.md docs/quantum-visualization/plans/readers-and-formats.md
git commit -m "docs: plan quantum data foundation"
```

### Task 3: 波函数、Blender 映射与周期电子结构计划

**Files:**
- Create: `docs/quantum-visualization/plans/wavefunction-and-grids.md`
- Create: `docs/quantum-visualization/plans/blender-visualization.md`
- Create: `docs/quantum-visualization/plans/periodic-electronic-structure.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `Grid3D`、`PropertyDataset`、reader capability 与 provenance 契约。
- Produces: 分子场、Blender 视图和周期电子结构的分阶段开发边界。

- [ ] **Step 1: 扩展计划文件列表测试**

将 Task 2 的 `test_foundation_plans_have_required_sections` 重命名为 `test_topic_plans_have_required_sections`，并把以下路径加入循环：

```python
            "docs/quantum-visualization/plans/wavefunction-and-grids.md",
            "docs/quantum-visualization/plans/blender-visualization.md",
            "docs/quantum-visualization/plans/periodic-electronic-structure.md",
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `test_topic_plans_have_required_sections` 因新增文件不存在而 `ERROR`。

- [ ] **Step 3: 写入三个主题计划**

`wavefunction-and-grids.md`：P0 覆盖多 dataset、非正交 step vectors、GridSemantic、SurfaceStyle、正负相位与 field-on-surface；P1 比较 IOData+GBasis/Grid 和 ORBKIT，并以数值/性能 fixture 选主后端；P2 才考虑 CuGBasis。明确 Cube 不是物理语义。

`blender-visualization.md`：P0 覆盖原子标量 named attribute、单一 instanced-arrow node group、当前帧轨迹、Volume/OpenVDB 与 mesh fallback；P1 覆盖振动、光谱、激发态、linked selection；P2 覆盖 publication templates 和高级交互。`.blend` 只存 ID、显示状态与缓存引用。

`periodic-electronic-structure.md`：P0 是 Gemmi/spglib 的 CIF/对称性边界和现有行为回归；P1 是 ASE/pymatgen、CHGCAR/ELFCAR/LOCPOT、band/DOS、phonopy 复数模态；P2 是 PyProcar 费米面、自旋纹理和 sumo 风格联动。

- [ ] **Step 4: 运行测试并确认通过**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `OK`，3 tests passed。

- [ ] **Step 5: 提交**

```bash
git add tests/test_quantum_visualization_docs.py docs/quantum-visualization/plans/wavefunction-and-grids.md docs/quantum-visualization/plans/blender-visualization.md docs/quantum-visualization/plans/periodic-electronic-structure.md
git commit -m "docs: plan quantum visualization backends"
```

### Task 4: 存储、worker 与工作流计划

**Files:**
- Create: `docs/quantum-visualization/plans/storage-and-workers.md`
- Create: `docs/quantum-visualization/plans/workflows-and-connectors.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: 数据模型 ID、provenance、Grid3D 和 Blender 缓存边界。
- Produces: 大型数据存储选择门与 recipe/外部 adapter 的开发顺序。

- [ ] **Step 1: 把两个路径加入主题计划测试**

```python
            "docs/quantum-visualization/plans/storage-and-workers.md",
            "docs/quantum-visualization/plans/workflows-and-connectors.md",
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: 主题计划测试因新增文件不存在而 `ERROR`。

- [ ] **Step 3: 写入两个主题计划**

`storage-and-workers.md`：P0 定义 `.cbq` manifest、source/parser/derivation/render hash 与故障恢复；P1 依据 benchmark 在 Zarr/HDF5 中选择一种权威数组存储，并加入 OpenVDB、lazy loading、worker 和长轨迹缓存；P2 才考虑远程 worker 和多计算 ensemble。

`workflows-and-connectors.md`：P0 定义 recipe schema 与输入/输出/单位/验证/引用；P1 实现 quantum-chem-skills 配方映射及 Multiwfn/critic2 外部 adapter；P2 接入 QCArchive、AiiDA、NOMAD 与自动报告。明确禁止 Blender UI 绑定 Multiwfn 菜单编号。

- [ ] **Step 4: 运行测试并确认通过**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `OK`，3 tests passed。

- [ ] **Step 5: 提交**

```bash
git add tests/test_quantum_visualization_docs.py docs/quantum-visualization/plans/storage-and-workers.md docs/quantum-visualization/plans/workflows-and-connectors.md
git commit -m "docs: plan quantum data scale and workflows"
```

### Task 5: 参考仓库目录与 submodule 空占位

**Files:**
- Create: `docs/quantum-visualization/references.md`
- Create: `submodules/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: 七个主题计划中的参考仓库触发条件。
- Produces: 候选仓库到主题/用途的映射；实际 `git submodule add` 前置检查清单。

- [ ] **Step 1: 追加参考仓库与占位契约**

```python
    def test_reference_catalog_and_empty_submodule_placeholder(self):
        references = self.read_doc("docs/quantum-visualization/references.md")
        placeholder = self.read_doc("submodules/README.md")
        for project in (
            "xyzrender",
            "quantum-chem-skills",
            "Molecular Blender",
            "Beautiful Atoms",
            "Molecular Nodes",
            "cclib",
            "IOData",
            "Gemmi",
            "spglib",
            "pymatgen",
            "phonopy",
        ):
            self.assertIn(project, references)
        self.assertIn("git submodule add", placeholder)
        self.assertFalse((ROOT / ".gitmodules").exists())
        children = {path.name for path in (ROOT / "submodules").iterdir()}
        self.assertEqual(children, {"README.md"})
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: 新测试因 `references.md` 不存在而 `ERROR`。

- [ ] **Step 3: 写入参考项目矩阵**

`references.md` 使用表格记录项目、用途、对应主题、复用方式、计划优先级、许可证核查状态、submodule 触发条件。至少覆盖调研正文中的 xyzrender、quantum-chem-skills、Molecular Blender、Beautiful Atoms、Molecular Nodes、cclib、IOData、ORBKIT、GBasis/Grid、CuGBasis、QCElemental/QCSchema、ASE、Gemmi、spglib、pymatgen、PyProcar、sumo、phonopy、Avogadro/CJSON、critic2、Multiwfn、MDAnalysis/MDTraj、QCArchive、AiiDA、NOMAD。

许可证未在当前仓库重新核实时写“集成前复核”，不得猜测或把调研日期的状态写成永久事实。

- [ ] **Step 4: 创建 `submodules/README.md`**

说明默认不拉取；只有已批准任务需要逐行审阅、运行对照测试或固定 commit 时才执行：

```bash
git submodule add <upstream-url> submodules/<name>
git -C submodules/<name> checkout <reviewed-commit>
git add .gitmodules submodules/<name>
```

同时要求记录 URL、固定 commit、许可证、用途、更新和移除方式。不得创建仓库目录空壳或 `.gitmodules`。

- [ ] **Step 5: 运行测试并确认通过**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: `OK`，4 tests passed。

- [ ] **Step 6: 提交**

```bash
git add tests/test_quantum_visualization_docs.py docs/quantum-visualization/references.md submodules/README.md
git commit -m "docs: catalog quantum visualization references"
```

### Task 6: 激活 Phase 0 并接入仓库文档入口

**Files:**
- Create: `.agents/active/quantum-visualization-foundation.md`
- Modify: `.agents/README.md`
- Modify: `docs/README.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/quantum-visualization/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: 路线图、七个主题计划、参考项目目录和设计规格。
- Produces: 唯一 current task 权威与从仓库根入口可达的文档导航。

- [ ] **Step 1: 追加 active 与本地 Markdown 链接测试**

```python
    def test_single_active_task(self):
        active = sorted((ROOT / ".agents" / "active").glob("*.md"))
        self.assertEqual(
            [path.name for path in active],
            ["quantum-visualization-foundation.md"],
        )

    def test_local_markdown_links_resolve(self):
        import re

        paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / ".agents" / "README.md",
            *(ROOT / ".agents" / "active").glob("*.md"),
            ROOT / "docs" / "README.md",
            *DOCS.rglob("*.md"),
        ]
        for path in paths:
            text = self.read_doc(str(path.relative_to(ROOT)))
            for destination in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                destination = destination.strip("<>").split("#", 1)[0]
                if not destination or destination.startswith(("http://", "https://")):
                    continue
                target = (path.parent / destination).resolve()
                self.assertTrue(target.exists(), f"{path}: {destination}")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs -v`

Expected: 新测试因 `.agents/active/` 不存在或 active 文件列表为空而失败。

- [ ] **Step 3: 创建唯一 active task**

`quantum-visualization-foundation.md` 必须包含：

- Goal：批准五项 ADR 后形成最小可实现契约；
- Success Criteria：每项 ADR 有明确选择、拒绝方案与验证；接口规格能由普通 CPython 测试；
- Constraints：无依赖、无 core scaffold、无 Blender 代码、无 submodule；
- Confirmed Facts：MOL2 声明不一致、当前 parser 与 `bpy` 耦合、2.2.0 Extension 边界；
- Next Action：起草语义模型 ADR，不同时起草五项以免互相矛盾；
- Verification：链接、UTF-8、`unittest`、`git diff --check`；
- References：设计规格、路线图、data-boundary 和两个 Phase 0 主题计划。

- [ ] **Step 4: 更新所有稳定入口**

- `.agents/README.md`：索引 active 文档，并加入路线图作为 durable documentation；
- `docs/README.md`：增加“Quantum Visualization Development”区，链接总入口与路线图；
- `README.md`：Development 下增加量子化学可视化路线图；
- `AGENTS.md`：Knowledge Entrypoints 增加路线图与数据边界；不写 live commit 或任务进度；
- `docs/quantum-visualization/README.md`：补齐七个主题计划、架构议程与 references 链接。

- [ ] **Step 5: 运行完整文档契约和仓库契约**

Run: `uv run --no-project python -m unittest tests.test_quantum_visualization_docs tests.test_repository_contract -v`

Expected: `OK`，所有测试通过。

- [ ] **Step 6: 检查链接目标、编码、占位范围和 Git diff**

Run:

```powershell
uv run --no-project python -c "from pathlib import Path; files=list(Path('docs/quantum-visualization').rglob('*.md'))+[Path('submodules/README.md'),Path('.agents/active/quantum-visualization-foundation.md')]; assert all(not p.read_bytes().startswith(b'\xef\xbb\xbf') for p in files); print(f'UTF8_NO_BOM={len(files)}')"
git submodule status
git diff --check
git status --short
```

Expected: 编码检查打印文件数；`git submodule status` 无输出；`git diff --check` 无输出；`git status --short` 只列本计划内文件。

- [ ] **Step 7: 提交**

```bash
git add AGENTS.md README.md docs/README.md docs/quantum-visualization/README.md .agents/README.md .agents/active/quantum-visualization-foundation.md tests/test_quantum_visualization_docs.py
git commit -m "docs: activate quantum visualization foundation"
```

## 最终验收

Run:

```powershell
uv run --no-project python -m unittest discover -s tests -p "test_*.py" -v
git diff HEAD~6..HEAD --check
git status --short
```

Expected：全部标准库测试通过；六个实施 commit 的 diff 无空白错误；工作树干净。Blender runtime test 为 `Not Run`，因为本轮没有修改扩展代码、打包或运行时依赖。
