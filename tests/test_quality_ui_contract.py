import json
import unittest
from dataclasses import FrozenInstanceError
from uuid import UUID

from ChemBlender.core import QualityStatus
from ChemBlender.core.import_pipeline.report import (
    render_diagnostics_markdown,
)
from ChemBlender.project_link import (
    MANIFEST_HASH_KEY,
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    ProjectLinkStatus,
)
from ChemBlender.ui.diagnostics import (
    RevisionViewPrompt,
    canonical_report_text,
    detach_project_links_for_scenes,
    diagnostic_detail_rows,
    project_recovery_actions,
    quality_presentation,
    revision_action_items,
)


_ZERO_COUNTS = {
    "complete": 0,
    "partial": 0,
    "ambiguous": 0,
    "incomplete": 0,
    "invalid": 0,
}


def _report_document():
    return {
        "schema_name": "chemblender_import_report",
        "schema_version": 1,
        "session_id": "00000000-0000-0000-0000-000000000001",
        "staged_batch_ids": [],
        "summary": {
            "overall": dict(_ZERO_COUNTS),
            "by_source": [],
            "by_entity": [],
        },
        "diagnostics": [],
    }


class QualityUIContractTests(unittest.TestCase):
    def test_all_quality_states_have_text_and_distinct_icons(self):
        expected = {
            QualityStatus.COMPLETE: ("Complete", "CHECKMARK", False),
            QualityStatus.PARTIAL: ("Partial", "INFO", False),
            QualityStatus.AMBIGUOUS: ("Ambiguous", "QUESTION", False),
            QualityStatus.INCOMPLETE: ("Incomplete", "ERROR", True),
            QualityStatus.INVALID: ("Invalid", "CANCEL", True),
        }

        actual = {
            status: (
                quality_presentation(status).label,
                quality_presentation(status).icon,
                quality_presentation(status).alert,
            )
            for status in QualityStatus
        }

        self.assertEqual(actual, expected)
        self.assertEqual(
            len({presentation[1] for presentation in actual.values()}),
            len(QualityStatus),
        )

    def test_quality_presentation_accepts_canonical_text_only(self):
        self.assertEqual(
            quality_presentation("partial"),
            quality_presentation(QualityStatus.PARTIAL),
        )
        with self.assertRaises(ValueError):
            quality_presentation("warning")

    def test_diagnostic_detail_projects_every_scientific_field(self):
        item = {
            "id": "00000000-0000-0000-0000-000000000010",
            "severity": "warning",
            "quality_status": "ambiguous",
            "source_revision_id": "00000000-0000-0000-0000-000000000011",
            "source_id": "00000000-0000-0000-0000-000000000012",
            "record_key": "record-7",
            "entity_id": "00000000-0000-0000-0000-000000000013",
            "field_path": "atoms[1].charge",
            "code": "charge.assumed",
            "message": "Charge unit was assumed.",
            "original_value": 1,
            "normalized_value": 1.0,
            "recovery_action": "Confirm the source unit.",
            "scientific_consequence": "Charge coloring may be misleading.",
            "suggested_action": "Inspect the source record.",
        }

        rows = dict(diagnostic_detail_rows(item))

        self.assertEqual(
            tuple(rows),
            (
                "Severity",
                "Source",
                "Source revision",
                "Record",
                "Entity",
                "Field",
                "Code",
                "Message",
                "Original",
                "Normalized",
                "Recovery",
                "Scientific consequence",
                "Suggested action",
            ),
        )
        self.assertEqual(rows["Severity"], "warning")
        self.assertEqual(rows["Original"], "1")
        self.assertEqual(rows["Normalized"], "1.0")

    def test_copy_export_text_uses_the_canonical_report_contract(self):
        document = _report_document()

        self.assertEqual(
            canonical_report_text(document, "markdown"),
            render_diagnostics_markdown(document),
        )
        self.assertEqual(
            canonical_report_text(document, "json"),
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )

    def test_invalid_report_is_rejected_for_every_export_format(self):
        invalid = _report_document()
        invalid["schema_name"] = "not_the_canonical_schema"

        for format_name in ("markdown", "json"):
            with self.subTest(format_name=format_name):
                with self.assertRaisesRegex(
                    ValueError,
                    "invalid diagnostics document",
                ):
                    canonical_report_text(invalid, format_name)

    def test_revision_actions_are_explicit_and_keep_current_is_default(self):
        self.assertEqual(
            revision_action_items(),
            (
                (
                    "update_selected_views",
                    "Update Selected Views",
                    "Create replacement views for the selected current views",
                ),
                (
                    "comparison_view",
                    "Comparison View",
                    "Create a new-revision view beside the current view",
                ),
                (
                    "keep_current",
                    "Keep Current",
                    "Keep every current view unchanged",
                ),
            ),
        )
        prompt = RevisionViewPrompt(
            current_revision_id=UUID(
                "00000000-0000-0000-0000-000000000020"
            ),
            new_revision_id=UUID(
                "00000000-0000-0000-0000-000000000021"
            ),
        )
        self.assertEqual(prompt.action, "keep_current")
        self.assertNotEqual(
            str(prompt.current_revision_id),
            str(prompt.new_revision_id),
        )
        with self.assertRaises(FrozenInstanceError):
            prompt.action = "comparison_view"

    def test_revision_prompt_rejects_implicit_or_unknown_decisions(self):
        revision_id = UUID("00000000-0000-0000-0000-000000000022")
        with self.assertRaisesRegex(ValueError, "must differ"):
            RevisionViewPrompt(
                current_revision_id=revision_id,
                new_revision_id=revision_id,
            )
        with self.assertRaisesRegex(ValueError, "unknown revision view action"):
            RevisionViewPrompt(
                current_revision_id=revision_id,
                new_revision_id=UUID(
                    "00000000-0000-0000-0000-000000000023"
                ),
                action="automatic_switch",
            )

    def test_recovery_actions_are_status_specific_and_safe(self):
        self.assertEqual(
            project_recovery_actions(ProjectLinkStatus.MISSING),
            ("relink", "verify", "open_read_only", "detach"),
        )
        self.assertEqual(
            project_recovery_actions(ProjectLinkStatus.MISMATCH),
            ("relink", "verify", "open_read_only", "detach"),
        )
        for status in (
            ProjectLinkStatus.INCOMPATIBLE,
            ProjectLinkStatus.INVALID,
        ):
            with self.subTest(status=status):
                self.assertEqual(
                    project_recovery_actions(status),
                    ("relink", "verify", "open_diagnostics", "detach"),
                )
        self.assertEqual(
            project_recovery_actions(ProjectLinkStatus.CONNECTED),
            (),
        )

    def test_detach_removes_only_link_metadata_and_keeps_scene_objects(self):
        objects = object()
        scene = {
            PROJECT_ID_KEY: "project",
            PROJECT_SCHEMA_KEY: "1.0",
            SIDECAR_LOCATOR_KEY: "example.cbq",
            MANIFEST_HASH_KEY: "a" * 64,
            "objects": objects,
            "unrelated": "kept",
        }

        detached = detach_project_links_for_scenes((scene,))

        self.assertEqual(detached, 1)
        self.assertTrue(
            all(
                key not in scene
                for key in (
                    PROJECT_ID_KEY,
                    PROJECT_SCHEMA_KEY,
                    SIDECAR_LOCATOR_KEY,
                    MANIFEST_HASH_KEY,
                )
            )
        )
        self.assertIs(scene["objects"], objects)
        self.assertEqual(scene["unrelated"], "kept")

    def test_detach_rolls_back_every_scene_when_one_write_fails(self):
        class FailingScene(dict):
            failed = False

            def __delitem__(self, key):
                if key == PROJECT_SCHEMA_KEY and not self.failed:
                    self.failed = True
                    raise OSError("scene is read-only")
                super().__delitem__(key)

        values = {
            PROJECT_ID_KEY: "project",
            PROJECT_SCHEMA_KEY: "1.0",
            SIDECAR_LOCATOR_KEY: "example.cbq",
            MANIFEST_HASH_KEY: "a" * 64,
        }
        first = dict(values)
        second = FailingScene(values)
        before = (dict(first), dict(second))

        with self.assertRaisesRegex(OSError, "scene is read-only"):
            detach_project_links_for_scenes((first, second))

        self.assertEqual((dict(first), dict(second)), before)


if __name__ == "__main__":
    unittest.main()
