import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from cbq_core.model import ImportBatch
from cbq_core.model import OrbitalKind
from cbq_core.model import QCProject
from cbq_core.session import close_session
from cbq_core.session import create_session
from ChemBlender.ui import wavefunction
from tests.test_wavefunction_grid import entities

class PreparedOrbitalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.structure, self.basis, self.orbitals = entities()
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(
            structures=(self.structure,),
            basis_sets=(self.basis,),
            orbital_sets=(self.orbitals,),
        ))
        self.session = create_session(
            temp_parent=self.temporary.name,
            project=project,
        )

    def tearDown(self):
        try:
            close_session(self.session)
        finally:
            self.temporary.cleanup()

    def test_source_selection_survives_derived_grid_and_resets_source_bound_choices(self):
        structure, basis, orbitals = entities(OrbitalKind.UNRESTRICTED)
        self.session.project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,),
                                               orbital_sets=(orbitals,)))
        settings = SimpleNamespace(orbital_source=str(self.orbitals.id),
            orbital_source_uuid=str(self.orbitals.id), channel="restricted", orbital_number=7)
        self.session.active_entity_id = orbitals.id
        self.assertIs(wavefunction._selected_orbitals(self.session, settings), orbitals)
        wavefunction.select_wavefunction_source(settings, orbitals)
        self.assertEqual(settings.orbital_source_uuid, str(orbitals.id))
        self.assertEqual(settings.channel, "alpha")
        self.assertEqual(settings.orbital_number, 1)
        self.session.active_entity_id = uuid4()  # Publication selects the new Grid, not the OrbitalSet.
        self.assertIs(wavefunction._selected_orbitals(self.session, settings), orbitals)
        settings.channel, settings.orbital_number = "beta", 2
        wavefunction.select_wavefunction_source(settings, orbitals)
        self.assertEqual((settings.channel, settings.orbital_number), ("beta", 2))
        # Selecting a prepared grid retains the chosen spin and orbital.
        settings.orbital_source_uuid = str(self.orbitals.id)
        wavefunction.select_wavefunction_source(settings, orbitals, reset=False)
        self.assertEqual(settings.orbital_source_uuid, str(orbitals.id))
        self.assertEqual((settings.channel, settings.orbital_number), ("beta", 2))

    def test_dynamic_entity_selection_uses_uuid_instead_of_old_list_position(self):
        first = (("NONE", "Select", ""), ("charge-a", "A", ""), ("charge-b", "B", ""))
        reordered = (("NONE", "Select", ""), ("charge-b", "B", ""), ("charge-a", "A", ""))
        replaced = (("NONE", "Select", ""), ("new-session-charge", "New", ""))
        self.assertEqual(wavefunction._enum_number(first, "charge-a"), 1)
        self.assertEqual(wavefunction._enum_number(reordered, "charge-a"), 2)
        self.assertEqual(wavefunction._enum_number(replaced, "charge-a"), 0)

    def test_stale_explicit_source_does_not_select_an_unrelated_set(self):
        settings = SimpleNamespace(orbital_source_uuid=str(uuid4()), channel="restricted")
        self.session.active_entity_id = uuid4()
        self.assertIsNone(wavefunction._selected_orbitals(self.session, settings))
        settings.orbital_source_uuid = "invalid-uuid"
        self.assertIsNone(wavefunction._selected_orbitals(self.session, settings))
        settings.orbital_source_uuid = ""
        self.assertIs(wavefunction._selected_orbitals(self.session, settings), self.orbitals)


if __name__ == "__main__":
    unittest.main()
