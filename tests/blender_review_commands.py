"""Agent 模拟用户：已验证 UI 操作的公开 MCP 重放目录。

UI 证据相对 .blend-analysis/2026-09-07-review/screenshots/。
2026-09-08 用户授权：重复操作可用 MCP；重放不记作新的原生 UI 首测。
宿主读取 COMMANDS，将 JSON 参数作为 args 传入 Blender；产品流程只用公开
bpy.ops / RNA。install 仅限停止旧进程后的独立测试 profile。
"""

OPERATOR_UI_EVIDENCE = {
    "extensions.package_install_files": "REP-BIOLOGICAL-R24-00-install-user-default.png",
    "wm.save_userpref": "REP-BIOLOGICAL-R23-04-enabled.png",
    "chemblender.quick_import": "REP-BIOLOGICAL-R23-05-pdb-preview.png",
    "chemblender.confirm_import": "REP-BIOLOGICAL-R23-06-hierarchy-fixed.png",
    "chemblender.cancel_import": "IMP: 原生 Preview Cancel，详见 IMP.md",
    "chemblender.select_biological_atoms": "REP-BIOLOGICAL-R23-21-zero-radius.png",
    "chemblender.play_biological_models": "REP-BIOLOGICAL-R23-10-model10.png",
    "chemblender.configure_trajectory_playback": "REP-TRAJECTORY-R22-03-playback-entry.png",
    "chemblender.apply_frame_force": "REP-TRAJECTORY-R22-09-playing.png",
    "screen.animation_play": "REP-BIOLOGICAL-R23-11-playing.png",
    "screen.animation_cancel": "REP-BIOLOGICAL-R23-UI-paused.json (outputs)",
    "wm.save_as_mainfile": "REP-TRAJECTORY-R22-12-saved.png",
    "wm.open_mainfile": "LIFE: 原生 Open/冷重开，详见 LIFE.md",
    "render.render": "OUTSIDE-R21-UI-render-final.png",
    "chemblender.toggle_selective_constraints": "DATA-R7-02: 原生隐藏/恢复，详见 DATA.md",
    "chemblender.derive_crystal_symmetry": "DATA: 原生禁用按钮及缺失原因，详见 DATA.md（仅验证失败停止）",
    "chemblender.resolve_grid_semantics": "VIEW-R9-03-resolved.png；R13 干净原生重测见 VIEW.md",
    "chemblender.create_grid_view": "VIEW-R9-04-volume.png、VIEW-R9-05-surface.png；R13 干净原生重测见 VIEW.md",
    "chemblender.export_project_entity": "EXP: 原生格式切换、损失预览、取消及确认，详见 EXP.md",
    "chemblender.import_smiles_text": "IMP: 原生 SMILES 预览与确认，详见 IMP.md",
    "chemblender.preview_legacy_migration": "MIG-R19-02-preview.png；R20 完整原生重测见 MIG.md",
    "chemblender.migrate_legacy_scene": "MIG-R19-03-confirmation.png；R20 完整原生重测见 MIG.md",
    "chemblender.project_link_recovery": "LIFE: 原生 Verify/Relink，详见 LIFE.md",
}

