import array
import unittest
from uuid import uuid4

from ChemBlender.core import (
    ArrayData,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    DensityMatrix,
    DensityMatrixLevel,
    DensityMatrixSpin,
    ImportBatch,
    QCProject,
    Structure,
)


def values(items, shape):
    raw = memoryview(array.array("d", items))
    return raw.cast("B").cast("d", shape=shape)


def entities(width=1):
    structure = Structure(
        id=uuid4(),
        revision="s1",
        atomic_numbers=(1,),
        coordinates=ArrayData(values([0.0, 0.0, 0.0], (1, 3)), ("atom", "xyz"), "bohr"),
    )
    angular_momentum = 0 if width == 1 else 1
    functions = ("1",) if width == 1 else ("x", "y", "z")
    basis = BasisSet(
        id=uuid4(),
        revision="b1",
        structure_id=structure.id,
        name="minimal",
        shells=(
            BasisShell(
                center_atom=0,
                angular_momenta=(angular_momentum,),
                kinds=(BasisFunctionKind.CARTESIAN,),
                exponents=ArrayData(
                    values([1.0], (1,)),
                    ("primitive",),
                    "inverse_square_bohr",
                ),
                coefficients=ArrayData(
                    values([1.0], (1, 1)),
                    ("primitive", "contraction"),
                    "dimensionless",
                ),
            ),
        ),
        conventions=(
            BasisConvention(
                angular_momentum,
                BasisFunctionKind.CARTESIAN,
                functions,
            ),
        ),
        primitive_normalization="l2",
        provenance_ids=(),
    )
    return structure, basis


def density_matrix(structure_id, basis_id, width=1, **overrides):
    fields = {
        "id": uuid4(),
        "revision": "d1",
        "structure_id": structure_id,
        "basis_set_id": basis_id,
        "level": DensityMatrixLevel.SCF,
        "spin_role": DensityMatrixSpin.TOTAL,
        "data": ArrayData(
            values([1.0] * (width * width), (width, width)),
            ("basis_function_row", "basis_function_column"),
            "dimensionless",
        ),
        "source_calculation": None,
        "provenance_ids": (),
    }
    fields.update(overrides)
    return DensityMatrix(**fields)


class DensityMatrixModelTests(unittest.TestCase):
    def test_total_and_spin_matrices_have_explicit_semantics(self):
        structure, basis = entities()
        total = density_matrix(structure.id, basis.id)
        spin = density_matrix(
            structure.id,
            basis.id,
            level=DensityMatrixLevel.POST_SCF,
            spin_role=DensityMatrixSpin.SPIN,
        )
        self.assertIs(total.level, DensityMatrixLevel.SCF)
        self.assertIs(total.spin_role, DensityMatrixSpin.TOTAL)
        self.assertIs(spin.level, DensityMatrixLevel.POST_SCF)
        self.assertIs(spin.spin_role, DensityMatrixSpin.SPIN)

    def test_matrix_shape_dims_unit_and_values_are_validated(self):
        structure, basis = entities()
        invalid_arrays = (
            ArrayData(values([1.0, 2.0], (2,)), ("basis_function",), "dimensionless"),
            ArrayData(
                values([1.0, 2.0], (1, 2)),
                ("basis_function_row", "basis_function_column"),
                "dimensionless",
            ),
            ArrayData(
                values([1.0], (1, 1)),
                ("basis_function_row", "basis_function_column"),
                "unknown",
            ),
        )
        for data in invalid_arrays:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    density_matrix(structure.id, basis.id, data=data)

    def test_project_commits_matrix_and_checks_basis_width(self):
        structure, basis = entities(width=3)
        matrix = density_matrix(structure.id, basis.id, width=3)
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(
                structures=(structure,),
                basis_sets=(basis,),
                density_matrices=(matrix,),
            )
        )
        self.assertIs(project.density_matrices[matrix.id], matrix)

    def test_dangling_and_wrong_width_matrices_fail_atomically(self):
        structure, basis = entities()
        wrong_width = density_matrix(structure.id, basis.id, width=2)
        dangling_structure = density_matrix(uuid4(), basis.id)
        dangling_basis = density_matrix(structure.id, uuid4())
        for matrix in (wrong_width, dangling_structure, dangling_basis):
            with self.subTest(matrix=matrix):
                project = QCProject(id=uuid4(), schema_version="0.1")
                with self.assertRaises(ValueError):
                    project.commit(
                        ImportBatch(
                            structures=(structure,),
                            basis_sets=(basis,),
                            density_matrices=(matrix,),
                        )
                    )
                self.assertEqual(project.structures, {})
                self.assertEqual(project.basis_sets, {})
                self.assertEqual(project.density_matrices, {})


if __name__ == "__main__":
    unittest.main()
