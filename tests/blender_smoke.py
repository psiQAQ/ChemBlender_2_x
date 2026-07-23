import array
import importlib
import importlib.util
import json
import math
import sys
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile

import bpy


def assert_package_contents(package):
    required = {
        "blender_manifest.toml",
        "LICENSE",
        "Chem_Nodes.blend",
        "Chem_Nodes_En.blend",
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
    }
    forbidden_prefixes = ("scripts/", "tests/", "worker/", "__pycache__/")

    with ZipFile(package) as archive:
        names = {entry.filename.replace("\\", "/") for entry in archive.infolist()}

    assert required <= names, required - names
    assert not any(name.startswith(forbidden_prefixes) for name in names)
    assert not any(name.endswith(".zip") for name in names)
    assert [name for name in names if name.endswith(".whl")] == [
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl"
    ]


def assert_enabled(module_key):
    assert module_key in bpy.context.preferences.addons
    assert f"{module_key}.core.cube" in sys.modules
    assert f"{module_key}.core.mol_v2000" in sys.modules
    assert f"{module_key}.core.xyz" in sys.modules
    assert f"{module_key}.core.wavefunction_grid" in sys.modules
    assert f"{module_key}.core.wavefunction_observables" in sys.modules
    assert f"{module_key}.core.recipe" in sys.modules
    assert f"{module_key}.core.critic2_adapter" in sys.modules
    assert "gbasis" not in sys.modules
    assert "ase" not in sys.modules
    assert "pymatgen" not in sys.modules
    assert f"{module_key}.grid_volume" in sys.modules
    assert f"{module_key}.dataset_view" in sys.modules
    assert f"{module_key}.trajectory_view" in sys.modules
    assert f"{module_key}.worker_client" in sys.modules
    assert f"{module_key}.topology_view" in sys.modules
    assert f"{module_key}.scene_preset_view" in sys.modules
    assert f"{module_key}.spectrum_plot" in sys.modules
    assert f"{module_key}.surface_view" in sys.modules
    assert f"{module_key}.core.worker_protocol" in sys.modules
    assert "worker" not in sys.modules
    core = importlib.import_module(f"{module_key}.core")
    assert set(core.builtin_recipes()) == {
        "tddft_uvvis",
        "vibrational_ir_spectrum",
        "wavefunction_molecular_orbital_grid",
    }
    assert sum(
        getattr(handler, "__module__", None) == f"{module_key}.trajectory_view"
        for handler in bpy.app.handlers.frame_change_post
    ) == 1
    assert hasattr(bpy.types.Object, "cif_original")
    assert hasattr(bpy.types.Object, "cif_current")
    assert hasattr(bpy.types.Scene, "my_tool")


def assert_disabled(module_key):
    assert module_key not in bpy.context.preferences.addons
    assert not hasattr(bpy.types.Object, "cif_original")
    assert not hasattr(bpy.types.Object, "cif_current")
    assert not hasattr(bpy.types.Scene, "my_tool")
    assert not any(
        getattr(handler, "__module__", None) == f"{module_key}.trajectory_view"
        for handler in bpy.app.handlers.frame_change_post
    )


def assert_installed_blend_libraries(module_key):
    spec = importlib.util.find_spec(module_key)
    assert spec is not None and spec.submodule_search_locations
    extension_root = Path(next(iter(spec.submodule_search_locations)))
    expected_node_groups = {
        "Chem_Nodes.blend": 174,
        "Chem_Nodes_En.blend": 171,
    }

    for filename, expected_count in expected_node_groups.items():
        blend_file = extension_root / filename
        assert blend_file.is_file(), blend_file
        with bpy.data.libraries.load(str(blend_file), link=False) as (data_from, _):
            assert len(data_from.node_groups) == expected_count, filename


def assert_grid_volume_adapter(module_key):
    import openvdb

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.grid_volume")
    values = memoryview(array.array("d", range(8)))
    values = values.cast("B").cast("d", shape=(2, 2, 2))
    dataset_id = uuid4()
    structure_id = uuid4()
    grid = core.Grid3D(
        id=dataset_id,
        revision="grid-revision",
        semantic_role="molecular_orbital",
        domain="grid",
        data=core.ArrayData(
            values, ("x", "y", "z"), "inverse_bohr_to_three_halves"
        ),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(1.0, 2.0, 3.0),
        step_vectors=((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.3, 1.0)),
        coordinate_unit="bohr",
        structure_id=structure_id,
    )
    with TemporaryDirectory() as directory:
        cache_root = Path(directory)
        cache = adapter.volume_cache_path(cache_root, grid)
        obj = adapter.create_grid_volume(
            grid,
            cache_root,
            collection=bpy.context.scene.collection,
        )
        volume = obj.data
        try:
            assert cache.is_file()
            assert obj.type == "VOLUME" and obj.matrix_world.is_identity
            assert len(volume.grids) == 1 and volume.grids["density"] is not None
            assert obj["cb_dataset_id"] == str(dataset_id)
            assert obj["cb_dataset_revision"] == "grid-revision"
            assert obj["cb_structure_id"] == str(structure_id)
            assert obj["cb_dataset_index"] == 0
            assert obj["cb_semantic_role"] == "molecular_orbital"
            assert obj["cb_value_unit"] == "inverse_bohr_to_three_halves"
            assert obj["cb_source_coordinate_unit"] == "bohr"
            assert obj["cb_display_coordinate_unit"] == "angstrom"
            assert obj["cb_render_cache_key"] == cache.stem
            cached = openvdb.read(str(cache), "density")
            assert cached.getAccessor().getValue((1, 0, 1)) == 5.0
            expected = tuple(value * 0.529177210903 for value in (2.2, 3.3, 4.0))
            actual = tuple(cached.transform.indexToWorld((1, 1, 1)))
            assert all(abs(a - b) < 1e-12 for a, b in zip(actual, expected))

            lod = core.derive_grid_lod(grid, strides=(2, 1, 1)).datasets[0]
            lod_cache = adapter.volume_cache_path(cache_root, lod)
            assert lod_cache != cache
            lod_obj = adapter.create_grid_volume(
                lod, cache_root, collection=bpy.context.scene.collection
            )
            lod_volume = lod_obj.data
            try:
                assert lod_cache.is_file()
                assert lod_obj["cb_render_cache_key"] == lod_cache.stem
                lod_cached = openvdb.read(str(lod_cache), "density")
                assert lod_cached.getAccessor().getValue((0, 1, 1)) == 3.0
                lod_world = tuple(
                    lod_cached.transform.indexToWorld((1, 0, 0))
                )
                expected_lod = tuple(
                    value * 0.529177210903 for value in (3.0, 2.0, 3.0)
                )
                assert all(
                    abs(a - b) < 1e-12
                    for a, b in zip(lod_world, expected_lod)
                )
            finally:
                bpy.data.objects.remove(lod_obj, do_unlink=True)
                bpy.data.volumes.remove(lod_volume)
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.volumes.remove(volume)


