# 发布状态与已知限制

本文档面向本地 2.5.0 发布候选。此前公开 Extension 为 2.4.0；未经发布授权前，PyPI 上没有 `chemblender-prepare 0.1.0`。本地制品存在不代表远端已经发布。

兼容组合固定为 Extension 2.5.0、Worker 0.1.0、Worker Protocol 1、Reader API `1.0-rc1`。

干净 Python 3.12 Standard 资格环境实际解析出以下发行包。后续安装时 NumPy 与传递依赖 Pillow 可能解析到更新的兼容版本；应以 `uv pip list --python <tool-python>` 和本机已安装发行包中的许可证文件作为权威清单。

| 发行包 | 资格版本 | 许可证元数据 | 用途 |
| --- | --- | --- | --- |
| chemblender-prepare | 0.1.0 | GPL-3.0-or-later | 处理器 |
| NumPy | 2.5.3 | BSD-3-Clause 及随包兼容声明 | 数组 |
| RDKit | 2026.3.3 | BSD-3-Clause | 分子格式与操作 |
| Gemmi | 0.7.5 | MPL-2.0 | CIF 格式 |
| Pillow | 12.3.0 | MIT-CMU | RDKit 传递依赖 |

已知限制：

- Standard 不自动安装 wavefunction、scientific、Fermi、critic2、QCEngine 或在线 provider 后端。
- 没有真实 provider/compute backend 时，provider fetch 与 QCSchema compute 明确 unavailable。
- Blender 不为每个 Worker operation 提供面板按钮。
- 只移动 `.blend`/`.cbq` 中一半时需要 Relink。
- `chemblender_prepare.core.*` 与 GUI helper 是内部实现，不是稳定 Python SDK。

旧 UI 证据见 [2.4 archive](../../archive/2.4.0/README.md)，不要继续把它当成 2.5 日常教程。
