# 安装、更新与卸载

## 要求

- Windows x64、Blender 5.1.0 或更高版本、`uv`。
- 同一发布中的 `chemblender-2.5.0.zip` 和 `chemblender_prepare-0.1.0-py3-none-any.whl`。

## 安装 Standard prepare

```powershell
uv tool install --python 3.12 "D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl[formats]"
$bin = uv tool dir --bin
Join-Path $bin 'chemblender-prepare.exe'
```

`uv tool` 会创建隔离环境和小型 launcher，不是单文件应用。Standard 安装 NumPy、RDKit、Gemmi；不要把这些包装进 Blender Python。

0.1.0 发布到 PyPI 后，可把 wheel 路径换成 `"chemblender-prepare[formats]"`。

## 安装 Extension

打开 Blender **Preferences > Get Extensions**，选择 **Install from Disk**，安装 `chemblender-2.5.0.zip` 并启用 ChemBlender。把 CLI launcher 的绝对路径填入 **Processor Executable**，点击 **Test Processor**。启用键为 `bl_ext.user_default.chemblender`。

## 更新或重装

```powershell
uv tool upgrade chemblender-prepare
uv tool install --python 3.12 "D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl[formats]" --force
```

保存并退出 Blender 后再安装新版 Extension ZIP。任一组件变化后都重新运行 **Test Processor**。

## 卸载

先在 Blender 禁用并卸载 Extension，再运行：

```powershell
uv tool uninstall chemblender-prepare
```

卸载组件不会删除已有 `.blend`/`.cbq` 项目。
