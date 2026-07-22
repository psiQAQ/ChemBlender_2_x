# critic2 fixture

`cpreport-minimal.json` 是根据 critic2 `4b5dec9131c3a035af1b421d68a227c47fd641db`
中 `src/autocp@proc.f90::cp_json_report` 字段逐项缩减的最小 JSON。数值为测试用小体系数据，
不作为科学基准；字段名称、嵌套和 connectivity 结构来自固定上游实现。

真实数值精度由 critic2 自身测试负责；本 fixture 验证 ChemBlender adapter 的 schema、identity、
单位和失败行为。
