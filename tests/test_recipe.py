import json
import unittest
from dataclasses import replace
from uuid import uuid4

import numpy as np

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    PropertyDataset,
    QCProject,
    RecipeCitation,
    RecipeDefinition,
    RecipeInputSpec,
    RecipeOutputSpec,
    RecipeParameterSpec,
    RecipeValidationSpec,
    RecipeViewSpec,
    builtin_recipes,
    plan_recipe,
    recipe_document,
    recipe_from_document,
)


def dataset(*, role="excitation_energy", unit="electron_volt", status=DatasetStatus.COMPLETE):
    return PropertyDataset(
        id=uuid4(),
        revision="dataset-r1",
        semantic_role=role,
        domain="state",
        data=ArrayData(np.array([2.5, 3.0]), ("state",), unit),
        status=status,
        source_calculation=None,
        provenance_ids=(),
    )


def definition():
    return RecipeDefinition(
        recipe_id="test.spectrum",
        version="1",
        title="Test spectrum",
        supported_programs=("gaussian", "orca"),
        inputs=(
            RecipeInputSpec(
                name="states",
                entity_kind="dataset",
                semantic_roles=("excitation_energy",),
                domains=("state",),
                dims=(("state",),),
                units=("electron_volt",),
            ),
        ),
        parameters=(
            RecipeParameterSpec(
                name="sigma",
                value_type="number",
                required=False,
                default=0.1,
                minimum=0.0,
            ),
            RecipeParameterSpec(
                name="profile",
                value_type="string",
                required=False,
                default="gaussian",
                choices=("gaussian", "lorentzian"),
            ),
        ),
        outputs=(
            RecipeOutputSpec(
                name="spectrum",
                semantic_role="uv_vis_spectrum",
                domain="frequency",
                dims=("frequency",),
                unit="arbitrary_unit",
            ),
        ),
        views=(RecipeViewSpec(kind="spectrum_plot", sources=("spectrum",)),),
        validations=(
            RecipeValidationSpec(
                rule="finite_output", message="Spectrum must be finite."
            ),
        ),
        citations=(
            RecipeCitation(
                key="method", title="Method reference", doi="10.1000/example"
            ),
        ),
    )


class RecipeTests(unittest.TestCase):
    def test_definition_rejects_duplicate_names_and_invalid_defaults(self):
        recipe = definition()
        with self.assertRaisesRegex(ValueError, "duplicate input"):
            replace(recipe, inputs=(recipe.inputs[0], recipe.inputs[0]))
        with self.assertRaisesRegex(ValueError, "default"):
            replace(
                recipe,
                parameters=(
                    replace(recipe.parameters[0], default=-1.0),
                    recipe.parameters[1],
                ),
            )

    def test_strict_codec_round_trips_and_rejects_unknown_fields(self):
        recipe = definition()
        document = recipe_document(recipe)
        self.assertEqual(recipe_from_document(json.loads(json.dumps(document))), recipe)
        document["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            recipe_from_document(document)

    def test_plan_binds_complete_dataset_and_normalizes_defaults(self):
        value = dataset()
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(datasets=(value,)))
        plan = plan_recipe(definition(), project, {"states": value.id}, {})
        self.assertEqual(plan.bindings[0].entity_id, value.id)
        self.assertEqual(plan.parameters, (("profile", "gaussian"), ("sigma", 0.1)))
        self.assertEqual(len(plan.derivation_key), 64)

    def test_plan_rejects_unknown_names_type_and_incompatible_dataset(self):
        value = dataset()
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(datasets=(value,)))
        recipe = definition()
        with self.assertRaisesRegex(ValueError, "input names"):
            plan_recipe(recipe, project, {"wrong": value.id}, {})
        with self.assertRaisesRegex(ValueError, "parameter names"):
            plan_recipe(recipe, project, {"states": value.id}, {"extra": 1})
        with self.assertRaisesRegex(TypeError, "sigma"):
            plan_recipe(recipe, project, {"states": value.id}, {"sigma": True})

        wrong = dataset(unit="hartree")
        wrong_project = QCProject(uuid4(), "0.1")
        wrong_project.commit(ImportBatch(datasets=(wrong,)))
        with self.assertRaisesRegex(ValueError, "unit"):
            plan_recipe(recipe, wrong_project, {"states": wrong.id}, {})

    def test_plan_rejects_partial_dataset(self):
        value = dataset(status=DatasetStatus.PARTIAL)
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(datasets=(value,)))
        with self.assertRaisesRegex(ValueError, "complete"):
            plan_recipe(definition(), project, {"states": value.id}, {})

    def test_derivation_identity_changes_with_revision_or_parameters(self):
        value = dataset()
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(datasets=(value,)))
        first = plan_recipe(definition(), project, {"states": value.id}, {})
        changed_parameter = plan_recipe(
            definition(), project, {"states": value.id}, {"sigma": 0.2}
        )
        self.assertNotEqual(first.derivation_key, changed_parameter.derivation_key)

        revised = replace(value, revision="dataset-r2")
        revised_project = QCProject(uuid4(), "0.1", datasets={revised.id: revised})
        changed_revision = plan_recipe(
            definition(), revised_project, {"states": revised.id}, {}
        )
        self.assertNotEqual(first.derivation_key, changed_revision.derivation_key)

    def test_builtin_recipes_cover_initial_workflow_families(self):
        recipes = builtin_recipes()
        self.assertEqual(
            set(recipes),
            {
                "tddft_uvvis",
                "vibrational_ir_spectrum",
                "wavefunction_molecular_orbital_grid",
            },
        )
        for recipe in recipes.values():
            self.assertTrue(recipe.views)
            self.assertTrue(recipe.validations)
            self.assertTrue(recipe.citations)
        self.assertEqual(
            recipes["tddft_uvvis"].inputs[0].required_attributes,
            ("oscillator_strengths",),
        )


if __name__ == "__main__":
    unittest.main()
