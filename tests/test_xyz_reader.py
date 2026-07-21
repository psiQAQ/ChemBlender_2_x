from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
