"""Reuse the research checker contracts; all fixtures are synthetic."""
import importlib.util
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'validate_evidence', ROOT / 'examples/tutorials/2.5.0/validate_evidence.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
with patch.dict(sys.modules, {'validate_evidence': validator}):
    contracts = runpy.run_path(str(ROOT / 'docs/chemblender25-research/test_validate_evidence.py'))


class TutorialEvidenceTests(contracts['EvidenceTests']):
    def replace_image(self, aid, suffix, payload):
        artifact = self.artifact(aid)
        artifact['path'] = aid + suffix
        path = self.root / artifact['path']
        path.write_bytes(payload)
        artifact['sha256'] = validator.sha256(path)

    def test_native_gui_jpeg_signature(self):
        # Signature check only, not a decoder or proof of screenshot authenticity.
        self.replace_image('pre', '.jpg', b'\xff\xd8\xffSYNTHETIC\xff\xd9')
        self.assertEqual(self.result()['verdict'], 'integrity_ok')

    def test_jpeg_cannot_replace_render(self):
        self.replace_image('render', '.jpg', b'\xff\xd8\xffSYNTHETIC\xff\xd9')
        self.assert_invalid()

    def test_jpeg_mislabeled_png_is_rejected(self):
        self.replace_image('pre', '.png', b'\xff\xd8\xffSYNTHETIC\xff\xd9')
        self.assert_invalid()

    def test_truncated_jpeg_is_rejected(self):
        self.replace_image('pre', '.jpeg', b'\xff\xd8\xffSYNTHETIC')
        self.assert_invalid()


if __name__ == '__main__':
    unittest.main()
