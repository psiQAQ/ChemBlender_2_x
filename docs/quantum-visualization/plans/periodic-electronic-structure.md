# 周期电子结构开发计划

## 范围

覆盖可靠的晶体语义、周期标量场、band/DOS、费米面和声子，并让实空间结构与倒空间数据共享稳定身份。

## 非目标

- 不继续扩展手写 CIF 语法和 brute-force 空间群识别。
- 不在 Phase 0/1 为完整 pymatgen/PyProcar 栈打包 wheel。
- 不把复数声子 eigenvector 简化成静态实部箭头。

## 优先级

| 优先级 | 内容 | 验证重点 |
| --- | --- | --- |
| P0 | 已完成 Gemmi CIF envelope、spglib 对称性/标准化、原始/标准晶胞关系与现有 CIF/POSCAR golden baseline | setting、origin shift、occupancy、Uij 和未知 tag 不被误解或丢失 |
| P1 | 当前实施 ASE/pymatgen structure 与 CHGCAR/ELFCAR/LOCPOT；随后 band/DOS、phonopy 复数 q-point 模态 | 晶格/单位/费米能一致；复数模态按相位公式动画 |
| P2 | PyProcar 费米面、投影着色、自旋纹理、速度/有效质量和 sumo 风格联动 | 倒空间 mesh 与投影数据可追溯到来源计算 |

## 依赖关系

P0 依赖结构模型、单位、raw envelope 和 reader contract。P1/P2 依赖数组边车、2D plot 与 Blender linked selection；新增重依赖必须走 worker/打包决策。

## 交付物

- CIF normalized fields + raw envelope 契约。
- spglib transformation、origin shift、equivalent atom 和 Wyckoff 映射。
- 周期体数据、band、DOS、projection、q-point 与 mode schema。
- 实空间/倒空间 adapter 和联动 ID 规则。

## 验收标准

- 非标准 setting、部分占位和不确定度 fixture 有明确解析报告。
- 标准化前后可以追踪原子与晶胞变换，不覆盖原始 CIF。
- band energy、DOS 和 projection 保留 spin、kpoint、band、atom、orbital 维度。
- 声子位移使用 `Re[e(q) exp(i(q·R - ωt + φ))]`，支持相位参数。
- 费米面顶点属性保留来源、单位和投影说明。

## 参考仓库触发条件

- CIF 与空间群替换实施时审阅 Gemmi、spglib 和 ASE。
- band/DOS schema 实施时审阅 pymatgen 与 sumo。
- 费米面进入 P2 时审阅 PyProcar；声子进入 P1 时审阅 phonopy。只有需要固定实现证据时才添加 submodule。
