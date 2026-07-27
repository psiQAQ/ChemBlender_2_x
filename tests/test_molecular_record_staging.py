import tempfile
import unittest
import hashlib
from pathlib import Path
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    CapabilitySupport,
    ImportBatch,
    MolecularRecord,
    ParserReport,
    ProvenanceRecord,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
    Structure,
    close_session,
    create_session,
)
from ChemBlender.core.import_pipeline import (
    ImportCommitDecisions,
    ImportRequest,
    ImportSource,
    ReaderOverride,
    StagedImportSession,
    ValidationMode,
    commit_import_preview,
)
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.protocol import ParseRequest
from ChemBlender.reader_api.registry import (
    ReaderPluginRegistry,
    _BuiltinReaderPlugin,
    _builtin_manifest,
    _builtin_plugin,
)


class MolecularRecordStagingTests(unittest.TestCase):
    def test_builtin_record_binds_to_the_staged_revision_and_commits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "records.synthetic"
            source_path.write_bytes(b"record")
            structure_id = uuid4()
            record_id = uuid4()
            provenance_id = uuid4()

            def parse(request):
                structure = Structure(
                    id=structure_id,
                    revision="structure-r1",
                    atomic_numbers=(1,),
                    coordinates=ArrayData(
                        numpy.asarray(((0.0, 0.0, 0.0),)),
                        ("atom", "xyz"),
                        "angstrom",
                    ),
                )
                provenance = ProvenanceRecord(
                    id=provenance_id,
                    revision="provenance-r1",
                    producer="synthetic",
                    producer_version="1",
                    source=request.source_path.name,
                    source_hash=request.source_content_hash,
                    parent_ids=(),
                    operation="parse",
                    parameters=(),
                )
                record = MolecularRecord(
                    id=record_id,
                    revision="record-r1",
                    source_revision_id=request.source_revision_id,
                    record_key="record-0001",
                    structure_id=structure.id,
                    topology_id=None,
                    raw_block=b"record",
                    title="record",
                    source_record_index=0,
                    block_version="V2000",
                    writer_name=None,
                    writer_version=None,
                    ordered_raw_properties=(),
                    provenance_ids=(provenance.id,),
                )
                return ImportBatch(
                    structures=(structure,),
                    molecular_records=(record,),
                    provenance=(provenance,),
                    report=ParserReport(
                        "synthetic-record",
                        "1",
                        (structure.id, record.id, provenance.id),
                        ("structure",),
                        (),
                    ),
                )

            descriptor = ReaderDescriptor(
                reader_id="synthetic-record",
                reader_version="1",
                extensions=(".synthetic",),
                capabilities={"structure": CapabilitySupport.SUPPORTED},
                priority=100,
                sniff=lambda path, prefix: SniffResult(SniffMatch.EXACT, "fixture"),
                parse=lambda path: ImportBatch(),
                parse_request=parse,
            )
            registry = ReaderPluginRegistry(
                (_builtin_plugin(descriptor, _builtin_manifest((descriptor,))),)
            )
            source = ImportSource(source_path)
            request = ImportRequest(
                (source,),
                ValidationMode.BALANCED,
                (ReaderOverride(source.id, descriptor.reader_id),),
            )
            staged_session = StagedImportSession.create(temp_parent=root)
            project_session = create_session(temp_parent=root)
            try:
                preview = preflight_reader_plugins(request, registry, staged_session)
                staged = staged_session.result(preview.staged_batch_ids[0])
                revision_id = staged.source_revisions[0].id

                self.assertEqual(staged.molecular_records[0].source_revision_id, revision_id)
                self.assertEqual(
                    staged.source_revisions[0].created_entity_ids,
                    (structure_id, record_id, provenance_id),
                )
                result = commit_import_preview(
                    project_session,
                    staged_session,
                    preview,
                    ImportCommitDecisions(),
                )
                self.assertEqual(
                    result.project.molecular_records[record_id].source_revision_id,
                    revision_id,
                )
            finally:
                close_session(project_session)
                staged_session.discard()

    def test_builtin_wrong_record_revision_fails_closed_before_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "wrong.synthetic"
            source_path.write_bytes(b"record")
            structure_id = uuid4()
            record_id = uuid4()

            def parse(request):
                structure = Structure(
                    id=structure_id,
                    revision="structure-r1",
                    atomic_numbers=(1,),
                    coordinates=ArrayData(
                        numpy.asarray(((0.0, 0.0, 0.0),)),
                        ("atom", "xyz"),
                        "angstrom",
                    ),
                )
                record = MolecularRecord(
                    id=record_id,
                    revision="record-r1",
                    source_revision_id=uuid4(),
                    record_key="record-0001",
                    structure_id=structure.id,
                    topology_id=None,
                    raw_block=b"record",
                    title="record",
                    source_record_index=0,
                    block_version="V2000",
                    writer_name=None,
                    writer_version=None,
                    ordered_raw_properties=(),
                    provenance_ids=(),
                )
                return ImportBatch(
                    structures=(structure,),
                    molecular_records=(record,),
                    report=ParserReport(
                        "wrong-record",
                        "1",
                        (structure.id, record.id),
                        ("structure",),
                        (),
                    ),
                )

            descriptor = ReaderDescriptor(
                reader_id="wrong-record",
                reader_version="1",
                extensions=(".synthetic",),
                capabilities={"structure": CapabilitySupport.SUPPORTED},
                priority=100,
                sniff=lambda path, prefix: SniffResult(SniffMatch.EXACT, "fixture"),
                parse=lambda path: ImportBatch(),
                parse_request=parse,
            )
            registry = ReaderPluginRegistry(
                (_builtin_plugin(descriptor, _builtin_manifest((descriptor,))),)
            )
            source = ImportSource(source_path)
            request = ImportRequest(
                (source,),
                ValidationMode.BALANCED,
                (ReaderOverride(source.id, descriptor.reader_id),),
            )
            staged_session = StagedImportSession.create(temp_parent=root)
            try:
                preview = preflight_reader_plugins(request, registry, staged_session)
                staged = staged_session.result(preview.staged_batch_ids[0])

                self.assertEqual(staged.molecular_records, ())
                self.assertEqual(
                    tuple(item.code for item in staged.diagnostics),
                    ("preflight.invalid_reader_result",),
                )
                self.assertEqual(len(staged_session.result_ids), 1)
            finally:
                staged_session.discard()

    def test_only_the_exact_builtin_plugin_uses_unbound_conversion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "derived.synthetic"
            source_path.write_bytes(b"record")

            def parse(request):
                structure = Structure(
                    id=uuid4(),
                    revision="structure-r1",
                    atomic_numbers=(1,),
                    coordinates=ArrayData(
                        numpy.asarray(((0.0, 0.0, 0.0),)),
                        ("atom", "xyz"),
                        "angstrom",
                    ),
                )
                record = MolecularRecord(
                    id=uuid4(),
                    revision="record-r1",
                    source_revision_id=request.source_revision_id,
                    record_key="record-0001",
                    structure_id=structure.id,
                    topology_id=None,
                    raw_block=b"record",
                    title="record",
                    source_record_index=0,
                    block_version="V2000",
                    writer_name=None,
                    writer_version=None,
                    ordered_raw_properties=(),
                    provenance_ids=(),
                )
                return ImportBatch(
                    structures=(structure,),
                    molecular_records=(record,),
                    report=ParserReport(
                        "derived-record",
                        "1",
                        (structure.id, record.id),
                        ("structure",),
                        (),
                    ),
                )

            descriptor = ReaderDescriptor(
                reader_id="derived-record",
                reader_version="1",
                extensions=(".synthetic",),
                capabilities={"structure": CapabilitySupport.SUPPORTED},
                priority=100,
                sniff=lambda path, prefix: SniffResult(SniffMatch.EXACT, "fixture"),
                parse=lambda path: ImportBatch(),
                parse_request=parse,
            )
            base = _builtin_plugin(descriptor, _builtin_manifest((descriptor,)))

            class DerivedBuiltin(_BuiltinReaderPlugin):
                pass

            plugin = DerivedBuiltin(
                base.core_descriptor,
                base.descriptor,
                base.manifest,
                base.priority,
            )
            request = ParseRequest(
                source_path=source_path,
                source_content_hash=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                validation_mode="balanced",
                canonical_parameters={},
                staging_root=root,
                progress=lambda event: None,
                is_cancelled=lambda: False,
                source_revision_id=uuid4(),
            )

            result = ReaderPluginRegistry((plugin,)).parse(
                descriptor.reader_id,
                request,
            )

            self.assertEqual(result.molecular_records, ())
            self.assertEqual(result.report.issues[0].path, "reader.parse")


if __name__ == "__main__":
    unittest.main()
