import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy

import ChemBlender.reader_api as reader_api
from ChemBlender.core import ImportBatch, QCProject
from ChemBlender.core.sidecar import close_project, open_project, save_project
from tests.test_exchange_project_contract import (
    annotation,
    external_reference,
    hierarchy,
    structure,
)


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SIDECAR = ROOT / "tests" / "fixtures" / "sidecar" / "model-v10"


def exchange_batch():
    item = structure()
    return ImportBatch(
        structures=(item,),
        biological_hierarchies=(hierarchy(item.id),),
        annotations=(annotation(item.id),),
        external_references=(external_reference(item.id),),
    )


class ExchangePersistenceTests(unittest.TestCase):
    def test_sidecar_schema_one_round_trip_preserves_exchange_groups(self):
        project = QCProject(id=uuid4(), schema_version="1.0")
        batch = exchange_batch()
        project.commit(batch)

        with TemporaryDirectory() as temporary:
            root = save_project(Path(temporary) / "exchange.cbq", project)
            restored = open_project(root)
            try:
                restored_hierarchy = restored.biological_hierarchies[
                    batch.biological_hierarchies[0].id
                ]
                self.assertEqual(
                    restored_hierarchy.structure_id,
                    batch.biological_hierarchies[0].structure_id,
                )
                self.assertEqual(
                    numpy.asarray(
                        restored_hierarchy.atom_sites.serial_numbers.values
                    ).tolist(),
                    [1, 2],
                )
                self.assertEqual(
                    tuple(restored.annotations.values()),
                    batch.annotations,
                )
                self.assertEqual(
                    tuple(restored.external_references.values()),
                    batch.external_references,
                )
            finally:
                close_project(restored)

    def test_existing_schema_one_sidecar_defaults_new_registries_to_empty(self):
        restored = open_project(LEGACY_SIDECAR)
        try:
            self.assertEqual(restored.biological_hierarchies, {})
            self.assertEqual(restored.annotations, {})
            self.assertEqual(restored.external_references, {})
        finally:
            close_project(restored)

    def test_public_and_canonical_round_trip_preserve_exchange_groups(self):
        batch = exchange_batch()
        public = reader_api.public_batch_from_internal(batch)
        self.assertEqual(public.biological_hierarchies, batch.biological_hierarchies)
        self.assertEqual(public.annotations, batch.annotations)
        self.assertEqual(public.external_references, batch.external_references)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = reader_api.public_batch_document(public, root)
            restored_public = reader_api.public_batch_from_document(document, root)
        restored = reader_api.internal_batch_from_public(restored_public)
        self.assertEqual(
            restored.biological_hierarchies[0].id,
            batch.biological_hierarchies[0].id,
        )
        numpy.testing.assert_array_equal(
            restored.biological_hierarchies[
                0
            ].atom_sites.residue_indices.values,
            batch.biological_hierarchies[0].atom_sites.residue_indices.values,
        )
        self.assertEqual(restored.annotations, batch.annotations)
        self.assertEqual(restored.external_references, batch.external_references)

    def test_empty_new_groups_are_omitted_and_defaulted_for_legacy_documents(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = reader_api.public_batch_document(
                reader_api.PublicImportBatch(),
                root,
            )
            for name in (
                b"biological_hierarchies",
                b"annotations",
                b"external_references",
            ):
                self.assertNotIn(name, document)
            restored = reader_api.public_batch_from_document(document, root)
        self.assertEqual(restored.biological_hierarchies, ())
        self.assertEqual(restored.annotations, ())
        self.assertEqual(restored.external_references, ())

    def test_public_types_are_exact_core_types_and_cold_imports_remain_optional(self):
        import ChemBlender.core as core

        for name in (
            "BiologicalAtomSiteData",
            "BiologicalChain",
            "BiologicalHierarchy",
            "BiologicalModel",
            "BiologicalResidue",
            "ChemicalAnnotation",
            "ExternalReference",
        ):
            self.assertIs(getattr(reader_api, name), getattr(core, name))

        code = (
            "import sys; import ChemBlender.core; import ChemBlender.reader_api; "
            "forbidden={'openbabel','Bio','rdkit','gemmi','spglib'}; "
            "raise SystemExit(bool(forbidden & set(sys.modules)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
