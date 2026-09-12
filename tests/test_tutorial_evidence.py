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
    def mark_incomplete(self, status):
        self.m.update(status=status, status_reason=f'Synthetic {status} run')

    def execution_supplement(self):
        artifact = self.artifact('assert')
        return {
            'schema_version': 1,
            'case_id': 'UNIT',
            'spec_sha256': validator.sha256(self.spec_path),
            'authorization': {
                'approved_by': 'user',
                'approved_at': '2026-09-10T00:00:00Z',
                'basis': 'Synthetic authorization contract',
            },
            'replays': [{
                'step_id': 's1',
                'interaction': 'authorized_mcp_replay',
                'classification': 'replay_not_direct_gui',
                'original_gui': {
                    'source_run_id': 'synthetic-original',
                    'source_extension_sha256': 'e' * 64,
                    'source_manifest_sha256': 'f' * 64,
                    'events_sha256': '1' * 64,
                    'event_id': 'original-e1',
                    'before_artifact_sha256': '2' * 64,
                    'after_artifact_sha256': '3' * 64,
                },
                'candidate_difference': {
                    'status': 'passed',
                    'to_extension_sha256': 'a' * 64,
                    'to_prepare_sha256': 'b' * 64,
                    'checked_fields': ['operator', 'scientific_output'],
                },
                'operator_receipt': {
                    'status': 'passed',
                    'artifact_id': 'assert',
                    'sha256': artifact['sha256'],
                },
            }],
        }

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

    def test_blocked_run_still_audits_tampered_artifact(self):
        self.mark_incomplete('blocked')
        (self.root / 'render.png').write_bytes(b'tampered')
        self.assert_invalid()

    def test_running_run_still_audits_missing_artifact(self):
        self.mark_incomplete('running')
        (self.root / 'render.png').unlink()
        self.assert_invalid()

    def test_failed_run_still_audits_path_escape(self):
        self.mark_incomplete('failed')
        self.artifact('pre')['path'] = '../outside.png'
        self.assert_invalid()

    def test_blocked_run_still_audits_wrong_hash(self):
        self.mark_incomplete('blocked')
        self.artifact('pre')['sha256'] = 'e' * 64
        self.assert_invalid()

    def test_running_run_still_audits_event_chain(self):
        self.mark_incomplete('running')
        self.m['steps'][0]['event_id'] = 'missing'
        self.assert_invalid()

    def test_minimal_not_run_needs_no_placeholder_evidence(self):
        self.m = {
            'schema_version': 1,
            'case_id': 'UNIT',
            'status': 'not_run',
            'status_reason': 'Synthetic case not executed',
            'spec_sha256': validator.sha256(self.spec_path),
        }
        result = self.result()
        self.assertEqual(result['verdict'], 'incomplete')
        self.assertEqual(result['integrity_status'], 'passed')
        self.assertEqual(result['technical_status'], 'incomplete')
        self.assertEqual(result['independent_review_status'], 'incomplete')
        self.assertEqual(result['acceptance_status'], 'incomplete')

    def test_10_missing_required_step(self):
        self.m['steps'] = []
        result = self.result()
        self.assertEqual(result['verdict'], 'incomplete')
        self.assertEqual(result['integrity_status'], 'passed')
        self.assertEqual(result['technical_status'], 'incomplete')

    def test_13_failed_science_check(self):
        self.m['checks'][0]['status'] = 'failed'
        result = self.result()
        self.assertEqual(result['verdict'], 'incomplete')
        self.assertEqual(result['integrity_status'], 'passed')
        self.assertEqual(result['technical_status'], 'incomplete')

    def test_14_missing_adjacent_project(self):
        artifact = self.artifact('blend')
        moved = self.root / 'other.blend'
        (self.root / 'project.blend').rename(moved)
        artifact['path'] = 'other.blend'
        result = self.result()
        self.assertEqual(result['verdict'], 'incomplete')
        self.assertEqual(result['integrity_status'], 'passed')
        self.assertEqual(result['technical_status'], 'incomplete')

    def test_17_missing_independent_review(self):
        self.alter_json('review', lambda value: value.update(independent=False))
        result = self.result()
        self.assertEqual(result['verdict'], 'incomplete')
        self.assertEqual(result['integrity_status'], 'passed')
        self.assertEqual(result['technical_status'], 'passed')
        self.assertEqual(result['independent_review_status'], 'incomplete')

    def test_wrong_candidate_hash_is_invalid_integrity(self):
        result = self.result(expected_extension='e' * 64)
        self.assertEqual(result['verdict'], 'invalid')
        self.assertEqual(result['integrity_status'], 'invalid')

    def test_historical_screenshot_cannot_be_relabelled(self):
        self.artifact('pre')['extension_sha256'] = 'e' * 64
        result = self.result()
        self.assertEqual(result['verdict'], 'invalid')
        self.assertEqual(result['integrity_status'], 'invalid')

    def test_execution_supplement_allows_only_explicit_replay(self):
        self.m['steps'][0].update(
            status='not_run', interaction='mcp_replay', replay_status='passed',
            artifact_ids=['assert'], reason='Authorized replay; not direct GUI',
        )
        supplement_path = self.root / 'execution-supplement.json'
        self.write_json(supplement_path, self.execution_supplement())
        result = self.result(execution_supplement=supplement_path)
        self.assertEqual(result['verdict'], 'integrity_ok')
        self.assertEqual(result['technical_status'], 'passed')

    def test_execution_supplement_requires_complete_reuse_chain(self):
        self.m['steps'][0].update(
            status='not_run', interaction='mcp_replay', replay_status='passed',
            artifact_ids=['assert'], reason='Authorized replay; not direct GUI',
        )
        supplement = self.execution_supplement()
        del supplement['replays'][0]['original_gui']['event_id']
        supplement_path = self.root / 'execution-supplement.json'
        self.write_json(supplement_path, supplement)
        result = self.result(execution_supplement=supplement_path)
        self.assertEqual(result['verdict'], 'invalid')
        self.assertEqual(result['integrity_status'], 'invalid')


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

    def test_environment_qualification_keeps_deployment_boundaries_separate(self):
        qualification_path = ROOT / 'examples/tutorials/2.5.0/environment-qualification.json'
        self.assertEqual(self.status['environment_qualification'], qualification_path.name)
        document = json.loads(qualification_path.read_text(encoding='utf-8'))
        allowed = {'development_reuse', 'isolated_install', 'distribution_ready'}
        environments = {item['name']: item for item in document['environments']}
        self.assertEqual(set(environments), {'standard', 'scientific', 'wavefunction', 'fermi'})
        for name, environment in environments.items():
            self.assertIn(environment['qualification'], allowed, name)
            if environment['cross_environment_pth']:
                self.assertEqual(environment['qualification'], 'development_reuse', name)
                self.assertFalse(environment['distribution_ready'], name)
            if environment['qualification'] == 'distribution_ready':
                self.assertTrue(environment['distribution_ready'], name)
                self.assertFalse(environment['wheel_python_files_changed'], name)
        self.assertEqual(environments['standard']['qualification'], 'isolated_install')
        self.assertEqual(environments['scientific']['qualification'], 'development_reuse')
        self.assertFalse(environments['wavefunction']['distribution_ready'])
        self.assertFalse(environments['fermi']['distribution_ready'])


