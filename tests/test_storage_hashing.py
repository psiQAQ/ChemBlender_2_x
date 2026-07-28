import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.core.storage.hashing import (
    sha256_bytes,
    sha256_file_snapshot,
)


class StorageHashingTests(unittest.TestCase):
    def test_bytes_and_file_snapshot_match_stdlib(self):
        payload = b"ChemBlender" * 10_000
        expected = hashlib.sha256(payload).hexdigest()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            source.write_bytes(payload)

            digest, size, prefix = sha256_file_snapshot(
                source,
                lambda: False,
                prefix_bytes=17,
            )

        self.assertEqual(sha256_bytes(payload), expected)
        self.assertEqual(digest, expected)
        self.assertEqual(size, len(payload))
        self.assertEqual(prefix, payload[:17])

    def test_snapshot_cancellation_stops_before_digest_publication(self):
        checks = iter((False, False, True))
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.bin"
            source.write_bytes(b"x" * 131_072)

            with self.assertRaisesRegex(InterruptedError, "cancelled"):
                sha256_file_snapshot(source, lambda: next(checks))


if __name__ == "__main__":
    unittest.main()