def assert_vibration_view_adapter(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.vibration_view")
    mesh = bpy.data.meshes.new("ChemBlender vibration smoke mesh")
    mesh.from_pydata([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [], [])
    obj = bpy.data.objects.new("ChemBlender vibration smoke", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mode_set_id = uuid4()
    modes = core.VibrationalModeSet(
        id=mode_set_id,
        revision="vibration-revision",
        semantic_role="vibrational_modes",
        domain="mode",
        data=core.ArrayData(numpy.asarray([-100.0]), ("mode",), "inverse_centimeter"),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=uuid4(),
        displacements=core.ArrayData(
            numpy.asarray([[[1.0, 0.0, 0.0], [0.0, 0.5, 0.0]]]),
            ("mode", "atom", "xyz"),
            "angstrom",
        ),
        reduced_masses=None,
        force_constants=None,
        ir_intensities=None,
        raman_activities=None,
        symmetries=None,
        displacement_convention="cclib_cartesian",
    )
    try:
        modifier = adapter.create_vibration_view(
            obj,
            modes,
            mode_index=0,
            arrow_scale=2.0,
        )
        assert obj["cb_vibration_mode_set_id"] == str(mode_set_id)
        assert obj["cb_vibration_mode_index"] == 0
        assert modifier.type == "NODES"
        assert modifier.node_group["cbq_contract"] == "vector_arrow_v1"
        assert len(obj.modifiers) == 1
        assert mesh.attributes["cbq_vector"].domain == "POINT"
        vectors = [0.0] * 6
        mesh.attributes["cbq_vector"].data.foreach_get("vector", vectors)
        assert vectors == [2.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        evaluated_geometry = evaluated.evaluated_geometry()
        assert len(evaluated_geometry.instance_references()) == 1
        assert len(evaluated_geometry.instances_pointcloud().points) == 2

        adapter.apply_vibration_phase(obj, math.pi / 2.0, amplitude_scale=0.5)
        coordinates = [0.0] * 6
        mesh.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(coordinates, [0.5, 0.0, 0.0, 1.0, 0.25, 0.0])
        adapter.apply_vibration_phase(obj, math.pi, amplitude_scale=0.5)
        mesh.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(coordinates, [0.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_dataset_and_trajectory_views(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.dataset_view")
    trajectory = importlib.import_module(f"{module_key}.trajectory_view")
    structure_id = uuid4()
    structure = core.Structure(
        id=structure_id,
        revision="structure-revision",
        atomic_numbers=(8, 1, 1),
        coordinates=core.ArrayData(
            numpy.asarray(
                [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]]
            ),
            ("atom", "xyz"),
            "bohr",
        ),
    )
    obj = adapter.create_structure_view(
        structure,
        name="ChemBlender dataset smoke",
        collection=bpy.context.scene.collection,
    )
    mesh = obj.data
    try:
        assert obj["cb_structure_id"] == str(structure_id)
        atom_ids = [0] * 3
        obj.data.attributes["cbq_atom_id"].data.foreach_get("value", atom_ids)
        assert atom_ids == [0, 1, 2]
        coordinates = [0.0] * 9
        obj.data.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(
            coordinates,
            [
                0.0,
                0.0,
                0.0,
                1.058354421806,
                0.0,
                0.0,
                -1.058354421806,
                0.0,
                0.0,
            ],
        )

        scalar_id = uuid4()
        scalar = core.AtomicProperty(
            id=scalar_id,
            revision="scalar-revision",
            semantic_role="mulliken_charge",
            domain="atom",
            data=core.ArrayData(
                numpy.asarray([-0.2, numpy.nan, 0.4]),
                ("atom",),
                "elementary_charge",
            ),
            status=core.DatasetStatus.PARTIAL,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
        )
        adapter.apply_atomic_scalar(obj, scalar, symmetric=True)
        scalar_values = [0.0] * 3
        scalar_valid = [False] * 3
        obj.data.attributes["cbq_atom_scalar"].data.foreach_get(
            "value", scalar_values
        )
        obj.data.attributes["cbq_atom_scalar_valid"].data.foreach_get(
            "value", scalar_valid
        )
        assert numpy.allclose(scalar_values, [-0.2, 0.0, 0.4])
        assert scalar_valid == [True, False, True]
        assert obj["cb_scalar_dataset_id"] == str(scalar_id)
        assert obj["cb_scalar_unit"] == "elementary_charge"
        assert obj["cb_scalar_display_min"] == -0.4
        assert obj["cb_scalar_display_max"] == 0.4
        assert obj.data.attributes["colour"].domain == "POINT"

        vector_id = uuid4()
        vector = core.AtomicProperty(
            id=vector_id,
            revision="vector-revision",
            semantic_role="force",
            domain="atom",
            data=core.ArrayData(
                numpy.asarray(
                    [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]]
                ),
                ("atom", "xyz"),
                "hartree_per_bohr",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
        )
        modifier = adapter.apply_atomic_vector(obj, vector, display_scale=0.5)
        assert modifier.node_group["cbq_contract"] == "vector_arrow_v1"
        assert obj["cb_vector_dataset_id"] == str(vector_id)
        assert obj["cb_vector_unit"] == "hartree_per_bohr"
        vector_values = [0.0] * 9
        obj.data.attributes["cbq_vector"].data.foreach_get(
            "vector", vector_values
        )
        assert vector_values == [0.5, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.5]
        assert len(obj.modifiers) == 1
        adapter.apply_atomic_vector(obj, vector, display_scale=1.0)
        assert len(obj.modifiers) == 1
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        evaluated_geometry = evaluated.evaluated_geometry()
        assert len(evaluated_geometry.instance_references()) == 1
        assert len(evaluated_geometry.instances_pointcloud().points) == 3

        adapter.apply_atom_selection(obj, [0, 2], name="terminal_atoms")
        selected = [False] * 3
        obj.data.attributes["cbq_selected"].data.foreach_get("value", selected)
        assert selected == [True, False, True]
        assert obj["cb_selection_name"] == "terminal_atoms"

        states = core.ExcitedStateSet(
            id=uuid4(),
            revision="states-revision",
            semantic_role="excited_states",
            domain="state",
            data=core.ArrayData(
                numpy.asarray([20000.0, 30000.0]),
                ("state",),
                "inverse_centimeter",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
            oscillator_strengths=core.ArrayData(
                numpy.asarray([0.1, 0.2]), ("state",), "dimensionless"
            ),
            rotatory_strengths=None,
            electric_transition_dipoles=None,
            velocity_transition_dipoles=None,
            magnetic_transition_dipoles=None,
            symmetries=None,
            multiplicities=(None, None),
            configurations=None,
            state_references=(
                core.ExcitedStateReferences(),
                core.ExcitedStateReferences(),
            ),
        )
        spectrum = core.derive_electronic_spectrum(
            states,
            kind=core.SpectrumKind.UV_VIS,
            profile=core.SpectrumProfile.STICK,
        ).datasets[0]
        adapter.link_stick_spectrum_selection(obj, spectrum, states, 1)
        assert obj["cb_selection_spectrum_id"] == str(spectrum.id)
        assert obj["cb_selection_dataset_id"] == str(states.id)
        assert obj["cb_selection_domain"] == "state"
        assert obj["cb_selection_index"] == 1
        broadened = core.derive_electronic_spectrum(
            states,
            kind=core.SpectrumKind.UV_VIS,
            profile=core.SpectrumProfile.GAUSSIAN,
            axis=numpy.asarray([19000.0, 20000.0, 21000.0]),
            fwhm=1000.0,
        ).datasets[0]
        try:
            adapter.link_stick_spectrum_selection(obj, broadened, states, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("broadened spectrum selection must be rejected")

        frames = core.FrameSet(
            id=uuid4(),
            revision="trajectory-revision",
            semantic_role="coordinates",
            domain="frame",
            data=core.ArrayData(
                numpy.asarray(
                    [
                        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]],
                        [[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [-2.0, 0.0, 1.0]],
                    ]
                ),
                ("frame", "atom", "xyz"),
                "bohr",
            ),
            status=core.DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
            comments=("first", "second"),
        )
        invalid_frames = core.FrameSet(
            id=uuid4(),
            revision="invalid-trajectory-revision",
            semantic_role="coordinates",
            domain="frame",
            data=core.ArrayData(
                numpy.asarray(
                    [
                        [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]],
                        [[0.0, 0.0, float("nan")], [2.0, 0.0, 1.0], [-2.0, 0.0, 1.0]],
                    ]
                ),
                ("frame", "atom", "xyz"),
                "bohr",
            ),
            status=core.DatasetStatus.PARTIAL,
            source_calculation=None,
            provenance_ids=(),
            structure_id=structure_id,
            comments=("first", "invalid"),
        )
        invalid_manager = core.TrajectoryFrameManager(invalid_frames)
        try:
            invalid_manager.frame(1)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid trajectory frames must be rejected")
        finally:
            invalid_manager.close()
        trajectory.configure_trajectory_view(
            obj, frames, frame_start=10, frame_step=2, cache_size=2
        )
        trajectory.configure_trajectory_view(
            obj, frames, frame_start=10, frame_step=2, cache_size=2
        )
        handlers = [
            handler
            for handler in bpy.app.handlers.frame_change_post
            if handler.__module__ == trajectory.__name__
        ]
        assert len(handlers) == 1
        bpy.context.scene.frame_set(12)
        obj.data.vertices.foreach_get("co", coordinates)
        assert numpy.allclose(
            numpy.asarray(coordinates).reshape((3, 3))[:, 2],
            [0.529177210903] * 3,
        )
        assert obj["cb_trajectory_frame_index"] == 1
        assert obj["cb_trajectory_cache_size"] == 2
        assert obj["cb_trajectory_prefetch_ahead"] == 0
        bpy.context.scene.frame_set(100)
        assert obj["cb_trajectory_frame_index"] == 1
        assert len(bpy.data.objects) >= 1
        trajectory.clear_trajectory_view(obj)
    finally:
        bpy.context.scene.frame_set(1)
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)


def assert_periodic_structure_view(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.dataset_view")
    structure = core.Structure(
        id=uuid4(),
        revision="periodic-structure-revision",
        atomic_numbers=(14,),
        coordinates=core.ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0]]), ("atom", "xyz"), "angstrom"
        ),
        cell=core.ArrayData(
            numpy.asarray([[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.0, 0.5, 5.0]]),
            ("cell_vector", "xyz"),
            "angstrom",
        ),
        periodic=core.PeriodicSiteData(
            fractional_coordinates=core.ArrayData(
                numpy.asarray([[0.0, 0.0, 0.0]]),
                ("atom", "xyz"),
                "dimensionless",
            ),
            site_labels=("Si1",),
            occupancies=core.ArrayData(
                numpy.ones(1), ("atom",), "dimensionless"
            ),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",),
            disorder_groups=(0,),
            declared_space_group_name=None,
            declared_space_group_number=None,
            symmetry_operations=(),
            cif_envelope_id=None,
            pbc=(True, False, True),
        ),
    )
    obj = adapter.create_structure_view(
        structure,
        name="ChemBlender periodic structure smoke",
        collection=bpy.context.scene.collection,
    )
    mesh = obj.data
    try:
        assert obj["cb_periodic"] is True
        assert list(obj["cb_pbc"]) == [True, False, True]
        assert numpy.allclose(
            list(obj["cb_periodic_cell"]),
            [4.0, 0.0, 0.0, 1.0, 3.0, 0.0, 0.0, 0.5, 5.0],
        )
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_periodic_electronic_plots(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    plots = importlib.import_module(f"{module_key}.electronic_plot")
    structure_id = uuid4()
    common = dict(
        revision="electronic-revision",
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        spin_channels=("alpha", "beta"),
        fermi_energy=5.0,
        energy_reference=core.EnergyReference.ABSOLUTE,
    )
    band = core.BandStructure(
        id=uuid4(),
        semantic_role="band_structure",
        domain="band",
        data=core.ArrayData(
            numpy.asarray([[[4.0, 6.0], [4.5, 6.5]], [[4.1, 6.1], [4.6, 6.6]]]),
            ("spin", "kpoint", "band"),
            "electron_volt",
        ),
        occupations=None,
        kpoints=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]]), ("kpoint", "reciprocal_axis"), "dimensionless"),
        reciprocal_lattice=core.ArrayData(numpy.eye(3), ("reciprocal_vector", "cartesian_axis"), "inverse_angstrom"),
        distances=core.ArrayData(numpy.asarray([0.0, 1.0]), ("kpoint",), "inverse_angstrom"),
        labels=("GAMMA", "X"),
        branches=(core.BandPathBranch(0, 1, "GAMMA", "X"),),
        projections=None,
        orbital_labels=(),
        **common,
    )
    dos = core.DensityOfStates(
        id=uuid4(),
        semantic_role="density_of_states",
        domain="energy",
        data=core.ArrayData(numpy.asarray([[1.0, 2.0, 3.0], [0.5, 1.0, 1.5]]), ("spin", "energy"), "states_per_electron_volt"),
        energies=core.ArrayData(numpy.asarray([4.0, 5.0, 6.0]), ("energy",), "electron_volt"),
        projections=None,
        orbital_labels=(),
        **common,
    )
    band_obj = plots.create_band_structure_plot(band, collection=bpy.context.scene.collection)
    dos_obj = plots.create_dos_plot(dos, collection=bpy.context.scene.collection)
    try:
        assert len(band_obj.data.splines) == 4
        assert band_obj["cb_energy_reference"] == "fermi_shifted"
        assert band_obj.data.splines[0].points[0].co.y == -1.0
        assert len(dos_obj.data.splines) == 2
        assert dos_obj.data.splines[1].points[0].co.x == -0.5
        plots.select_band_sample(band_obj, band, 1, 0, 1)
        assert band_obj["cb_selected_spin"] == 1
        assert band_obj["cb_selected_band"] == 1
        plots.select_dos_sample(dos_obj, dos, 0, 2)
        assert dos_obj["cb_selected_energy"] == 2
    finally:
        for obj in (band_obj, dos_obj):
            curve = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.curves.remove(curve)