class LocalBlockedManifestTests(unittest.TestCase):
    RUN_ROOT = ROOT / '.blend-analysis/2.5-real-user-tutorials/run-003'

    @unittest.skipUnless((RUN_ROOT / 'T01/run-manifest.json').is_file() and
                         (RUN_ROOT / 'T02/run-manifest.json').is_file(),
                         'local T01/T02 run-003 evidence is unavailable')
    def test_real_blocked_manifests_are_incomplete_but_corruption_is_invalid(self):
        for case_id in ('T01', 'T02'):
            with self.subTest(case_id=case_id):
                manifest = self.RUN_ROOT / case_id / 'run-manifest.json'
                spec_path = ROOT / f'examples/tutorials/2.5.0/{case_id}.case-spec.json'
                supplement = (ROOT / 'examples/tutorials/2.5.0/T01.execution-supplement.json'
                              if case_id == 'T01' else None)
                result = validator.audit(
                    manifest, spec_path, execution_supplement=supplement)
                self.assertEqual(result['verdict'], 'incomplete')
                self.assertEqual(result['integrity_status'], 'passed')
                document = json.loads(manifest.read_text(encoding='utf-8'))
                target = (manifest.parent / document['artifacts'][0]['path']).resolve()
                actual_sha256 = validator.sha256

                def wrong_hash(path):
                    return '0' * 64 if path.resolve() == target else actual_sha256(path)

                with patch.object(validator, 'sha256', side_effect=wrong_hash):
                    corrupted = validator.audit(
                        manifest, spec_path, execution_supplement=supplement)
                self.assertEqual(corrupted['verdict'], 'invalid')
                self.assertEqual(corrupted['integrity_status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
