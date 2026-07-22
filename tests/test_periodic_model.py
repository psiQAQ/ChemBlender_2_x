import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    CIFEnvelope,
    ImportBatch,
    PeriodicSiteData,
    ProvenanceRecord,
    QCProject,
    Structure,
    SymmetryResult,
)


def periodic_site_data(envelope_id, atom_count=2):
    return PeriodicSiteData(
        fractional_coordinates=ArrayData(
            numpy.zeros((atom_count, 3)),
            ("atom", "xyz"),
            "dimensionless",
        ),
        site_labels=tuple(f"site_{index}" for index in range(atom_count)),
        occupancies=ArrayData(
            numpy.ones(atom_count), ("atom",), "dimensionless"
        ),
        isotropic_displacements=None,
        anisotropic_displacements=None,
        adp_types=("none",) * atom_count,
        disorder_groups=(0,) * atom_count,
        declared_space_group_name="P 1",
        declared_space_group_number=1,
        symmetry_operations=("x,y,z",),
        cif_envelope_id=envelope_id,
    )


def structure(envelope_id):
    return Structure(
        id=uuid4(),
        revision="structure-revision",
        atomic_numbers=(6, 8),
        coordinates=ArrayData(
            numpy.zeros((2, 3)), ("atom", "xyz"), "angstrom"
        ),
        cell=ArrayData(
            numpy.eye(3), ("cell_vector", "xyz"), "angstrom"
        ),
        periodic=periodic_site_data(envelope_id),
    )


def symmetry_result(input_id, standard_id, provenance_id):
    return SymmetryResult(
        id=uuid4(),
        revision="symmetry-revision",
        structure_id=input_id,
        standardized_structure_id=standard_id,
        hall_number=1,
        international_number=1,
        international_symbol="P1",
        hall_symbol="P 1",
        choice="",
        pointgroup="1",
        rotations=ArrayData(
            numpy.eye(3, dtype=int).reshape((1, 3, 3)),
            ("operation", "output_axis", "input_axis"),
            "dimensionless",
        ),
        translations=ArrayData(
            numpy.zeros((1, 3)),
            ("operation", "axis"),
            "dimensionless",
        ),
        wyckoffs=("a", "a"),
        site_symmetry_symbols=("1", "1"),
        equivalent_atoms=ArrayData(
            numpy.asarray([0, 1]), ("atom",), "dimensionless"
        ),
        crystallographic_orbits=ArrayData(
            numpy.asarray([0, 1]), ("atom",), "dimensionless"
        ),
        transformation_matrix=ArrayData(
            numpy.eye(3),
            ("standard_axis", "input_axis"),
            "dimensionless",
        ),
        origin_shift=ArrayData(
            numpy.zeros(3), ("axis",), "dimensionless"
        ),
        mapping_to_primitive=ArrayData(
            numpy.asarray([0, 1]), ("atom",), "dimensionless"
        ),
        std_mapping_to_primitive=ArrayData(
            numpy.asarray([0, 1]), ("standard_atom",), "dimensionless"
        ),
        std_rotation_matrix=ArrayData(
            numpy.eye(3),
            ("cartesian_output_axis", "cartesian_input_axis"),
            "dimensionless",
        ),
        symprec=1.0e-5,
        angle_tolerance=-1.0,
        provenance_ids=(provenance_id,),
    )


class PeriodicModelTests(unittest.TestCase):
    def test_project_commits_periodic_entities_atomically(self):
        provenance_id = uuid4()
        envelope = CIFEnvelope(
            id=uuid4(),
            revision="envelope-revision",
            block_name="test",
            source_bytes=b"data_test\n_custom 1\n",
            tag_names=("_custom",),
            provenance_ids=(provenance_id,),
        )
        original = structure(envelope.id)
        standard = structure(envelope.id)
        provenance = ProvenanceRecord(
            id=provenance_id,
            revision="provenance-revision",
            producer="test",
            producer_version="1",
            source="fixture",
            source_hash="",
            parent_ids=(),
            operation="parse",
            parameters=(),
        )
        symmetry = symmetry_result(original.id, standard.id, provenance_id)
        batch = ImportBatch(
            structures=(original, standard),
            cif_envelopes=(envelope,),
            symmetry_results=(symmetry,),
            provenance=(provenance,),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(batch)
        self.assertIs(project.cif_envelopes[envelope.id], envelope)
        self.assertIs(project.symmetry_results[symmetry.id], symmetry)

    def test_periodic_structure_requires_cell_and_matching_atoms(self):
        envelope_id = uuid4()
        with self.assertRaisesRegex(ValueError, "periodic structure requires a cell"):
            Structure(
                id=uuid4(),
                revision="revision",
                atomic_numbers=(6, 8),
                coordinates=ArrayData(
                    numpy.zeros((2, 3)), ("atom", "xyz"), "angstrom"
                ),
                periodic=periodic_site_data(envelope_id),
            )
        with self.assertRaisesRegex(ValueError, "periodic atom dimension"):
            Structure(
                id=uuid4(),
                revision="revision",
                atomic_numbers=(6, 8),
                coordinates=ArrayData(
                    numpy.zeros((2, 3)), ("atom", "xyz"), "angstrom"
                ),
                cell=ArrayData(
                    numpy.eye(3), ("cell_vector", "xyz"), "angstrom"
                ),
                periodic=periodic_site_data(envelope_id, atom_count=1),
            )

    def test_project_rejects_dangling_periodic_references(self):
        periodic_structure = structure(uuid4())
        project = QCProject(id=uuid4(), schema_version="0.1")
        with self.assertRaisesRegex(ValueError, "CIF envelope"):
            project.commit(ImportBatch(structures=(periodic_structure,)))

        envelope = CIFEnvelope(
            id=uuid4(),
            revision="revision",
            block_name="test",
            source_bytes=b"data_test\n",
            tag_names=(),
            provenance_ids=(),
        )
        original = structure(envelope.id)
        symmetry = symmetry_result(original.id, uuid4(), uuid4())
        with self.assertRaisesRegex(ValueError, "standardized structure"):
            project.commit(
                ImportBatch(
                    structures=(original,),
                    cif_envelopes=(envelope,),
                    symmetry_results=(symmetry,),
                )
            )

    def test_non_cif_periodic_structure_does_not_require_an_envelope(self):
        original = structure(uuid4())
        periodic_structure = Structure(
            id=original.id,
            revision=original.revision,
            atomic_numbers=original.atomic_numbers,
            coordinates=original.coordinates,
            cell=original.cell,
            periodic=PeriodicSiteData(
                fractional_coordinates=original.periodic.fractional_coordinates,
                site_labels=original.periodic.site_labels,
                occupancies=original.periodic.occupancies,
                isotropic_displacements=None,
                anisotropic_displacements=None,
                adp_types=original.periodic.adp_types,
                disorder_groups=original.periodic.disorder_groups,
                declared_space_group_name=None,
                declared_space_group_number=None,
                symmetry_operations=(),
                cif_envelope_id=None,
            ),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(periodic_structure,)))
        self.assertIs(project.structures[periodic_structure.id], periodic_structure)


if __name__ == "__main__":
    unittest.main()
