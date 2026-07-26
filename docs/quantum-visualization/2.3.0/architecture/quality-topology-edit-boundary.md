# 2.3.0 数据质量、拓扑与科学编辑边界

## 1. 质量状态

```python
class QualityStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
```

- Complete：该 reader 声明的 capability contract 已满足，语义和单位明确。
- Partial：数据缺少部分元素，但现有值可信。
- Ambiguous：值存在，但语义、单位、对应关系或来源不能唯一确定。
- Incomplete：计算或多步数据未完成，已有中间结果可用。
- Invalid：违反结构、引用、shape 或格式完整性，不可使用。

## 2. Recovery mode

```text
strict    → 关键拓扑、类型或可选属性矛盾也拒绝对应 record
balanced  → 默认；结构身份严格，可选数据宽容
maximum   → 尽量恢复可证明字段，但质量不能自动提升
```

统一规则：

| 情况 | Balanced 行为 |
| --- | --- |
| 原子数量与坐标不一致 | 拒绝 Structure |
| 键索引越界 | 拒绝 Topology，保留 Structure |
| SDF 单条损坏 | 记录失败，保留其他 records |
| RDKit sanitize失败 | 保留 raw explicit topology，标记 ambiguous/unsanitized |
| Cube数据点数错误 | 拒绝 Grid；头部结构可单独保留并报告 |
| Cube语义/单位未知 | Grid保留为 ambiguous，要求用户确认 |
| CIF Uij部分缺失 | ADP dataset partial，结构保留 |
| 计算未结束 | Calculation incomplete，已有结构/能量可用 |
| extXYZ某属性无效 | 对应 property partial，结构继续 |

## 3. ImportDiagnostic

```python
@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    id: UUID
    severity: DiagnosticSeverity
    quality_status: QualityStatus
    source_revision_id: UUID
    record_key: str | None
    entity_id: UUID | None
    field_path: str
    code: str
    message: str
    original_value: DiagnosticValue | None
    normalized_value: DiagnosticValue | None
    recovery_action: str | None
    scientific_consequence: str
    suggested_action: str | None
```

诊断 code是稳定机器标识，例如：

```text
xyz.extra_property_type_mismatch
sdf.record_parse_failed
mol.sanitize_failed
cube.scalar_semantics_unknown
cif.partial_anisotropic_displacement
project.duplicate_content
```

UI 只对阻断问题弹窗。其余显示摘要和 badge，详细报告可复制、导出 canonical JSON 和 Markdown。

## 4. 拓扑实体

`MolecularTopology` 只有 bond indices/orders，无法表达 provenance和可信度。2.3.0 使用独立 `TopologyRecord`：

```python
@dataclass(frozen=True, slots=True)
class TopologyRecord:
    id: UUID
    revision: str
    structure_id: UUID
    bond_indices: ArrayData
    bond_orders: ArrayData
    aromatic_flags: ArrayData | None
    stereo_labels: tuple[str, ...]
    source_kind: TopologySource
    quality_status: QualityStatus
    inference_parameters: tuple[tuple[str, CanonicalValue], ...]
    provenance_ids: tuple[UUID, ...]
```

来源优先级：

```text
explicit_file
rdkit_sanitized
distance_inferred
user_edited
```

一个 Structure可以拥有多套拓扑。View选择 active topology，不覆盖其他版本。

## 5. 距离推断

距离推断产生派生 topology，不伪装成原始文件键：

- 使用空间格子或邻居列表，避免全局 O(N²)。
- 周期结构支持 minimum-image/PBC。
- 元素对阈值、共价半径 scale、最大配位和金属规则进入 inference parameters。
- 周期材料连接默认 bond order为 unknown/coordination，不强行标为普通单键。
- 金属配合物、异常价态和过渡态显示 ambiguous badge。
- 用户 Accept 产生 user-confirmed revision；Reject 不删除原建议。

## 6. 原子身份与字符串

基础格式需要：

```text
atom serial
atom name
isotope
formal charge
partial charge
residue name/index
chain ID
insertion code
altloc
site label
substructure ID/name
```

NumPy object arrays不能进入 sidecar。采用：

```python
@dataclass(frozen=True, slots=True)
class CategoricalData:
    codes: ArrayData
    categories: tuple[str, ...]
    missing_code: int
```

原始字符串表保留，Blender写 integer code和 mapping JSON/hash。

## 7. 科学编辑

### 不产生新科学实体

- Object平移、旋转、缩放；
- 材质、球半径、键粗细；
- 相机、灯光、隐藏、selection；
- View参数和 scene preset。

### 必须产生派生实体

- 原子坐标变化；
- 元素、同位素、形式电荷变化；
- 增删原子或键；
- 晶胞、occupancy、Uij变化。

流程：

```text
Imported Structure A
→ user edits Blender view
→ Apply Scientific Edits
→ diff preview
→ Derived Structure B + optional Topology B
→ provenance(operation="scientific_edit", parent=A)
```

A关联的轨道、振动、网格和电荷不自动继承到B。导出B时明确标记为派生结构。
