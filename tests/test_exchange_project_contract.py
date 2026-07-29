import unittest
from dataclasses import replace
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    BiologicalAtomSiteData,
    BiologicalChain,
    BiologicalHierarchy,
    BiologicalModel,
    BiologicalResidue,
    CategoricalData,
    ChemicalAnnotation,
    ExternalReference,
    ImportBatch,
    ProvenanceRecord,
    QCProject,
    Structure,
)
from ChemBlender.core.model.project import validate_project_graph


def structure(atom_count=2):
    return Structure(
        id=uuid4(),
        revision="structure-r1",
        atomic_numbers=(6,) * atom_count,
        coordinates=ArrayData(
            numpy.zeros((atom_count, 3)),
            ("atom", "xyz"),
            "angstrom",
        ),
    )


def hierarchy(structure_id, atom_count=2, **updates):
    sites = BiologicalAtomSiteData(
        serial_numbers=ArrayData(
            numpy.arange(1, atom_count + 1, dtype=numpy.int64),
            ("atom",),
            "dimensionless",
        ),
        residue_indices=ArrayData(
            numpy.zeros(atom_count, dtype=numpy.int64),
            ("atom",),
            "dimensionless",
        ),
        alternate_locations=CategoricalData(
            ArrayData(
                numpy.full(atom_count, -1, dtype=numpy.int16),
                ("atom",),
                "dimensionless",
            ),
            (),
            -1,
        ),
        record_kinds=CategoricalData(
            ArrayData(
                numpy.zeros(atom_count, dtype=numpy.int16),
                ("atom",),
                "dimensionless",
            ),
            ("atom",),
            -1,
        ),
    )
    fields = {
        "id": uuid4(),
        "revision": "hierarchy-r1",
        "structure_id": structure_id,
        "model": BiologicalModel(1),
        "chains": (BiologicalChain("A", 0),),
        "residues": (BiologicalResidue(0, "GLY", 1, "", False),),
        "atom_sites": sites,
        "provenance_ids": (),
    }
    fields.update(updates)
    return BiologicalHierarchy(**fields)


def annotation(target_id, **updates):
    fields = {
        "id": uuid4(),
        "revision": "annotation-r1",
        "target_entity_id": target_id,
        "namespace": "tripos",
        "key": "molecule_type",
        "value": "small",
        "source": "mol2",
        "confidence": None,
        "provenance_ids": (),
    }
    fields.update(updates)
    return ChemicalAnnotation(**fields)


def external_reference(target_id, **updates):
    fields = {
        "id": uuid4(),
        "revision": "reference-r1",
        "target_entity_id": target_id,
        "namespace": "pdb",
        "identifier": "1CRN",
        "source": "pdb_header",
        "provenance_ids": (),
    }
    fields.update(updates)
    return ExternalReference(**fields)


class ExchangeProjectContractTests(unittest.TestCase):
    def test_commits_all_exchange_groups_and_revalidates_the_graph(self):
        item = structure()
        bio = hierarchy(item.id)
        note = annotation(item.id)
        reference = external_reference(item.id)
        project = QCProject(id=uuid4(), schema_version="1.0")

        project.commit(
            ImportBatch(
                structures=(item,),
                biological_hierarchies=(bio,),
                annotations=(note,),
                external_references=(reference,),
            )
        )

        self.assertIs(project.biological_hierarchies[bio.id], bio)
        self.assertIs(project.annotations[note.id], note)
        self.assertIs(project.external_references[reference.id], reference)
        validate_project_graph(project)

    def test_rejects_dangling_targets_provenance_and_atom_count_without_mutation(self):
        item = structure()
        project = QCProject(id=uuid4(), schema_version="1.0")
        project.commit(ImportBatch(structures=(item,)))
        missing = uuid4()
        invalid_batches = (
            ImportBatch(annotations=(annotation(missing),)),
            ImportBatch(external_references=(external_reference(missing),)),
            ImportBatch(
                annotations=(
                    annotation(item.id, provenance_ids=(missing,)),
                )
            ),
            ImportBatch(
                biological_hierarchies=(hierarchy(item.id, atom_count=1),)
            ),
        )

        for batch in invalid_batches:
            with self.subTest(batch=batch):
                with self.assertRaises(ValueError):
                    project.commit(batch)
                self.assertEqual(project.annotations, {})
                self.assertEqual(project.external_references, {})
                self.assertEqual(project.biological_hierarchies, {})

    def test_rejects_duplicate_semantic_identities_and_second_hierarchy(self):
        item = structure()
        first_annotation = annotation(item.id)
        first_reference = external_reference(item.id)
        first_hierarchy = hierarchy(item.id)
        project = QCProject(id=uuid4(), schema_version="1.0")
        project.commit(
            ImportBatch(
                structures=(item,),
                biological_hierarchies=(first_hierarchy,),
                annotations=(first_annotation,),
                external_references=(first_reference,),
            )
        )

        invalid_batches = (
            ImportBatch(
                annotations=(
                    annotation(
                        item.id,
                        namespace=first_annotation.namespace,
                        key=first_annotation.key,
                    ),
                )
            ),
            ImportBatch(
                external_references=(
                    external_reference(
                        item.id,
                        namespace=first_reference.namespace,
                        identifier=first_reference.identifier,
                    ),
                )
            ),
            ImportBatch(biological_hierarchies=(hierarchy(item.id),)),
        )
        for batch in invalid_batches:
            with self.subTest(batch=batch):
                with self.assertRaises(ValueError):
                    project.commit(batch)

    def test_exchange_metadata_cannot_target_metadata_or_provenance(self):
        item = structure()
        note = annotation(item.id)
        reference = external_reference(item.id)
        bio = hierarchy(item.id)
        provenance = ProvenanceRecord(
            id=uuid4(),
            revision="provenance-r1",
            producer="test",
            producer_version="1",
            source="",
            source_hash="",
            parent_ids=(),
            operation="parse",
            parameters=(),
        )
        project = QCProject(id=uuid4(), schema_version="1.0")
        project.commit(
            ImportBatch(
                structures=(item,),
                biological_hierarchies=(bio,),
                annotations=(note,),
                external_references=(reference,),
                provenance=(provenance,),
            )
        )

        for target in (note.id, reference.id, bio.id, provenance.id):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    project.commit(
                        ImportBatch(
                            annotations=(
                                replace(
                                    note,
                                    id=uuid4(),
                                    target_entity_id=target,
                                    key=f"invalid_{target.hex}",
                                ),
                            )
                        )
                    )


if __name__ == "__main__":
    unittest.main()
