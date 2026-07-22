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

    def test_topic_plans_have_required_sections(self):
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
            "docs/quantum-visualization/plans/wavefunction-and-grids.md",
            "docs/quantum-visualization/plans/blender-visualization.md",
            "docs/quantum-visualization/plans/periodic-electronic-structure.md",
            "docs/quantum-visualization/plans/storage-and-workers.md",
            "docs/quantum-visualization/plans/workflows-and-connectors.md",
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

    def test_reference_catalog_and_pinned_submodule(self):
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
        gitmodules = self.read_doc(".gitmodules")
        self.assertIn("submodules/cclib", gitmodules)
        self.assertIn("submodules/iodata", gitmodules)
        self.assertIn("submodules/gbasis", gitmodules)
        children = {path.name for path in (ROOT / "submodules").iterdir()}
        self.assertEqual(children, {"README.md", "cclib", "gbasis", "iodata"})
        self.assertIn("07260dd0394cb1a2381d4d897746d727a12ad6ce", placeholder)
        self.assertIn("adab5813713ba64641565eb2a8c11803a4e9bba6", placeholder)
        self.assertIn("6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f", placeholder)

    def test_single_active_task(self):
        active = sorted((ROOT / ".agents" / "active").glob("*.md"))
        self.assertEqual(
            [path.name for path in active],
            ["vibrations-and-spectra.md"],
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


if __name__ == "__main__":
    unittest.main()
