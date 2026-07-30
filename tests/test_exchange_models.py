import unittest
from dataclasses import FrozenInstanceError
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
)


def categorical(values, categories):
    return CategoricalData(
        codes=ArrayData(
            numpy.asarray(values, dtype=numpy.int16),
            ("atom",),
            "dimensionless",
        ),
        categories=categories,
        missing_code=-1,
    )


def atom_sites(*, residue_indices=(0, 0)):
    return BiologicalAtomSiteData(
        serial_numbers=ArrayData(
            numpy.asarray((1, 2), dtype=numpy.int64),
            ("atom",),
            "dimensionless",
        ),
        residue_indices=ArrayData(
            numpy.asarray(residue_indices, dtype=numpy.int64),
            ("atom",),
            "dimensionless",
        ),
        alternate_locations=categorical((-1, 0), ("A",)),
        record_kinds=categorical((0, 1), ("atom", "hetatm")),
    )


class ChemicalAnnotationTests(unittest.TestCase):
    def fields(self, **updates):
        fields = {
            "id": uuid4(),
            "revision": "annotation-r1",
            "target_entity_id": uuid4(),
            "namespace": "tripos",
            "key": "molecule_type",
            "value": "small",
            "source": "mol2",
            "confidence": 1.0,
            "provenance_ids": (uuid4(),),
        }
        fields.update(updates)
        return fields

    def test_accepts_only_immutable_scalar_values(self):
        for value in ("C.3", 3, 0.125, True):
            with self.subTest(value=value):
                annotation = ChemicalAnnotation(**self.fields(value=value))
                self.assertIs(annotation.value, value)

        for value in (None, b"C.3", (), [], {}, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    ChemicalAnnotation(**self.fields(value=value))

    def test_validates_tokens_confidence_and_is_frozen(self):
        for updates in (
            {"namespace": "Tripos"},
            {"key": "atom type"},
            {"confidence": -0.1},
            {"confidence": 1.1},
            {"confidence": True},
        ):
            with self.subTest(updates=updates):
                with self.assertRaises((TypeError, ValueError)):
                    ChemicalAnnotation(**self.fields(**updates))

        annotation = ChemicalAnnotation(**self.fields(confidence=None))
        with self.assertRaises(FrozenInstanceError):
            annotation.value = "changed"

    def test_wrong_field_types_raise_type_error(self):
        for updates in (
            {"revision": 1},
            {"namespace": 1},
            {"key": 1},
            {"source": 1},
            {"confidence": 1},
        ):
            with self.subTest(updates=updates):
                with self.assertRaises(TypeError):
                    ChemicalAnnotation(**self.fields(**updates))


class ExternalReferenceTests(unittest.TestCase):
    def test_requires_stable_namespace_identifier_and_source(self):
        reference = ExternalReference(
            id=uuid4(),
            revision="reference-r1",
            target_entity_id=uuid4(),
            namespace="pdb",
            identifier="1CRN",
            source="pdb_header",
            provenance_ids=(),
        )
        self.assertEqual(reference.identifier, "1CRN")

        for field, value in (
            ("namespace", "PDB"),
            ("identifier", ""),
            ("source", ""),
        ):
            fields = {
                "id": uuid4(),
                "revision": "reference-r1",
                "target_entity_id": uuid4(),
                "namespace": "pdb",
                "identifier": "1CRN",
                "source": "pdb_header",
                "provenance_ids": (),
            }
            fields[field] = value
            with self.subTest(field=field):
                with self.assertRaises((TypeError, ValueError)):
                    ExternalReference(**fields)

    def test_wrong_field_types_raise_type_error(self):
        fields = {
            "id": uuid4(),
            "revision": "reference-r1",
            "target_entity_id": uuid4(),
            "namespace": "pdb",
            "identifier": "1CRN",
            "source": "pdb_header",
            "provenance_ids": (),
        }
        for field in ("revision", "namespace", "identifier", "source"):
            invalid = dict(fields, **{field: 1})
            with self.subTest(field=field):
                with self.assertRaises(TypeError):
                    ExternalReference(**invalid)


class BiologicalHierarchyTests(unittest.TestCase):
    def hierarchy(self, **updates):
        fields = {
            "id": uuid4(),
            "revision": "hierarchy-r1",
            "structure_id": uuid4(),
            "model": BiologicalModel(number=1),
            "chains": (BiologicalChain(chain_id="A", segment_index=0),),
            "residues": (
                BiologicalResidue(
                    chain_index=0,
                    residue_name="GLY",
                    sequence_number=1,
                    insertion_code="",
                    hetero=False,
                ),
            ),
            "atom_sites": atom_sites(),
            "provenance_ids": (),
        }
        fields.update(updates)
        return BiologicalHierarchy(**fields)

    def test_preserves_compact_model_chain_residue_atom_site_hierarchy(self):
        hierarchy = self.hierarchy()
        self.assertEqual(hierarchy.model.number, 1)
        self.assertEqual(hierarchy.chains[0].chain_id, "A")
        self.assertEqual(hierarchy.residues[0].residue_name, "GLY")
        self.assertEqual(hierarchy.atom_count, 2)

    def test_atom_site_columns_are_atom_aligned_integer_or_categorical_data(self):
        invalid = (
            {
                "serial_numbers": ArrayData(
                    numpy.asarray((1.0, 2.0)),
                    ("atom",),
                    "dimensionless",
                )
            },
            {
                "residue_indices": ArrayData(
                    numpy.asarray((0,), dtype=numpy.int64),
                    ("atom",),
                    "dimensionless",
                )
            },
            {
                "alternate_locations": CategoricalData(
                    codes=ArrayData(
                        numpy.asarray((-1, 0), dtype=numpy.int16),
                        ("site",),
                        "dimensionless",
                    ),
                    categories=("A",),
                    missing_code=-1,
                )
            },
        )
        valid = atom_sites()
        for update in invalid:
            fields = {
                "serial_numbers": valid.serial_numbers,
                "residue_indices": valid.residue_indices,
                "alternate_locations": valid.alternate_locations,
                "record_kinds": valid.record_kinds,
            }
            fields.update(update)
            with self.subTest(update=next(iter(update))):
                with self.assertRaises((TypeError, ValueError)):
                    BiologicalAtomSiteData(**fields)

    def test_record_kind_is_required_for_every_atom_site(self):
        valid = atom_sites()
        missing_record_kind = CategoricalData(
            codes=ArrayData(
                numpy.asarray((-1, 0), dtype=numpy.int16),
                ("atom",),
                "dimensionless",
            ),
            categories=("atom",),
            missing_code=-1,
        )
        with self.assertRaisesRegex(ValueError, "record kind"):
            BiologicalAtomSiteData(
                serial_numbers=valid.serial_numbers,
                residue_indices=valid.residue_indices,
                alternate_locations=valid.alternate_locations,
                record_kinds=missing_record_kind,
            )

    def test_rejects_invalid_indexes_and_duplicate_hierarchy_keys(self):
        with self.assertRaisesRegex(ValueError, "residue index"):
            self.hierarchy(atom_sites=atom_sites(residue_indices=(0, 1)))

        with self.assertRaisesRegex(ValueError, "chain"):
            self.hierarchy(
                chains=(
                    BiologicalChain("A", 0),
                    BiologicalChain("A", 0),
                )
            )

        residue = BiologicalResidue(0, "GLY", 1, "", False)
        with self.assertRaisesRegex(ValueError, "residue"):
            self.hierarchy(residues=(residue, residue))

        with self.assertRaises((TypeError, ValueError)):
            BiologicalModel(number=0)
        with self.assertRaises((TypeError, ValueError)):
            BiologicalChain(chain_id=1, segment_index=0)

    def test_wrong_hierarchy_value_types_raise_type_error(self):
        invalid_calls = (
            lambda: BiologicalModel(number="1"),
            lambda: BiologicalChain(chain_id=1, segment_index=0),
            lambda: BiologicalChain(chain_id="A", segment_index="0"),
            lambda: BiologicalResidue("0", "GLY", 1, "", False),
            lambda: BiologicalResidue(0, 1, 1, "", False),
            lambda: BiologicalResidue(0, "GLY", True, "", False),
            lambda: BiologicalResidue(0, "GLY", 1, 0, False),
            lambda: BiologicalResidue(0, "GLY", 1, "", 0),
        )
        for invalid_call in invalid_calls:
            with self.subTest(invalid_call=invalid_call):
                with self.assertRaises(TypeError):
                    invalid_call()


if __name__ == "__main__":
    unittest.main()
