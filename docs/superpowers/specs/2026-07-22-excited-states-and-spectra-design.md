# 激发态、UV-Vis/ECD 与 transition reference 设计

## 目标

将 cclib 垂直激发态结果归一化为 `ExcitedStateSet`，保留带符号 configuration coefficients、transition dipoles 与不确定字段，并从同一 state identity 派生 UV-Vis/ECD stick、Gaussian 和 Lorentzian spectrum。

## 已确认的 cclib 1.8.1 契约

| 属性 | shape | unit / convention | ChemBlender 处理 |
| --- | --- | --- | --- |
| `etenergies` | `(state,)` | `1/cm` | 非负 excitation energy |
| `etoscs` | `(state,)` | dimensionless | UV-Vis oscillator strength |
| `etsyms` | state labels | program-dependent string | 原样保留；只从标准前缀派生 multiplicity |
| `etsecs` | ragged state/configuration | `(from MO, spin), (to MO, spin), coefficient` | typed contribution；spin 0/1 → alpha/beta |
| `etdips` | `(state, xyz)` | elementary charge × bohr | length-gauge electric transition dipole |
| `etveldips` | `(state, xyz)` | cclib 标为 elementary charge × bohr | velocity-gauge value，保持独立字段 |
| `etmagdips` | `(state, xyz)` | cclib 标为 elementary charge × bohr | magnetic value，保持独立字段 |
| `etrotats` | `(state,)` | cclib 公共 contract 为 unknown | 保存 signed value，整体标为 ambiguous，生成相对 ECD |

`etsecs` coefficient 是 cclib 转换后的带符号、未归一化 coefficient；对完整 alpha/beta configuration 集合，平方和应接近 1。模型保留 coefficient 本身；只有明确请求 contribution weight 时才使用 `coefficient**2`，并记录派生规则。NaN/非法 configuration 不使 energy/oscillator strength 消失：该 configuration block 被舍弃并进入 `ParserReport.INVALID`。

真实固定 fixture：

- Gaussian 16 `dvb_td.out`：5 states，energy/oscillator/symmetry/configuration/三类 dipole/rotatory strength；
- Gaussian 09 `dvb_td.out`：5 states，包含非零 signed rotatory strengths（首值 `-0.478`）；
- ORCA 5.0 `dvb_td.out`：10 states，energy/oscillator/symmetry/configuration/rotatory strength，缺 transition dipoles；
- ORCA 5.0 `dvb_adc2.log`：2 states，higher-level parser coverage。

## 语义模型

`ExcitationContribution`：

- `occupied_orbital` / `virtual_orbital`：zero-based MO index；
- `occupied_spin` / `virtual_spin`：`alpha` 或 `beta`；
- `coefficient`：finite signed float。

`ExcitedStateReferences` 为每个 state 提供可选 UUID：`transition_density`、`nto_hole`、`nto_particle`、`hole_density`、`electron_density`。cclib adapter 初始全部为 `None`；后续 IOData/Multiwfn/worker 派生只更新项目数据，不创建空数组。

`ExcitedStateSet` 继承 `PropertyDataset`：

- `semantic_role="excited_states"`、`domain="state"`；
- `data` 是 `(state,)` excitation energy，unit `inverse_centimeter`；
- optional oscillator/rotatory strength、三类 `(state, xyz)` dipole；
- symmetry、derived multiplicity、ragged configurations 和 state references；
- rotatory strength 存在时 status 为 `ambiguous`，直到来源提供可靠单位。

`Spectrum` 保持通用 `source_dataset_id`。`SpectrumKind` 扩展 `uv_vis` 与 `ecd`，并把振动专用 boolean 改为通用 `selection_policy`：`all_modes`、`nonnegative_modes` 或 `all_states`。项目按 kind 校验 source dataset 类型。

## Spectrum derivation

- UV-Vis 使用 oscillator strength，unit `dimensionless`，status `complete`；
- ECD 使用 signed rotatory strength，unit `unknown`，status `ambiguous`，明确标为 relative/unknown-unit display；
- 复用 peak-normalized stick/Gaussian/Lorentzian 和 FWHM contract；
- 不把 transition energy 换算为 wavelength 后再展宽。主轴保持 wavenumber；波长只作为 UI 派生显示，以避免非线性轴上错误线形。

## Multiplicity 与 identity

只识别 label 开头的 `Singlet`、`Doublet`、`Triplet`、`Quartet`、`Quintet`，分别映射 1–5。未知 label 对应 `None` 并报告 ambiguous，不从 oscillator strength 或程序名推断。state index 是 `ExcitedStateSet` 内 zero-based index；UI 可显示 one-based label，但 dataset/state identity 不变。

## 验证

- synthetic 模型验证 shape/unit/status、configuration spin/index/coefficient、references 和项目 dangling checks；
- synthetic adapter 覆盖完整、缺失辅助字段、unknown multiplicity、NaN configuration 和非法 shape；
- 四个真实 fixture 对照 state count、首个 energy、rotatory/dipole coverage 与 configuration 结构；
- UV-Vis/ECD 测试覆盖 signed ECD、FWHM 半峰值、通用 source identity 和 deterministic provenance；
- Blender Extension smoke 继续证明 cclib 未打包，核心 import 不加载 cclib/scipy。

## 非目标

- 自行执行 TDDFT/EOM-CC、计算 transition density 或 NTO 分解；
- 为 cclib unknown rotatory-strength unit 指定伪单位；
- wavelength-domain line broadening、solvent/vibronic fine structure、state tracking 和最终 2D plotting UI。
