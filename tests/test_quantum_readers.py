from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.core import ImportBatch
from ChemBlender.core.readers import (
    AmbiguousReaderError,
    CapabilitySupport,
    ReaderAvailability,
    ReaderDescriptor,
    ReaderNotFoundError,
    ReaderRegistry,
    ReaderRuntimeDescriptor,
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
    def test_legacy_descriptor_gets_available_builtin_runtime_metadata(self):
        reader = descriptor("legacy")
        registry = ReaderRegistry((reader,))

        runtime = registry.runtime("legacy")

        self.assertIs(runtime.descriptor, reader)
        self.assertEqual(runtime.plugin_id, "chemblender.builtin")
        self.assertEqual(runtime.api_version, "0.1")
        self.assertEqual(runtime.execution_mode, "built_in")
        self.assertEqual(
            runtime.current_availability(),
            ReaderAvailability(True, "built_in", "available", ""),
        )
        self.assertIs(registry.select("unused", reader_id="legacy"), reader)

    def test_runtime_descriptor_keeps_selection_separate_from_availability(self):
        reader = descriptor("optional")
        runtime = ReaderRuntimeDescriptor(
            descriptor=reader,
            plugin_id="example.optional",
            api_version="0.1",
            execution_mode="worker",
            availability=lambda: ReaderAvailability(
                False,
                "worker",
                "dependency_unavailable",
                "worker dependency missing",
            ),
        )
        registry = ReaderRegistry((runtime,))

        self.assertIs(registry.select("unused", reader_id="optional"), reader)
        self.assertFalse(registry.runtime("optional").current_availability().available)

    def test_runtime_contract_rejects_invalid_modes_and_probe_results(self):
        with self.assertRaises(ValueError):
            ReaderAvailability(True, "thread", "available", "")
        with self.assertRaises(ValueError):
            ReaderAvailability(True, "built_in", "Invalid Code", "")

        runtime = ReaderRuntimeDescriptor(
            descriptor=descriptor("bad-probe"),
            availability=lambda: object(),
        )
        with self.assertRaises(TypeError):
            runtime.current_availability()

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

    def test_selects_highest_match_then_priority(self):
        registry = ReaderRegistry()
        registry.register(
            descriptor("probable", SniffMatch.PROBABLE, priority=100)
        )
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
                    registry.register(
                        descriptor(reader_id, SniffMatch.EXACT, priority=1)
                    )
                with self.assertRaises(AmbiguousReaderError):
                    registry.select(source)

    def test_explicit_reader_bypasses_sniff_and_file_read(self):
        registry = ReaderRegistry()
        registry.register(descriptor("chosen"))
        selected = registry.select(Path("missing.out"), reader_id="chosen")
        self.assertEqual(selected.reader_id, "chosen")

    def test_missing_explicit_reader_raises_not_found(self):
        with self.assertRaises(ReaderNotFoundError):
            ReaderRegistry().select(Path("missing.out"), reader_id="missing")

    def test_sniff_prefix_is_bounded(self):
        seen = []

        def sniff(path, prefix):
            seen.append(len(prefix))
            return SniffResult(SniffMatch.EXACT, "bounded")

        reader = descriptor("bounded")
        reader = ReaderDescriptor(
            reader.reader_id,
            reader.reader_version,
            reader.extensions,
            reader.capabilities,
            reader.priority,
            sniff,
            reader.parse,
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
            reader.reader_id,
            reader.reader_version,
            reader.extensions,
            reader.capabilities,
            reader.priority,
            reader.sniff,
            lambda path: object(),
        )
        registry = ReaderRegistry((bad,))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "sample.out"
            source.write_bytes(b"content")
            with self.assertRaises(TypeError):
                registry.parse(source)

    def test_legacy_file_validation_does_not_claim_mol2(self):
        source = (ROOT / "ChemBlender" / "scaffold.py").read_text(
            encoding="utf-8"
        )
        valid_exts = source.split("valid_exts = {", 1)[1].split("}", 1)[0]
        self.assertNotIn('".mol2"', valid_exts)


if __name__ == "__main__":
    unittest.main()
