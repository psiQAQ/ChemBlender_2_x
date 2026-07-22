# 振动、IR/Raman 光谱与 Blender 模态设计

## 目标

将 cclib 的谐振动结果转换为独立于 Blender 的语义对象，从同一组有符号频率和强度派生 stick/Gaussian/Lorentzian 光谱，并用一个 Mesh、named attributes 和一个 instanced-arrow Geometry Nodes contract 表达当前模态。

## 已确认的输入契约

cclib 1.8.1 的权威属性表定义：

| 属性 | shape | unit | ChemBlender 语义 |
| --- | --- | --- | --- |
| `vibfreqs` | `(mode,)` | `1/cm` | 有符号谐振动频率 |
| `vibdisps` | `(mode, atom, xyz)` | Å | Cartesian displacement |
| `vibrmasses` | `(mode,)` | Da | reduced mass |
| `vibfconsts` | `(mode,)` | mDyne/Å | force constant |
| `vibirs` | `(mode,)` | km/mol | IR intensity |
| `vibramans` | `(mode,)` | Å⁴/Da | Raman activity |
| `vibsyms` | `(mode,)` | dimensionless label | symmetry label |

真实 fixture 基线：Gaussian 16 `dvb_ir.out` 与 `dvb_raman.out`、ORCA 5.0 同名输出均含 20 atoms、54 modes。四者都有 frequency/displacement/IR；两个 Raman 输出有 Raman activity；Gaussian 有 reduced mass/force constant/symmetry，ORCA 5.0 fixture 没有这些字段。adapter 必须依据实际属性生成 `ParserReport`，不能按程序名称补值。

## 语义模型

`VibrationalModeSet` 继承 `PropertyDataset`：

- `semantic_role="vibrational_modes"`、`domain="mode"`；
- `data` 是 signed frequencies，dims `("mode",)`，unit `inverse_centimeter`；
- `structure_id` 指向位移对应的结构；
- `displacements` 使用 dims `("mode", "atom", "xyz")` 与 unit `angstrom`；
- reduced mass、force constant、IR intensity、Raman activity 均为可选 `ArrayData`；
- symmetry labels 保持字符串 tuple，不写入 Geometry Nodes；
- 记录 `displacement_convention="cclib_cartesian"`、source calculation 与 provenance。

虚频保留负号。缺少 frequency 或 displacement 时不创建伪完整 mode set；只缺辅助量时仍创建，并逐字段报告 `MISSING`。

`Spectrum` 也继承 `PropertyDataset`：

- `semantic_role` 为 `ir_spectrum` 或 `raman_spectrum`；
- `axis` 和 `data` 共享 `("sample",)`；axis unit 为 `inverse_centimeter`；
- `profile` 为 `stick`、`gaussian` 或 `lorentzian`；
- `source_dataset_id` 保持通用 linked selection 身份；IR/Raman 在项目校验时要求它指向 `VibrationalModeSet`；
- broadened profile 使用 FWHM，采用 peak-normalized line shape，因此纵轴仍保留源 intensity/activity unit。

Gaussian：`exp(-4 ln(2) ((x-f)/FWHM)^2)`；Lorentzian：`1 / (1 + 4 ((x-f)/FWHM)^2)`。默认保留并计算所有有符号 modes；若调用方排除 imaginary modes，必须显式传参并写入 provenance。

## Blender 映射

`create_vibration_view` 消费现有原子 Mesh 与 normalized mode set：

- 在 POINT domain 写入 `cbq_vibration_displacement`、`cbq_vibration_magnitude`；
- 将 reference positions 保留在 adapter 的运行态映射，不写回权威 `Structure`；
- `apply_vibration_phase` 计算 `r(phase) = r0 + scale * sin(phase) * displacement`；
- 一个 Geometry Nodes modifier 从 named vector attribute 实例化箭头；不为每个 atom/mode/frame 创建 Object；
- Object custom properties 只保存 mode-set UUID/revision、mode index、scale、phase 和 attribute contract version。

本切片提供可调用 adapter 和 runtime smoke，不新增完整 UI panel、长期 session 恢复或光谱绘图库；这些使用同一 dataset/mode ID 在 Phase 1 收口。

## 验证

- synthetic 模型覆盖 shape/unit/reference、虚频、可选字段和原子数检查。
- synthetic cclib data 覆盖完整、辅助字段缺失、frequency/displacement 不成对和非法 shape。
- Gaussian/ORCA 四个真实 fixture 对照 54 modes、首个频率、字段 coverage 与 Raman presence。
- 光谱测试覆盖 stick identity、FWHM 半峰值、profile、imaginary-mode policy 和 deterministic provenance。
- Blender 5.1 smoke 验证一个 Mesh、一个 modifier、named attributes、箭头 instance contract，以及 `phase=π/2` 和 `phase=π` 的顶点坐标。

## 非目标

- phonopy complex q-point eigenvectors、声子色散、VCD、非谐频率和温度占据；
- 从 Raman activity 推导实验 Raman intensity；
- 将动画帧或光谱图片作为权威数据写入 `.blend`；
- 新增绘图库或将 cclib 打包进 Extension。
