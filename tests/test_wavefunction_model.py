import array
import unittest
from uuid import uuid4

from ChemBlender.core import (
    ArrayData,
    BasisConvention,
    BasisFunctionKind,
    BasisSet,
    BasisShell,
    ImportBatch,
    OrbitalChannel,
    OrbitalKind,
    OrbitalSet,
    QCProject,
    Structure,
)


def array_view(values, shape):
    raw = memoryview(array.array("d", values))
    return raw.cast("B").cast("d", shape=shape)


def structure(atom_count=1):
    return Structure(
        id=uuid4(),
        revision="s1",
        atomic_numbers=(1,) * atom_count,
        coordinates=ArrayData(
            array_view(range(atom_count * 3), (atom_count, 3)),
            ("atom", "xyz"),
            "bohr",
        ),
    )


def shell(center_atom=0, angular_momenta=(0,), kinds=(BasisFunctionKind.CARTESIAN,)):
    return BasisShell(
        center_atom=center_atom,
        angular_momenta=angular_momenta,
        kinds=kinds,
        exponents=ArrayData(
            array_view([1.0, 0.5], (2,)),
            ("primitive",),
            "inverse_square_bohr",
        ),
        coefficients=ArrayData(
            array_view([0.7, 0.3] * len(angular_momenta), (2, len(angular_momenta))),
            ("primitive", "contraction"),
            "dimensionless",
        ),
    )


def basis_set(structure_id, *, shells=None):
    return BasisSet(
        id=uuid4(),
        revision="b1",
        structure_id=structure_id,
        name="sto-3g",
        shells=tuple(shells or (shell(),)),
        conventions=(
            BasisConvention(
                angular_momentum=0,
                kind=BasisFunctionKind.CARTESIAN,
                functions=("1",),
            ),
        ),
        primitive_normalization="l2",
        provenance_ids=(),
    )


def channel(label="restricted", orbital_count=2, basis_width=1):
    return OrbitalChannel(
        label=label,
        coefficients=ArrayData(
            array_view(range(orbital_count * basis_width), (orbital_count, basis_width)),
            ("orbital", "basis_function")
            if label != "generalized"
            else ("orbital", "spin_basis_function"),
            "dimensionless",
        ),
        energies=ArrayData(
            array_view(range(orbital_count), (orbital_count,)),
            ("orbital",),
            "hartree",
        ),
        occupations=ArrayData(
            array_view([1.0] * orbital_count, (orbital_count,)),
            ("orbital",),
            "dimensionless",
        ),
        irreps=("a1",) * orbital_count,
    )


class WavefunctionModelTests(unittest.TestCase):
    def test_basis_shell_and_convention_preserve_generalized_contraction(self):
        sp = shell(
            angular_momenta=(0, 1),
            kinds=(BasisFunctionKind.CARTESIAN, BasisFunctionKind.CARTESIAN),
        )
        self.assertEqual(sp.basis_function_count, 4)
        self.assertEqual(sp.coefficients.shape, (2, 2))

        pure_d = BasisConvention(
            angular_momentum=2,
            kind=BasisFunctionKind.PURE,
            functions=("c0", "c1", "s1", "c2", "-s2"),
        )
        self.assertEqual(pure_d.function_count, 5)
        self.assertEqual(pure_d.functions[-1], "-s2")

    def test_restricted_wavefunction_commits_to_project(self):
        struct = structure()
        basis = basis_set(struct.id)
        orbitals = OrbitalSet(
            id=uuid4(),
            revision="o1",
            structure_id=struct.id,
            basis_set_id=basis.id,
            kind=OrbitalKind.RESTRICTED,
            channels=(channel(),),
            provenance_ids=(),
        )
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(
                structures=(struct,),
                basis_sets=(basis,),
                orbital_sets=(orbitals,),
            )
        )
        self.assertEqual(basis.basis_function_count, 1)
        self.assertIs(project.basis_sets[basis.id], basis)
        self.assertIs(project.orbital_sets[orbitals.id], orbitals)

    def test_unrestricted_and_generalized_channel_layouts_are_explicit(self):
        struct = structure()
        basis = basis_set(struct.id)
        unrestricted = OrbitalSet(
            id=uuid4(),
            revision="u1",
            structure_id=struct.id,
            basis_set_id=basis.id,
            kind=OrbitalKind.UNRESTRICTED,
            channels=(channel("alpha", 2), channel("beta", 1)),
            provenance_ids=(),
        )
        generalized = OrbitalSet(
            id=uuid4(),
            revision="g1",
            structure_id=struct.id,
            basis_set_id=basis.id,
            kind=OrbitalKind.GENERALIZED,
            channels=(channel("generalized", 2, 2),),
            provenance_ids=(),
        )
        self.assertEqual(tuple(item.label for item in unrestricted.channels), ("alpha", "beta"))
        self.assertEqual(
            generalized.channels[0].coefficients.dims,
            ("orbital", "spin_basis_function"),
        )

    def test_invalid_channel_layouts_and_shapes_are_rejected(self):
        common = {
            "id": uuid4(),
            "revision": "bad",
            "structure_id": uuid4(),
            "basis_set_id": uuid4(),
            "provenance_ids": (),
        }
        cases = (
            (OrbitalKind.RESTRICTED, (channel("alpha"),)),
            (OrbitalKind.UNRESTRICTED, (channel("alpha"),)),
            (OrbitalKind.GENERALIZED, (channel("restricted"),)),
        )
        for kind, channels in cases:
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    OrbitalSet(kind=kind, channels=channels, **common)

        with self.assertRaises(ValueError):
            OrbitalChannel(
                label="restricted",
                coefficients=channel().coefficients,
                energies=ArrayData(
                    array_view([0.0], (1,)), ("orbital",), "hartree"
                ),
                occupations=None,
                irreps=(),
            )

    def test_project_rejects_invalid_basis_references_and_width_atomically(self):
        struct = structure()
        invalid_center_basis = basis_set(struct.id, shells=(shell(center_atom=1),))
        dangling_basis = basis_set(uuid4())
        valid_basis = basis_set(struct.id)
        wide_orbitals = OrbitalSet(
            id=uuid4(),
            revision="wide",
            structure_id=struct.id,
            basis_set_id=valid_basis.id,
            kind=OrbitalKind.RESTRICTED,
            channels=(channel(basis_width=2),),
            provenance_ids=(),
        )
        batches = (
            ImportBatch(structures=(struct,), basis_sets=(invalid_center_basis,)),
            ImportBatch(basis_sets=(dangling_basis,)),
            ImportBatch(
                structures=(struct,),
                basis_sets=(valid_basis,),
                orbital_sets=(wide_orbitals,),
            ),
        )
        for batch in batches:
            with self.subTest(batch=batch):
                project = QCProject(id=uuid4(), schema_version="0.1")
                with self.assertRaises(ValueError):
                    project.commit(batch)
                self.assertEqual(project.structures, {})
                self.assertEqual(project.basis_sets, {})
                self.assertEqual(project.orbital_sets, {})


if __name__ == "__main__":
    unittest.main()