def assert_scene_preset_application(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    view = importlib.import_module(f"{module_key}.scene_preset_view")
    surface_view = importlib.import_module(f"{module_key}.surface_view")
    presets = core.builtin_scene_presets()
    structure = core.Structure(
        id=uuid4(), revision="scene-structure-r1", atomic_numbers=(8, 1),
        coordinates=core.ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            ("atom", "xyz"), "angstrom",
        ),
    )
    modes = core.VibrationalModeSet(
        id=uuid4(), revision="scene-modes-r1", semantic_role="vibrational_modes",
        domain="mode", data=core.ArrayData(numpy.asarray([1000.0]), ("mode",), "inverse_centimeter"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=structure.id,
        displacements=core.ArrayData(numpy.asarray([[[0.1, 0.0, 0.0], [-0.1, 0.0, 0.0]]]), ("mode", "atom", "xyz"), "angstrom"),
        reduced_masses=None, force_constants=None,
        ir_intensities=core.ArrayData(numpy.asarray([10.0]), ("mode",), "kilometer_per_mole"),
        raman_activities=None, symmetries=("A1",), displacement_convention="cclib_cartesian",
    )
    states = core.ExcitedStateSet(
        id=uuid4(), revision="scene-states-r1", semantic_role="excited_states",
        domain="state", data=core.ArrayData(numpy.asarray([20000.0]), ("state",), "inverse_centimeter"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=structure.id,
        oscillator_strengths=core.ArrayData(numpy.asarray([0.2]), ("state",), "dimensionless"),
        rotatory_strengths=None, electric_transition_dipoles=None,
        velocity_transition_dipoles=None, magnetic_transition_dipoles=None,
        symmetries=("A1",), multiplicities=(1,), configurations=((),),
        state_references=(core.ExcitedStateReferences(),),
    )
    ir_batch = core.derive_vibrational_spectrum(
        modes, kind=core.SpectrumKind.IR, profile=core.SpectrumProfile.STICK
    )
    ir = ir_batch.datasets[0]
    uv_batch = core.derive_electronic_spectrum(
        states, kind=core.SpectrumKind.UV_VIS, profile=core.SpectrumProfile.STICK
    )
    uv = uv_batch.datasets[0]
    project = core.QCProject(uuid4(), "0.1")
    project.commit(core.ImportBatch(structures=(structure,), datasets=(modes, states)))
    project.commit(ir_batch)
    project.commit(uv_batch)

    created = []
    try:
        structure_plan = core.plan_scene_preset(
            presets["structure_publication"], project, {"structure": structure.id}, {}
        )
        created.extend(view.apply_scene_preset(structure_plan, project, collection=bpy.context.scene.collection))
        assert created[-1]["cb_scene_render_identity"] == structure_plan.render_identity

        vibration_plan = core.plan_scene_preset(
            presets["vibration_spectrum_linked"], project,
            {"structure": structure.id, "modes": modes.id, "spectrum": ir.id},
            {"arrow_scale": 2.0},
        )
        vibration_objects = view.apply_scene_preset(vibration_plan, project, collection=bpy.context.scene.collection)
        created.extend(vibration_objects)
        assert {obj.type for obj in vibration_objects} == {"MESH", "CURVE"}
        assert vibration_objects[0]["cb_selection_domain"] == "mode"
        assert vibration_objects[1]["cb_plot_contract"] == "spectrum_curve_v1"
        assert len(vibration_objects[1].data.splines) == 1

        electronic_plan = core.plan_scene_preset(
            presets["electronic_spectrum_linked"], project,
            {"structure": structure.id, "states": states.id, "spectrum": uv.id}, {},
        )
        electronic_objects = view.apply_scene_preset(electronic_plan, project, collection=bpy.context.scene.collection)
        created.extend(electronic_objects)
        assert electronic_objects[0]["cb_selection_domain"] == "state"

        grid_coordinates = numpy.indices((5, 5, 5), dtype=float)
        signed_values = grid_coordinates[0] - 2.0
        radius = numpy.sqrt(sum((axis - 2.0) ** 2 for axis in grid_coordinates))
        density_values = 1.5 - radius
        property_values = sum(axis - 2.0 for axis in grid_coordinates)
        grid_fields = dict(
            domain="grid", status=core.DatasetStatus.COMPLETE,
            source_calculation=None, provenance_ids=(), structure_id=None,
            origin=(-2.0, -2.0, -2.0),
            step_vectors=((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.1, 1.0)),
            coordinate_unit="angstrom",
        )
        signed_grid = core.Grid3D(
            id=uuid4(), revision="signed-grid-r1", semantic_role="molecular_orbital",
            data=core.ArrayData(signed_values, ("x", "y", "z"), "dimensionless"),
            **grid_fields,
        )
        density_grid = core.Grid3D(
            id=uuid4(), revision="density-grid-r1", semantic_role="electron_density",
            data=core.ArrayData(density_values, ("x", "y", "z"), "dimensionless"),
            **grid_fields,
        )
        property_grid = core.Grid3D(
            id=uuid4(), revision="property-grid-r1", semantic_role="electrostatic_potential",
            data=core.ArrayData(property_values, ("x", "y", "z"), "dimensionless"),
            **grid_fields,
        )
        grid_project = core.QCProject(uuid4(), "0.1")
        grid_project.commit(core.ImportBatch(datasets=(signed_grid, density_grid, property_grid)))
        with TemporaryDirectory() as cache_root:
            signed_plan = core.plan_scene_preset(
                presets["signed_isosurface"], grid_project, {"grid": signed_grid.id},
                {"isovalue": 0.5},
            )
            signed_objects = view.apply_scene_preset(
                signed_plan, grid_project, cache_root=cache_root,
                collection=bpy.context.scene.collection,
            )
            created.extend(signed_objects)
            assert [obj["cb_surface_phase"] for obj in signed_objects] == ["positive", "negative"]
            assert [obj["cb_surface_isovalue"] for obj in signed_objects] == [0.5, -0.5]
            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            for obj in signed_objects:
                evaluated = obj.evaluated_get(depsgraph)
                geometry = evaluated.evaluated_geometry()
                assert geometry.mesh is not None
                assert len(geometry.mesh.vertices) > 0

            property_plan = core.plan_scene_preset(
                presets["property_on_surface"], grid_project,
                {"surface_grid": density_grid.id, "property_grid": property_grid.id},
                {"surface_isovalue": 0.2, "color_min": -3.0, "color_max": 3.0},
            )
            property_objects = view.apply_scene_preset(
                property_plan, grid_project, cache_root=cache_root,
                collection=bpy.context.scene.collection,
            )
            created.extend(property_objects)
            property_obj = property_objects[0]
            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = property_obj.evaluated_get(depsgraph)
            geometry = evaluated.evaluated_geometry()
            assert geometry.mesh is not None
            mesh = geometry.mesh
            assert len(mesh.vertices) > 0
            attribute = mesh.attributes["cbq_surface_property"]
            sampled = [0.0] * len(mesh.vertices)
            attribute.data.foreach_get("value", sampled)
            assert min(sampled) < max(sampled)
            assert property_obj["cb_property_colormap"] == "coolwarm"
            assert len(list(Path(cache_root).glob("surface/*.vdb"))) == 3

        periodic_id = uuid4()
        band = core.BandStructure(
            id=uuid4(), revision="scene-band-r1", semantic_role="band_structure", domain="band",
            data=core.ArrayData(numpy.asarray([[[4.0], [6.0]]]), ("spin", "kpoint", "band"), "electron_volt"),
            status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(), structure_id=periodic_id,
            occupations=None,
            kpoints=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]]), ("kpoint", "reciprocal_axis"), "dimensionless"),
            reciprocal_lattice=core.ArrayData(numpy.eye(3), ("reciprocal_vector", "cartesian_axis"), "inverse_angstrom"),
            distances=core.ArrayData(numpy.asarray([0.0, 1.0]), ("kpoint",), "inverse_angstrom"),
            spin_channels=("alpha",), labels=("GAMMA", "X"), branches=(core.BandPathBranch(0, 1, "GAMMA", "X"),),
            projections=None, orbital_labels=(), fermi_energy=5.0, energy_reference=core.EnergyReference.ABSOLUTE,
        )
        dos = core.DensityOfStates(
            id=uuid4(), revision="scene-dos-r1", semantic_role="density_of_states", domain="energy",
            data=core.ArrayData(numpy.asarray([[1.0, 2.0]]), ("spin", "energy"), "states_per_electron_volt"),
            status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(), structure_id=periodic_id,
            energies=core.ArrayData(numpy.asarray([4.0, 6.0]), ("energy",), "electron_volt"),
            spin_channels=("alpha",), projections=None, orbital_labels=(), fermi_energy=5.0,
            energy_reference=core.EnergyReference.ABSOLUTE,
        )
        periodic = core.Structure(
            id=periodic_id, revision="periodic-r1", atomic_numbers=(14,),
            coordinates=core.ArrayData(numpy.zeros((1, 3)), ("atom", "xyz"), "angstrom"),
        )
        periodic_project = core.QCProject(uuid4(), "0.1")
        periodic_project.commit(core.ImportBatch(structures=(periodic,), datasets=(band, dos)))
        band_plan = core.plan_scene_preset(
            presets["band_dos_linked"], periodic_project, {"band": band.id, "dos": dos.id}, {}
        )
        band_objects = view.apply_scene_preset(band_plan, periodic_project, collection=bpy.context.scene.collection)
        created.extend(band_objects)
        assert [obj["cb_plot_contract"] for obj in band_objects] == ["band_structure_curve_v1", "density_of_states_curve_v1"]

        before = len(bpy.data.objects)
        project.structures[structure.id] = replace(structure, revision="scene-structure-r2")
        try:
            view.apply_scene_preset(structure_plan, project)
            raise AssertionError("stale plan must fail")
        except core.ScenePresetError:
            pass
        assert len(bpy.data.objects) == before

        original = view.create_spectrum_plot
        view.create_spectrum_plot = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced failure"))
        project.structures[structure.id] = structure
        before = len(bpy.data.objects)
        try:
            view.apply_scene_preset(vibration_plan, project)
            raise AssertionError("adapter failure must fail")
        except RuntimeError as error:
            assert str(error) == "forced failure"
        finally:
            view.create_spectrum_plot = original
        assert len(bpy.data.objects) == before
    finally:
        for obj in reversed(created):
            if obj.type == "VOLUME":
                surface_view.remove_surface_object(obj)
            else:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data.users == 0:
                    bpy.data.batch_remove(ids=(data,))


