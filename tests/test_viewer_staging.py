"""The shared source is vendored without external scientific wheels."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.scripts.stage_viewer import stage_viewer


class ViewerStagingTests(unittest.TestCase):
    def test_shared_worker_protocol_is_vendored_and_loads_without_external_tool(self):
        import subprocess
        import sys
        core = Path(__file__).resolve().parents[1] / "cbq_core"
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "ChemBlender"
            source.mkdir()
            (source / "blender_manifest.toml").write_text('wheels = []\n', encoding='utf-8')
            output = stage_viewer(source, root / "stage", core_source=core)
            original = (core / "worker_protocol.py").read_bytes()
            self.assertEqual((output / "_cbq_core/worker_protocol.py").read_bytes(), original)
            hashes = json.loads((output / "_cbq_core_source.json").read_text())['files']
            self.assertEqual(hashes['worker_protocol.py'], hashlib.sha256(original).hexdigest())
            script = """
import sys
sys.path.insert(0, sys.argv[1])
from _cbq_core.worker_protocol import PROTOCOL_VERSION, WorkerResult, WorkerStatus, result_document
from uuid import UUID
result = WorkerResult(request_id=UUID('30000000-0000-0000-0000-000000000003'), status=WorkerStatus.SUCCESS)
assert result_document(result)['protocol_version'] == PROTOCOL_VERSION == '1'
assert not any(name.split('.')[0] in {'chemblender_prepare', 'bpy', 'rdkit', 'gemmi', 'numpy'} for name in sys.modules)
"""
            result = subprocess.run([sys.executable, '-I', '-S', '-c', script, str(output)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_vendors_identical_core_and_excludes_wheels(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'ChemBlender'
            (source / 'wheels').mkdir(parents=True)
            (source / 'ui').mkdir()
            (source / 'blender_manifest.toml').write_text('', encoding='utf-8')
            (source / 'wheels/rdkit-test.whl').write_bytes(b'external wheel')
            (source / 'ui/panel.py').write_text(
                'from cbq_core.model import Structure\n', encoding='utf-8')
            core = root / 'cbq_core'
            core.mkdir()
            original = b'"""One authoritative source."""\n'
            (core / '__init__.py').write_bytes(original)
            output = stage_viewer(source, root / 'stage')
            self.assertFalse((output / 'wheels').exists())
            self.assertEqual((output / '_cbq_core/__init__.py').read_bytes(), original)
            self.assertEqual((output / 'ui/panel.py').read_text(),
                             'from .._cbq_core.model import Structure\n')
            self.assertEqual(json.loads((output / '_cbq_core_source.json').read_text())['files'],
                             {'__init__.py': hashlib.sha256(original).hexdigest()})
            (core / 'bad.py').write_text('from cbq_core.model import Structure\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, "relative imports"):
                stage_viewer(source, root / 'absolute-core-import')


if __name__ == '__main__':
    unittest.main()
