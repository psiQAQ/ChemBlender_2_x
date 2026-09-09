# Optional Backends and Routes

Standard needs no JSON file. Advanced users may place `chemblender-prepare.json` beside the CLI launcher returned by `uv tool dir --bin`, or set `CHEMBLENDER_PREPARE_CONFIG`.

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

Install the same prepare wheel into every routed environment without changing that environment's backend dependencies:

```powershell
uv pip install --python D:\envs\wavefunction\Scripts\python.exe --no-deps --reinstall D:\Downloads\chemblender_prepare-0.1.0-py3-none-any.whl
```

Then install and pin only the documented backend family: qc-gbasis/qc-iodata for wavefunction, ASE/cclib/pymatgen/phonopy for scientific, pyprocar for Fermi, or a separate critic2 executable. The routed process is `python -I -m chemblender_prepare.worker.runner`; source or `site-packages` injection is forbidden. Verify the actual Python, prepare path, backend versions and NumPy with `capabilities` and `doctor`.
