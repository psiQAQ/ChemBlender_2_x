import ast
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core import (
    CapabilitySupport,
    ImportBatch,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
    close_session,
    close_project,
    create_session,
    open_project,
    save_project,
)
from ChemBlender.core.import_pipeline import (
    StagedImportSession,
    ValidationMode,
)
from ChemBlender.core.import_pipeline.parse import stage_import_batch
from ChemBlender.reader_api import (
    ReaderPluginRegistry,
    builtin_reader_plugin_registry,
)
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import _builtin_manifest, _builtin_plugin


READER_BRIDGE = "ChemBlender.legacy.reader_bridge"
SCAFFOLD_BRIDGE = "ChemBlender.legacy.scaffold_bridge"
SCAFFOLD_MODULE = "ChemBlender.scaffold"
OUTPUT_MODULE = "ChemBlender.output"
PANEL_MODULE = "ChemBlender.panel"
CRYS_MODULE = "ChemBlender.crys_utils"
QUICK_IMPORT_MODULE = "ChemBlender.ui.quick_import"


class _Response:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class LegacyReaderBridgeTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop(READER_BRIDGE, None)
        self.bridge = importlib.import_module(READER_BRIDGE)

    def tearDown(self):
        sys.modules.pop(READER_BRIDGE, None)

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


class LegacyOperatorRoutingTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        fake_props = ModuleType("bpy.props")
        fake_types = ModuleType("bpy.types")
        for name in (
            "BoolProperty",
            "CollectionProperty",
            "EnumProperty",
            "FloatProperty",
            "FloatVectorProperty",
            "IntProperty",
            "IntVectorProperty",
            "PointerProperty",
            "StringProperty",
        ):
            setattr(fake_props, name, lambda **_keywords: None)
        fake_bpy.props = fake_props
        fake_types.Operator = object
        fake_types.OperatorFileListElement = object
        fake_types.PropertyGroup = object
        fake_types.Panel = object
        fake_bpy.types = fake_types
        fake_bpy.context = SimpleNamespace(
            preferences=SimpleNamespace(view=SimpleNamespace(language="en_US")),
            scene=SimpleNamespace(cursor=SimpleNamespace(location=SimpleNamespace(x=0, y=0, z=0))),
        )
        fake_bpy.path = SimpleNamespace(abspath=lambda value: value)
        fake_bpy.ops = SimpleNamespace(
            chemblender=SimpleNamespace(),
            error=SimpleNamespace(custom_dialog=lambda *_args, **_kwargs: None),
        )
        fake_data = ModuleType("ChemBlender.Chem_data")
        fake_data.ELEMENTS_DEFAULT = {}
        fake_data.BONDS_DEFAULT = {"Default": (0, 0, 0, 1.0)}
        fake_data.SYMOP_OPERATIONS = {}
        fake_data.SPACE_GROUP_DATA = {}
        fake_data.metals = ()
        fake_data.preset_smiles = {
            "sugar": ("Sugar", "OC"),
            "amino": ("Amino acid", "NCC(=O)O"),
            "polymer": ("Polymer unit", "CC"),
        }
        self.modules = patch.dict(
            sys.modules,
            {
                "bpy": fake_bpy,
                "bpy.props": fake_props,
                "bpy.types": fake_types,
                "ChemBlender._math": ModuleType("ChemBlender._math"),
                "ChemBlender.Chem_data": fake_data,
                "ChemBlender.mesh": ModuleType("ChemBlender.mesh"),
                "ChemBlender.node": ModuleType("ChemBlender.node"),
            },
        )
        self.modules.start()
        self.fake_bpy = fake_bpy
        for name in (
            SCAFFOLD_MODULE,
            OUTPUT_MODULE,
            PANEL_MODULE,
            CRYS_MODULE,
            SCAFFOLD_BRIDGE,
            QUICK_IMPORT_MODULE,
        ):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in (
            SCAFFOLD_MODULE,
            OUTPUT_MODULE,
            PANEL_MODULE,
            CRYS_MODULE,
            SCAFFOLD_BRIDGE,
            QUICK_IMPORT_MODULE,
        ):
            sys.modules.pop(name, None)
        self.modules.stop()

    def _operation(self, calls, name):
        def invoke(*args, **kwargs):
            calls.append((name, args, kwargs))
            return {"FINISHED"}

        return invoke

    def _scaffold_context(self, filetext, *, choose="File"):
        calls = []
        self.fake_bpy.ops.chemblender = SimpleNamespace(
            quick_import=self._operation(calls, "quick_import"),
            import_smiles_text=self._operation(calls, "import_smiles_text"),
            export_project_entity=self._operation(calls, "export_project_entity"),
            apply_scientific_edits=self._operation(calls, "apply_scientific_edits"),
        )
        scaffold = importlib.import_module(SCAFFOLD_MODULE)
        operator = scaffold.MESH_OT_SCAFFOLD_BUILD()
        operator.filter = ""
        operator.report = lambda *_args: None
        context = SimpleNamespace(
            scene=SimpleNamespace(
                my_tool=SimpleNamespace(
                    choose=choose,
                    filetext=str(filetext),
                    pubchemtext="2244",
                    smilestext="",
                    Saccharides="sugar",
                    Amino_Acids="amino",
                    Polymer_Units="polymer",
                ),
                chemblender_quick_import=SimpleNamespace(validation_mode="strict"),
            ),
            window_manager=object(),
        )
        return scaffold, operator, context, calls

    def test_legacy_file_operator_uses_quick_import_for_cif_poscar_and_contcar(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("legacy.cif", "POSCAR", "CONTCAR"):
                source = Path(directory) / name
                source.write_text("data_example\n", encoding="utf-8")
                scaffold, operator, context, calls = self._scaffold_context(source)
                result = operator.execute(context)

                self.assertEqual(result, {"FINISHED"})
                self.assertEqual(calls[0][0], "quick_import")
                self.assertEqual(calls[0][2]["files"], [{"name": name}])

    def test_legacy_pubchem_operator_does_not_forward_trust_claims_to_quick_import(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pubchem-2244.sdf"
            source.write_bytes(b"PubChem SDF\n$$$$\n")
            scaffold, operator, context, calls = self._scaffold_context(
                source,
                choose="PubChem",
            )
            stage = SimpleNamespace(
                request=SimpleNamespace(
                    sources=(SimpleNamespace(path=source),),
                    validation_mode=ValidationMode.STRICT,
                ),
                source_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/SDF",
                content_hash="a" * 64,
                diagnostics=(),
            )
            with (
                patch.object(scaffold, "get_scene_session", return_value=object()),
                patch.object(scaffold, "stage_pubchem_import", return_value=stage),
            ):
                result = operator.execute(context)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(calls[0][0], "quick_import")
        self.assertNotIn("legacy_source_url", calls[0][2])
        self.assertNotIn("legacy_source_hash", calls[0][2])

    def test_modal_preflight_job_uses_the_same_pubchem_attachment(self):
        quick_import = importlib.import_module(QUICK_IMPORT_MODULE)
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_session = create_session(temp_parent=root)
            stage = importlib.import_module(READER_BRIDGE).stage_pubchem_import(
                "2244",
                project_session,
                fetch=lambda _url, timeout: _Response(payload),
            )
            sync_staged = StagedImportSession.create(temp_parent=root)
            modal_staged = StagedImportSession.create(temp_parent=root)
            try:
                attachment = quick_import._legacy_pubchem_batch_attachment(
                    project_session,
                )
                sync_preview = preflight_reader_plugins(
                    stage.request,
                    builtin_reader_plugin_registry(),
                    sync_staged,
                    _batch_attachment=attachment,
                )
                job = quick_import._PreflightJob(
                    stage.request,
                    builtin_reader_plugin_registry(),
                    modal_staged,
                    batch_attachment=attachment,
                    prepare_conformers=False,
                )
                job._run()
                self.assertIsNone(job.error)
                sync_batch = sync_staged.result(sync_preview.staged_batch_ids[0])
                modal_batch = modal_staged.result(
                    job.preview.staged_batch_ids[0]
                )
                sync_provenance, = tuple(
                    item
                    for item in sync_batch.provenance
                    if item.operation == "pubchem_import"
                )
                modal_provenance, = tuple(
                    item
                    for item in modal_batch.provenance
                    if item.operation == "pubchem_import"
                )
            finally:
                sync_staged.discard()
                modal_staged.discard()
                close_session(project_session)

        self.assertEqual(sync_provenance.id, modal_provenance.id)

    def test_scaffold_bridge_routes_export_and_scientific_changes_to_unified_operators(self):
        bridge = importlib.import_module(SCAFFOLD_BRIDGE)
        calls = []

        bridge.route_legacy_export(lambda operator_id: calls.append(operator_id))
        bridge.route_legacy_scientific_edit(lambda operator_id: calls.append(operator_id))

        self.assertEqual(
            calls,
            [
                "chemblender.export_project_entity",
                "chemblender.apply_scientific_edits",
            ],
        )

    def test_legacy_output_wrappers_forward_without_legacy_export_properties(self):
        output = importlib.import_module(OUTPUT_MODULE)
        calls = []
        self.fake_bpy.ops.chemblender = SimpleNamespace(
            export_project_entity=self._operation(calls, "export_project_entity"),
            apply_scientific_edits=self._operation(calls, "apply_scientific_edits"),
        )

        export_result = output.SaveMolButton().execute(SimpleNamespace())
        edit_result = output.UpdateCIFFromMesh().execute(SimpleNamespace())

        self.assertEqual(export_result, {"FINISHED"})
        self.assertEqual(edit_result, {"FINISHED"})
        self.assertEqual(
            [call[0] for call in calls],
            ["export_project_entity", "apply_scientific_edits"],
        )
        self.assertFalse(
            {"export_format", "mol_version", "vasp_coord_mode", "filepath"}
            & set(output.SaveMolButton.__annotations__)
        )

    def test_crystal_panel_hides_legacy_scaffold_actions_for_unified_views(self):
        fake_ex_package = ModuleType("ChemBlender.ex_package")
        fake_ex_package.safe_check_rdkit = lambda: True
        with patch.dict(sys.modules, {"ChemBlender.ex_package": fake_ex_package}):
            panel = importlib.import_module(PANEL_MODULE)

        calls = []

        class Layout:
            def label(self, **kwargs):
                calls.append(("label", kwargs))

            def operator(self, operator_id, **kwargs):
                calls.append(("operator", operator_id, kwargs))
                return SimpleNamespace()

        class UnifiedObject:
            def get(self, key, default=None):
                if key == "cb_structure_contract":
                    return "structure_view_v1"
                return default

        view = panel.CRYSTAL_PT_TOOLS()
        view.layout = Layout()
        view.draw(
            SimpleNamespace(
                active_object=UnifiedObject(),
                scene=SimpleNamespace(my_tool=SimpleNamespace()),
            )
        )

        self.assertEqual(
            [call[1] for call in calls if call[0] == "operator"],
            ["chemblender.apply_scientific_edits"],
        )

    def test_all_legacy_crystal_direct_write_operators_cancel_for_unified_view(self):
        fake_bmesh = ModuleType("bmesh")
        fake_mathutils = ModuleType("mathutils")
        with patch.dict(
            sys.modules,
            {"bmesh": fake_bmesh, "mathutils": fake_mathutils},
        ):
            crystal = importlib.import_module(CRYS_MODULE)

        reports = []

        class UnifiedObject:
            name = "unit_demo"

            def get(self, key, default=None):
                if key == "cb_structure_contract":
                    return "structure_view_v1"
                return default

        context = SimpleNamespace(
            object=UnifiedObject(),
            active_object=UnifiedObject(),
        )
        for class_name in (
            "SupercellButton",
            "AddCellButton",
            "AddCrysScaffoldButton",
            "AddCoordPolyhedraButton",
            "AddDummyButton",
            "SymmetryDuplicate",
        ):
            with self.subTest(operator=class_name):
                reports.clear()
                operator = getattr(crystal, class_name)()
                operator.report = (
                    lambda level, message: reports.append((level, message))
                )

                result = operator.execute(context)

                self.assertEqual(result, {"CANCELLED"})
                self.assertIn("Apply Scientific Edits", reports[0][1])


class LegacyCallerInventoryTests(unittest.TestCase):
    def test_direct_crystal_writers_and_visible_panel_callers_have_an_ast_contract(self):
        root = Path(__file__).resolve().parents[1]
        crystal_tree = ast.parse((root / "ChemBlender" / "crys_utils.py").read_text(encoding="utf-8"))
        panel_tree = ast.parse((root / "ChemBlender" / "panel.py").read_text(encoding="utf-8"))

        def class_by_name(tree, name):
            return next(
                node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == name
            )

        def called_names(node):
            return {
                ast.unparse(call.func)
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            }

        direct_writers = {
            "SupercellButton": {"mesh.copy_mesh_object", "node.Supercell"},
            "AddCellButton": {"mesh.unit_cell_edges"},
            "AddCrysScaffoldButton": {"mesh.create_object", "node.crys_expand"},
            "AddCoordPolyhedraButton": {"node.CoordPolyhedra"},
            "AddDummyButton": {"bpy.data.meshes.new", "bpy.data.objects.new"},
            "SymmetryDuplicate": {"bpy.data.meshes.new", "bpy.data.objects.new"},
        }
        for class_name, expected_calls in direct_writers.items():
            self.assertTrue(expected_calls <= called_names(class_by_name(crystal_tree, class_name)))

        panel = class_by_name(panel_tree, "CRYSTAL_PT_TOOLS")
        visible_callers = {
            call.args[0].value
            for call in ast.walk(panel)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "operator"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        }
        self.assertEqual(
            visible_callers,
            {
                "chem.add_unit_cell",
                "chem.add_crys_scaffold",
                "chem.sel_symmetry",
                "chem.duplicate_symmetry",
                "chem.supercell",
                "chem.add_coordpolyhedra",
                "chem.avgfract",
                "chem.add_dummy",
                "chem.update_cif_from_mesh",
                "chem.view_set",
            },
        )

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
                "xyz_block": {
                    (
                        "ChemBlender/ui/scientific_edit.py",
                        "_write_xyz",
                        "xyz_block",
                    ),
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
