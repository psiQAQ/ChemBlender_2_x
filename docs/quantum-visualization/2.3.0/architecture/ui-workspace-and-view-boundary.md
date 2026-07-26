# 2.3.0 UI、Workspace 与 Blender View 边界

## 1. 双层 UI

### N 面板

面向日常用户：

```text
Quick Import
Current Project
Recent Sources
Active Data
Common View Controls
Open ChemBlender Workspace
```

Quick Import后不强制切换 workspace。

### ChemBlender Workspace

面向复杂项目：

```text
Top: Import / Save / Verify / Export
Left: Project Browser (By Source / By Data)
Center: 3D View
Right: Entity and View Properties
Bottom: Diagnostics / numeric preview / spectrum
```

第一版 Project Browser使用 `UIList` 扁平化树投影；不修改 Blender Outliner，也不把未创建 view的实体伪装成 Object。

## 2. Session state

```python
@dataclass(slots=True)
class ProjectSession:
    project: QCProject
    sidecar_path: Path | None
    temporary_root: Path
    dirty: bool
    link_status: ProjectLinkStatus
    active_entity_id: UUID | None
    active_view_object_name: str | None
```

Session对象由 Python service管理，Scene只保存可序列化 locator/UUID/schema/hash和 UI selection ID。register/unregister必须清理 handlers和临时资源句柄。

## 3. Project Browser 投影

```text
By Source
  SourceRecord
    SourceRevision
      ParserReport / Diagnostics
      Created Entities

By Data
  Structures
  Topologies
  Conformer Sets
  Trajectories
  Atomic Properties
  Grids
  Vibrations
  Excited States
  Spectra
  Blender Views
```

每一行包含：

- expand state；
- entity icon/type；
- display name；
- quality badge；
- active revision；
- view count；
- optional dependency unavailable indicator。

搜索和过滤使用缓存行模型；`draw()` 不遍历大型数组或触发 lazy load。

## 4. Import Preview

单文件、多文件和拖放都先打开 Preview：

- source/record列表；
- detected reader和执行模式；
- dependency availability；
- capabilities；
- quality summary；
- duplicate/revision conflict；
- source grouping suggestion；
- default view计划；
- recovery mode。

普通完整单文件允许“一步确认”而不是无条件弹出复杂设置；存在冲突、ambiguity、失败或多 record时展开详细页。

## 5. Drag-and-drop

使用 Blender `FileHandler` API：

- 3D View drop创建 ImportRequest并自动建议默认 view；
- Project Browser drop只导入项目，不强制创建 view；
- 多文件由一个 transaction处理；
- 只接受注册 reader声明的扩展名或 content sniff；
- 不扫描目录。

## 6. View registry

新增可重建 view记录：

```python
@dataclass(frozen=True, slots=True)
class ViewRecord:
    id: UUID
    view_kind: str
    entity_bindings: tuple[ViewBinding, ...]
    settings: tuple[tuple[str, CanonicalValue], ...]
    render_identity: str
    object_names: tuple[str, ...]
    quality_status: QualityStatus
```

Blender对象仍保存最小 identity用于定位，但项目的 ViewRecord负责重建、更新和失效判断。

## 7. Unified StructureViewBuilder

输入：

```text
Structure
selected TopologyRecord
atomic properties
ViewSettings
```

输出一个兼容新旧工具的 Mesh：

- vertices = atoms；
- edges = selected topology；
- `atomic_num`；
- `bond_order`；
- stable atom/bond IDs；
- structure/topology UUID/revision；
- periodic cell metadata；
- existing ball-and-stick Geometry Nodes；
- quality and topology-source metadata。

旧 scaffold operators在迁移期通过 bridge访问该对象，不另建第二对象格式。

## 8. 长任务

预计超过 1 s 的 parse、index、sidecar写入、Cube缓存和大型 view创建：

- 使用 modal operator + timer，或受控 worker；
- 显示阶段、已处理/总量、elapsed；
- 支持 Cancel；
- cancel后删除 staging，不改变项目；
- Blender RNA和datablock只在主线程修改。
