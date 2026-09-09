"""Native bounded cloud framing, cancellation and coordinate metadata regression."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ['BLENDER_USER_RESOURCES']).resolve()
assert ROOT / '.agents/cache' in private.parents
private.mkdir(parents=True, exist_ok=True)

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from cbq_core.sidecar import LazyNpyArray
from cbq_core.sidecar import close_project
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from ChemBlender.render_scene import RenderCancelled, RenderScope, _coordinate_metadata

values = numpy.zeros((41, 41, 41))
values[4:39, 10:26, 3:37] = .3
grid = Grid3D(id=uuid4(), revision='framing', semantic_role='electron_density', domain='grid',
    data=ArrayData(values, ('x', 'y', 'z'), 'electron_per_cubic_angstrom'),
    status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
    origin=(-2., -2., -2.), step_vectors=((.1, 0., 0.), (.02, .1, 0.), (0., .01, .1)),
    coordinate_unit='angstrom')
project = QCProject(id=uuid4(), schema_version="0.1")
project.commit(ImportBatch(datasets=(grid,)))
save_project(private / 'field.cbq', project)
project = open_project(private / 'field.cbq')
assert isinstance(project.datasets[grid.id].data.values, LazyNpyArray)
plan = plan_scene_preset(builtin_scene_presets()['grid_volume'], project, {'grid': grid.id}, {})
selected = numpy.argwhere(values >= .2)
lower, upper = selected.min(axis=0) - 1, selected.max(axis=0) + 1
expected = numpy.asarray([numpy.asarray(grid.origin) + numpy.asarray((x, y, z)) @ grid.step_vectors
    for x in (lower[0], upper[0]) for y in (lower[1], upper[1]) for z in (lower[2], upper[2])])
before = {name: len(getattr(bpy.data, name)) for name in
          ('objects', 'meshes', 'volumes', 'materials', 'node_groups', 'curves', 'lights', 'cameras', 'worlds')}
with RenderScope(bpy.context, project, template='research', width=96, height=72,
                 samples=1, volume_focus_threshold=.2) as renderer:
    original = renderer.frame_objects
    def frame(objects, **kwargs):
        numpy.testing.assert_allclose(numpy.asarray(kwargs['extra_corners']), expected, atol=1e-6)
        return original(objects, **kwargs)
    with patch.object(renderer, 'frame_objects', side_effect=frame):
        document = renderer.render(plan, private / 'focus.png', private / 'cache')
assert document['display_coordinate_unit'] == 'angstrom'
calls = []
with RenderScope(bpy.context, project, template='research', width=96, height=72,
                 samples=1, volume_focus_threshold=.2) as renderer:
    def cancelled():
        calls.append(True)
        return len(calls) == 2
    try:
        renderer.render(plan, private / 'cancelled.png', private / 'cache', is_cancelled=cancelled)
    except RenderCancelled:
        pass
    else:
        raise AssertionError('second chunk cancellation was ignored')
assert not (private / 'cancelled.png').exists()
assert before == {name: len(getattr(bpy.data, name)) for name in before}
numpy.testing.assert_array_equal(grid.data.values, values)
numpy.testing.assert_array_equal(project.datasets[grid.id].data.values, values)
close_project(project)
assert _coordinate_metadata(SimpleNamespace(view_kind='fermi_surface'), None, ()) == {
    'display_coordinate_unit': 'inverse_angstrom', 'display_coordinate_system': 'reciprocal_cartesian_2pi'}
print('SCIENTIFIC_RENDER_COORDINATES_PASSED: affine focus bounds, bounded cancellation, full cleanup, reciprocal units')
