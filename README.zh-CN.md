# ChemBlender

[English](README.md)

ChemBlender 2.5 是面向 Blender 5.1+ 的 CBQ 科学项目 Viewer。原始文件解析和科学重计算由独立的 `chemblender-prepare` 完成；Blender 只负责编辑、View、动画、缓存、Cycles 渲染和项目重开，不承载科学 Python 依赖。

## 双组件

| 组件 | 版本 | 职责 |
| --- | --- | --- |
| ChemBlender Extension | 2.5.0 | CBQ 导入导出、纯 Mesh 编辑与 Apply、View、动画、项目生命周期和渲染 |
| chemblender-prepare | 0.1.0 | CLI/GUI 转换、校验、派生、导出、诊断和 Worker Protocol v1 |

Extension ZIP 不包含 RDKit、Gemmi 或其他科学 wheel。Standard prepare 把 NumPy、RDKit、Gemmi 安装在独立的 Python 3.12 `uv tool` 环境中。波函数、scientific、Fermi、critic2、QCEngine 和在线 provider 在未配置时会明确显示 unavailable。

## 安装

1. 在 Blender 的 **Preferences > Get Extensions > Install from Disk** 安装 `chemblender-2.5.0.zip`。
2. 从发布 wheel 安装 Standard prepare：

```powershell
uv tool install --python 3.12 "D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl[formats]"
uv tool dir --bin
```

3. 把 `chemblender-prepare.exe` 的绝对路径填入 ChemBlender preferences，点击 **Test Processor**。

未来 PyPI 命令为 `uv tool install --python 3.12 "chemblender-prepare[formats]"`；正式发布前 PyPI 上还没有 0.1.0。

## 从这里开始

- [中文用户指南](docs/user/zh-CN/index.md)
- [中文 prepare CLI/GUI/API 指南](docs/prepare/zh-CN/index.md)
- [English user guide](docs/user/en/index.md)
- [English prepare guide](docs/prepare/en/index.md)
- [源码生成的公开能力清单](docs/prepare/public-surface.json)
- [版本记录](CHANGELOG.md)

CBQ 是唯一科学数据交换边界。保存后应让 `project.blend` 与 `project.cbq/` 始终相邻。移动或删除 processor 不会删除已经入库的科学实体和可重建的 Blender View。

项目网站：https://www.chemblender.com