COMMANDS = {
    "package_identity": """
from pathlib import Path
import hashlib,zipfile
package=Path(args['package'])
repo=next(r for r in bpy.context.preferences.extensions.repos if r.module=='user_default')
with zipfile.ZipFile(package) as archive:
    differences=[n for n in archive.namelist() if n.endswith('.py') and (Path(repo.directory)/'chemblender'/n).read_bytes()!=archive.read(n)]
assert not differences,differences
result={'package_sha256':hashlib.sha256(package.read_bytes()).hexdigest(),
 'installed_python_matches':True,'enabled':'bl_ext.user_default.chemblender' in bpy.context.preferences.addons}
assert result['enabled']
""",
    "inspect": """
import sys
result={'version':bpy.app.version_string,'binary':bpy.app.binary_path,
 'python':sys.executable,'file':bpy.data.filepath,'dirty':bpy.data.is_dirty,
 'addons':list(bpy.context.preferences.addons.keys()),
 'repos':[{'module':r.module,'directory':r.directory} for r in bpy.context.preferences.extensions.repos],
 'objects':[(o.name,o.type) for o in bpy.context.scene.objects]}
""",
    "operator": """
operator_id=args['operator']
assert operator_id in tested_operators, 'UI evidence required before reuse'
namespace,name=operator_id.split('.')
operation=getattr(getattr(bpy.ops,namespace),name)
assert operation.poll(), operator_id+' poll failed'
rna=operation.get_rna_type()
keywords=args.get('kwargs',{})
assert set(keywords)<=set(rna.properties.keys()), 'Unknown public RNA argument'
try:
    returned=operation(**keywords)
except RuntimeError as error:
    assert args.get('expected_error') and args['expected_error'] in str(error),str(error)
    result={'operator':operator_id,'error':str(error),'expected_failure':True}
else:
    result={'operator':operator_id,'returned':sorted(returned),
     'ui_evidence':tested_operators[operator_id]}
    assert not args.get('expected_error'), 'Expected error did not occur'
    assert sorted(returned)==args.get('expected_return',sorted(returned))
    assert 'CANCELLED' not in returned or args.get('expected_return')==['CANCELLED'], result
""",
    "rna": """
result={}
for operator_id in args['operators']:
    namespace,name=operator_id.split('.')
    operation=getattr(getattr(bpy.ops,namespace),name)
    result[operator_id]={'poll':operation.poll(),'properties':[{ 'name':p.identifier,'type':p.type} for p in operation.get_rna_type().properties]}
""",
    "select_context": """
settings=bpy.context.scene.chemblender_project_browser
if 'row' in args:settings.selected_index=args['row']
if 'object' in args:
    obj=bpy.data.objects[args['object']]
    for other in bpy.context.selected_objects:other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
for area in bpy.context.screen.areas:area.tag_redraw()
result={'selected_index':settings.selected_index,'active_object':bpy.context.active_object.name if bpy.context.active_object else None}
""",
    "grid_settings": """
settings=bpy.context.scene.chemblender_grid
for key,value in args.get('values',{}).items():
    assert key in settings.bl_rna.properties
    setattr(settings,key,value)
result={p.identifier:getattr(settings,p.identifier) for p in settings.bl_rna.properties if p.type in {'STRING','INT','FLOAT','ENUM'}}
""",
    "environment": """
import sys,rdkit,gemmi,numpy
from bl_ext.user_default.chemblender import reader_api
descriptors=reader_api.builtin_reader_plugin_registry().descriptors
result={'blender':bpy.app.version_string,'python':sys.version,'enabled':'bl_ext.user_default.chemblender' in bpy.context.preferences.addons,
 'modules':{m.__name__:{'file':m.__file__,'version':getattr(m,'__version__',None)} for m in (rdkit,gemmi,numpy)},
 'scene_rna':[p for p in ('chemblender_quick_import','chemblender_project_browser','chemblender_grid') if hasattr(bpy.context.scene,p)],
 'reader_api':True,'reader_count':len(descriptors),'quick_import_poll':bpy.ops.chemblender.quick_import.poll()}
assert result['enabled'] and len(result['scene_rna'])==3 and result['reader_count']>0 and result['quick_import_poll']
""",
    "migration_preview": """
value=bpy.context.scene.chemblender_migration_preview_json
result={'preview':json.loads(value) if value else None}
""",
    "clean": """
assert not bpy.data.is_dirty or args.get('discard_test_scene')
bpy.ops.wm.read_homefile(use_empty=True)
bpy.context.scene.name=args['scene']
result={'scene':bpy.context.scene.name,'objects':len(bpy.data.objects)}
""",
    "preview": """
settings=bpy.context.scene.chemblender_quick_import
result={'summary':settings.recent_summary,
 'preview':json.loads(settings.preview_json) if settings.preview_json else None,
 'objects':[(o.name,o.type) for o in bpy.context.scene.objects]}
""",
    "browser": """
settings=bpy.context.scene.chemblender_project_browser
if 'mode' in args:settings.mode=args['mode']
if 'search' in args:settings.search=args['search']
result={'mode':settings.mode,'search':settings.search,
 'rows':[{'index':i,'kind':r.kind,'entity_id':r.entity_id,'label':r.label} for i,r in enumerate(settings.rows)]}
""",
    "biological_context": """
settings=bpy.context.scene.chemblender_project_browser
matches=[o for o in bpy.context.scene.objects if o.type=='MESH' and len(o.data.vertices)==args['atoms']]
assert len(matches)==1, 'Biological view must be unique'
obj=matches[0]
indices=[i for i,r in enumerate(settings.rows) if r.kind=='biological_hierarchy' and r.entity_id==obj.get('cb_biological_hierarchy_id')]
assert len(indices)==1, 'Select By Data and search hierarchy before selecting'
for other in bpy.context.selected_objects:other.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active=obj
settings.selected_index=indices[0]
result={'active_object':obj.name,'hierarchy_id':obj['cb_biological_hierarchy_id'],'selected_index':settings.selected_index}
""",
    "frame": """
bpy.context.scene.frame_set(args['frame'])
result={'frame':bpy.context.scene.frame_current,'end':bpy.context.scene.frame_end,
 'playing':bpy.context.screen.is_animation_playing}
""",
    "snapshot_bio": """
s=bpy.context.scene
b=s.chemblender_project_browser
result={'scene':s.name,'frame':s.frame_current,'end':s.frame_end,
 'playing':bpy.context.screen.is_animation_playing,'file':bpy.data.filepath,'dirty':bpy.data.is_dirty,
 'project':{k:v for k,v in s.items() if k.startswith('cbq_')},
 'settings':{p.identifier:getattr(b,p.identifier) for p in b.bl_rna.properties if p.type in {'STRING','INT','ENUM'}},
 'rows':[{p.identifier:getattr(r,p.identifier) for p in r.bl_rna.properties if p.type in {'STRING','INT','ENUM'}} for r in b.rows],
 'objects':[{'name':o.name,'xyz':[list(v.co) for v in o.data.vertices],
 'attrs':{a.name:[d.value for d in a.data] for a in o.data.attributes if a.name=='cbq_selected'},
 'props':dict(o.items()),'polygons':len(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons)} for o in s.objects if o.type=='MESH']}
result=json.loads(json.dumps(result,default=list))
""",
    "render_path": """
bpy.context.scene.render.filepath=args['path']
result={'path':bpy.context.scene.render.filepath}
""",
    "instance_geometry": """
result={}
for instance in bpy.context.evaluated_depsgraph_get().object_instances:
    if instance.is_instance and instance.parent:
        entry=result.setdefault(instance.parent.original.name,{'instances':0,'polygons':0})
        entry['instances']+=1
        if instance.object.type=='MESH':entry['polygons']+=len(instance.object.data.polygons)
""",
    "snapshot_grid": """
s=bpy.context.scene
result={'file':bpy.data.filepath,'dirty':bpy.data.is_dirty,'project':{k:v for k,v in s.items() if k.startswith('cbq_')},
 'objects':[{'name':o.name,'type':o.type,'properties':dict(o.items()),'collections':[c.name for c in o.users_collection],
 'volume_filepath':bpy.path.abspath(o.data.filepath) if o.type=='VOLUME' else None,
 'xyz':[list(v.co) for v in o.data.vertices] if o.type=='MESH' else None,
 'location':list(o.location),'scale':list(o.scale),'hide_render':o.hide_render} for o in s.objects],
 'materials':[{'name':m.name,'nodes':[{'name':n.name,'type':n.bl_idname} for n in m.node_tree.nodes] if m.use_nodes else []} for m in bpy.data.materials]}
result=json.loads(json.dumps(result,default=list))
""",
    "active_view": """
o=bpy.context.active_object
assert o and o.type=='MESH'
marker=bpy.data.objects.get(o.get('cb_selective_marker_object',''))
result={'name':o.name,'frame':bpy.context.scene.frame_current,'playing':bpy.context.screen.is_animation_playing,
 'xyz':[list(v.co) for v in o.data.vertices],'properties':dict(o.items()),
 'vectors':[list(v.vector) for v in o.data.attributes['cbq_vector'].data] if 'cbq_vector' in o.data.attributes else None,
 'selected':[d.value for d in o.data.attributes['cbq_selected'].data] if 'cbq_selected' in o.data.attributes else None,
 'marker_hidden':marker.hide_get() if marker else None}
result=json.loads(json.dumps(result,default=list))
""",
    "presentation": """
from pathlib import Path
script=Path(args['script']).resolve()
assert script.is_relative_to(Path(args['run_root']).resolve())
exec(compile(script.read_text(encoding='utf-8'),str(script),'exec'))
""",
}
