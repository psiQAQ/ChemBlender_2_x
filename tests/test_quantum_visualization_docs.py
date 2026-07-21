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
