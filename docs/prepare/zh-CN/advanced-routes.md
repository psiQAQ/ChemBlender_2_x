# 可选后端与 Route

Standard 不需要 JSON。高级用户可以把 `chemblender-prepare.json` 放在 `uv tool dir --bin` 返回的 CLI launcher 旁边，或设置 `CHEMBLENDER_PREPARE_CONFIG`。

```json
{
  "schema_version": "1",
  "python": {
    "wavefunction": "D:\\envs\\wavefunction\\Scripts\\python.exe",
    "scientific": "D:\\envs\\scientific\\Scripts\\python.exe",
    "fermi": "D:\\envs\\fermi\\Scripts\\python.exe"
  },
  "critic2": "D:\\tools\\critic2.exe"
}
```

每个 route 都必须安装同一 prepare wheel，但不改动该环境已有后端依赖：

```powershell
uv pip install --python D:\envs\wavefunction\Scripts\python.exe --no-deps --reinstall D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl
```

随后只安装并固定需要的后端族：wavefunction 使用 qc-gbasis/qc-iodata，scientific 使用 ASE/cclib/pymatgen/phonopy，Fermi 使用 pyprocar；critic2 使用独立 executable。route 通过 `python -I -m chemblender_prepare.worker.runner` 运行，禁止注入源码或其他 `site-packages`。用 `capabilities` 和 `doctor` 核对实际 Python、prepare 路径、后端版本和 NumPy。