def assert_complex_phonon_trajectory(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    views = importlib.import_module(f"{module_key}.dataset_view")
    trajectory = importlib.import_module(f"{module_key}.trajectory_view")
    primitive_id = uuid4()
    eigenvectors = numpy.zeros((1, 3, 1, 3), dtype=complex)
    eigenvectors[0, 0, 0, 0] = 1.0 + 2.0j
    modes = core.PhononModeSet(
        id=uuid4(), revision="phonon-smoke", semantic_role="phonon_modes", domain="mode",
        data=core.ArrayData(numpy.asarray([[-1.0, 2.0, 3.0]]), ("qpoint", "mode"), "terahertz"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=primitive_id,
        qpoints=core.ArrayData(numpy.asarray([[0.5, 0.0, 0.0]]), ("qpoint", "reciprocal_axis"), "dimensionless"),
        eigenvectors=core.ArrayData(eigenvectors, ("qpoint", "mode", "atom", "xyz"), "dimensionless"),
        masses=core.ArrayData(numpy.asarray([4.0]), ("atom",), "atomic_mass_unit"),
        group_velocities=None, weights=None,
        eigenvector_convention="phonopy_mass_weighted_dynamical_matrix",
    )
    supercell = core.Structure(
        id=uuid4(), revision="phonon-supercell", atomic_numbers=(14, 14),
        coordinates=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]]), ("atom", "xyz"), "angstrom"),
        cell=core.ArrayData(numpy.diag([6.0, 3.0, 3.0]), ("cell_vector", "xyz"), "angstrom"),
        periodic=core.PeriodicSiteData(
            fractional_coordinates=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]]), ("atom", "xyz"), "dimensionless"),
            site_labels=("Si1", "Si2"), occupancies=core.ArrayData(numpy.ones(2), ("atom",), "dimensionless"),
            isotropic_displacements=None, anisotropic_displacements=None,
            adp_types=("none", "none"), disorder_groups=(0, 0),
            declared_space_group_name=None, declared_space_group_number=None,
            symmetry_operations=(), cif_envelope_id=None,
        ),
    )
    frames = core.derive_phonon_frames(
        modes, supercell,
        primitive_atom_indices=[0, 0], translations=[[0, 0, 0], [1, 0, 0]],
        qpoint_index=0, mode_index=0, phases=[0.0, math.pi / 2], amplitude=2.0,
    ).datasets[0]
    obj = views.create_structure_view(supercell, name="ChemBlender phonon smoke", collection=bpy.context.scene.collection)
    mesh = obj.data
    try:
        bpy.context.scene.frame_set(1)
        trajectory.configure_trajectory_view(obj, frames)
        first = [0.0] * 6
        mesh.vertices.foreach_get("co", first)
        assert numpy.allclose(first, [1.0, 0.0, 0.0, 2.0, 0.0, 0.0])
        bpy.context.scene.frame_set(2)
        second = [0.0] * 6
        mesh.vertices.foreach_get("co", second)
        assert numpy.allclose(second, [2.0, 0.0, 0.0, 1.0, 0.0, 0.0])
    finally:
        trajectory.clear_trajectory_view(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_fermi_surface_view(module_key):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    view = importlib.import_module(f"{module_key}.fermi_surface_view")
    surface = core.FermiSurfaceMesh(
        id=uuid4(), revision="fermi-smoke", semantic_role="fermi_surface", domain="surface_vertex",
        data=core.ArrayData(numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]), ("vertex", "xyz"), "inverse_angstrom"),
        status=core.DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
        structure_id=uuid4(), band_structure_id=uuid4(),
        faces=core.ArrayData(numpy.asarray([[0, 1, 2], [0, 2, 3]]), ("face", "corner"), "dimensionless"),
        band_indices=core.ArrayData(numpy.asarray([1, 3]), ("face",), "dimensionless"),
        spin_index=1, fermi_energy=5.25, coordinate_convention="cartesian_reciprocal_2pi",
        properties=(
            core.SurfaceProperty("orbital_contribution", "vertex", core.ArrayData(numpy.asarray([0.1, 0.2, 0.3, 0.4]), ("vertex",), "dimensionless")),
            core.SurfaceProperty("spin_texture", "vertex", core.ArrayData(numpy.ones((4, 3)), ("vertex", "xyz"), "dimensionless")),
        ),
    )
    obj = view.create_fermi_surface_view(surface, collection=bpy.context.scene.collection)
    mesh = obj.data
    try:
        assert len(mesh.vertices) == 4 and len(mesh.polygons) == 2
        bands = [0, 0]
        mesh.attributes["cbq_band_index"].data.foreach_get("value", bands)
        assert bands == [1, 3]
        scalars = [0.0] * 4
        mesh.attributes["cbq_orbital_contribution"].data.foreach_get("value", scalars)
        assert numpy.allclose(scalars, [0.1, 0.2, 0.3, 0.4])
        view.select_fermi_face(obj, surface, 1)
        assert obj["cb_selected_face"] == 1
        assert obj["cb_selected_band"] == 3
        assert obj["cb_spin_index"] == 1
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_project_sidecar_link(module_key):
    core = importlib.import_module(f"{module_key}.core")
    links = importlib.import_module(f"{module_key}.project_link")
    scene = bpy.context.scene
    marker = bpy.data.meshes.new("ChemBlender sidecar marker mesh")
    marker_object = bpy.data.objects.new("ChemBlender sidecar marker", marker)
    scene.collection.objects.link(marker_object)
    try:
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            blend_path = directory / "scene" / "view.blend"
            sidecar = directory / "data" / "smoke.cbq"
            project = core.QCProject(id=uuid4(), schema_version="0.1")
            core.save_project(sidecar, project)
            locator = links.write_project_link(
                scene, project, sidecar, blend_path=blend_path
            )
            assert not Path(locator).is_absolute()
            assert links.MANIFEST_HASH_KEY in scene
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.CONNECTED
            assert result.project.id == project.id
            core.close_project(result.project)

            core.save_project(sidecar, project)
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.MISMATCH
            assert marker_object.name in bpy.data.objects

            links.write_project_link(
                scene, project, sidecar, blend_path=blend_path
            )
            manifest_path = sidecar / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["manifest_sha256"] = "0" * 64
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True),
                encoding="utf-8",
            )
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.INVALID
            assert marker_object.name in bpy.data.objects

            scene[links.SIDECAR_LOCATOR_KEY] = "missing.cbq"
            result = links.resolve_project_link(scene, blend_path=blend_path)
            assert result.status is links.ProjectLinkStatus.MISSING
            assert marker_object.name in bpy.data.objects
    finally:
        for key in (
            links.PROJECT_ID_KEY,
            links.PROJECT_SCHEMA_KEY,
            links.SIDECAR_LOCATOR_KEY,
            links.MANIFEST_HASH_KEY,
        ):
            if key in scene:
                del scene[key]
        bpy.data.objects.remove(marker_object, do_unlink=True)
        bpy.data.meshes.remove(marker)


