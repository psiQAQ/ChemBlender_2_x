import ast
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from chemblender_prepare.core.readers import CapabilitySupport
from cbq_core.model import ImportBatch
from chemblender_prepare.core.readers import ReaderDescriptor
from chemblender_prepare.core.readers import SniffMatch
from chemblender_prepare.core.readers import SniffResult
from cbq_core.session import close_session
from cbq_core.sidecar import close_project
from cbq_core.session import create_session
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from chemblender_prepare.core.import_pipeline import StagedImportSession
from chemblender_prepare.core.import_pipeline import ValidationMode
from chemblender_prepare.core.import_pipeline.parse import stage_import_batch
from chemblender_prepare.reader_api import ReaderPluginRegistry
from chemblender_prepare.reader_api import builtin_reader_plugin_registry
from chemblender_prepare.reader_api.import_pipeline_bridge import preflight_reader_plugins
from chemblender_prepare.reader_api.registry import _builtin_manifest
from chemblender_prepare.reader_api.registry import _builtin_plugin


READER_BRIDGE = "chemblender_prepare.pubchem_import"


class _Response:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class LegacyReaderBridgeTests(unittest.TestCase):
    def setUp(self):
        # The external module has no Blender state; keep package and sys.modules identities aligned.
        self.bridge = importlib.import_module(READER_BRIDGE)

    def test_external_default_fetch_closes_response_and_bounds_reads(self):
        response = MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.return_value = b'{"IdentifierList":{"CID":[2244]}}'
        with patch.object(self.bridge, "urlopen", return_value=response) as opened:
            result = self.bridge._fetch("https://pubchem.ncbi.nlm.nih.gov/", timeout=30)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"IdentifierList": {"CID": [2244]}})
        opened.assert_called_once_with("https://pubchem.ncbi.nlm.nih.gov/", timeout=30)
        response.read.assert_called_once_with(64 * 1024 * 1024 + 1)
        response.__exit__.assert_called_once()
        oversized = MagicMock()
        oversized.__len__.return_value = 64 * 1024 * 1024 + 1
        response.reset_mock()
        response.read.return_value = oversized
        with patch.object(self.bridge, "urlopen", return_value=response), self.assertRaisesRegex(
            OSError, "exceeds 64 MiB"
        ):
            self.bridge._fetch("https://pubchem.ncbi.nlm.nih.gov/", timeout=30)
        response.__exit__.assert_called_once()

    def test_pubchem_cancellation_never_returns_staged_input(self):
        from concurrent.futures import CancelledError
        for cancel_at in (1, 2, 3, 4, 5):
            with self.subTest(cancel_at=cancel_at), tempfile.TemporaryDirectory() as directory:
                session = create_session(temp_parent=Path(directory))
                checks = 0
                def cancelled():
                    nonlocal checks
                    checks += 1
                    return checks >= cancel_at
                fetch = MagicMock(return_value=_Response(b"SDF"))
                try:
                    with self.assertRaises(CancelledError):
                        self.bridge.stage_pubchem_import(
                            "2244", session, fetch=fetch, is_cancelled=cancelled)
                    root = Path(session.temporary_root) / self.bridge._PUBCHEM_ROOT
                    self.assertEqual(list(root.glob("*")), [])
                    if cancel_at == 1:
                        fetch.assert_not_called()
                finally:
                    close_session(session)

    def test_pubchem_partial_metadata_failure_removes_both_owned_files(self):
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            def fail_dump(document, stream, **kwargs):
                stream.write("{")
                raise OSError("disk full")
            try:
                with patch.object(self.bridge.json, "dump", side_effect=fail_dump):
                    with self.assertRaisesRegex(OSError, "disk full"):
                        self.bridge.stage_pubchem_import(
                            "2244", session, fetch=lambda *a, **k: _Response(b"SDF"))
                root = Path(session.temporary_root) / self.bridge._PUBCHEM_ROOT
                self.assertEqual(list(root.glob("*")), [])
            finally:
                close_session(session)

    def test_pubchem_failed_staging_preserves_collisions_and_original_error(self):
        from uuid import UUID
        for failure in ("collision", "source_write", "cleanup"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                session = create_session(temp_parent=Path(directory))
                token = UUID(int=1)
                root = self.bridge._owned_pubchem_root(session, create=True)
                metadata = root / f"pubchem-2244-{token.hex}.json"
                original_open = Path.open
                def open_path(path, mode="r", *args, **kwargs):
                    stream = original_open(path, mode, *args, **kwargs)
                    if failure == "source_write" and mode == "xb":
                        wrapper = MagicMock()
                        wrapper.__enter__.return_value = wrapper
                        wrapper.__exit__.side_effect = lambda *a: stream.close()
                        def fail_write(payload):
                            stream.write(payload[:1])
                            raise OSError("source write failed")
                        wrapper.write.side_effect = fail_write
                        return wrapper
                    return stream
                def fail_dump(*args, **kwargs):
                    raise OSError("metadata failed")
                try:
                    if failure == "collision":
                        metadata.write_bytes(b"existing")
                    from contextlib import ExitStack
                    with ExitStack() as stack:
                        stack.enter_context(patch.object(self.bridge, "uuid4", return_value=token))
                        stack.enter_context(patch.object(Path, "open", open_path))
                        if failure == "cleanup":
                            stack.enter_context(patch.object(self.bridge.json, "dump", side_effect=fail_dump))
                            stack.enter_context(patch.object(Path, "unlink", side_effect=OSError("locked")))
                        with self.assertRaises(OSError) as raised:
                            self.bridge.stage_pubchem_import(
                                "2244", session, fetch=lambda *a, **k: _Response(b"SDF"))
                    if failure == "collision":
                        self.assertEqual(metadata.read_bytes(), b"existing")
                        self.assertEqual(list(root.glob("*.sdf")), [])
                    elif failure == "source_write":
                        self.assertIn("source write failed", str(raised.exception))
                        self.assertEqual(list(root.iterdir()), [])
                    else:
                        self.assertEqual(str(raised.exception), "metadata failed")
                        self.assertEqual(len(raised.exception.__notes__), 2)
                finally:
                    close_session(session)

    def test_file_and_smiles_build_unified_import_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.cif"
            source.write_text("data_example\n", encoding="utf-8")

            file_request = self.bridge.file_import_request(
                source,
                ValidationMode.STRICT,
            )

        smiles_request = self.bridge.smiles_import_request(
            "C/C=C/C",
            ValidationMode.BALANCED,
        )

        self.assertEqual(file_request.validation_mode, ValidationMode.STRICT)
        self.assertEqual(file_request.sources[0].path, source.resolve())
        self.assertEqual(smiles_request.validation_mode, ValidationMode.BALANCED)
        self.assertEqual(smiles_request.sources[0].text, "C/C=C/C")

    def test_pubchem_stages_owned_sdf_with_url_hash_and_request(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda url, timeout: _Response(payload),
            )

            self.assertEqual(stage.diagnostics, ())
            self.assertEqual(stage.source_url,
                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/SDF",
            )
            self.assertEqual(stage.content_hash, hashlib.sha256(payload).hexdigest())
            self.assertEqual(stage.owner_id, session.id)
            self.assertEqual(stage.request.sources[0].path.read_bytes(), payload)
            self.assertTrue(stage.request.sources[0].path.is_relative_to(session.temporary_root))
            self.assertTrue(stage.metadata_path.is_file())

    def test_pubchem_network_failure_becomes_an_import_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: (_ for _ in ()).throw(OSError("offline")),
            )

        self.assertIsNone(stage.request)
        self.assertEqual(stage.diagnostics[0].code, "legacy.pubchem_network")
        self.assertIn("offline", stage.diagnostics[0].message)

    def test_pubchem_name_lookup_escapes_a_path_separator(self):
        calls = []

        def fetch(url, timeout):
            calls.append((url, timeout))
            if url.endswith("/cids/JSON"):
                return SimpleNamespace(
                    status_code=200,
                    json=lambda: {"IdentifierList": {"CID": [2244]}},
                )
            return _Response(b"PubChem SDF\n$$$$\n")

        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "ethyl/alcohol",
                session,
                fetch=fetch,
            )

        self.assertIsNotNone(stage.request)
        self.assertEqual(
            calls[0][0],
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            "name/ethyl%2Falcohol/cids/JSON",
        )

    def test_pubchem_source_is_reverified_before_canonical_parameters(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: _Response(payload),
            )

            parameters = self.bridge.verified_pubchem_parameters(
                stage.request.sources[0].path,
                session,
            )

        self.assertEqual(
            parameters,
            {
                "legacy_source_url": stage.source_url,
                "legacy_source_sha256": stage.content_hash,
            },
        )

    def test_pubchem_source_or_metadata_tampering_fails_closed(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: _Response(payload),
            )
            source = stage.request.sources[0].path
            source.write_bytes(b"tampered\n")

            with self.assertRaisesRegex(ValueError, "legacy.pubchem_untrusted"):
                self.bridge.verified_pubchem_parameters(source, session)

            source.write_bytes(payload)
            metadata = json.loads(stage.metadata_path.read_text(encoding="utf-8"))
            metadata["owner_session_id"] = "00000000-0000-0000-0000-000000000000"
            stage.metadata_path.write_text(
                json.dumps(metadata),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "legacy.pubchem_untrusted"):
                self.bridge.verified_pubchem_parameters(source, session)

    def test_pubchem_provenance_is_verified_at_the_host_boundary_and_reopens(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = create_session(temp_parent=root)
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: _Response(payload),
            )
            source, = stage.request.sources
            batch = stage_import_batch(
                source=source,
                validation_mode=stage.request.validation_mode,
                content_hash=hashlib.sha256(source.path.read_bytes()).hexdigest(),
                byte_size=source.path.stat().st_size,
                plugin_id="test.reader",
                reader_id="test",
                reader_version="1",
                api_version="1",
            )
            attached = self.bridge.attach_verified_pubchem_provenance(
                source,
                stage.content_hash,
                batch,
                session,
            )
            session.project.commit(attached)
            provenance, = session.project.provenance.values()
            revision, = session.project.source_revisions.values()
            sidecar = root / "pubchem.cbq"
            save_project(sidecar, session.project)
            reopened = open_project(sidecar)
            try:
                persisted = reopened.provenance[provenance.id]
                self.assertEqual(persisted.id, provenance.id)
                self.assertEqual(persisted.source, stage.source_url)
                self.assertEqual(persisted.source_hash, stage.content_hash)
                self.assertEqual(persisted.operation, "pubchem_import")
                self.assertEqual(persisted.parameters, provenance.parameters)
            finally:
                close_project(reopened)

        self.assertEqual(provenance.source, stage.source_url)
        self.assertEqual(provenance.source_hash, stage.content_hash)
        self.assertEqual(provenance.operation, "pubchem_import")
        self.assertIn(provenance.id, revision.created_entity_ids)

    def test_pubchem_host_attachment_reverifies_sync_and_modal_previews(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_session = create_session(temp_parent=root)
            stage = self.bridge.stage_pubchem_import(
                "2244",
                project_session,
                fetch=lambda _url, timeout: _Response(payload),
            )

            def attach(source, content_hash, batch):
                return self.bridge.attach_verified_pubchem_provenance(
                    source,
                    content_hash,
                    batch,
                    project_session,
                )

            previews = []
            batches = []
            for _mode in ("sync", "modal"):
                staged = StagedImportSession.create(temp_parent=root)
                try:
                    preview = preflight_reader_plugins(
                        stage.request,
                        builtin_reader_plugin_registry(),
                        staged,
                        _batch_attachment=attach,
                    )
                    batch = staged.result(preview.staged_batch_ids[0])
                    provenance, = tuple(
                        item
                        for item in batch.provenance
                        if item.operation == "pubchem_import"
                    )
                    previews.append(preview)
                    batches.append((batch, provenance))
                finally:
                    staged.discard()

        self.assertEqual(previews[0].source_previews[0].source_id, previews[1].source_previews[0].source_id)
        self.assertEqual(batches[0][1].id, batches[1][1].id)
        for batch, provenance in batches:
            self.assertEqual(provenance.source, stage.source_url)
            self.assertEqual(provenance.source_hash, stage.content_hash)
            self.assertIn(provenance.id, batch.source_revisions[0].created_entity_ids)

    def test_pubchem_host_attachment_reverifies_deferred_materialization(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_session = create_session(temp_parent=root)
            stage = self.bridge.stage_pubchem_import(
                "2244",
                project_session,
                fetch=lambda _url, timeout: _Response(payload),
            )

            def preview_request(request):
                (request.staging_root / "preview.marker").write_bytes(
                    b"preview"
                )
                return ImportBatch()

            descriptor = ReaderDescriptor(
                reader_id="deferred_sdf",
                reader_version="1",
                extensions=(".sdf",),
                capabilities={"structure": CapabilitySupport.SUPPORTED},
                priority=100,
                sniff=lambda _path, _prefix: SniffResult(
                    SniffMatch.EXACT,
                    "fixture",
                ),
                parse=lambda _path: ImportBatch(),
                preview_request=preview_request,
                materialize_request=lambda _request: ImportBatch(),
            )
            registry = ReaderPluginRegistry((
                _builtin_plugin(descriptor, _builtin_manifest((descriptor,))),
            ))
            calls = []

            def attach(source, content_hash, batch):
                calls.append((source.id, content_hash))
                return self.bridge.attach_verified_pubchem_provenance(
                    source,
                    content_hash,
                    batch,
                    project_session,
                )

            staged = StagedImportSession.create(temp_parent=root)
            try:
                preview = preflight_reader_plugins(
                    stage.request,
                    registry,
                    staged,
                    _batch_attachment=attach,
                )
                result_id, = preview.staged_batch_ids
                preview_batch = staged.result(result_id)
                preview_provenance, = tuple(
                    item
                    for item in preview_batch.provenance
                    if item.operation == "pubchem_import"
                )

                self.assertTrue(staged.has_pending_materializer(result_id))
                materialized = staged.materialize_result(result_id)
                materialized_provenance, = tuple(
                    item
                    for item in materialized.provenance
                    if item.operation == "pubchem_import"
                )
            finally:
                staged.discard()

        self.assertEqual(calls, [(stage.request.sources[0].id, stage.content_hash)] * 2)
        self.assertEqual(materialized_provenance.id, preview_provenance.id)
        self.assertIn(
            materialized_provenance.id,
            materialized.source_revisions[0].created_entity_ids,
        )






class LegacyCallerInventoryTests(unittest.TestCase):
    def test_viewer_registration_and_panels_exclude_legacy_direct_crystal_writers(self):
        root = Path(__file__).resolve().parents[1]
        from ChemBlender.runtime.registration import REGISTER_MODULE_NAMES
        self.assertIn(".ui.cbq_import", REGISTER_MODULE_NAMES)
        self.assertIn(".ui.mesh_edit", REGISTER_MODULE_NAMES)
        self.assertFalse({".crys_utils", ".panel", ".read", ".output", ".ui.quick_import",
                          ".ui.scientific_edit"} & set(REGISTER_MODULE_NAMES))
        old_classes = {"SupercellButton", "AddCellButton", "AddCrysScaffoldButton",
                       "AddCoordPolyhedraButton", "AddDummyButton", "SymmetryDuplicate"}
        old_actions = {"chem.add_unit_cell", "chem.add_crys_scaffold", "chem.duplicate_symmetry",
                       "chem.supercell", "chem.add_coordpolyhedra", "chem.add_dummy",
                       "chem.update_cif_from_mesh"}
        for path in sorted((root / "ChemBlender").rglob("*.py")):
            if "scripts" in path.relative_to(root / "ChemBlender").parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(path=path.relative_to(root)):
                self.assertFalse(old_classes & {node.name for node in ast.walk(tree)
                                                if isinstance(node, ast.ClassDef)})
                for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
                    if (isinstance(call.func, ast.Attribute) and call.func.attr == "operator"
                            and call.args and isinstance(call.args[0], ast.Constant)):
                        self.assertNotIn(call.args[0].value, old_actions)


    def test_legacy_reader_and_block_helper_callers_have_an_exact_ast_contract(self):
        root = Path(__file__).resolve().parents[1]
        targets = {
            "read_MOL",
            "read_Cryst",
            "read_cif",
            "read_poscar",
            "mol_block_v2000",
            "mol_block_v3000",
            "sdf_block",
            "cif_block",
            "vasp_block",
            "xyz_block",
        }
        callers = {name: set() for name in targets}

        class Calls(ast.NodeVisitor):
            def __init__(self, relative_path):
                self.relative_path = relative_path
                self.scope = []

            def visit_ClassDef(self, node):
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            def visit_FunctionDef(self, node):
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)

            def visit_Call(self, node):
                target = ast.unparse(node.func).rsplit(".", 1)[-1]
                if target in callers:
                    callers[target].add(
                        (
                            self.relative_path,
                            ".".join(self.scope) or "<module>",
                            ast.unparse(node.func),
                        )
                    )
                self.generic_visit(node)

        source_root = root / "ChemBlender"
        for path in sorted(source_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            Calls(path.relative_to(root).as_posix()).visit(tree)

        self.assertEqual(
            callers,
            {
                "read_MOL": set(),
                "read_Cryst": set(),
                "read_cif": set(),
                "read_poscar": set(),
                "mol_block_v2000": set(),
                "mol_block_v3000": set(),
                "sdf_block": set(),
                "cif_block": set(),
                "vasp_block": set(),
                "xyz_block": set(),
            },
        )


if __name__ == "__main__":
    unittest.main()
