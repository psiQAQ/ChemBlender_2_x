# Wave 2 Gemmi package and CIF parse baseline

## 结论

2026-07-29 的 Windows x64 基线中，Gemmi 0.7.5 wheel 为 2,270,352 bytes，
使 extension ZIP 增加 2,270,536 bytes。独立 Python 进程的 import
median/p95 为 0.071923/0.077734 s；ChemBlender CIF parse median/p95 为
0.001518/0.001734 s。

## 环境与包体

| 项目 | 数值 |
| --- | --- |
| CPU | AMD Ryzen 7 4800H，8 cores / 16 logical processors |
| 内存 | 17,042,837,504 bytes |
| Blender / Python | 5.1.2 / 3.13.9 |
| Gemmi wheel | `gemmi-0.7.5-cp313-cp313-win_amd64.whl` |
| Wheel SHA-256 | `ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d` |
| wheel compressed / unpacked | 2,270,352 / 5,345,458 bytes |
| baseline ZIP（无 Gemmi） | 27,561,854 bytes |
| Gemmi ZIP | 29,832,390 bytes |
| artifact delta | 2,270,536 bytes |

ZIP delta 等于 wheel 本体加 184 bytes ZIP entry overhead。

## 性能

| 操作 | 样本 | Median (s) | P95 (s) | Min / Max (s) |
| --- | ---: | ---: | ---: | ---: |
| fresh-process `import gemmi` | 20 | 0.071923 | 0.077734 | 0.069800 / 0.078687 |
| Gemmi parse `mixed-site-data.cif` | 200 | 0.000021 | 0.000025 | 0.000019 / 0.000076 |
| ChemBlender `parse_cif` | 100 | 0.001518 | 0.001734 | 0.001436 / 0.390658 |

ChemBlender parse 的最大值是首次 cold import；median/p95 反映 warm parse。
结果为本地验证证据；Remote CI: Not Run。
