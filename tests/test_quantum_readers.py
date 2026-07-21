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


ROOT = Path(__file__).resolve().parents[1]


def descriptor(
    reader_id,
    match=SniffMatch.POSSIBLE,
    priority=0,
    extensions=(".out",),
):
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


class ReaderRegistryTests(unittest.TestCase):
    def test_descriptor_normalizes_extensions_and_capabilities(self):
        reader = descriptor("test-reader", extensions=("OUT", ".LOG"))
        self.assertEqual(reader.extensions, (".out", ".log"))
        self.assertEqual(
            reader.capabilities["structure"],
            CapabilitySupport.SUPPORTED,
        )

    def test_registry_rejects_duplicate_reader_id(self):
        registry = ReaderRegistry()
        registry.register(descriptor("same"))
        with self.assertRaises(ValueError):
            registry.register(descriptor("same"))


if __name__ == "__main__":
    unittest.main()
