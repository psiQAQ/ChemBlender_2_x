"""Reuse the research checker contracts; all fixtures are synthetic."""
import importlib.util
import hashlib
import json
from pathlib import Path
import runpy
import sys
import unittest
import zipfile
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
        cls.applicability = json.loads(
            (ROOT / 'examples/tutorials/2.5.0/P6-final-candidate-applicability.json').read_text(encoding='utf-8')
        )

    def test_final_candidate_applicability_preserves_historical_bytes(self):
        current = self.status['current_candidate']
        self.assertEqual(self.applicability['to_candidate']['extension_sha256'], current['extension_sha256'])
        self.assertEqual(self.applicability['to_candidate']['prepare_wheel_sha256'], current['prepare_wheel_sha256'])
        self.assertEqual(
            set(self.applicability['source_difference']['extension']),
            {'ChemBlender/electronic_plot.py', 'ChemBlender/ui/scientific_view.py'},
        )
        self.assertEqual(self.applicability['source_difference']['prepare'], ['chemblender_prepare/runtime.py'])
        self.assertEqual(self.applicability['human_review'], 'not_run')

    def test_primary_tutorial_routes_keep_run_metadata_in_appendix(self):
        tutorials = (
            ('en/first-aspirin.md', '## Validation appendix'),
            ('zh-CN/first-aspirin.md', '## 验证附录'),
            ('en/ethanol-conformers.md', '## Validation appendix'),
            ('zh-CN/ethanol-conformers.md', '## 验证附录'),
            ('en/aspirin-trajectory.md', '## Validation appendix'),
            ('zh-CN/aspirin-trajectory.md', '## 验证附录'),
        )
        hashes = (
            self.status['current_candidate']['extension_sha256'],
            self.status['current_candidate']['prepare_wheel_sha256'],
        )
        for relative, marker in tutorials:
            with self.subTest(tutorial=relative):
                text = (ROOT / 'docs/user' / relative).read_text(encoding='utf-8')
                self.assertEqual(text.count(marker), 1)
                body, appendix = text.split(marker)
                for audit_term in ('run-00', 'MCP', 'API replay', 'Computer Use',
                                   'Current-candidate', '当前候选', *hashes):
                    self.assertNotIn(audit_term, body)
                for candidate_hash in hashes:
                    self.assertIn(candidate_hash, appendix)
                self.assertTrue('human' in appendix.lower() or '人工' in appendix)

    def test_p6_tutorial_completeness_audit_covers_every_case(self):
        audit = json.loads((ROOT / 'examples/tutorials/2.5.0/P6-tutorial-completeness-audit.json').read_text(encoding='utf-8'))
        covered = set(audit['documented_cases']) | set(audit['missing_bilingual_case_chapters'])
        expected = {f'T{index:02d}' for index in range(21)} | {'B01'}
        self.assertEqual(covered, expected)
        self.assertFalse(set(audit['documented_cases']) & set(audit['missing_bilingual_case_chapters']))
        self.assertEqual(audit['status'], 'blocked')
        self.assertTrue(all(item['missing'] for item in audit['documented_cases'].values()))

    def test_p6_review_packages_keep_development_paths_in_evidence_only(self):
        audit = json.loads((ROOT / 'examples/tutorials/2.5.0/P6-review-package-path-audit.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['status'], 'passed')
        self.assertEqual(audit['crc_status'], 'passed_all')
        self.assertEqual(set(audit['archives']), {'T01', 'T02-current', 'T02-historical', 'T04', 'T06', 'T07', 'T17', 'scientific-viewer'})
        for name, archive in audit['archives'].items():
            self.assertFalse(archive['unsafe_member_names'], name)
            self.assertFalse(archive['development_paths_outside_evidence'], name)
            self.assertEqual(len(archive['sha256']), 64, name)

    def test_t01_t02_review_receipts_bind_current_execution_supplements(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        for case_id in ('T01', 'T02'):
            with self.subTest(case_id=case_id):
                receipt = json.loads((base / f'{case_id}-run010-package-check.json').read_text(encoding='utf-8'))
                supplement = base / f'{case_id}.current-execution-supplement.json'
                self.assertEqual(
                    receipt['included_evidence']['current_execution_supplement_sha256'],
                    hashlib.sha256(supplement.read_bytes()).hexdigest(),
                )

    def test_scientific_review_package_is_portable_and_complete(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        receipt = json.loads((base / 'P6-scientific-project-package-check.json').read_text(encoding='utf-8'))
        package = ROOT / receipt['package']['path']
        self.assertEqual(hashlib.sha256(package.read_bytes()).hexdigest(), receipt['package']['sha256'])
        with zipfile.ZipFile(package) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertEqual(len(names), receipt['package']['members'])
            self.assertEqual(sum(name.endswith('.blend') for name in names), 22)
            self.assertEqual(sum(name.endswith('/project.cbq/manifest.json') for name in names), 22)
            for name in names:
                self.assertFalse(name.startswith(('/', '\\')) or '..' in Path(name).parts or '\\' in name)
                if name.endswith('/project.cbq/manifest.json'):
                    text = archive.read(name).decode('utf-8')
                    self.assertNotIn('.blend-analysis', text)
                    self.assertNotIn('D:\\\\workspace', text)
                    self.assertNotIn('/mnt/', text)

    def test_independent_review_checklist_has_one_unsigned_section_per_case(self):
        path = ROOT / 'examples/tutorials/2.5.0/independent-human-review-checklists.md'
        text = path.read_text(encoding='utf-8')
        headings = {line.split()[1] for line in text.splitlines() if line.startswith('## T') or line.startswith('## B')}
        expected = {f'T{index:02d}' for index in range(21)} | {'B01'}
        self.assertEqual(headings, expected)
        self.assertNotIn('- [x]', text.lower())
        self.assertEqual(text.count('Reviewer／日期／签名：________________'), 22)
        self.assertTrue(all(case['human_review'] == 'not_run' for case in self.status['cases']))

    def test_local_artifacts_are_frozen_without_distribution_claim(self):
        audit = json.loads((ROOT / 'examples/tutorials/2.5.0/P6-final-artifact-freeze-audit.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['status'], 'passed_local_freeze_with_acceptance_blockers')
        self.assertTrue(audit['final_artifact_frozen'])
        self.assertFalse(audit['published'])
        self.assertEqual(audit['current_source_commit'], audit['frozen_local_artifacts']['extension']['source_commit'])
        self.assertTrue(all(len(item['sha256']) == 64 for item in audit['frozen_local_artifacts'].values()))

    def test_p6_full_suite_has_no_failures_or_errors(self):
        receipt = json.loads((ROOT / 'examples/tutorials/2.5.0/P6-full-test-check.json').read_text(encoding='utf-8'))
        counts = receipt['counts']
        self.assertEqual(receipt['status'], 'passed')
        self.assertEqual(receipt['exit_code'], 0)
        self.assertEqual(counts['failed'], 0)
        self.assertEqual(counts['errors'], 0)
        self.assertEqual(counts['total'], counts['passed'] + counts['skipped'])

    def test_current_extension_passed_clean_and_user_default_qualification(self):
        receipt = json.loads((ROOT / 'examples/tutorials/2.5.0/P6-current-extension-qualification.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['status'], 'passed')
        self.assertEqual(receipt['extension']['members'], 109)
        self.assertFalse(receipt['extension']['unsafe_members'])
        self.assertFalse(receipt['extension']['wheel_members'])
        self.assertTrue(all(value == 'passed' or value.startswith('passed_') or value == 'completed'
                            for value in receipt['checks'].values()))
        self.assertFalse(receipt['viewer_dependency_result']['rdkit_available'])
        self.assertFalse(receipt['viewer_dependency_result']['gemmi_available'])
        self.assertFalse(receipt['viewer_dependency_result']['prepare_available'])
        self.assertEqual(self.status['current_candidate']['extension_sha256'], receipt['extension']['sha256'])

    def test_p6_offline_gate_summary_preserves_blockers(self):
        receipt = json.loads((ROOT / 'examples/tutorials/2.5.0/P6-offline-gate-summary.json').read_text(encoding='utf-8'))
        checkers = receipt['case_checkers']
        self.assertEqual(checkers['discovered_manifest_count'], checkers['executed_manifest_count'])
        self.assertEqual({item['case_id'] for item in checkers['current_applicable']}, {'T01', 'T02', 'T06'})
        self.assertEqual(set(checkers['no_conforming_manifest']), {item['case_id'] for item in self.status['cases']} - {'T01', 'T02', 'T06'})
        self.assertEqual(receipt['static_gates']['offline_project_downloads'], 'passed_shared_companion_zip')
        self.assertEqual(receipt['acceptance']['ready_for_human_review'], [])
        self.assertEqual(receipt['acceptance']['human_review'], 'not_run')
        self.assertEqual(receipt['acceptance']['distribution'], 'blocked')

    def test_p6_local_delivery_report_is_explicitly_blocked(self):
        delivery = self.status['local_delivery']
        report = (ROOT / 'examples/tutorials/2.5.0' / delivery['report']).read_text(encoding='utf-8')
        self.assertEqual(delivery['status'], 'blocked')
        self.assertEqual(delivery['remote_writes'], 'not_authorized')
        self.assertIn('整体仍为 **Blocked**', report)
        self.assertIn('当前环境不能产生真实鼠标/键盘 GUI 事件', report)
        self.assertIn('22 个案例的 `human_review` 全部为 `not_run`', report)
        self.assertIn('`git push`、tag、GitHub Release、PyPI', report)

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
        self.assertEqual(
            set(environments),
            {'standard', 'scientific', 'wavefunction', 'fermi', 'qcschema'},
        )
        for name, environment in environments.items():
            self.assertIn(environment['qualification'], allowed, name)
            if environment['cross_environment_pth']:
                self.assertEqual(environment['qualification'], 'development_reuse', name)
                self.assertFalse(environment['distribution_ready'], name)
            if environment['qualification'] == 'distribution_ready':
                self.assertTrue(environment['distribution_ready'], name)
                self.assertFalse(environment['wheel_python_files_changed'], name)
        self.assertEqual(environments['standard']['qualification'], 'isolated_install')
        self.assertEqual(environments['scientific']['qualification'], 'isolated_install')
        self.assertEqual(environments['qcschema']['qualification'], 'isolated_install')
        self.assertIn('real PySCF compute passed', self.status['environment_routes']['qcschema_compute'])
        self.assertFalse(environments['wavefunction']['distribution_ready'])
        self.assertFalse(environments['fermi']['distribution_ready'])

    def test_current_replay_chains_match_current_receipts(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        candidate = self.status['current_candidate']
        for case_id in ('T01', 'T02'):
            receipt_path = base / f'{case_id}-current-candidate-check.json'
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            supplement = json.loads(
                (base / f'{case_id}.current-execution-supplement.json').read_text(encoding='utf-8')
            )
            self.assertEqual(supplement['target_run'], f'run-010/{case_id}')
            for replay in supplement['replays']:
                self.assertEqual(replay['interaction'], 'authorized_mcp_replay')
                self.assertEqual(replay['classification'], 'replay_not_direct_gui')
                self.assertEqual(
                    replay['candidate_difference']['to_extension_sha256'],
                    candidate['extension_sha256'],
                )
                self.assertEqual(
                    replay['candidate_difference']['to_prepare_sha256'],
                    candidate['prepare_wheel_sha256'],
                )
                self.assertEqual(
                    replay['operator_receipt']['sha256'], validator.sha256(receipt_path)
                )
            self.assertEqual(receipt['case_id'], case_id)

    def test_t04_current_sidebar_capture_is_byte_bound_to_provenance(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        receipt = json.loads((base / 'T04-current-candidate-check.json').read_text(encoding='utf-8'))
        capture = receipt['native_sidebar_capture']
        public_copy = ROOT / capture['public_copy']
        provenance = json.loads(
            (ROOT / 'docs/user/assets/2.5-tutorials/provenance.json').read_text(encoding='utf-8')
        )
        entry = next(item for item in provenance['images'] if item['path'] == public_copy.name)
        self.assertEqual(receipt['candidate']['extension_sha256'], self.applicability['from_candidate']['extension_sha256'])
        self.assertEqual(receipt['candidate']['prepare_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertEqual(validator.sha256(public_copy), capture['sha256'])
        self.assertEqual(entry['sha256'], capture['sha256'])
        self.assertEqual(entry['interaction'], 'os_gui')
        self.assertEqual(receipt['human_review'], 'not_run')

    def test_t03_standard_receipt_keeps_gui_and_lifecycle_blocked(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T03')
        spec_path = base / 'T03.case-spec.json'
        receipt = json.loads((base / 'T03-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads(spec_path.read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['inputs'], [{key: item[key] for key in ('path', 'sha256')} for item in spec['inputs'][:2]])
        self.assertEqual(receipt['verified']['confirmed_grouping'], 'passed')
        self.assertTrue(receipt['verified']['different_molecules'].startswith('AIN/CFF/TA1'))
        self.assertIn('prepare_gui', receipt['blocked'])
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t05_standard_receipt_preserves_format_boundaries(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T05')
        receipt = json.loads((base / 'T05-current-candidate-check.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertIn('no FrameSet fabricated', receipt['verified']['pdb_incompatible'])
        self.assertIn("unknown 'un'", receipt['verified']['mol2_partial'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed_all_five')
        self.assertIn('blender_views_render_lifecycle', receipt['blocked'])
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t08_historical_environment_blocker_remains_historical(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        receipt = json.loads((base / 'T08-environment-blocker.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['current_candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertFalse(receipt['current_candidate']['availability']['available'])
        self.assertEqual(receipt['existing_wavefunction_cache']['qualification'], 'development_reuse')
        self.assertEqual(receipt['existing_wavefunction_cache']['current_candidate_python_files_changed'], 8)
        self.assertEqual(receipt['scientific_processing'], 'not_run')

    def test_t08_current_science_keeps_downstream_gates_separate(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T08')
        receipt = json.loads((base / 'T08-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T08.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(
            [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in receipt['inputs']],
            [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in spec['inputs']],
        )
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed for both paired projects')
        self.assertTrue(receipt['verified']['method_inference_avoided'])
        self.assertEqual({item['index'] for item in receipt['grids']}, {4, 5})
        for grid in receipt['grids']:
            self.assertLess(grid['minimum'], -0.03)
            self.assertGreater(grid['maximum'], 0.03)
            self.assertGreater(grid['positive_voxels_at_0.03'], 0)
            self.assertGreater(grid['negative_voxels_at_minus_0.03'], 0)
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['distribution'], 'blocked')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t09_current_density_science_keeps_downstream_gates_separate(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T09')
        receipt = json.loads((base / 'T09-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T09.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['inputs'], [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in spec['inputs']])
        self.assertAlmostEqual(float(receipt['verified']['water_total_grid'].split('integral ')[1].split(' electrons')[0]), 10.009725189952228)
        self.assertIn('maximum absolute difference 6.20106722047653e-14', receipt['verified']['water_orbital_rdm_match'])
        self.assertIn('minimum -0.03088356337703481', receipt['verified']['ch3_spin_grid'])
        self.assertIn('post-SCF minus SCF', receipt['verified']['nitrogen_difference'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed for water total, CH3 spin and nitrogen paired-level difference projects')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t10_current_density_esp_science_keeps_viewer_gates_separate(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T10')
        receipt = json.loads((base / 'T10-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T10.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['input'], {key: spec['inputs'][0][key] for key in ('path', 'sha256', 'bytes')})
        self.assertTrue(receipt['verified']['same_affine_grid'])
        self.assertEqual(receipt['verified']['density_unit'], 'electron_per_cubic_bohr')
        self.assertEqual(receipt['verified']['esp_unit'], 'hartree_per_elementary_charge')
        self.assertGreater(receipt['verified']['surface_band_voxels'], 0)
        self.assertLess(receipt['verified']['surface_esp_range'][0], 0)
        self.assertGreater(receipt['verified']['surface_esp_range'][1], 0)
        self.assertIn('exit 1 and no output project', receipt['verified']['nuclear_singularity_recovery'])
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t11_current_vibration_science_preserves_missing_fields(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T11')
        receipt = json.loads((base / 'T11-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T11.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['inputs'], [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in spec['inputs']])
        self.assertIn('54 finite modes', receipt['verified']['common'])
        self.assertIn('Raman absent', receipt['verified']['gaussian_ir'])
        self.assertIn('reduced masses and force constants absent', receipt['verified']['orca_ir'])
        self.assertIn('not synthesized', receipt['verified']['missing_fields'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed_all_four')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t11_t14_historical_scientific_route_blocker_remains_historical(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        receipt = json.loads((base / 'T11-T14-scientific-route-blocker.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['route']['qualification'], 'development_reuse')
        self.assertEqual(len(receipt['route']['cross_environment_paths']), 2)

    def test_t13_current_electronic_structure_keeps_independent_calculations_separate(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T13')
        receipt = json.loads((base / 'T13-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T13.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['inputs'], [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in spec['inputs']])
        self.assertIn('10 explicit branches', receipt['verified']['k_path'])
        self.assertIn('2x160x13x2x9', receipt['verified']['band_projections'])
        self.assertIn('not silently aligned or merged', receipt['verified']['independent_calculation_boundary'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed_both')
        self.assertTrue(all(
            len(value) == 64 for key, value in receipt['raw_evidence'].items()
            if key.endswith('_sha256')
        ))
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t14_current_phonon_science_keeps_animation_gates_separate(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T14')
        receipt = json.loads((base / 'T14-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T14.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['inputs'], [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in spec['inputs']])
        self.assertIn('maximum absolute difference 0', receipt['verified']['source_consistency'])
        self.assertIn('2x6x2x3', receipt['verified']['eigenvectors'])
        self.assertIn('exp_i_2pi_qR_minus_phase', receipt['verified']['periodic_phase'])
        self.assertIn('neither field is synthesized', receipt['verified']['missing_fields'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed')
        self.assertTrue(all(
            len(value) == 64 for key, value in receipt['raw_evidence'].items()
            if key.endswith('_sha256')
        ))
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t12_current_td_science_keeps_orca_gauge_ambiguous(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T12')
        receipt = json.loads((base / 'T12-current-candidate-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T12.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['inputs'], [{key: item[key] for key in ('path', 'sha256', 'bytes')} for item in spec['inputs']])
        self.assertIn('gauge length', receipt['verified']['gaussian_rotatory_evidence'])
        self.assertIn('unit unknown and no gauge claim', receipt['verified']['orca5'])
        self.assertIn('absent and not synthesized', receipt['verified']['orca_missing_transition_dipoles'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed_all_three')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t15_current_science_keeps_gui_and_distribution_blocked(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T15')
        spec_path = base / 'T15.case-spec.json'
        receipt_path = base / 'T15-current-candidate-check.json'
        spec = json.loads(spec_path.read_text(encoding='utf-8'))
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        source = ROOT / spec['inputs'][0]['path']
        self.assertEqual(source.stat().st_size, spec['inputs'][0]['bytes'])
        self.assertEqual(validator.sha256(source), spec['inputs'][0]['sha256'])
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['candidate']['critic2_route_qualification'], 'development_reuse')
        self.assertIn('5 critical points', receipt['verified']['qtaim'])
        self.assertIn('40x40x40', receipt['verified']['nci'])
        self.assertFalse(receipt['verified']['bond_energy_claimed'])
        self.assertEqual(receipt['raw_evidence']['root'], '.blend-analysis/2.5-real-user-tutorials/run-011/T15')
        self.assertTrue(all(
            len(value) == 64 for key, value in receipt['raw_evidence'].items()
            if key.endswith('_sha256')
        ))
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['distribution'], 'blocked')
        self.assertEqual(case['human_review'], 'not_run')
        self.assertEqual(self.status['environment_routes']['critic2'], 'development_reuse: retained WSL ELF configured per run')

    def test_t19_external_reader_does_not_claim_ordinary_import(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T19')
        spec = json.loads((base / 'T19.case-spec.json').read_text(encoding='utf-8'))
        receipt = json.loads((base / 'T19-current-candidate-check.json').read_text(encoding='utf-8'))
        for item in spec['inputs']:
            path = ROOT / item['path']
            self.assertEqual(path.stat().st_size, item['bytes'])
            self.assertEqual(validator.sha256(path), item['sha256'])
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertEqual(receipt['candidate']['reader_api_version'], '1.0-rc1')
        self.assertIn('22 built-in readers', receipt['verified']['ordinary_import'])
        self.assertFalse(receipt['verified']['historical_blender_extension_installed'])
        self.assertFalse(receipt['verified']['distribution_claimed'])
        self.assertIn('not promised as stable', receipt['api_boundary']['statement'])
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['distribution'], 'blocked')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t20_separates_exchange_from_real_compute_and_downstream_gates(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T20')
        spec = json.loads((base / 'T20.case-spec.json').read_text(encoding='utf-8'))
        receipt = json.loads((base / 'T20-current-candidate-check.json').read_text(encoding='utf-8'))
        for item in spec['inputs']:
            path = ROOT / item['path']
            self.assertEqual(path.stat().st_size, item['bytes'])
            self.assertEqual(validator.sha256(path), item['sha256'])
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertIn('qc_schema_output/1', receipt['verified']['exchange'])
        self.assertIn('force is its negative', receipt['verified']['gradient_semantics'])
        self.assertTrue(receipt['verified']['actual_compute_succeeded'])
        self.assertLess(receipt['verified']['absolute_difference_hartree'], 1e-9)
        self.assertEqual(receipt['verified']['computed_cbq_validation'], 'passed')
        self.assertIn('Not run', receipt['blocked']['gui_render_lifecycle'])
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['distribution'], 'blocked')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t16_private_fermi_cache_receipt_remains_historical(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        spec = json.loads((base / 'T16.case-spec.json').read_text(encoding='utf-8'))
        receipt = json.loads((base / 'T16-environment-license-blocker.json').read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'examples/scientific-visualization/input-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['private_input_record']['archive_sha256'], manifest['fermi_cache']['sha256'])
        self.assertEqual(spec['private_input_record']['distribution'], 'historical_cache_only')
        self.assertEqual(receipt['private_cache']['qualification'], 'development_reuse')
        self.assertEqual(receipt['private_cache']['current_candidate_python_files_changed'], 8)
        self.assertFalse(receipt['private_cache']['potcar_extracted_or_distributed'])
        self.assertFalse(receipt['private_cache']['pickle_extracted_executed_or_distributed'])
        self.assertEqual(receipt['private_cache']['scientific_processing'], 'not_run')
        self.assertFalse(receipt['current_operation_probe']['output_published'])

    def test_t16_current_fermi_surface_binds_public_allowlist_and_recovery(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T16')
        spec = json.loads((base / 'T16.case-spec.json').read_text(encoding='utf-8'))
        receipt = json.loads((base / 'T16-current-candidate-check.json').read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'examples/scientific-visualization/input-manifest.json').read_text(encoding='utf-8'))
        for item in spec['inputs']:
            path = ROOT / item['path']
            self.assertEqual(path.stat().st_size, item['bytes'])
            self.assertEqual(validator.sha256(path), item['sha256'])
        public = manifest['fermi_public_bundle']
        self.assertEqual(public['license'], 'MIT')
        self.assertEqual(public['license_evidence']['sha256'], receipt['license']['dataset_card_sha256'])
        names = {path.name for path in (ROOT / 'examples/scientific-visualization/inputs/fermi/SrVO3').iterdir()}
        self.assertTrue({'POTCAR', 'WAVECAR', 'ebs.pkl', 'structure.pkl'}.isdisjoint(names))
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.status['current_prepare_candidate']['prepare_wheel_sha256'])
        self.assertIn('9261 full k points', receipt['verified']['mesh'])
        self.assertIn('5064 valid non-degenerate triangles', receipt['verified']['surface'])
        self.assertIn('fermi_source_invalid', receipt['verified']['hash_recovery'])
        self.assertIn('returned cancelled', receipt['verified']['cancel_recovery'])
        self.assertEqual(receipt['verified']['cbq_validation'], 'passed')
        self.assertEqual(case['scientific_processing'], 'passed')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['distribution'], 'blocked')
        self.assertEqual(case['human_review'], 'not_run')

    def test_b01_unavailable_boundary_is_not_positive_fetch(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'B01')
        spec = json.loads((base / 'B01.case-spec.json').read_text(encoding='utf-8'))
        receipt = json.loads((base / 'B01-current-candidate-check.json').read_text(encoding='utf-8'))
        request = ROOT / spec['inputs'][0]['path']
        self.assertEqual(request.stat().st_size, spec['inputs'][0]['bytes'])
        self.assertEqual(validator.sha256(request), spec['inputs'][0]['sha256'])
        self.assertEqual(receipt['candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertIn('available=false', receipt['verified']['capability'])
        self.assertFalse(receipt['verified']['network_request_performed'])
        self.assertFalse(receipt['verified']['positive_fetch_succeeded'])
        self.assertFalse(receipt['verified']['offline_fixture_claimed_as_live'])
        self.assertFalse(receipt['verified']['pubchem_claimed_as_generic_provider'])
        self.assertEqual(case['scientific_processing'], 'not_applicable_boundary')
        self.assertEqual(case['technical_status'], 'incomplete')
        self.assertEqual(case['direct_gui'], 'not_run')
        self.assertEqual(case['distribution'], 'not_applicable_boundary')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t08_t14_specs_bind_existing_input_bytes(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        for case_id in ('T08', 'T09', 'T10', 'T11', 'T12', 'T13', 'T14'):
            spec = json.loads((base / f'{case_id}.case-spec.json').read_text(encoding='utf-8'))
            for item in spec['inputs']:
                path = ROOT / item['path']
                self.assertEqual(path.stat().st_size, item['bytes'], (case_id, path))
                self.assertEqual(validator.sha256(path), item['sha256'], (case_id, path))

    def test_t06_current_frame_panel_values_match_frozen_spec(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        receipt = json.loads((base / 'T06-current-frame-panel-check.json').read_text(encoding='utf-8'))
        spec = json.loads((base / 'T06.case-spec.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['sample_frames'], spec['reference']['sample_frames'])
        self.assertTrue(receipt['scientific_arrays_unchanged'])
        self.assertFalse(receipt['viewer_forbidden_modules_loaded'])
        self.assertEqual(receipt['direct_gui'], 'blocked_for_new_panel_capture')
        self.assertEqual(receipt['human_review'], 'not_run')

    def test_t07_recovery_and_review_package_remain_separately_classified(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T07')
        candidate = json.loads((base / 'T07-current-candidate-check.json').read_text(encoding='utf-8'))
        recovery = json.loads((base / 'T07-run010-offline-recovery-check.json').read_text(encoding='utf-8'))
        package = json.loads((base / 'T07-run010-package-check.json').read_text(encoding='utf-8'))
        self.assertEqual(candidate['accepted_candidate']['extension_sha256'], self.applicability['from_candidate']['extension_sha256'])
        self.assertEqual(recovery['status'], 'passed')
        self.assertEqual(recovery['direct_gui'], 'not_run_for_recovery')
        self.assertEqual(package['classification'], 'review_only')
        self.assertEqual(package['cold_open']['status'], 'passed')
        self.assertEqual(package['limitations'][-1], 'VASP direct GUI and independent human review are not run.')
        self.assertEqual(case['review_package'], 'passed')
        self.assertEqual(case['human_review'], 'not_run')

    def test_t17_current_regression_and_prepare_handover_cover_all_formats(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        case = next(item for item in self.status['cases'] if item['case_id'] == 'T17')
        current = json.loads((base / 'T17-current-candidate-check.json').read_text(encoding='utf-8'))
        package = json.loads((base / 'T17-run010-package-check.json').read_text(encoding='utf-8'))
        self.assertEqual(current['current_candidate']['prepare_wheel_sha256'], self.applicability['from_candidate']['prepare_wheel_sha256'])
        self.assertEqual(current['regression']['format_count'], 13)
        self.assertEqual(current['regression']['byte_equal_to_scientifically_checked_run006_outputs'], 'passed_all')
        self.assertEqual(current['historical_gui_candidate']['classification'], 'historical_direct_gui_not_relabelled')
        self.assertEqual(package['contents']['authoritative_source_cbq_count'], 13)
        self.assertEqual(package['contents']['roundtrip_cbq_count'], 13)
        self.assertEqual(package['extracted_validation']['validated_cbq_count'], 26)
        self.assertEqual(package['contents']['blender_project'], 'not_applicable_prepare_only_case')
        self.assertEqual(case['render'], 'not_applicable')
        self.assertEqual(case['human_review'], 'not_run')

    def test_p0_checker_summary_matches_blocked_statuses(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        summary = json.loads((base / 'P4-p0-checker-summary.json').read_text(encoding='utf-8'))
        p0 = {item['case_id']: item for item in summary['cases']}
        self.assertEqual(set(p0), {'T00', 'T01', 'T02', 'T04', 'T06', 'T07', 'T17', 'T18'})
        self.assertEqual(set(summary['blocked']), set(p0))
        self.assertFalse(summary['ready_for_human_review'])
        cases = {item['case_id']: item for item in self.status['cases']}
        for case_id, result in p0.items():
            self.assertEqual(result['classification'], 'blocked', case_id)
            self.assertEqual(cases[case_id]['status'], 'blocked', case_id)
            self.assertEqual(cases[case_id]['human_review'], 'not_run', case_id)
        self.assertEqual(p0['T01']['integrity_status'], 'passed')
        self.assertEqual(p0['T02']['integrity_status'], 'passed')
        self.assertEqual(p0['T06']['verdict'], 'invalid')

    def test_t18_current_audit_preserves_gui_and_native_boundaries(self):
        base = ROOT / 'examples/tutorials/2.5.0'
        receipt = json.loads((base / 'T18-current-candidate-check.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['status'], 'blocked')
        self.assertEqual(receipt['verified']['gui_save_as_and_cancel'], 'passed_historical_candidate')
        self.assertEqual(receipt['verified']['legacy_export_restore_and_portable_cold_reopen'], 'passed_native_replay')
        self.assertIn('legacy_migration_direct_gui', receipt['blocked'])
        self.assertEqual(receipt['human_review'], 'not_run')


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
