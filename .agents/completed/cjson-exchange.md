# CJSON Exchange

Completed on 2026-07-22.

## Result

- 固定 avogadrolibs `1.103.0` / `5d5d11f4a9ca716f7fb9653eb92424f1714b68ac` 作为 CJSON reader/writer 证据。
- 新增 `MolecularTopology`、`CJSONEnvelope` 与 CJSON 0/1 reader。
- 规范化结构、键、charge/multiplicity、formal/partial charge、选择、轨迹及 electronic spectra。
- 对 vibration vectors、Cube、orbitals 等未自描述约定保留 raw 字段并产生 `ParserReport` issue。
- 保持 CJSON 为轻量交换格式；Avogadro C++ 依赖未进入 Extension。

## Verification

- `python -m compileall -q ChemBlender/core tests`: Passed。
- `python -m unittest discover -s tests -p 'test_*.py'`: Passed，256 tests，27 skipped。
- Blender 5.1.2 native extension validate/build: Passed，59 ZIP entries。
- ZIP audit: CJSON adapter 已包含；Avogadro 未包含；仅固定 RDKit wheel。
- 隔离 `BLENDER_USER_RESOURCES` lifecycle smoke: Passed。
