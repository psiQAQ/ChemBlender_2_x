import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ChemBlender import reader_api


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "water.cbsimple"


def load_reader():
    name = "_simplecoords_reader_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "reader.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)


class SimpleCoordsReaderTests(unittest.TestCase):
    def test_water_fixture_uses_public_reader_api(self):
        plugin = load_reader().create_plugin(reader_api)
        with TemporaryDirectory() as temporary:
            request = reader_api.ParseRequest(
                FIXTURE,
                hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                "balanced",
                {},
                Path(temporary),
                lambda _event: None,
                lambda: False,
            )
            batch = plugin.parse(request)

        self.assertEqual(batch.structures[0].atomic_numbers, (8, 1, 1))
        self.assertEqual(batch.structures[0].coordinates.shape, (3, 3))
        reader_api.internal_batch_from_public(batch)


if __name__ == "__main__":
    unittest.main()