def assert_topology_view(module_key, repository_root):
    import numpy

    core = importlib.import_module(f"{module_key}.core")
    view = importlib.import_module(f"{module_key}.topology_view")
    fixture = (
        repository_root
        / "tests"
        / "fixtures"
        / "critic2"
        / "cpreport-minimal.json"
    )
    graph = core.parse_critic2_cpreport(
        fixture, structure_id=uuid4()
    ).datasets[0]
    path = core.TopologyPath(
        id=uuid4(),
        start_id=graph.critical_point_ids[0],
        end_id=graph.critical_point_ids[2],
        samples=core.ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            ("sample", "xyz"),
            "bohr",
        ),
    )
    graph = replace(graph, paths=(path,))
    points, paths = view.create_topology_view(graph)
    mesh = points.data
    curve = paths.data
    try:
        assert len(mesh.vertices) == 3
        assert numpy.allclose(mesh.vertices[1].co, [1.058354421806, 0.0, 0.0])
        kinds = [0, 0, 0]
        mesh.attributes["cbq_critical_point_kind"].data.foreach_get("value", kinds)
        assert kinds == [0, 0, 2]
        fields = [0.0, 0.0, 0.0]
        mesh.attributes["cbq_field_value"].data.foreach_get("value", fields)
        assert numpy.allclose(fields, [10.0, 10.0, 0.25])
        assert points["cb_topology_contract"] == "topology_graph_v1"
        assert len(curve.splines) == 1
        assert len(curve.splines[0].points) == 2
        assert paths["cb_topology_contract"] == "topology_paths_v1"
    finally:
        bpy.data.objects.remove(paths, do_unlink=True)
        bpy.data.curves.remove(curve)
        bpy.data.objects.remove(points, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def assert_legacy_crystal_reader_baseline(module_key, repository_root):
    reader = importlib.import_module(f"{module_key}.read")
    cif = repository_root / "tests" / "fixtures" / "cif" / "cscl.cif"
    poscar = repository_root / "tests" / "fixtures" / "poscar" / "cscl.vasp"
    cif_result = reader.read_cif(cif)
    assert cif_result[0] == [4.12, 4.12, 4.12]
    assert cif_result[1] == [90.0, 90.0, 90.0]
    assert cif_result[3] == 221
    assert cif_result[4] == ["Cs", "Cl"]
    assert cif_result[5] == ["Cs1", "Cl1"]
    assert cif_result[6:9] == ([0.0, 0.5], [0.0, 0.5], [0.0, 0.5])
    assert cif_result[9] == ["x,y,z"]

    poscar_result = reader.read_poscar(poscar)
    assert poscar_result[0] == (4.12, 4.12, 4.12), poscar_result
    assert poscar_result[1] == (90.0, 90.0, 90.0)
    assert poscar_result[3] == 221
    assert poscar_result[4] == ["Cs", "Cl"]
    assert poscar_result[5] == ["Cs1", "Cl1"]
    assert poscar_result[6:9] == ([0.0, 0.5], [0.0, 0.5], [0.0, 0.5])
    assert len(poscar_result[9]) == 48


arguments = sys.argv[sys.argv.index("--") + 1 :]
assert len(arguments) in (1, 2), "expected ZIP path and optional --keep-enabled"
assert len(arguments) == 1 or arguments[1] == "--keep-enabled"
keep_enabled = arguments[1:] == ["--keep-enabled"]
package = Path(arguments[0]).resolve()
assert package.is_file(), package
assert_package_contents(package)

result = bpy.ops.extensions.package_install_files(
    filepath=str(package),
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
assert result == {"FINISHED"}, result

module_key = "bl_ext.user_default.chemblender"
assert_enabled(module_key)
assert_installed_blend_libraries(module_key)
assert_grid_volume_adapter(module_key)
assert_vibration_view_adapter(module_key)
assert_dataset_and_trajectory_views(module_key)
assert_periodic_structure_view(module_key)
assert_periodic_electronic_plots(module_key)
assert_scene_preset_application(module_key)
assert_complex_phonon_trajectory(module_key)
assert_fermi_surface_view(module_key)
assert_project_sidecar_link(module_key)
assert_topology_view(module_key, package.parent.parent)
assert_legacy_crystal_reader_baseline(module_key, package.parent.parent)

for _ in range(2):
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key)
    assert bpy.ops.preferences.addon_enable(module=module_key) == {"FINISHED"}
    assert_enabled(module_key)

import rdkit
from rdkit import Chem
from rdkit.Chem import AllChem

assert rdkit.__version__
assert version("rdkit") == "2026.3.3"
molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
assert molecule is not None
assert AllChem.EmbedMolecule(molecule, randomSeed=0xC0FFEE) == 0

if keep_enabled:
    print("PASS: ChemBlender extension installed and enabled")
else:
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key)
    print("PASS: ChemBlender extension lifecycle")
