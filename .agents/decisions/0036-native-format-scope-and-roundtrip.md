# 0036：2.3.0 原生格式范围与分层 round-trip

## Status

Proposed for 2.3.0; user direction approved.

## Context

“支持格式”若不说明深度会误导用户。不同格式的可逆性和科学语义不同。

## Decision

2.3.0基础范围为XYZ/extXYZ、MOL V2000/V3000、SDF、SMILES、CIF、POSCAR/CONTCAR、MOL2、PDB/PQR、Cube和CJSON。按F0–F5成熟度报告。

XYZ/extXYZ、MOL、SDF、CIF受控、POSCAR和CJSON承诺适用round-trip；MOL2/PDB/PQR导出为P1；Cube不承诺无损重写。

## Consequences

- capability matrix必须显示import/export/loss policy和fixture families。
- SDF多record智能分组，但每条先保留独立record身份。
- extXYZ未知property仍类型化保存。

## Rejected Alternatives

- 所有格式只做坐标导入。
- 所有格式都承诺无损导出。
- 一次覆盖所有外部量子输出作为基础功能。

## Verification Contract

每个格式有真实fixture、质量报告和默认View；承诺F5的格式有规范化round-trip比较器。
