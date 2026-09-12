"""Reuse the research checker contracts; all fixtures are synthetic."""
import importlib.util
import json
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


class TutorialStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status = json.loads(
            (ROOT / 'examples/tutorials/2.5.0/status.json').read_text(encoding='utf-8')
        )

    def test_all_cases_have_separate_acceptance_dimensions(self):
        expected = {f'T{index:02d}' for index in range(21)} | {'B01'}
        cases = {case['case_id']: case for case in self.status['cases']}
        self.assertEqual(set(cases), expected)
        required = {
            'technical_status', 'scientific_processing', 'direct_gui',
            'authorized_replay', 'render', 'recovery', 'tutorial',
            'review_package', 'human_review', 'distribution', 'evidence_refs',
        }
        for case_id, case in cases.items():
            self.assertFalse(required - set(case), case_id)

    def test_receipts_cannot_be_summarized_as_not_run(self):
        for case in self.status['cases']:
            if case['evidence_refs']:
                self.assertNotEqual(case['status'], 'not_run', case['case_id'])
                self.assertTrue(case['status_reason'], case['case_id'])

    def test_human_technical_and_distribution_do_not_substitute(self):
        for case in self.status['cases']:
            if case['status'] == 'not_run':
                self.assertEqual(case['technical_status'], 'not_run', case['case_id'])
                self.assertFalse(case['evidence_refs'], case['case_id'])
            if case['human_review'] == 'passed':
                self.assertEqual(case['technical_status'], 'passed', case['case_id'])
            if case['distribution'] == 'passed':
                self.assertEqual(case['technical_status'], 'passed', case['case_id'])
                self.assertEqual(case['human_review'], 'passed', case['case_id'])


if __name__ == '__main__':
    unittest.main()
