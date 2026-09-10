"""Synthetic unit tests ONLY. No fixture is a real Blender result or screenshot."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from validate_evidence import audit, read_json, sha256


def png_fixture():
    # A 1x1 synthetic PNG exercises file validation, never GUI authenticity.
    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body +
                struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\0\0\0\0')) + chunk(b'IEND', b''))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-evidence-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spec_path = self.root / 'spec.json'
        self.manifest_path = self.root / 'run.json'
        self.spec = dict(schema_version=1, case_id='UNIT',
                         required_steps=[dict(id='s1', requires_gui=True)],
                         required_checks=['science'],
                         required_artifact_kinds=['gui_raw','render','events','assertions','environment',
                                                  'scene_blend','cbq_manifest','lifecycle','review'],
                         requires_project_pair=True, requires_cold_reopen=True,
                         requires_independent_review=True)
        self.write_json(self.spec_path, self.spec)
        self.m = dict(schema_version=1,case_id='UNIT',status='passed',synthetic=True,
                      spec_sha256=sha256(self.spec_path),
                      baseline=dict(reviewed_commit='c'*40,extension_sha256='a'*64,prepare_sha256='b'*64),
                      environment=dict(blender_version='synthetic-test',operating_system='synthetic-test',
                                       profile_id='synthetic-profile',run_id='synthetic-unit-run'),
                      artifacts=[],steps=[],checks=[])
        for aid in ('pre','post'):
            self.add_artifact(aid, 'gui_raw', aid+'.png', png_fixture())
        self.add_artifact('render','render','render.png',png_fixture())
        self.add_artifact('blend','scene_blend','project.blend',b'SYNTHETIC UNIT FIXTURE; NOT A BLEND FILE')
        self.add_json('cbq','cbq_manifest','project.cbq/manifest.json',{'synthetic':True})
        self.add_json('env','environment','environment.json',{'synthetic':True})
        self.add_json('assert','assertions','assertions.json',{'synthetic':True})
        self.add_json('events','events','events.json',[dict(event_id='e1',step_id='s1',interaction='os_gui',
                     action='SYNTHETIC action; not a real click',timestamp_utc='2026-09-10T00:00:00Z',
                     session_id='synthetic-1',before_artifact_id='pre',after_artifact_id='post')])
        self.add_json('life','lifecycle','lifecycle.json',dict(status='passed',saved_session_id='synthetic-1',
                      reopened_session_id='synthetic-2',before_scientific_hashes={'array':'d'*64},
                      after_scientific_hashes={'array':'d'*64}))
        self.add_json('review','review','review.json',dict(status='passed',reviewer='synthetic-unit-test',independent=True))
        self.m['steps']=[dict(id='s1',status='passed',interaction='os_gui',event_id='e1',
                            before_artifact_id='pre',after_artifact_id='post')]
        self.m['checks']=[dict(id='science',status='passed',expected='synthetic',observed='synthetic',artifact_ids=['assert'])]

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def add_artifact(self, aid, kind, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        item = dict(id=aid,kind=kind,path=relative,sha256=sha256(path))
        if kind in {'gui_raw','render'}:
            item['extension_sha256']='a'*64
        self.m['artifacts'].append(item)

    def add_json(self, aid, kind, relative, value):
        self.add_artifact(aid,kind,relative,json.dumps(value).encode())

    def artifact(self, aid):
        return next(a for a in self.m['artifacts'] if a['id']==aid)

    def alter_json(self, aid, mutator):
        a=self.artifact(aid); path=self.root/a['path']
        doc=read_json(path); mutator(doc); self.write_json(path,doc); a['sha256']=sha256(path)

    def result(self, **kwargs):
        self.write_json(self.manifest_path,self.m)
        return audit(self.manifest_path,self.spec_path,**kwargs)

    def assert_invalid(self, **kwargs):
        self.assertEqual(self.result(**kwargs)['verdict'],'invalid')

    def test_01_synthetic_consistency_is_not_real_validation(self):
        r=self.result()
        self.assertEqual(r['verdict'],'integrity_ok')
        self.assertIn('no Blender execution',r['limitation'])

    def test_02_synthetic_publish_is_rejected(self):
        self.assert_invalid(publish=True,expected_extension='a'*64,expected_prepare='b'*64)

    def test_03_missing_independent_release_hashes(self):
        self.m['synthetic']=False
        self.assert_invalid(publish=True)

    def test_04_expected_build_mismatch(self):
        self.assert_invalid(expected_extension='e'*64)

    def test_05_image_from_different_build(self):
        self.artifact('pre')['extension_sha256']='e'*64
        self.assert_invalid()

    def test_06_artifact_tampering(self):
        (self.root/'render.png').write_bytes(b'tampered')
        self.assert_invalid()

    def test_07_unsafe_path(self):
        self.artifact('pre')['path']='../outside.png'
        self.assert_invalid()

    def test_08_windows_absolute_path(self):
        self.artifact('pre')['path']='C:\\private\\image.png'
        self.assert_invalid()

    def test_09_link_escape(self):
        target=self.root/'pre.png'
        link=self.root/'linked.png'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('OS does not permit symlink creation')
        self.artifact('pre')['path']='linked.png'
        self.assert_invalid()

    def test_10_missing_required_step(self):
        self.m['steps']=[]
        self.assert_invalid()

    def test_11_operator_cannot_replace_gui(self):
        self.m['steps'][0]['interaction']='blender_operator'
        self.assert_invalid()

    def test_12_missing_gui_event(self):
        self.m['steps'][0]['event_id']='missing'
        self.assert_invalid()

    def test_13_failed_science_check(self):
        self.m['checks'][0]['status']='failed'
        self.assert_invalid()

    def test_14_missing_adjacent_project(self):
        a=self.artifact('blend')
        p=self.root/'other.blend'; (self.root/'project.blend').rename(p)
        a['path']='other.blend'
        self.assert_invalid()

    def test_15_not_a_new_session(self):
        self.alter_json('life',lambda d:d.update(reopened_session_id=d['saved_session_id']))
        self.assert_invalid()

    def test_16_scientific_array_changed(self):
        self.alter_json('life',lambda d:d.update(after_scientific_hashes={'array':'e'*64}))
        self.assert_invalid()

    def test_17_missing_independent_review(self):
        self.alter_json('review',lambda d:d.update(independent=False))
        self.assert_invalid()

    def test_18_spec_changed_without_manifest_update(self):
        self.spec['new_note']='changed'; self.write_json(self.spec_path,self.spec)
        self.assert_invalid()

    def test_19_duplicate_json_keys_and_nonfinite_values(self):
        for text in ('{"schema_version":1,"schema_version":2}','{"x":NaN}'):
            with self.subTest(text=text):
                self.manifest_path.write_text(text,encoding='utf-8')
                r=audit(self.manifest_path,self.spec_path)
                self.assertEqual(r['verdict'],'invalid')

    def test_20_not_run_never_passes(self):
        self.m.update(status='not_run',status_reason='Not executed')
        self.assertEqual(self.result()['verdict'],'incomplete')


if __name__=='__main__':
    unittest.main(verbosity=2)
