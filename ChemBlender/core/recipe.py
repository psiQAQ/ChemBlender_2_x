"""Versioned, declarative quantum-analysis recipe contract."""

import json
import math
import re
from dataclasses import dataclass
from uuid import UUID

from .cache_identity import derivation_cache_key
from .model import DatasetStatus, PropertyDataset, QCProject


_TOKEN = re.compile(r"[a-z][a-z0-9_.-]*")
_KINDS = {"structure", "dataset", "basis_set", "orbital_set", "density_matrix"}
_VALUE_TYPES = {"boolean", "integer", "number", "string"}


def _token(value, name):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{name} must be a lower token")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be non-empty text")
    return value


def _tokens(values, name):
    result = tuple(values)
    for value in result:
        _token(value, name)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _json_value(value, name="value"):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{name} keys must be strings")
        return {key: _json_value(value[key], name) for key in sorted(value)}
    raise ValueError(f"{name} must be JSON-compatible")


def _plain_json(value):
    if isinstance(value, dict):
        return {key: _plain_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RecipeInputSpec:
    name: str
    entity_kind: str
    semantic_roles: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    dims: tuple[tuple[str, ...], ...] = ()
    units: tuple[str, ...] = ()
    required_attributes: tuple[str, ...] = ()

    def __post_init__(self):
        _token(self.name, "input name")
        if self.entity_kind not in _KINDS:
            raise ValueError("entity_kind is not supported")
        object.__setattr__(
            self, "semantic_roles", _tokens(self.semantic_roles, "semantic role")
        )
        object.__setattr__(self, "domains", _tokens(self.domains, "domain"))
        dims = tuple(tuple(value) for value in self.dims)
        for signature in dims:
            _tokens(signature, "dimension")
        if len(set(dims)) != len(dims):
            raise ValueError("dims must not contain duplicates")
        object.__setattr__(self, "dims", dims)
        object.__setattr__(self, "units", _tokens(self.units, "unit"))
        object.__setattr__(
            self,
            "required_attributes",
            _tokens(self.required_attributes, "required attribute"),
        )


def _parameter_value(spec, value, label):
    if spec.value_type == "boolean":
        valid = isinstance(value, bool)
    elif spec.value_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif spec.value_type == "number":
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    else:
        valid = isinstance(value, str)
    if not valid:
        raise TypeError(f"{spec.name} {label} must be {spec.value_type}")
    if spec.minimum is not None and value < spec.minimum:
        raise ValueError(f"{spec.name} {label} is below minimum")
    if spec.maximum is not None and value > spec.maximum:
        raise ValueError(f"{spec.name} {label} is above maximum")
    if spec.choices and value not in spec.choices:
        raise ValueError(f"{spec.name} {label} is not an allowed choice")
    return value


@dataclass(frozen=True, slots=True)
class RecipeParameterSpec:
    name: str
    value_type: str
    required: bool
    default: object = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[object, ...] = ()

    def __post_init__(self):
        _token(self.name, "parameter name")
        if self.value_type not in _VALUE_TYPES:
            raise ValueError("value_type is not supported")
        if not isinstance(self.required, bool):
            raise TypeError("required must be boolean")
        for value, name in ((self.minimum, "minimum"), (self.maximum, "maximum")):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        if (self.minimum is not None or self.maximum is not None) and self.value_type not in {
            "integer",
            "number",
        }:
            raise ValueError("bounds require a numeric parameter")
        choices = tuple(_json_value(value, "choice") for value in self.choices)
        choice_keys = tuple(
            json.dumps(_plain_json(value), sort_keys=True, separators=(",", ":"))
            for value in choices
        )
        if len(set(choice_keys)) != len(choices):
            raise ValueError("choices must not contain duplicates")
        object.__setattr__(self, "choices", choices)
        if self.required:
            if self.default is not None:
                raise ValueError("required parameter must not define a default")
        elif self.default is None:
            raise ValueError("optional parameter requires a default")
        else:
            default = _json_value(self.default, "default")
            _parameter_value(self, default, "default")
            object.__setattr__(self, "default", default)


@dataclass(frozen=True, slots=True)
class RecipeOutputSpec:
    name: str
    semantic_role: str
    domain: str
    dims: tuple[str, ...]
    unit: str

    def __post_init__(self):
        for value, name in (
            (self.name, "output name"),
            (self.semantic_role, "semantic role"),
            (self.domain, "domain"),
            (self.unit, "unit"),
        ):
            _token(value, name)
        dims = _tokens(self.dims, "dimension")
        object.__setattr__(self, "dims", dims)


@dataclass(frozen=True, slots=True)
class RecipeViewSpec:
    kind: str
    sources: tuple[str, ...]

    def __post_init__(self):
        _token(self.kind, "view kind")
        sources = _tokens(self.sources, "view source")
        if not sources:
            raise ValueError("view requires at least one source")
        object.__setattr__(self, "sources", sources)


@dataclass(frozen=True, slots=True)
class RecipeValidationSpec:
    rule: str
    message: str

    def __post_init__(self):
        _token(self.rule, "validation rule")
        _text(self.message, "validation message")


@dataclass(frozen=True, slots=True)
class RecipeCitation:
    key: str
    title: str
    doi: str = ""
    url: str = ""

    def __post_init__(self):
        _token(self.key, "citation key")
        _text(self.title, "citation title")
        if not isinstance(self.doi, str) or not isinstance(self.url, str):
            raise TypeError("citation doi and url must be strings")
        if not self.doi and not self.url:
            raise ValueError("citation requires a DOI or URL")


@dataclass(frozen=True, slots=True)
class RecipeDefinition:
    recipe_id: str
    version: str
    title: str
    supported_programs: tuple[str, ...]
    inputs: tuple[RecipeInputSpec, ...]
    parameters: tuple[RecipeParameterSpec, ...]
    outputs: tuple[RecipeOutputSpec, ...]
    views: tuple[RecipeViewSpec, ...]
    validations: tuple[RecipeValidationSpec, ...]
    citations: tuple[RecipeCitation, ...]

    def __post_init__(self):
        _token(self.recipe_id, "recipe_id")
        _text(self.version, "recipe version")
        _text(self.title, "recipe title")
        object.__setattr__(
            self,
            "supported_programs",
            _tokens(self.supported_programs, "supported program"),
        )
        if not self.supported_programs:
            raise ValueError("recipe requires at least one supported program")
        groups = (
            ("inputs", RecipeInputSpec),
            ("parameters", RecipeParameterSpec),
            ("outputs", RecipeOutputSpec),
            ("views", RecipeViewSpec),
            ("validations", RecipeValidationSpec),
            ("citations", RecipeCitation),
        )
        for name, expected in groups:
            values = tuple(getattr(self, name))
            if any(not isinstance(value, expected) for value in values):
                raise TypeError(f"{name} contains an invalid value")
            object.__setattr__(self, name, values)
        for name in ("inputs", "parameters", "outputs"):
            names = tuple(value.name for value in getattr(self, name))
            if len(set(names)) != len(names):
                raise ValueError(f"duplicate {name[:-1]} name")
        if not self.inputs or not self.outputs or not self.views or not self.validations or not self.citations:
            raise ValueError("recipe requires inputs, outputs, views, validations and citations")
        sources = {value.name for value in self.inputs}.union(
            value.name for value in self.outputs
        )
        if any(source not in sources for view in self.views for source in view.sources):
            raise ValueError("view references an unknown source")


@dataclass(frozen=True, slots=True)
class RecipeBinding:
    name: str
    entity_kind: str
    entity_id: UUID
    revision: str


@dataclass(frozen=True, slots=True)
class RecipePlan:
    recipe_id: str
    recipe_version: str
    bindings: tuple[RecipeBinding, ...]
    parameters: tuple[tuple[str, object], ...]
    derivation_key: str


def _entity(project, kind, entity_id):
    registries = {
        "structure": project.structures,
        "dataset": project.datasets,
        "basis_set": project.basis_sets,
        "orbital_set": project.orbital_sets,
        "density_matrix": project.density_matrices,
    }
    try:
        return registries[kind][entity_id]
    except KeyError as error:
        raise ValueError(f"{kind} input is not present in the project") from error


def _validate_input(spec, entity):
    if spec.entity_kind == "dataset":
        if not isinstance(entity, PropertyDataset):
            raise TypeError(f"{spec.name} must bind a dataset")
        if entity.status is DatasetStatus.PARTIAL:
            raise ValueError(f"{spec.name} dataset must be complete enough for the recipe")
        checks = (
            (spec.semantic_roles, entity.semantic_role, "semantic role"),
            (spec.domains, entity.domain, "domain"),
            (spec.dims, entity.data.dims, "dims"),
            (spec.units, entity.data.unit, "unit"),
        )
        for accepted, actual, label in checks:
            if accepted and actual not in accepted:
                raise ValueError(f"{spec.name} has incompatible {label}")
    for attribute in spec.required_attributes:
        if not hasattr(entity, attribute) or getattr(entity, attribute) is None:
            raise ValueError(f"{spec.name} is missing required attribute {attribute}")


def plan_recipe(recipe, project, inputs, parameters):
    if not isinstance(recipe, RecipeDefinition):
        raise TypeError("recipe must be a RecipeDefinition")
    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    if not isinstance(inputs, dict) or set(inputs) != {item.name for item in recipe.inputs}:
        raise ValueError("input names must exactly match the recipe")
    if not isinstance(parameters, dict):
        raise TypeError("parameters must be a mapping")
    specs = {item.name: item for item in recipe.parameters}
    if not set(parameters).issubset(specs):
        raise ValueError("parameter names must be declared by the recipe")

    bindings = []
    identities = []
    for spec in recipe.inputs:
        entity_id = inputs[spec.name]
        if not isinstance(entity_id, UUID):
            raise TypeError(f"{spec.name} input ID must be a UUID")
        entity = _entity(project, spec.entity_kind, entity_id)
        _validate_input(spec, entity)
        bindings.append(RecipeBinding(spec.name, spec.entity_kind, entity.id, entity.revision))
        identities.append((entity.id, entity.revision))

    normalized = {}
    for spec in recipe.parameters:
        if spec.name in parameters:
            value = _json_value(parameters[spec.name], spec.name)
            normalized[spec.name] = _parameter_value(spec, value, "value")
        elif spec.required:
            raise ValueError(f"required parameter is missing: {spec.name}")
        else:
            normalized[spec.name] = spec.default
    normalized_items = tuple((name, normalized[name]) for name in sorted(normalized))
    key = derivation_cache_key(
        identities,
        f"recipe.{recipe.recipe_id}",
        recipe.version,
        {name: _plain_json(value) for name, value in normalized_items},
    )
    return RecipePlan(
        recipe.recipe_id, recipe.version, tuple(bindings), normalized_items, key
    )


def recipe_document(recipe):
    if not isinstance(recipe, RecipeDefinition):
        raise TypeError("recipe must be a RecipeDefinition")
    return {
        "recipe_id": recipe.recipe_id,
        "version": recipe.version,
        "title": recipe.title,
        "supported_programs": list(recipe.supported_programs),
        "inputs": [
            {
                "name": value.name,
                "entity_kind": value.entity_kind,
                "semantic_roles": list(value.semantic_roles),
                "domains": list(value.domains),
                "dims": [list(item) for item in value.dims],
                "units": list(value.units),
                "required_attributes": list(value.required_attributes),
            }
            for value in recipe.inputs
        ],
        "parameters": [
            {
                "name": value.name,
                "value_type": value.value_type,
                "required": value.required,
                "default": _plain_json(value.default),
                "minimum": value.minimum,
                "maximum": value.maximum,
                "choices": [_plain_json(item) for item in value.choices],
            }
            for value in recipe.parameters
        ],
        "outputs": [
            {
                "name": value.name,
                "semantic_role": value.semantic_role,
                "domain": value.domain,
                "dims": list(value.dims),
                "unit": value.unit,
            }
            for value in recipe.outputs
        ],
        "views": [
            {"kind": value.kind, "sources": list(value.sources)}
            for value in recipe.views
        ],
        "validations": [
            {"rule": value.rule, "message": value.message}
            for value in recipe.validations
        ],
        "citations": [
            {
                "key": value.key,
                "title": value.title,
                "doi": value.doi,
                "url": value.url,
            }
            for value in recipe.citations
        ],
    }


def _exact(document, fields, label):
    if not isinstance(document, dict) or set(document) != set(fields):
        raise ValueError(f"invalid {label} fields")


def recipe_from_document(document):
    root = {
        "recipe_id", "version", "title", "supported_programs", "inputs",
        "parameters", "outputs", "views", "validations", "citations",
    }
    _exact(document, root, "recipe")

    def build(items, fields, constructor, label, transform=None):
        if not isinstance(items, list):
            raise ValueError(f"{label} must be a list")
        result = []
        for item in items:
            _exact(item, fields, label)
            values = dict(item)
            if transform is not None:
                transform(values)
            result.append(constructor(**values))
        return tuple(result)

    inputs = build(
        document["inputs"],
        {"name", "entity_kind", "semantic_roles", "domains", "dims", "units", "required_attributes"},
        RecipeInputSpec,
        "recipe input",
        lambda value: value.update(
            semantic_roles=tuple(value["semantic_roles"]),
            domains=tuple(value["domains"]),
            dims=tuple(tuple(item) for item in value["dims"]),
            units=tuple(value["units"]),
            required_attributes=tuple(value["required_attributes"]),
        ),
    )
    parameters = build(
        document["parameters"],
        {"name", "value_type", "required", "default", "minimum", "maximum", "choices"},
        RecipeParameterSpec,
        "recipe parameter",
        lambda value: value.update(choices=tuple(value["choices"])),
    )
    outputs = build(
        document["outputs"],
        {"name", "semantic_role", "domain", "dims", "unit"},
        RecipeOutputSpec,
        "recipe output",
        lambda value: value.update(dims=tuple(value["dims"])),
    )
    views = build(
        document["views"], {"kind", "sources"}, RecipeViewSpec, "recipe view",
        lambda value: value.update(sources=tuple(value["sources"])),
    )
    validations = build(
        document["validations"], {"rule", "message"}, RecipeValidationSpec,
        "recipe validation",
    )
    citations = build(
        document["citations"], {"key", "title", "doi", "url"}, RecipeCitation,
        "recipe citation",
    )
    return RecipeDefinition(
        recipe_id=document["recipe_id"], version=document["version"],
        title=document["title"], supported_programs=tuple(document["supported_programs"]),
        inputs=inputs, parameters=parameters, outputs=outputs, views=views,
        validations=validations, citations=citations,
    )


def builtin_recipes():
    finite = (RecipeValidationSpec("finite_output", "Output arrays must be finite."),)
    cclib_citation = RecipeCitation(
        "cclib", "cclib: a library for package-independent computational chemistry algorithms", url="https://cclib.github.io/"
    )
    gbasis_citation = RecipeCitation(
        "gbasis", "GBasis Gaussian basis-set toolkit", url="https://github.com/theochem/gbasis"
    )
    spectrum_parameters = (
        RecipeParameterSpec("profile", "string", False, "stick", choices=("stick", "gaussian", "lorentzian")),
        RecipeParameterSpec("fwhm", "number", False, 10.0, minimum=0.0),
    )
    vibration = RecipeDefinition(
        "vibrational_ir_spectrum", "1", "Vibrational IR spectrum", ("cclib",),
        (RecipeInputSpec("modes", "dataset", ("vibrational_modes",), ("mode",), (("mode",),), ("inverse_centimeter",), ("ir_intensities",)),),
        spectrum_parameters,
        (RecipeOutputSpec("spectrum", "ir_spectrum", "frequency", ("sample",), "kilometer_per_mole"),),
        (RecipeViewSpec("spectrum_plot", ("spectrum", "modes")),), finite,
        (cclib_citation,),
    )
    tddft = RecipeDefinition(
        "tddft_uvvis", "1", "TDDFT UV-Vis spectrum", ("cclib",),
        (RecipeInputSpec("states", "dataset", ("excited_states",), ("state",), (("state",),), ("inverse_centimeter",), ("oscillator_strengths",)),),
        spectrum_parameters,
        (RecipeOutputSpec("spectrum", "uv_vis_spectrum", "frequency", ("sample",), "dimensionless"),),
        (RecipeViewSpec("spectrum_plot", ("spectrum", "states")),), finite,
        (cclib_citation,),
    )
    orbital = RecipeDefinition(
        "wavefunction_molecular_orbital_grid", "1", "Molecular orbital grid", ("iodata", "pyscf"),
        (
            RecipeInputSpec("structure", "structure"),
            RecipeInputSpec("basis", "basis_set"),
            RecipeInputSpec("orbitals", "orbital_set"),
        ),
        (
            RecipeParameterSpec("orbital_index", "integer", True),
            RecipeParameterSpec("channel", "string", False, "alpha", choices=("alpha", "beta")),
            RecipeParameterSpec("spacing", "number", False, 0.25, minimum=0.000001),
            RecipeParameterSpec("padding", "number", False, 4.0, minimum=0.0),
        ),
        (RecipeOutputSpec("grid", "molecular_orbital", "grid", ("x", "y", "z"), "inverse_bohr_to_three_halves"),),
        (RecipeViewSpec("signed_isosurface", ("grid",)),), finite,
        (gbasis_citation,),
    )
    return {recipe.recipe_id: recipe for recipe in (vibration, tddft, orbital)}
